import numpy as np
import json
import os
from scipy.optimize import linprog
import database

def get_dynamic_regions():
    """Fetches regions and capacities from the database."""
    nodes = database.get_nodes()
    regions = [n['name'] for n in nodes]
    cap = {n['name']: n['capacity'] for n in nodes}
    # For default forecast values, we need cost/eco/security too
    defaults = {
        "cost": {n['name']: n['cost'] for n in nodes},
        "eco": {n['name']: n['carbon'] * 1000 for n in nodes}, # Scale if needed
        "sicherheit": {n['name']: n['security'] for n in nodes}
    }
    return regions, cap, defaults

# Reference sets (workloads remain mostly static for this demo)
workloads = ["inference_EU", "inference_MENA", "batch_training"]

# Internal enterprise assets: Customer Demand (D) in MW
D = {"inference_EU": 35.0, "inference_MENA": 20.0, "batch_training": 50.0}

def normalize(values):
    """Min-Max normalization to [0, 1]."""
    arr = np.array(values)
    v_min, v_max = arr.min(), arr.max()
    if v_max == v_min:
        return np.zeros_like(arr)
    return (arr - v_min) / (v_max - v_min)

def get_forecast_values(regions, defaults):
    """
    Attempts to load forecasted values from sybilion_forecast_results.json.
    If missing, returns realistic synthetic median values from defaults.
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

    for m in metrics:
        for r in regions:
            if r not in forecasts[m]:
                forecasts[m][r] = defaults[m][r]
                
    return forecasts

def run_optimization_with_weights(weights_dict: dict):
    """
    Runs LP optimization using custom priority weights.
    """
    regions, Cap, defaults = get_dynamic_regions()
    forecasts = get_forecast_values(regions, defaults)
    
    num_regions = len(regions)
    num_workloads = len(workloads)
    
    # Calculate Normalized Scores
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
    
    # LP Setup
    # Decision variables: x[w, r] -> num_workloads * num_regions variables
    c = []
    for w in workloads:
        for r in regions:
            c.append(scores[r] * D[w])

    # Equality Constraints (sum of shares for each workload = 1)
    A_eq, b_eq = [], []
    for i in range(num_workloads):
        row = np.zeros(num_workloads * num_regions)
        row[i * num_regions : (i + 1) * num_regions] = 1.0
        A_eq.append(row)
        b_eq.append(1.0)

    # Inequality Constraints (capacity per region)
    A_ub, b_ub = [], []
    for j, r in enumerate(regions):
        row = np.zeros(num_workloads * num_regions)
        for i, w in enumerate(workloads):
            row[i * num_regions + j] = D[w]
        A_ub.append(row)
        b_ub.append(Cap[r])

    # Bounds
    bounds = []
    for i, w in enumerate(workloads):
        for j, r in enumerate(regions):
            # Dynamic SLA blocks if needed, but for now allow any
            # (In production we'd map regions to SLA zones)
            bounds.append((0.0, 1.0))

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
        
        return {
            "allocation": allocation,
            "scores": scores,
            "forecasts": forecasts,
            "weights": weights_dict,
            "status": "Optimal"
        }
    else:
        return {"status": "Failed", "error": f"Solver failed: {res.message}"}

def run_optimization():
    # Backward compatibility
    return run_optimization_with_weights({"cost": 0.4, "eco": 0.3, "sicherheit": 0.3})

if __name__ == "__main__":
    run_optimization()

