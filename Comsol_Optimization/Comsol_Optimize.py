import mph
from pathlib import Path
import sys
import csv
from scipy.optimize import minimize
import os
import math
import argparse

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

# Enforcement configuration: safety factor and reasonable bounds for sphere radius (multiples of rod_radius)
SPHERE_SAFETY_FACTOR = 1.05
MIN_SPHERE_MULT = 5.0
MAX_SPHERE_MULT = 50.0

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
    ret+urn score

def run_trial(params, model, writer, f, enforce=True):
    # enforce inscribed-sphere constraint so the geometry does not exceed the sphere surface
    # params order: V_rf, V_dc, V_endcap, rod_spacing, rod_radius, rod_length, endcap_offset
    def enforce_inscribed_constraint(p, model_obj=None):
        p = list(p)
        # indices
        i_spacing = 3
        i_radius = 4
        i_length = 5
        i_endcap_off = 6

        rod_spacing = float(p[i_spacing])
        rod_radius = float(p[i_radius])
        rod_length = float(p[i_length])
        endcap_offset = float(p[i_endcap_off])

        # attempt to read endcap_thick and endcap_rad from model parameters if available
        # Use numeric evaluation (model.evaluate) via try_eval to avoid expression/unit strings
        endcap_thick = 0.0
        endcap_rad = 0.0
        if model_obj is not None:
            try:
                val = try_eval(model_obj, "endcap_thick")
                if val is not None:
                    endcap_thick = float(val)
            except Exception:
                endcap_thick = 0.0
            try:
                val2 = try_eval(model_obj, "endcap_rad")
                if val2 is not None:
                    endcap_rad = float(val2)
            except Exception:
                endcap_rad = 0.0

        # structure radius is the max of pole-cylinder radius and endcap radius
        cyl_radius = (rod_spacing / 2.0) + rod_radius
        struct_radius = max(cyl_radius, endcap_rad)
        # cylinder height includes both endcaps (thickness contributes to height)
        cyl_height = rod_length + 2.0 * (endcap_offset + endcap_thick)
        half_height = cyl_height / 2.0

        # minimal sphere radius required to contain the cylinder
        R_min = math.sqrt(half_height * half_height + struct_radius * struct_radius)
        # apply a small safety factor, but clamp to reasonable multiples of rod_radius
        min_allowed = MIN_SPHERE_MULT * rod_radius
        max_allowed = MAX_SPHERE_MULT * rod_radius
        R_sphere = max(min_allowed, min(R_min * SPHERE_SAFETY_FACTOR, max_allowed))

        # if already fits, no adjustment
        current = math.sqrt(half_height * half_height + struct_radius * struct_radius)
        if current <= R_sphere:
            return p, False

        # scale <= 1 to shrink spacing/length/offset so cylinder fits inside sphere of radius R_sphere
        scale = min(1.0, R_sphere / current)

        new_spacing = rod_spacing * scale
        new_length = rod_length * scale
        new_endcap_off = endcap_offset * scale

        p[i_spacing] = float(new_spacing)
        p[i_length] = float(new_length)
        p[i_endcap_off] = float(new_endcap_off)
        return p, True

    if enforce:
        params, adjusted = enforce_inscribed_constraint(params, model)
        if adjusted:
            print("Parameters adjusted to fit inside clamped sphere bounds:", params)

    # unpack params
    V_rf, V_dc, V_endcap, rod_spacing, rod_radius, rod_length, endcap_offset = params

    # set COMSOL parameters and run a trial, but guard against COMSOL errors
    print("Running trial with params:", params)
    depth_eV = None
    offset_mm = None
    P_est_mW = None
    endcap_thick = None
    endcap_rad = None
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
        # capture endcap properties if available
        try:
            endcap_thick = try_eval(model, "endcap_thick")
        except Exception:
            endcap_thick = None
        try:
            endcap_rad = try_eval(model, "endcap_rad")
        except Exception:
            endcap_rad = None
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
            "endcap_thick": endcap_thick, "endcap_rad": endcap_rad,
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
    parser = argparse.ArgumentParser(description="COMSOL optimization runner")
    parser.add_argument("--no-enforce", action="store_true", help="Disable inscribed-sphere enforcement (allow params to exceed sphere)")
    args = parser.parse_args()
    enforce_flag = not args.no_enforce
    print(f"Inscribed-sphere enforcement: {'ON' if enforce_flag else 'OFF'}")

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
                                "rod_length","endcap_offset","endcap_thick","endcap_rad","depth_eV","offset_mm","P_est_mW","score"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            # run optimizer, passing both the DictWriter and the open file handle for flushing
            result = minimize(lambda p: run_trial(p, model, writer, f, enforce=enforce_flag),
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