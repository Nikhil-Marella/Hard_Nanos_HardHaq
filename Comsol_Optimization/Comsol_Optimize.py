import mph
from pathlib import Path
import sys
import csv
from scipy.optimize import minimize
import os
import math

# Parameters ordering used throughout the optimizer
PARAM_ORDER = [
    "V_rf",
    "V_dc",
    "V_endcap",
    "rod_spacing",
    "rod_radius",
    "rod_length",
    "endcap_offset",
]


def enforce_inscribed_constraint(params, model=None):
    """Ensure the cylinder defined by (rod_spacing, rod_length) can be inscribed
    inside a sphere of radius R_sphere = 20 * rod_radius.

    Assumptions:
    - The cylinder radius is approximated as rod_spacing / 2.
    - The cylinder height is rod_length.

    If the cylinder does not fit, scale down both rod_spacing and rod_length
    by the same factor so the cylinder fits exactly on the sphere surface.
    Returns the (possibly modified) params list and a boolean indicating whether
    a modification was applied.
    """
    # params is list ordered as PARAM_ORDER
    p = list(params)
    # indices
    i_spacing = PARAM_ORDER.index("rod_spacing")
    i_radius = PARAM_ORDER.index("rod_radius")
    i_length = PARAM_ORDER.index("rod_length")
    i_endcap_off = PARAM_ORDER.index("endcap_offset")

    rod_spacing = float(p[i_spacing])
    rod_radius = float(p[i_radius])
    rod_length = float(p[i_length])
    endcap_offset = float(p[i_endcap_off])

    # try to read endcap_thick from the model if available, otherwise assume 0
    endcap_thick = 0.0
    if model is not None:
        try:
            val = model.parameter("endcap_thick")
            endcap_thick = float(val) if val is not None else 0.0
        except Exception:
            endcap_thick = 0.0

    # cylinder radius includes rod_radius as requested
    cyl_radius = (rod_spacing / 2.0) + rod_radius
    # cylinder height includes endcaps
    cyl_height = rod_length + 2.0 * (endcap_offset + endcap_thick)
    half_height = cyl_height / 2.0
    R_sphere = 20.0 * rod_radius

    lhs = half_height * half_height + cyl_radius * cyl_radius
    rhs = R_sphere * R_sphere
    if lhs <= rhs or rhs <= 0:
        return p, False

    # scale factor to make lhs == rhs (scale <= 1)
    current = math.sqrt(lhs)
    desired = R_sphere
    scale = min(1.0, desired / current)
    # apply scale to spacing, length, and endcap_offset (keep rod_radius unchanged)
    new_spacing = rod_spacing * scale
    new_length = rod_length * scale
    new_endcap_off = endcap_offset * scale
    p[i_spacing] = float(new_spacing)
    p[i_length] = float(new_length)
    p[i_endcap_off] = float(new_endcap_off)
    return p, True

# --- Baseline values from your COMSOL GUI ---
baseline_values = {
    "V_rf": 300,
    "V_dc": 50,
    "V_endcap": 10,
    "rod_spacing": 0.005,
    "rod_radius": 0.002,
    "rod_length": 0.04,
    "endcap_offset": 0.001
}

# --- Target values for normalization ---
targets = {
    "depth_eV": 9.0,     # want >= 5 eV, was 5.0eV
    "offset_mm": 0.005,    # want ~0 mm, was 0.001mm
    "P_est_mW": 2000.0      # want ~1000 mW, was 1000mW
}

# --- Weights for each objective ---
weights = {
    "depth_eV": 2.0, #was 1.0
    "offset_mm": 200.0, #was 100.0
    "P_est_mW": 0.5 #was 0.8
}

def find_model_file(preferred_name: str = "3d_pole_trap - Copy.mph") -> Path:
    cwd = Path(__file__).resolve().parent
    preferred_path = cwd / preferred_name
    if preferred_path.exists():
        print(f"Using model file: {preferred_path}")
        return preferred_path

    candidates = list(cwd.glob("*.mph"))
    if candidates:
        print("Preferred model not found. Available .mph files in the folder:")
        for i, p in enumerate(candidates, 1):
            print(f"  {i}. {p.name}")
        fallback = candidates[0]
        print(f"Falling back to: {fallback}")
        return fallback

    print(f"No .mph model file found in {cwd}. Please place your COMSOL model there or provide the correct path.")
    sys.exit(2)

def try_eval(model, name):
    try:
        return float(model.evaluate(name))
    except Exception:
        return None
    
