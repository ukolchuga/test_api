# GridPilot: A Probabilistic Risk and Resilience Management Agent for AI Data Centers

GridPilot is an intelligent decision layer built on top of the **Sybilion** probabilistic forecasting API. The agent converts volatility and uncertainty across energy markets, climate variations, and power grid stresses into concrete operational choices: routing GPU workloads across global regions to minimize costs, carbon footprints, and infrastructural downsides.

---

## 1. System Architecture and Data Pipeline

GridPilot implements **Prescriptive Analytics**. Instead of just displaying passive dashboards with past trends, the system leverages forward-looking probabilistic insights to automate physical infrastructure routing.

### Pipeline Execution Steps:
1. **Historical Data Ingestion:** Extract monthly time-series data (minimum 60 data points) from verified, open-source energy and climate platforms.
2. **Probabilistic Forecasting (Sybilion API):** Send historical datasets to Sybilion to obtain 6-month forward-looking probability distributions (median forecast $q_{50}$ along with tail-risk quantiles).
3. **Penalty Scoring:** Normalize the received forecasts and apply the user's custom strategic priority weights.
4. **Linear Programming (LP) Optimization:** Execute a mathematical solver to discover the ideal workload allocation matrix while strictly satisfying hardware capacity and network SLA limits.

---

## 2. Business Heuristics and Data Sources

To train Sybilion and evaluate the target objective function, GridPilot tracks three foundational vectors:

| Heuristic | Target Series (Sybilion Forecast) | Contextual Drivers | Primary Data Source |
| :--- | :--- | :--- | :--- |
| **Cost Efficiency** | `power_price_{region}` *(Wholesale price in EUR/MWh)* | European natural gas prices (FRED: PNGASEUUSDM), carbon credits (Ember) | ENTSO-E (Day-ahead Prices) |
| **Eco / CO2** | `carbon_intensity_{region}` *(Grid intensity in gCO2/kWh)* | Renewable energy generation shares (wind, solar, hydro) | Ember (Monthly Electricity Data) |
| **Sicherheit (Security)** | `grid_stress_index_{region}` *(Grid capacity margin in %)* | Power grid transmission bottlenecks, historical peak loads | ENTSO-E (Actual Load / Installed Capacity) |

> **Note:** The `grid_stress_index` is calculated internally by the agent using the following formula: 
> $$\text{Grid Stress Index} = \frac{\text{Actual Total Load}}{\text{Installed Generation Capacity}}$$
> Local weather variables used to compute data center cooling penalties (PUE multipliers) are fetched directly via the **Open-Meteo Historical API**.

---

## 3. Mathematical Model of Linear Programming (LP)

The problem of distributing multi-tenant GPU workloads for a target forecast month is modeled as a classic constrained optimization problem.

### Indices and Sets:
* $r \in R$ — Set of available data center regions: $R = \{\text{Frankfurt}, \text{Madrid}, \text{Helsinki}\}$
* $w \in W$ — Set of workload classes: $W = \{\text{inference\_EU}, \text{inference\_MENA}, \text{batch\_training}\}$

### 3.1. Pre-Processing (Normalization & Scoring)
Raw predictions $\hat{M}_r$ from Sybilion are normalized using Min-Max scaling to a dimensionless scale between 0 (best market condition) and 1 (worst market condition):
$$N_r^{\text{Metric}} = \frac{\hat{M}_r - \min_{k} \hat{M}_k}{\max_{k} \hat{M}_k - \min_{k} \hat{M}_k}$$

User-defined strategic priority weights ($W_{\text{Cost}}, W_{\text{Eco}}, W_{\text{Sicherheit}} \in [0, 100]$) are scaled to sum to one ($\sum w_i = 1$) to calculate the definitive **Penalty Score** for each region ($Score_r$):
$$Score_r = w_{\text{Cost}} \cdot N_r^{\text{Cost}} + w_{\text{Eco}} \cdot N_r^{\text{Eco}} + w_{\text{Sicherheit}} \cdot N_r^{\text{Sicherheit}}$$

### 3.2. LP Model Formulation

**Objective Function (Minimize Global System Penalty):**
$$\min_{x} \sum_{w \in W} \sum_{r \in R} Score_r \cdot D_w \cdot x_{w, r}$$

**System Constraints:**

1. *Workload Allocation Completeness (Ensures 100% of each task runs somewhere):*
$$\sum_{r \in R} x_{w, r} = 1 \quad \forall w \in W$$

2. *Physical Data Center Capacity Limits (Prevents overloads, calculated in absolute MW):*
$$\sum_{w \in W} D_w \cdot x_{w, r} \le Cap_r \quad \forall r \in R$$

3. *Network SLA Compliance (Enforces hard latency blocks):*
$$x_{w, r} = 0 \quad \forall (w, r) \in \{(w, r) \mid L_{w, r} = 1\}$$

4. *Decision Bounds:*
$$0 \le x_{w, r} \le 1 \quad \forall w \in W, \forall r \in R$$

### Parameter Matrix Definitions:
* $x_{w, r}$ — **Decision Variable:** The fraction of workload $w$ routed to region $r$. The system evaluates a flat vector of $3 \times 3 = 9$ unknown variables.
* $D_w$ — **Demand:** The total power capacity required to handle workload $w$ for the billing cycle (in MW, derived from internal scheduler metrics).
* $Cap_r$ — **Capacity:** The physical power draw limit of the facility in region $r$ (in MW).
* $L_{w, r}$ — **Binary Latency Violator Flag:** Equals 1 if the network ping between user base $w$ and infrastructure node $r$ breaks the SLA threshold; equals 0 if it is safe to route.

---

## 4. Latency SLA Mechanics

Because GridPilot operates on a macro operational horizon, ping is handled discretely using an SLA compliance grid. If the network path metrics show $Lat_{w,r} > \text{SLA}_w$, the flag $L_{w,r}$ is flagged as 1, removing that region from the decision tree.

### Example Binary SLA Violation Matrix ($L$):
```text
                  Frankfurt  Madrid  Helsinki
inference_EU    [    0,        1,       1    ]  -> Locked to Frankfurt
inference_MENA  [    1,        0,       1    ]  -> Locked to Madrid
batch_training  [    0,        0,       0    ]  -> Location-agnostic