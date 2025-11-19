import mph
from scipy.optimize import minimize
from pathlib import Path
import sys
from tqdm import tqdm
import logging
import traceback

# --- Setup logging ---
logging.basicConfig(filename="optimization_log.txt", level=logging.INFO, format="%(message)s")

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


def main():
    model_path = find_model_file()
    print("Starting COMSOL client (mph.start)...")
    client = mph.start(cores=2, version="6.3")

    try:
        print(f"Loading model from: {model_path}")
        model = client.load(str(model_path))

        # --- Progress bar setup ---
        iteration_counter = tqdm(total=50, desc="Optimizing", unit="iter")

        def objective(params):
            try:
                V_rf, V_dc, endcap_dc, rod_spacing = params
                model.parameter("V_rf", V_rf)
                model.parameter("V_dc", V_dc)
                model.parameter("endcap_dc", endcap_dc)
                model.parameter("rod_spacing", rod_spacing)

                try:
                    model.solve()
                except Exception as e:
                    logging.info(f"⚠️ Solve failed for params: {params}")
                    iteration_counter.update(1)
                    return 1e6

                depth_eV = float(model.evaluate("depth_eV"))
                P_est_mW = float(model.evaluate("P_est_mW"))
                offset_m = float(model.evaluate("offset_m"))

                # --- Normalization hyperparameters ---
                d_min, d_max = 0.05, 0.5       # eV
                p_min, p_max = 1.0, 50.0       # mW
                o_cap = 50e-6                  # m (soft cap ~ 50 µm)
                eps = 1e-9

                # --- Normalized scores ---
                s_d = (depth_eV - d_min) / max(d_max - d_min, eps)
                s_d = max(0.0, min(1.0, s_d))

                s_p = (P_est_mW - p_min) / max(p_max - p_min, eps)
                s_p = max(0.0, min(1.0, s_p))

                s_o = (offset_m / max(o_cap, eps)) ** 2

                # --- Weights ---
                w_d, w_p, w_o = 1.0, 1.0, 1.0

                cost = w_p * s_p + w_o * s_o - w_d * s_d

                # --- Hard penalties ---
                if depth_eV < d_min:   cost += 0.2
                if P_est_mW > p_max:   cost += 0.2
                if offset_m > 3*o_cap: cost += 0.5

                # --- Logging ---
                logging.info(f"Params: V_rf={V_rf:.2f}, V_dc={V_dc:.2f}, endcap_dc={endcap_dc:.2f}, rod_spacing={rod_spacing:.4f} | "
                             f"depth_eV={depth_eV:.4f}, P_est_mW={P_est_mW:.4f}, offset_m={offset_m:.6f} | Cost={cost:.4f}")

                iteration_counter.update(1)
                print(f"Iter: V_rf={V_rf:.2f}, V_dc={V_dc:.2f}, endcap_dc={endcap_dc:.2f}, rod_spacing={rod_spacing:.4f} | "
                      f"depth_eV={depth_eV:.4f}, P_est_mW={P_est_mW:.4f}, offset_m={offset_m:.6f} | Cost={cost:.4f}")

                return cost

            except Exception as e:
                logging.info(f"⚠️ Evaluation error for params: {params}")
                iteration_counter.update(1)
                return 1e6

        # --- Initial guess and bounds ---
        initial_guess = [300, 50, 10, 0.004]
        bounds = [(100, 600), (0, 100), (0, 20), (0.002, 0.006)]

        print("Running optimization...")
        result = minimize(objective, initial_guess, bounds=bounds, method="Powell", options={"maxiter": 50})

        iteration_counter.close()

        print("\n✅ Optimization complete:")
        print(f"V_rf       = {result.x[0]:.3f} V")
        print(f"V_dc       = {result.x[1]:.3f} V")
        print(f"endcap_dc  = {result.x[2]:.3f} V")
        print(f"rod_spacing= {result.x[3]:.6f} m")
        print(f"Final cost = {result.fun:.6f}")

        model.save()
        client.remove(model)

    except Exception as e:
        print("An exception occurred while loading/solving the model:")
        traceback.print_exc()
        try:
            client.remove_all()
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
