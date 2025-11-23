import mph
from pathlib import Path
import sys
import csv
from scipy.optimize import minimize
import os
import traceback

# --- Baseline values from COMSOL GUI ---
baseline_values = {
    "V_rf": 300,
    "V_dc": 50,
    "V_endcap": 10,
    "electrode_spacing": 0.009,
    "electrode_amplitude": 0.004,
    "umax": 1.0,
    "endcap_offset": 0.005,
    "endcap_rad":0.006,
    "endcap_thick":0.0005,
    "f":1e7
}

# --- Target values for normalization ---
targets = {
    "depth_eV": 5.0,     # want >= 5 eV
    "offset_mm": 0.001,  # want ~0 mm
    "P_est_mW": 1000.0   # want ~1000 mW
}

# --- Weights for each objective ---
weights = {
    "depth_eV": 1.0,
    "offset_mm": 10.0,
    "P_est_mW": 0.8
}

# --- Bounds in physical units ---
bounds = [
    (0, 1000),      # V_rf
    (0, 500),       # V_dc
    (0, 500),       # V_endcap
    (0.009, 0.01),   # electrode_spacing
    (0.003, 0.0044),# electrode_amplitude
    (1, 1.6),    # umax
    (0.005, 0.01),    # endcap_offset
    (0.005, 0.01),  # endcap_rad
    (0.0001, 0.001),# endcap_thick
    (1e6, 1e8)      # f
]

# --- Normalization helpers ---
def normalize(x, bounds):
    return [(xi - low) / (high - low) for xi, (low, high) in zip(x, bounds)]

def denormalize(y, bounds):
    return [low + yi * (high - low) for yi, (low, high) in zip(y, bounds)]

def find_model_file(preferred_name: str = "hyperb_electrode_shape_drafting_HARDLIMITCOPY.mph") -> Path:
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
        val = model.evaluate(name)
        if val is None:
            return None
        # handle numpy scalars or single-element arrays returned by COMSOL
        try:
            if hasattr(val, "item"):
                return float(val.item())
            return float(val)
        except Exception:
            # last resort: attempt conversion of first element
            try:
                return float(val[0])
            except Exception:
                return None
    except Exception:
        return None
    
def objective(depth_eV, offset_mm, P_est_mW):
    # Normalized scores relative to targets
    depth_score  = depth_eV / (targets["depth_eV"] + 1e-9)
    offset_score = (targets["offset_mm"] + 1e-9) / (offset_mm + 1e-9)
    power_score  = (targets["P_est_mW"] + 1e-9) / (P_est_mW + 1e-9)

    print(depth_score, offset_score, power_score)
    print((weights["depth_eV"] * depth_score),
          (weights["offset_mm"] * offset_score),
          (weights["P_est_mW"] * power_score))

    # Weighted sum
    score = (weights["depth_eV"] * depth_score
           + weights["offset_mm"] * offset_score
           + weights["P_est_mW"] * power_score)
    return score

