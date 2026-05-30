import numpy as np
from scipy.optimize import linprog

# Reference sets
workloads = ["inference_EU", "inference_MENA", "batch_training"]
regions = ["Frankfurt", "Madrid", "Helsinki"]

# Internal enterprise assets: Customer Demand (D) in MW
D = {"inference_EU": 35.0, "inference_MENA": 20.0, "batch_training": 50.0}

# Physical constraints: Maximum DC Capacity (Cap) in MW
Cap = {"Frankfurt": 50.0, "Madrid": 40.0, "Helsinki": 40.0}

# Complex penalty coefficients (Generated downstream from Sybilion forecasts)
# Reflects an operational profile emphasizing Eco/Cost (Helsinki is cleanest/cheapest)
scores = {"Frankfurt": 0.6, "Madrid": 0.3, "Helsinki": 0.2}

print("=== INPUT METRICS ===")
print(f"Total User Demand:      {sum(D.values())} MW")
print(f"Total Network Capacity: {sum(Cap.values())} MW\n")

# Flattening the 9 decision variables into a 1D vector for the LP objective function 'c':
# [x1_FRA, x1_MAD, x1_HEL,  x2_FRA, x2_MAD, x2_HEL,  x3_FRA, x3_MAD, x3_HEL]
c = []
for w in workloads:
    for r in regions:
        c.append(scores[r] * D[w])

# EQUALITY CONSTRAINTS (A_eq, b_eq) -> Sum of shares for each workload must equal 1.0
A_eq = []
b_eq = []
for i, w in enumerate(workloads):
    row = np.zeros(9)
    row[i * 3 : (i + 1) * 3] = 1.0
    A_eq.append(row)
    b_eq.append(1.0)

# INEQUALITY CONSTRAINTS (A_ub, b_ub) -> Total consumed MW in region <= Cap_r
A_ub = []
b_ub = []
for j, r in enumerate(regions):
    row = np.zeros(9)
    row[j] = D["inference_EU"]  # EU Inference share
    row[3 + j] = D["inference_MENA"]  # MENA Inference share
    row[6 + j] = D["batch_training"]  # Batch training share
    A_ub.append(row)
    b_ub.append(Cap[r])

# Variable bounds and network Latency SLA filtering
bounds = [
    # inference_EU: Only Frankfurt allowed. Madrid and Helsinki are zeroed out by SLA.
    (0.0, 1.0),
    (0.0, 0.0),
    (0.0, 0.0),
    # inference_MENA: Only Madrid allowed. Frankfurt and Helsinki are zeroed out by SLA.
    (0.0, 0.0),
    (0.0, 1.0),
    (0.0, 0.0),
    # batch_training: Location-agnostic. Free to float across any region.
    (0.0, 1.0),
    (0.0, 1.0),
    (0.0, 1.0),
]

# Run Linear Programming using the modern HiGHS solver backend
res = linprog(
    c, A_eq=A_eq, b_eq=b_eq, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs"
)

# Evaluate and print results
if res.success:
    print("=== OPTIMAL WORKLOAD ALLOCATION (LP RESULT) ===")
    x = res.x
    idx = 0
    for w in workloads:
        print(f"\nWorkload Class: {w} (Required: {D[w]} MW)")
        for r in regions:
            share = x[idx]
            allocated_mw = share * D[w]
            if allocated_mw > 0:
                print(f" -> Region [{r}]: {share * 100:.1f}% ({allocated_mw:.1f} MW)")
            idx += 1

    print("\n=== PHYSICAL INFRASTRUCTURE LOAD VERIFICATION ===")
    fra_load = (
        x[0] * D["inference_EU"]
        + x[3] * D["inference_MENA"]
        + x[6] * D["batch_training"]
    )
    mad_load = (
        x[1] * D["inference_EU"]
        + x[4] * D["inference_MENA"]
        + x[7] * D["batch_training"]
    )
    hel_load = (
        x[2] * D["inference_EU"]
        + x[5] * D["inference_MENA"]
        + x[8] * D["batch_training"]
    )

    print(
        f"Frankfurt: Utilized {fra_load:.1f} MW out of {Cap['Frankfurt']} MW Max Limit"
    )
    print(f"Madrid:    Utilized {mad_load:.1f} MW out of {Cap['Madrid']} MW Max Limit")
    print(
        f"Helsinki:  Utilized {hel_load:.1f} MW out of {Cap['Helsinki']} MW Max Limit"
    )
else:
    print(
        "Optimization Error: Solver failed to find a valid allocation. Verify bounds and capacities!"
    )
