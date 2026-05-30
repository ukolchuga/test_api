import json
import random
from datetime import datetime, timedelta

REGIONS = ["Frankfurt", "Madrid", "Helsinki"]
METRICS = ["power_price", "carbon_intensity", "grid_stress"]

def generate_ts(base, noise, trend, months=72):
    ts = {}
    start_date = datetime(2020, 1, 1)
    for i in range(months):
        date_str = (start_date + timedelta(days=i*31)).replace(day=1).strftime("%Y-%m-01")
        val = base + (i * trend) + random.uniform(-noise, noise)
        ts[date_str] = round(max(0.1, val), 4)
    return ts

def main():
    config = {
        "power_price": {"base": 100, "noise": 30, "trend": 0.5},
        "carbon_intensity": {"base": 300, "noise": 50, "trend": -1.0},
        "grid_stress": {"base": 0.6, "noise": 0.15, "trend": 0.002}
    }

    for region in REGIONS:
        for metric in METRICS:
            # Add some regional variance
            reg_base = config[metric]["base"]
            if region == "Helsinki":
                if metric == "carbon_intensity": reg_base = 50
                if metric == "power_price": reg_base = 60
            elif region == "Madrid":
                if metric == "power_price": reg_base = 80
                
            ts = generate_ts(reg_base, config[metric]["noise"], config[metric]["trend"])
            filename = f"data_{region.lower()}_{metric}.json"
            with open(filename, "w") as f:
                json.dump(ts, f, indent=2)
            print(f"Generated {filename}")

if __name__ == "__main__":
    main()
