import os
import json
from datetime import datetime
from dotenv import load_dotenv
from sybilion import Client
import pandas as pd

# Load environment variables
load_dotenv()

METRIC_METADATA = {
    "cost": {
        "title": "Electricity Day-Ahead Price Forecast",
        "description": "Wholesale electricity price forecast based on fuel prices, carbon costs, and regional demand patterns.",
        "keywords": ["electricity", "price", "energy", "market", "wholesale"]
    },
    "eco": {
        "title": "Grid Carbon Intensity Forecast",
        "description": "Forecast of CO2 emissions per kWh based on generation mix and renewable availability.",
        "keywords": ["carbon", "intensity", "eco", "emissions", "sustainability"]
    },
    "sicherheit": {
        "title": "Grid Stress and Resilience Index",
        "description": "Composite index tracking grid stability, physical delivery risk, and extreme weather impacts.",
        "keywords": ["grid", "stress", "resilience", "security", "reliability"]
    }
}

class GridPilotForecaster:
    def __init__(self):
        token = os.environ.get("SYBILION_API_TOKEN")
        if not token:
            raise ValueError("SYBILION_API_TOKEN not found in environment.")
        self.client = Client(token=token)

    def run_forecast(self, timeseries_data: dict, metric_type: str, region: str, horizon: int = 6):
        """Runs a Sybilion forecast for a specific metric and region."""
        if metric_type not in METRIC_METADATA:
            raise ValueError(f"Unknown metric type: {metric_type}")

        metadata = METRIC_METADATA[metric_type].copy()
        metadata["title"] = f"{region} - {metadata['title']}"
        
        print(f"\n--- Forecasting {metric_type.upper()} for {region} ---")
        
        body = {
            "pipeline_version": "v1",
            "frequency": "monthly",
            "soft_horizon": horizon,
            "recency_factor": 0.5,
            "backtest": True,
            "timeseries_metadata": metadata,
            "timeseries": timeseries_data
        }

        try:
            submit = self.client.submit_forecast(body)
            print(f"Job ID: {submit.job_id}")
            job = self.client.wait_forecast(submit.job_id, poll_s=10.0, timeout_s=3600.0)
            
            if job.status != "completed":
                print(f"Forecast failed for {region} {metric_type}: {job.status}")
                return None

            results = {}
            for artifact in ["forecast.json", "external_signals.json"]:
                data = self.client.get_forecast_artifact(job.job_id, artifact)
                results[artifact] = json.loads(data)
            
            return results
        except Exception as e:
            print(f"Error in forecast pipeline for {region} {metric_type}: {e}")
            # Try to print more details if it's an API error
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                print(f"API Response Details: {e.response.text}")
            return None

def process_all_forecasts(csv_path: str):
    """Orchestrates forecasts for all regions and metrics based on historical data."""
    df = pd.read_csv(csv_path)
    df['Date'] = pd.to_datetime(df['Date'])
    df.set_index('Date', inplace=True)
    
    forecaster = GridPilotForecaster()
    regions = ["Frankfurt", "Madrid", "Helsinki"]
    metrics = ["cost", "eco", "sicherheit"]
    
    all_results = {}

    for region in regions:
        all_results[region] = {}
        for metric in metrics:
            # Map metric to column in CSV
            col_map = {
                "cost": f"{region}_Power_Price_EUR",
                "eco": f"{region}_CO2_Intensity",
                "sicherheit": f"{region}_Grid_Stress"
            }
            
            # Temporary safety fallback for Grid Stress in other regions
            col_name = col_map[metric]
            if not col_name or col_name not in df.columns:
                print(f"Warning: Column {col_name} not found for {region} {metric}. Skipping.")
                continue
                
            ts_data = df[col_name].to_dict()
            # Convert timestamp keys to string YYYY-MM-01
            ts_data = {k.strftime("%Y-%m-01"): v for k, v in ts_data.items()}
            
            res = forecaster.run_forecast(ts_data, metric, region)
            if res:
                all_results[region][metric] = res
                
    # Save results to a single JSON for the next step
    with open("sybilion_forecast_results.json", "w") as f:
        json.dump(all_results, f, indent=4)
    print("\nAll forecasts completed and saved to sybilion_forecast_results.json")

if __name__ == "__main__":
    # In a real run, we would call ingestion first
    # For now, assume gridpilot_historical_context.csv exists
    if os.path.exists("gridpilot_historical_context.csv"):
        process_all_forecasts("gridpilot_historical_context.csv")
    else:
        print("Historical context CSV not found. Please run ingestion.py first.")