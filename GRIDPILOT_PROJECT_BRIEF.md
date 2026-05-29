# GridPilot Project Brief

## 1. Executive Summary

**GridPilot** is a probabilistic energy-risk and resilience agent for AI data centers.

It converts energy, carbon, grid, weather, volatility, and geopolitical uncertainty into operational decisions:

- where to run GPU workloads;
- how much workload to move between regions;
- how much energy exposure to hedge;
- when to activate backup capacity;
- how to respond to shocks such as heatwaves, grid stress, carbon-price spikes, or physical delivery failures.

The core idea is not to forecast electricity prices for their own sake. The agent uses probabilistic forecasts to change a real decision.

GridPilot is built as a decision layer on top of the Sybilion probabilistic forecasting API. Sybilion provides forecast distributions, driver importance, and backtest artifacts. GridPilot adds scenario generation, GARCH-based volatility adjustment, CVaR95 tail-risk scoring, user-configurable business priorities, and workload-allocation optimization.

## 2. Target User

The primary user is an AI infrastructure operator, cloud provider, hyperscaler, or large enterprise running GPU workloads across multiple data-center regions.

Typical stakeholders:

- CFO: wants predictable energy spend and lower downside risk.
- Infrastructure / operations team: wants uptime, SLA protection, and resilient capacity.
- Sustainability team: wants lower CO2 footprint.
- Risk team: wants controlled exposure to volatility, grid stress, and geopolitical events.
- Product team: wants latency-sensitive inference to remain reliable.

## 3. Decision Problem

The agent decides how to allocate workloads across regions.

Example regions:

- Frankfurt
- Madrid
- Helsinki
- future extension: UAE, Singapore, Saudi Arabia, Qatar, India

Example workload classes:

- `real_time_inference`: latency-sensitive, must stay close to users.
- `batch_training`: flexible, can move between regions.
- `experiments_and_eval`: highly flexible, can be delayed or moved.

The decision variable is:

```text
x[w, r] = share of workload w assigned to region r
```

Example:

```text
x[batch_training, Madrid] = 0.60
x[batch_training, Helsinki] = 0.40
```

Each workload must be fully allocated:

```text
sum_r x[w, r] = 1
```

## 4. Forecast Horizon

GridPilot uses a **rolling 6-month forecast horizon**.

This does not mean the forecast is updated only every six months. It means the agent regularly refreshes a forecast for the next six months.

Example:

```text
June 2026 run -> forecast June-November 2026
July 2026 run -> forecast July-December 2026
August 2026 run -> forecast August 2026-January 2027
```

Why six months:

- 1-3 months is too tactical for hedging, backup capacity, and regional workload strategy.
- 2-3 years is useful for strategic siting decisions, but too uncertain for operational workload allocation.
- 6 months gives enough time to adjust contracts, reserves, migration plans, and capacity policy while keeping uncertainty narrow enough to support a concrete decision.

## 5. System Architecture

Current code modules:

```text
gridpilot/
  cli.py          -> command-line entrypoint
  demo_case.py    -> self-contained demo scenario
  domain.py       -> data models
  garch.py        -> volatility layer
  scenarios.py    -> probabilistic scenario generator
  optimizer.py    -> CVaR-based workload optimizer
  sybilion.py     -> Sybilion API adapter
```

High-level pipeline:

```text
1. Collect monthly time series and contextual metadata.
2. Send time series to Sybilion.
3. Receive probabilistic forecast bands, driver importance, and backtests.
4. Fit GARCH volatility layer on recent price behavior.
5. Generate hundreds or thousands of future scenarios.
6. Score candidate workload allocations under each scenario.
7. Optimize for cost, CO2, volatility exposure, and security.
8. Produce a transparent recommendation and explanation.
9. Re-run instantly when assumptions change.
```

## 6. Data Requirements

The current demo uses synthetic realistic data so the project runs without API keys. For production, the following data is required.

