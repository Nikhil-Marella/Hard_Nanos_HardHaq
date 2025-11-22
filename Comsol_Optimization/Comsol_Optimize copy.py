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
    "rod_spacing": 0.005,
    "rod_radius": 0.002,
    "rod_length": 0.04,
    "endcap_offset": 0.001,
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
    (0.003, 0.1),   # rod_spacing
    (0.0005, 0.008),# rod_radius
    (0.02, 0.1),    # rod_length
    (0.0, 0.01),    # endcap_offset
    (0.005, 0.01),  # endcap_rad
    (0.0001, 0.001),# endcap_thick
    (1e6, 1e8)      # f
]

# --- Normalization helpers ---
def normalize(x, bounds):
    return [(xi - low) / (high - low) for xi, (low, high) in zip(x, bounds)]

def denormalize(y, bounds):
    return [low + yi * (high - low) for yi, (low, high) in zip(y, bounds)]

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
    V_rf, V_dc, V_endcap, rod_spacing, rod_radius, rod_length, endcap_offset, endcap_rad, endcap_thick, f = params

    # set COMSOL parameters
    model.parameter("V_rf", V_rf)
    model.parameter("V_dc", V_dc)
    model.parameter("V_endcap", V_endcap)
    model.parameter("rod_spacing", rod_spacing)
    model.parameter("rod_radius", rod_radius)
    model.parameter("rod_length", rod_length)
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
    
    if score == -1e6:
        pass  # keep the penalty score
    else:
        score = objective(depth_eV, offset_mm, P_est_mW)
    print("Optimizer result:", -score)

    if offset_mm > 15:
        print("Offset too high, penalizing")
        score = -1e6
    if depth_eV < 0.0001:
        print("Depth too low, penalizing")
        score = -1e6
    if P_est_mW < 10:
        print("Power probably a lie, penalizing")
        score = -1e6

    try:
        writer.writerow({
                "V_rf": V_rf, "V_dc": V_dc, "V_endcap": V_endcap,
                "rod_spacing": rod_spacing, "rod_radius": rod_radius,
                "rod_length": rod_length, "endcap_offset": endcap_offset,
                "endcap_rad": endcap_rad, "endcap_thick": endcap_thick, "f": f,
                "depth_eV": depth_eV, "offset_mm": offset_mm,
                "P_est_mW": P_est_mW, "score": score
            })
        filename.flush()
        os.fsync(filename.fileno())
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
              baseline_values["rod_spacing"], baseline_values["rod_radius"],
              baseline_values["rod_length"], baseline_values["endcap_offset"],
              baseline_values["endcap_rad"], baseline_values["endcap_thick"],
              baseline_values["f"]]

        # normalize baseline
        y0 = normalize(x0, bounds)

        with open("optimization_log.csv", "w", newline="") as filename:
            fieldnames = ["V_rf","V_dc","V_endcap","rod_spacing","rod_radius",
                          "rod_length","endcap_offset","endcap_rad","endcap_thick","f",
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
        except:
            pass
    sys.exit(1)
if __name__ == "__main__":
    print("Starting script...")
    try:
        main()
    except Exception as e:
        print("❌ Exception at top level:", e)