def objective(depth_eV, offset_mm, P_est_mW):
    # Normalized scores relative to targets
    depth_score  = depth_eV / (targets["depth_eV"] + 1e-9)
    offset_score = (targets["offset_mm"] + 1e-9) / (offset_mm + 1e-9)
    power_score  = (targets["P_est_mW"] + 1e-9) / (P_est_mW + 1e-9)

    print(depth_score, offset_score, power_score)
    print((weights["depth_eV"] * depth_score), \
          (weights["offset_mm"] * offset_score), \
          (weights["P_est_mW"] * power_score))

    # Weighted sum
    score = (weights["depth_eV"] * depth_score) \
          + (weights["offset_mm"] * offset_score) \
          + (weights["P_est_mW"] * power_score)
    return score

def run_trial(params, model, writer, f):
    # enforce inscribed constraint (may modify spacing/length to fit inside sphere)
    params, modified = enforce_inscribed_constraint(params)
    if modified:
        print("Adjusted params to satisfy inscribed-sphere constraint:", params)

    # unpack params
    V_rf, V_dc, V_endcap, rod_spacing, rod_radius, rod_length, endcap_offset = params

    # set COMSOL parameters and run a trial, but guard against COMSOL errors
    print("Running trial with params:", params)
    depth_eV = None
    offset_mm = None
    P_est_mW = None
    try:
        model.parameter("V_rf", V_rf)
        model.parameter("V_dc", V_dc)
        model.parameter("V_endcap", V_endcap)
        model.parameter("rod_spacing", rod_spacing)
        model.parameter("rod_radius", rod_radius)
        model.parameter("rod_length", rod_length)
        model.parameter("endcap_offset", endcap_offset)

        model.solve()
        print('solved Trial')

        depth_eV = try_eval(model, "depth_eV")
        offset_mm = try_eval(model, "offset_mm")
        P_est_mW = try_eval(model, "P_est_mW")
        print("depth_eV:", depth_eV, "offset_mm:", offset_mm, "P_est_mW:", P_est_mW)

        score = objective(depth_eV, offset_mm, P_est_mW)
        print("Optimizer result:", -score)
    except Exception as e:
        # log and return a large penalty so optimizer keeps going
        print("COMSOL trial failed:", e)
        score = -1e6

    try:
        # write a row using the provided DictWriter and flush the underlying file
        writer.writerow({
                "V_rf": V_rf, "V_dc": V_dc, "V_endcap": V_endcap,
                "rod_spacing": rod_spacing, "rod_radius": rod_radius,
                "rod_length": rod_length, "endcap_offset": endcap_offset,
                "depth_eV": depth_eV, "offset_mm": offset_mm,
                "P_est_mW": P_est_mW, "score": score
            })
        f.flush()
        os.fsync(f.fileno())

        print("Row written")
    except Exception as e:
        print("Failed to write row:", e)

    # return negative score for minimizer (we used score higher is better). If trial failed, return large positive penalty.
    return -score if score is not None else 1e6
def main():
    model_path = find_model_file()
    print("Starting COMSOL client...")
    client = mph.start(cores=8, version="6.3") #THE CORE COUNT IS SO IMPORTANT GODDAMNIT KEEP IT 8

    try:
        print(f"Loading model: {model_path}")
        model = client.load(str(model_path))

        # --- Print all COMSOL parameters (expression + value) ---
        print("\n📋 All COMSOL parameters:")
        exprs = model.parameters()
        for name, expr in exprs.items():
            val = model.parameter(name)
            print(f"  {name:<20} | Expression: {expr:<10} | Value: {val}")
        x0 = [baseline_values["V_rf"], baseline_values["V_dc"], baseline_values["V_endcap"],
                  baseline_values["rod_spacing"], baseline_values["rod_radius"],
                  baseline_values["rod_length"], baseline_values["endcap_offset"]]

            

        with open("optimization_log.csv", "w", newline="") as f:
            fieldnames = ["V_rf","V_dc","V_endcap","rod_spacing","rod_radius",
                                "rod_length","endcap_offset","depth_eV","offset_mm","P_est_mW","score"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            # run optimizer, passing both the DictWriter and the open file handle for flushing
            result = minimize(lambda p: run_trial(p, model, writer, f),
                            x0, method="Nelder-Mead", options={"maxiter": 50})
        
        
        model.save()
        client.remove(model)

    except Exception as e:
        print("❌ Exception occurred:")
        print(e)
        try:
            client.remove_all()
        except Exception:
            pass
        raise

if __name__ == "__main__":
    main()