| Data Category | Purpose | Candidate Sources |
|---|---|---|
| Electricity prices by region | Main forecast target | [ENTSO-E Transparency Platform](https://www.entsoe.eu/data/transparency-platform/), [Ember API](https://api.ember-energy.org/docs) |
| Load, generation, renewables, interconnector flows | Grid-stress and price drivers | [ENTSO-E Transparency Platform](https://www.entsoe.eu/data/transparency-platform/) |
| European natural gas prices | Major power-price driver | [FRED PNGASEUUSDM](https://fred.stlouisfed.org/series/PNGASEUUSDM) |
| Carbon price / EU ETS | Carbon cost and regulatory risk | EEX, ICE EUA futures, exchange or market-data provider |
| Temperature / weather | Cooling demand, PUE stress, heatwave risk | [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api), [NASA POWER Daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/) |
| Carbon intensity | CO2 impact per MWh | Ember, Electricity Maps, ENTSO-E generation mix |
| GPU workload demand | Required GPU-hours by workload class | Kubernetes, Slurm, cloud billing, internal scheduler logs |
| Data-center capacity | Maximum usable regional energy or GPU capacity | Internal infrastructure data |
| Latency / SLA requirements | Which workloads can move where | Internal observability and product SLA data |
| Forward energy contracts | Hedged volume, price, tenor, firmness | Internal contract data |
| Backup power and emergency supply | Resilience modeling | Facility data, fuel contracts, battery/UPS specs |
| Counterparty and geopolitical risk | Delivery risk and force majeure exposure | Internal risk ratings, external geopolitical feeds |

Sybilion requires monthly time series. For the challenge case, a 6-month horizon is practical because it requires at least 60 monthly observations according to the stated challenge requirements.

## 7. Forecasting Layer

Sybilion is used for the core probabilistic forecasts.

Forecast targets can include:

- electricity price for Frankfurt;
- electricity price for Madrid;
- electricity price for Helsinki;
- carbon price;
- gas price;
- cooling degree days or temperature index;
- grid stress proxy.

Sybilion output used by GridPilot:

```text
q10 forecast
q50 forecast
q90 forecast
driver importance
backtest metrics
backtest trajectories
```

The agent uses these outputs to build scenario distributions rather than relying on a single point forecast.

## 8. GARCH Volatility Layer

GARCH is not used as a replacement for Sybilion. It is used as a volatility-risk overlay.

Purpose:

- detect whether the market is in a calm or turbulent volatility regime;
- widen forecast bands when recent shocks imply higher tail risk;
- make CVaR95 more sensitive to current market stress.

Simplified GARCH(1,1):

```text
sigma_t^2 = omega + alpha * epsilon_{t-1}^2 + beta * sigma_{t-1}^2
```

Meaning:

- `sigma_t^2` = current conditional variance;
- `epsilon_{t-1}^2` = size of the previous shock;
- `alpha` = how strongly new shocks affect volatility;
- `beta` = how persistent volatility is.

Electricity prices can be zero or negative, so the current implementation uses an `asinh` transform instead of simple log returns.

## 9. Scenario Generation

The scenario engine converts forecast bands into many possible futures.

Each scenario contains:

- monthly power prices by region;
- cooling degree days by region;
- carbon prices;
- optional shocks.

Examples of shocks:

- Spain heatwave: higher cooling demand and higher Madrid volatility.
- Germany grid stress: higher Frankfurt power-price tail and lower available capacity.
- Carbon spike: higher EU ETS price.
- Strict latency: tighter SLA buffer.
- UAE physical delivery failure: local power availability drops sharply despite forward contracts.

This is important because a forward contract can reduce price risk but may not eliminate physical delivery risk.

## 10. Objective Function

The current baseline objective is:

```text
objective = expected_cost + risk_aversion * CVaR95
```

Where:

- `expected_cost` = average cost across scenarios;
- `CVaR95` = average cost in the worst 5% of scenarios;
- `risk_aversion` = how conservative the user is.

Total cost per scenario:

```text
total_cost =
  electricity_cost
+ carbon_cost
+ migration_cost
+ latency_penalty
+ capacity_penalty
+ carbon_budget_penalty
+ emergency_power_cost
+ downtime_penalty
+ contract_default_loss
```

The current implementation already includes:

- electricity cost;
- carbon cost;
- migration cost;
- latency penalty;
- capacity penalty;
- carbon budget penalty.

Planned extension:

- emergency power;
- downtime loss;
- physical delivery shortfall;
- counterparty default;
- forward-contract firmness.

## 11. User-Configurable Priorities

Production GridPilot should allow users to set strategic priorities.

Example:

```text
Cost efficiency: 25%
Eco / CO2:       30%
Volatility risk: 25%
Sicherheit:      20%
```

The optimizer should minimize a weighted score:

```text
score =
  w_cost     * normalized_expected_cost
+ w_eco      * normalized_emissions
+ w_risk     * normalized_CVaR95
+ w_security * normalized_security_risk
```

Definitions:

- `cost_score`: normalized expected energy and operating cost.
- `emissions_score`: normalized CO2 footprint.
- `cvar_score`: normalized bad-tail cost exposure.
- `security_score`: normalized risk of power shortfall, SLA breach, capacity breach, or delivery failure.

This makes the agent enterprise-relevant because different users can make different tradeoffs.

## 12. Optimization Method

The current demo uses discrete grid search over allocation shares.

Example share grid:

```text
0%, 25%, 50%, 75%, 100%
```

This is useful for a hackathon demo because it is robust, explainable, and dependency-free.

For production, the correct mathematical formulation is:

```text
stochastic linear programming with CVaR
```

Decision variable:

```text
x[w, r] = share of workload w assigned to region r
```

Main constraints:

```text
sum_r x[w, r] = 1
0 <= x[w, r] <= 1
regional_energy_use[r] <= available_capacity[r]
latency[w, r] <= SLA_limit[w]
emissions <= carbon_budget
region_share[r] <= max_region_concentration
physical_power_required[r, s] <= available_power[r, s] + emergency_power[r, s] + shortfall[r, s]
```

CVaR can be represented linearly with auxiliary variables:

```text
CVaR_alpha = eta + 1 / ((1 - alpha) * N) * sum_s z_s
```

Subject to:

```text
z_s >= L_s(x) - eta
z_s >= 0
```

Where:

- `L_s(x)` = loss or total cost in scenario `s`;
- `eta` = VaR threshold variable;
- `z_s` = excess loss above the threshold;
- `alpha = 0.95`;
- `N` = number of scenarios.

Recommended production solvers:

- SciPy `linprog` for lightweight linear programming;
- CVXPY for more expressive optimization;
- OR-Tools for mixed-integer extensions;
- commercial solvers such as Gurobi or CPLEX if enterprise scale is required.

## 13. Constraints

Business and operational constraints:

- Critical inference cannot move to regions that violate latency limits.
- Workload must remain served unless explicitly allowed to degrade.
- Energy use must respect regional capacity.
- Carbon budget should not be exceeded without penalty.
- No single region should carry too much workload concentration.
- Emergency power is limited and expensive.
- Forward contracts may be firm, non-firm, financially settled, or physically deliverable.
- Some shocks affect price only; others affect physical availability.

Competition constraints:

- The demo must run live.
- The reasoning must be visible.
- The agent must adapt when a core assumption changes.
- The project must not be a thin LLM wrapper.
- Monthly time series must satisfy Sybilion minimum data requirements.

Technical constraints:

- Data must be normalized to monthly frequency.
- Forecast features must avoid lookahead leakage.
- Forecast and decision backtests must only use information available at each historical point.
- Weather, price, carbon, and workload data may have different time zones and reporting calendars.
- API quotas and rate limits must be handled.

## 14. Limitations

Current demo limitations:

- Uses synthetic data rather than live ENTSO-E, Ember, or Sybilion forecasts.
- Uses grid search, not a production-grade LP solver.
- Uses simplified region and workload definitions.
- Does not yet model physical delivery failure in the optimizer.
- Does not yet ingest real forward-contract data.
- Does not yet include real counterparty or geopolitical risk feeds.
- No UI yet; output is CLI text or JSON.

Model limitations:

- Long-horizon energy forecasts become highly uncertain.
- Electricity prices can be nonlinear, spiky, capped, or negative.
- Driver importance is useful for explanation but should not be treated as causal proof.
- GARCH captures volatility clustering but not all structural market breaks.
- CVaR depends on scenario quality; poor scenarios produce misleading tail-risk estimates.
- Physical grid failures may be rare and difficult to estimate from historical data alone.

Operational limitations:

- Moving workloads may require data locality, compliance, and networking checks.
- Some AI workloads cannot be interrupted or migrated cheaply.
- Backup generators may have fuel, emissions, permitting, and runtime constraints.
- Local regulation may limit demand response or energy resale behavior.

## 15. Development Plan

### Phase 0: Current Demo

Status: implemented.

Capabilities:

- self-contained synthetic demo;
- Frankfurt, Madrid, Helsinki regions;
- three workload classes;
- GARCH volatility overlay;
- probabilistic scenario generation;
- CVaR95 decision scoring;
- shock scenarios;
- CLI output and JSON output.

Run:

```powershell
py -3 -B -m gridpilot.cli demo
py -3 -B -m gridpilot.cli demo --shock spain-heatwave
py -3 -B -m gridpilot.cli demo --shock carbon-spike
```

### Phase 1: Hackathon MVP

Goal: working end-to-end agent using at least one real data source and Sybilion forecast artifacts.

Tasks:

- Replace synthetic power prices with real monthly electricity data.
- Add real gas price as contextual driver.
- Add real temperature-derived cooling degree days.
- Send monthly series to Sybilion.
- Parse Sybilion `forecast.json` and `external_signals.json`.
- Display driver importance in the decision explanation.
- Add at least three live shock buttons or CLI options.
- Generate a written backtest summary.

Acceptance criteria:

- Agent runs live.
- Forecast changes the decision.
- Reasoning is visible.
- Shock changes allocation or risk metrics.
- Baseline comparison is shown.

### Phase 2: Strong Competition Version

Goal: make the project clearly more sophisticated than a forecast dashboard.

Tasks:

- Add user priority weights: cost, eco, volatility, Sicherheit.
- Add physical delivery risk variable: `available_mwh`.
- Add emergency power and downtime penalty.
- Add forward-contract representation:
  - contracted volume;
  - contracted price;
  - firm vs non-firm;
  - physical vs financial settlement;
  - default or force majeure penalty.
- Add sensitivity report:
  - what changed;
  - why allocation changed;
  - which driver mattered most.
- Add simple UI or dashboard consuming CLI JSON output.

Acceptance criteria:

- User can change priorities.
- User can trigger shock.
- Agent visibly recomputes allocation.
- Agent explains cost, CO2, CVaR95, and Sicherheit tradeoff.

### Phase 3: Production Prototype

Goal: make the system deployable for a real enterprise pilot.

Tasks:

- Build data ingestion pipelines:
  - ENTSO-E / Ember;
  - FRED gas;
  - weather;
  - carbon price;
  - internal workload logs.
- Store normalized monthly data.
- Add forecast job orchestration.
- Add rolling backtest workflow.
- Replace grid search with stochastic LP backend.
- Add monitoring for forecast drift and missing data.
- Add authentication and organization-level configuration.
- Build UI:
  - forecast bands;
  - driver importance;
  - allocation recommendation;
  - CVaR waterfall;
  - priority sliders;
  - shock simulator;
  - backtest tab.

Acceptance criteria:

- Reproducible monthly forecast run.
- Automated backtest.
- Configurable risk preferences.
- Stable API and UI.
- Deployment-ready architecture.

### Phase 4: Enterprise Production

Goal: full resilience decision platform.

Tasks:

- Add real-time or daily monitoring for shock indicators.
- Add contract and counterparty risk engine.
- Add geopolitical risk feeds.
- Add automated alerting.
- Add scenario library maintained by risk team.
- Add audit logs and explainability exports.
- Add solver benchmarking and fallback logic.
- Add integration with workload orchestrators:
  - Kubernetes;
  - Slurm;
  - internal schedulers;
  - cloud APIs.

Acceptance criteria:

- Agent can recommend actions and optionally trigger controlled workflow changes.
- All decisions are auditable.
- Risk assumptions are versioned.
- SLA and business-continuity policies are enforced.

## 16. Backtesting Plan

Forecast backtest:

- Use Sybilion backtest metrics.
- Check forecast calibration: how often actuals fall within forecast bands.
- Compare forecast error against naive baselines.

Decision backtest:

- Replay historical months.
- At each date, use only data available at that time.
- Generate forecast.
- Let GridPilot choose allocation.
- Compare against baselines:
  - all workload in home region;
  - cheapest median-price region;
  - fixed static allocation;
  - cost-only optimizer.

Metrics:

- realized total cost;
- realized emissions;
- CVaR95 reduction;
- budget overruns;
- SLA violations;
- downtime / unserved workload;
- regret versus hindsight optimum.

## 17. Demo Story

Baseline:

```text
real_time_inference -> Frankfurt
batch_training -> Madrid
experiments_and_eval -> Madrid / Helsinki
```

Shock 1: Spain heatwave

```text
Madrid cooling demand rises.
Madrid volatility increases.
Agent shifts flexible training to Helsinki.
```

Shock 2: Germany grid stress

```text
Frankfurt price tail widens.
Frankfurt capacity drops.
Agent reduces non-critical dependence on Frankfurt.
```

Shock 3: carbon spike

```text
Carbon price increases.
High-carbon regions become less attractive.
Agent shifts toward lower-carbon capacity.
```

Shock 4: UAE physical delivery failure

```text
Forward price remains fixed, but deliverable MWh collapses.
Agent switches to continuity mode:
critical local inference only,
flexible training migrated,
emergency power priced,
downtime risk quantified.
```

## 18. Why This Can Win

GridPilot fits the challenge criteria well:

1. **Decision change**  
   The forecast directly changes workload allocation, hedging posture, and resilience actions.

2. **Visible reasoning**  
   The agent exposes forecast bands, driver importance, CVaR95, CO2 impact, SLA limits, and security constraints.

3. **Adaptive behavior**  
   The agent responds to live changes in heat, grid stress, carbon price, latency requirements, or physical availability.

The project is stronger than a basic forecast dashboard because it combines:

- probabilistic forecasting;
- risk-aware optimization;
- CVaR tail-risk management;
- GARCH volatility regime detection;
- user-defined business priorities;
- physical delivery and resilience logic;
- transparent decision explanations.

## 19. Recommended Next Steps

Immediate next build steps:

1. Add `PreferenceProfile` to the codebase.
2. Add CLI flags for cost, eco, volatility, and Sicherheit weights.
3. Add physical delivery risk:

```text
available_mwh_by_region_by_scenario
emergency_power_price
downtime_penalty
```

4. Add one real data ingestion script, preferably FRED gas or Open-Meteo weather.
5. Add Sybilion forecast run example using one monthly time series.
6. Build a minimal UI from JSON output.
7. Prepare Sunday demo with three scripted shocks.

Recommended pitch sentence:

```text
GridPilot is a probabilistic AI infrastructure resilience agent that converts energy, carbon, grid, volatility, and geopolitical uncertainty into transparent workload, hedging, and continuity decisions.
```

