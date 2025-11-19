import mph
from pathlib import Path
import sys
import numpy as np
import csv
from scipy.optimize import differential_evolution
from tqdm import tqdm

# --- Baseline values from COMSOL GUI ---
baseline_values = {
    "V_rf": 300,
    "V_dc": 50,
    "V_endcap": 10,
    "rod_spacing": 0.005,
    "rod_radius": 0.002,
    "rod_length": 0.04,
    "endcap_offset": 0.01
}

# --- Parameter bounds (min, max) ---
param_bounds = {
    "V_rf": (100, 600),
    "V_dc": (0, 200),
    "V_endcap": (0, 50),
    "rod_spacing": (0.004, 0.006),
    "rod_radius": (0.001, 0.003),
    "rod_length": (0.03, 0.30),
    "endcap_offset": (0.005, 0.05)
}

# --- Targets for normalization ---
depth_ref = 2       # set to baseline or desired goal (e.g. baseline depth_eV)
offset_target = 1e-5  # acceptable offset in meters
power_budget = 4000  # acceptable power budget in mW

# --- Objective weights (dimensionless, tunable) ---
weights = {"depth": 1.0, "offset": 1.0, "power": 1.0}

# --- Penalty coefficients for constraint violations ---
penalties = {"offset": 6.0, "power": 6.0}

# --- CSV logging setup ---
log_file = "optimization_log.csv"
log_header = list(param_bounds.keys()) + ["depth_eV", "offset_m", "P_est_mW", "score"]

def init_csv():
    with open(log_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(log_header)

def log_csv(params, depth, offset, power, score):
    with open(log_file, "a", newline="") as f:
        writer = csv.writer(f)
        row = [params[name] for name in param_bounds.keys()] + [depth, offset, power, score]
        writer.writerow(row)

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

def compute_score(depth_eV, offset_m, P_est_mW):
    # Normalize
    depth_norm  = depth_eV / depth_ref if depth_ref > 0 else 0
    offset_norm = offset_m / offset_target if offset_target > 0 else 0

    # Log-scale power to reduce domination by extreme values
    power_scaled = np.log10(max(P_est_mW, 1.0))  # avoid log(0)
    power_ref    = np.log10(max(power_budget, 1.0))
    power_norm   = power_scaled / power_ref

    # Base weighted score (maximize depth, minimize offset/power)
    score = (weights["depth"] * depth_norm
             - weights["offset"] * offset_norm
             - weights["power"] * power_norm)

    # Constraint penalties (capped to avoid runaway dominance)
    penalty = 0.0
    if offset_m > offset_target:
        penalty += penalties["offset"] * ((offset_m / offset_target) - 1.0) ** 2
    if P_est_mW > power_budget:
        penalty += penalties["power"] * ((P_est_mW / power_budget) - 1.0) ** 2

    # Cap total penalty to keep the landscape navigable
    penalty = min(penalty, 50.0)

    return score - penalty


def objective(x, model):
    """
    Objective function for optimizer with error handling and geometry checks.
    x is a normalized vector in [0,1] for each parameter.
    """
    # Map normalized [0,1] -> actual parameter ranges
    params = {}
    for i, (name, (low, high)) in enumerate(param_bounds.items()):
        params[name] = low + x[i] * (high - low)

    # --- Geometry sanity checks ---
    # Prevent rods overlapping or unrealistic geometries
    if params["rod_spacing"] <= 2 * params["rod_radius"]:
        print(f"⚠️ Invalid geometry (spacing <= 2*radius): {params}")
        return 1e9  # large penalty

    if params["rod_length"] < 0.02 or params["rod_length"] > 0.20:
        print(f"⚠️ Rod length out of safe range: {params}")
        return 1e9
    # Set parameters in COMSOL
    for name, val in params.items():
        model.parameter(name, val)

    # --- Solve with error handling ---
    try:
        model.solve()
    except Exception as e:
        print(f"⚠️ Solver failed for params={params}: {e}")
        # Penalize failed solves heavily
        return 1e9

    # --- Safe evaluation of outputs ---
    def safe_eval(name):
        try:
            return float(model.evaluate(name))
        except Exception:
            return np.nan

    depth_eV = safe_eval("depth_eV")
    offset_m = safe_eval("offset_m")
    P_est_mW = safe_eval("P_est_mW")

    # Handle NaN results (failed evaluation)
    if np.isnan(depth_eV) or np.isnan(offset_m) or np.isnan(P_est_mW):
        print(f"⚠️ Invalid results for params={params}")
        return 1e9

    # --- Compute normalized score ---
    score = compute_score(depth_eV, offset_m, P_est_mW)

    # Logging
    print(f"Params={params} | depth={depth_eV:.3f}, offset={offset_m:.3e}, "
          f"power={P_est_mW:.3f}, score={score:.3f}")
    log_csv(params, depth_eV, offset_m, P_est_mW, score)

    # Return negative score (SciPy minimizes)
    return -score


def main():
    model_path = find_model_file()
    print("Starting COMSOL client...")
    client = mph.start(cores=8, version="6.3")

    try:
        print(f"Loading model: {model_path}")
        model = client.load(str(model_path))

        # --- Initialize CSV log ---
        init_csv()

        # --- Run optimizer ---
        bounds = [(0, 1)] * len(param_bounds)  # normalized bounds

        with tqdm(total=30, desc="Optimization progress") as pbar:
            def callback(x, convergence):
                pbar.update(1)

            result = differential_evolution(
                func=lambda x: objective(x, model),
                bounds=bounds,
                maxiter=300,
                callback=callback,
                polish=True
            )

        print("\n✅ Optimization complete")
        print("Best normalized vector:", result.x)

        # Map back to actual parameters
        best_params = {}
        for i, (name, (low, high)) in enumerate(param_bounds.items()):
            best_params[name] = low + result.x[i] * (high - low)

        print("Best parameters:", best_params)
        print("Best score:", -result.fun)

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