def run_trial(params, model, writer, filename):
    # params are in PHYSICAL units here
    V_rf, V_dc, V_endcap, electrode_spacing, electrode_amplitude, umax, endcap_offset, endcap_rad, endcap_thick, f = params

    # set COMSOL parameters
    model.parameter("V_rf", V_rf)
    model.parameter("V_dc", V_dc)
    model.parameter("V_endcap", V_endcap)
    model.parameter("electrode_spacing", electrode_spacing)
    model.parameter("electrode_amplitude", electrode_amplitude)
    model.parameter("umax", umax)
    model.parameter("endcap_offset", endcap_offset)
    model.parameter("endcap_rad", endcap_rad)
    model.parameter("endcap_thick", endcap_thick)
    model.parameter("f", f)
    score = 0

    print("Running trial with params:", params)

    try:
        model.solve()
    except Exception as e:
        print("COMSOL study run failed:", e)
        score = -1e6
    
    print('solved Trial')

    depth_eV   = try_eval(model, "depth_eV")
    offset_mm  = try_eval(model, "offset_mm")
    P_est_mW   = try_eval(model, "P_est_mW")
    print("depth_eV:", depth_eV, "offset_mm:", offset_mm, "P_est_mW:", P_est_mW)

    # If the solve failed to produce scalars, penalize this trial
    if score == -1e6:
        pass
    else:
        if depth_eV is None or offset_mm is None or P_est_mW is None:
            print("Missing metric(s); applying penalty")
            score = -1e6
        else:
            score = objective(depth_eV, offset_mm, P_est_mW)
    print("Optimizer result:", -score)

    # safe numeric checks (guard against None)
    if offset_mm is None or offset_mm > 19.13:
        print("Offset missing or too high, penalizing")
        score = -1e6
    if depth_eV is None or depth_eV < 0.00001:
        print("Depth missing or too low, penalizing")
        score = -1e6
    if P_est_mW is None:
        print("Power missing or too low, penalizing")
        score = -1e6

    try:
        writer.writerow({
                "V_rf": V_rf, "V_dc": V_dc, "V_endcap": V_endcap,
                "electrode_spacing": electrode_spacing, "electrode_amplitude": electrode_amplitude,
                "umax": umax, "endcap_offset": endcap_offset,
                "endcap_rad": endcap_rad, "endcap_thick": endcap_thick, "f": f,
                "depth_eV": depth_eV, "offset_mm": offset_mm,
                "P_est_mW": P_est_mW, "score": score
            })
        # flush to disk
        try:
            filename.flush()
            os.fsync(filename.fileno())
        except Exception:
            pass
        print("Row written")
    except Exception as e:
        print("Failed to write row:", e)

    return -score  # minimize negative score

def normalized_objective(y, model, writer, filename):
    # y is in [0,1]^n
    x = denormalize(y, bounds)  # convert to physical units
    return run_trial(x, model, writer, filename)

def main():
    model_path = find_model_file()
    print("Starting COMSOL client...")
    client = mph.start(cores=8, version="6.3")

    try:
        print(f"Loading model: {model_path}")
        model = client.load(str(model_path))

        print("\n📋 All COMSOL parameters:")
        exprs = model.parameters()
        for name, expr in exprs.items():
            val = model.parameter(name)
            print(f"  {name:<20} | Expression: {expr:<10} | Value: {val}")

        # baseline in physical units
        x0 = [baseline_values["V_rf"], baseline_values["V_dc"], baseline_values["V_endcap"],
              baseline_values["electrode_spacing"], baseline_values["electrode_amplitude"],
              baseline_values["umax"], baseline_values["endcap_offset"],
              baseline_values["endcap_rad"], baseline_values["endcap_thick"],
              baseline_values["f"]]

        # normalize baseline
        y0 = normalize(x0, bounds)

        with open("optimization_log.csv", "w", newline="") as filename:
            fieldnames = ["V_rf","V_dc","V_endcap","electrode_spacing","electrode_amplitude",
                          "umax","endcap_offset","endcap_rad","endcap_thick","f",
                          "depth_eV","offset_mm","P_est_mW","score"]
            writer = csv.DictWriter(filename, fieldnames=fieldnames)
            writer.writeheader()

            # run optimizer in normalized space
            result = minimize(lambda y: normalized_objective(y, model, writer, filename),
                              y0,
                              method="Nelder-Mead",
                              options={"maxiter": 2000, "xatol": 1e-9, "fatol": 1e-9})

        print("Optimization result (normalized):", result)
        best_params = denormalize(result.x, bounds)
        print("Best physical parameters:", best_params)

        model.save()
        client.remove(model)

    except Exception as e:
        print("❌ Exception occurred:")
        traceback.print_exc()
        try:
            client.stop()
        except Exception:
            pass
        return 1
    return 0
if __name__ == "__main__":
    print("Starting script...")
    try:
        rc = main()
        sys.exit(rc)
    except Exception as e:
        print("❌ Exception at top level:", e)
        sys.exit(1)