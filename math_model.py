import numpy as np
import json
import os
from scipy.optimize import linprog

# Reference sets
workloads = ["inference_EU", "inference_MENA", "batch_training"]
regions = ["Frankfurt", "Madrid", "Helsinki"]

# Internal enterprise assets: Customer Demand (D) in MW
D = {"inference_EU": 35.0, "inference_MENA": 20.0, "batch_training": 50.0}

# Physical constraints: Maximum DC Capacity (Cap) in MW
Cap = {"Frankfurt": 50.0, "Madrid": 40.0, "Helsinki": 40.0}

def normalize(values):
    """Min-Max normalization to [0, 1]."""
    arr = np.array(values)
    v_min, v_max = arr.min(), arr.max()
    if v_max == v_min:
        return np.zeros_like(arr)
    return (arr - v_min) / (v_max - v_min)

def get_forecast_values():
    """
    Attempts to load forecasted values from sybilion_forecast_results.json.
    If missing, returns realistic synthetic median values.
    """
    results_path = "sybilion_forecast_results.json"
    metrics = ["cost", "eco", "sicherheit"]
    
    forecasts = {m: {} for m in metrics}
    
    if os.path.exists(results_path):
        with open(results_path, "r") as f:
            data = json.load(f)
            for r in regions:
                for m in metrics:
                    try:
                        # Extract the first forecast point
                        val = list(data[r][m]["forecast.json"]["data"]["forecast_series"].values())[0]["forecast"]
                        forecasts[m][r] = val
                    except:
                        pass

    # Fill missing with defaults if necessary
    defaults = {
        "cost": {"Frankfurt": 120, "Madrid": 90, "Helsinki": 65},
        "eco": {"Frankfurt": 420, "Madrid": 250, "Helsinki": 60},
        "sicherheit": {"Frankfurt": 0.85, "Madrid": 0.70, "Helsinki": 0.50}
    }
    
    for m in metrics:
        for r in regions:
            if r not in forecasts[m]:
                forecasts[m][r] = defaults[m][r]
                
    return forecasts

def run_optimization_with_weights(weights_dict: dict):
    """
    Runs LP optimization using custom priority weights.
    weights_dict: {"cost": float, "eco": float, "sicherheit": float} (should sum to ~1.0)
    """
    forecasts = get_forecast_values()
    
    # Calculate Normalized Scores
    # N_r_Metric = (M_r - min) / (max - min)
    norm_data = {}
    for m in ["cost", "eco", "sicherheit"]:
        vals = [forecasts[m][r] for r in regions]
        n_vals = normalize(vals)
        norm_data[m] = dict(zip(regions, n_vals))
    
    # Final Penalty Score per region
    scores = {}
    w_cost = weights_dict.get("cost", 0.33)
    w_eco = weights_dict.get("eco", 0.33)
    w_sich = weights_dict.get("sicherheit", 0.34)
    
    for r in regions:
        scores[r] = (w_cost * norm_data["cost"][r] + 
                     w_eco * norm_data["eco"][r] + 
                     w_sich * norm_data["sicherheit"][r])
    
    print(f"Priority Weights: Cost={w_cost}, Eco={w_eco}, Sicherheit={w_sich}")
    print(f"Calculated Scores: {scores}")

    # LP Setup
    # Decision variables: x[w, r] -> 9 variables
    c = []
    for w in workloads:
        for r in regions:
            c.append(scores[r] * D[w])

    # Constraints
    A_eq, b_eq = [], []
    for i, w in enumerate(workloads):
        row = np.zeros(9)
        row[i * 3 : (i + 1) * 3] = 1.0
        A_eq.append(row)
        b_eq.append(1.0)

    A_ub, b_ub = [], []
    for j, r in enumerate(regions):
        row = np.zeros(9)
        row[j] = D["inference_EU"]
        row[3 + j] = D["inference_MENA"]
        row[6 + j] = D["batch_training"]
        A_ub.append(row)
        b_ub.append(Cap[r])

    # Bounds & Latency Blocks (SLA)
    # Frankfurt block: MAD/HEL for EU
    # Madrid block: FRA/HEL for MENA
    bounds = [
        (0.0, 1.0), (0.0, 0.0), (0.0, 0.0), # inference_EU -> FRA only
        (0.0, 0.0), (0.0, 1.0), (0.0, 0.0), # inference_MENA -> MAD only
        (0.0, 1.0), (0.0, 1.0), (0.0, 1.0), # batch_training -> ANY
    ]

    res = linprog(c, A_eq=A_eq, b_eq=b_eq, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")

    if res.success:
        allocation = {}
        x = res.x
        idx = 0
        for w in workloads:
            allocation[w] = {}
            for r in regions:
                allocation[w][r] = float(x[idx])
                idx += 1
        
        output = {
            "allocation": allocation,
            "scores": scores,
            "forecasts": forecasts,
            "weights": weights_dict,
            "status": "Optimal"
        }
        
        # Save for persistence if needed
        with open("ui_data.json", "w") as f:
            json.dump(output, f, indent=4)
            
        return output
    else:
        return {"status": "Failed", "error": "Solver could not find a solution"}

def run_optimization():
    # Backward compatibility
    return run_optimization_with_weights({"cost": 0.4, "eco": 0.3, "sicherheit": 0.3})

if __name__ == "__main__":
    run_optimization()

