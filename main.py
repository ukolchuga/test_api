import os
import json
import random
from datetime import date
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from matplotlib import pyplot as plt
from sybilion import Client
from datetime import datetime

# Load environment variables from the .env file
load_dotenv()


def run_sybilion_forecast(timeseries_data: dict, metadata: dict, horizon: int = 3):
    """
    Submits a timeseries to the Sybilion API and waits for the results.

    :param timeseries_data: Dictionary in the format {"YYYY-MM-01": float_value}
    :param metadata: Dictionary with keys: title, description, keywords
    :param horizon: Forecast horizon in months (soft_horizon)
    """
    # Initialize the client. The token is now safely loaded from .env into os.environ
    token = os.environ.get("SYBILION_API_TOKEN")
    if not token:
        raise ValueError("Error: SYBILION_API_TOKEN not found. Did you create the .env file?")

    client = Client(token=token)

    # 1. Verify authentication and check balance
    print("Checking connection and balance...")
    try:
        me = client.me()
        print(f"Success. Balance: {me.available_eur_cents / 100:.2f} EUR (Tier {me.api_usage_tier})")
    except Exception as e:
        print(f"Authentication error: {e}")
        return None

    if len(timeseries_data) < 40:
        print("WARNING: A minimum of 40 observations is required. The API might reject the request.")

    # 2. Build the request body
    body = {
        "pipeline_version": "v1",
        "frequency": "monthly",
        "soft_horizon": horizon,
        "recency_factor": 0.5,
        "backtest": True,
        "timeseries_metadata": metadata,
        "timeseries": timeseries_data
    }

    # 3. Submit the forecast job
    print("\nSubmitting data to the Sybilion pipeline...")
    try:
        submit = client.submit_forecast(body)
        print(f"Job accepted! Job ID: {submit.job_id}")
    except Exception as e:
        print(f"Error submitting data: {e}")
        return None

    # 4. Wait for completion
    print("Waiting for the forecast job to finish (usually takes a few minutes)...")
    job = client.wait_forecast(submit.job_id, poll_s=10.0, timeout_s=3600.0)
    if job.status != "completed":
        print(f"\nForecast failed. Status: {job.status}")

        error_info = getattr(job, "pipeline_error", None)
        if error_info:
            # Check if it's a dictionary or an object and extract safely
            code = error_info.get('code') if isinstance(error_info, dict) else getattr(error_info, 'code', 'Unknown')
            detail = error_info.get('detail') if isinstance(error_info, dict) else getattr(error_info, 'detail',
                                                                                           'Unknown')

            print(f"Error Code: {code}")
            print(f"Error Detail: {detail}")
            print(f"Raw Error Dump: {error_info}")  # Prints the whole thing just in case!
        else:
            print("No detailed error message was returned.")

        return None

    print(f"\nCalculation completed! Final cost: {job.eur_cents_final / 100:.2f} EUR")

    # 5. Download the artifacts
    print("Downloading results...")
    results = {}
    artifacts_to_fetch = ["forecast.json", "external_signals.json", "backtest_metrics.json"]

    for artifact_name in artifacts_to_fetch:
        try:
            data = client.get_forecast_artifact(job.job_id, artifact_name)
            results[artifact_name] = json.loads(data)
            print(f" - {artifact_name} downloaded successfully.")
        except Exception as e:
            print(f" - Error downloading {artifact_name}: {e}")

    return results


def plot_sybilion_forecast(history_data: dict, forecast_json: dict):
    """
    Plots the historical data and the forecast with quantile bands.
    """
    # 1. Sort and parse history
    sorted_history = sorted(history_data.items())
    hist_dates = [datetime.strptime(date, "%Y-%m-%d") for date, _ in sorted_history]
    hist_values = [val for _, val in sorted_history]

    # 2. Parse the forecast
    # If you pass the dictionary received from the API, check the keys:
    forecast_series = forecast_json.get("2026-05-01")  # Check if it's a direct date key
    if not forecast_series:
        # If the full JSON response was passed, go deeper:
        forecast_series = forecast_json.get("data", {}).get("forecast_series", forecast_json)

    sorted_forecast = sorted(forecast_series.items())

    fcst_dates = []
    fcst_values = []
    lower_band_80 = []  # 10th percentile
    upper_band_80 = []  # 90th percentile
    lower_band_50 = []  # 25th percentile
    upper_band_50 = []  # 75th percentile

    for date_str, metrics in sorted_forecast:
        fcst_dates.append(datetime.strptime(date_str, "%Y-%m-%d"))
        fcst_values.append(metrics["forecast"])

        quantiles = metrics.get("quantile_forecast", {})

        # Collect interval boundaries
        lower_band_80.append(quantiles.get("0.10", metrics["forecast"]))
        upper_band_80.append(quantiles.get("0.90", metrics["forecast"]))

        lower_band_50.append(quantiles.get("0.25", metrics["forecast"]))
        upper_band_50.append(quantiles.get("0.75", metrics["forecast"]))

    # 3. "Stitch" history and forecast so there is no gap on the chart
    if hist_dates and fcst_dates:
        last_hist_date = hist_dates[-1]
        last_hist_val = hist_values[-1]

        fcst_dates.insert(0, last_hist_date)
        fcst_values.insert(0, last_hist_val)
        lower_band_80.insert(0, last_hist_val)
        upper_band_80.insert(0, last_hist_val)
        lower_band_50.insert(0, last_hist_val)
        upper_band_50.insert(0, last_hist_val)

    # 4. Plotting
    plt.figure(figsize=(14, 7))

    # Plot history (take the last 20 points for context)
    plt.plot(hist_dates[-20:], hist_values[-20:], label="History (last 20 months)", color="black", linewidth=2)

    # Plot the point forecast
    plt.plot(fcst_dates, fcst_values, label="Point Forecast", color="blue", linestyle="--", linewidth=2, marker='o')

    # Shade the 50% confidence interval (darker)
    plt.fill_between(
        fcst_dates, lower_band_50, upper_band_50,
        color="blue", alpha=0.3, label="50% Confidence Interval (Q0.25 - Q0.75)"
    )

    # Shade the 80% confidence interval (lighter)
    plt.fill_between(
        fcst_dates, lower_band_80, upper_band_80,
        color="blue", alpha=0.1, label="80% Confidence Interval (Q0.10 - Q0.90)"
    )

    # Formatting the chart
    plt.title("Sybilion Forecast (Synthetic Data)", fontsize=16, fontweight="bold")
    plt.xlabel("Date", fontsize=12)
    plt.ylabel("Sensor Value", fontsize=12)
    plt.grid(True, linestyle=":", alpha=0.7)
    plt.legend(loc="upper left")
    plt.xticks(rotation=45)
    plt.tight_layout()

    plt.show()

# --- Test Execution ---
if __name__ == "__main__":
    print("Generating random test data (base value + trend + heavy noise)...")

    start_date = date(2018, 1, 1)
    random_ts = {}

    # Generate 100 months of randomized data
    base_value = 150.0
    for i in range(100):
        current_date = start_date + relativedelta(months=i)
        date_str = current_date.strftime("%Y-%m-01")

        # Add a slight trend (i * 1.5) and random noise between -20 and +20
        noise = random.uniform(-20.0, 20.0)
        value = base_value + (i * 1.5) + noise

        random_ts[date_str] = round(value, 2)

    # The "prompt" / metadata describing the data to the Sybilion pipeline
    random_metadata = {
        "title": "Randomized Industrial Sensor Output",
        "description": "A synthetic dataset representing highly volatile, noisy output from an industrial sensor with a slight upward drift over time.",
        "keywords": ["synthetic", "noise", "sensor", "industrial", "volatility"]
    }

    print("\nGenerated Metadata:")
    print(json.dumps(random_metadata, indent=2))
    print(f"\nGenerated {len(random_ts)} data points. First 3 points:")
    print(list(random_ts.items())[:3])

    print("\nStarting forecast...")
    final_data = run_sybilion_forecast(random_ts, random_metadata, horizon=3)

    if final_data and "forecast.json" in final_data:
        print("\n=== Forecast Result ===")
        forecast_series = final_data["forecast.json"]["data"]["forecast_series"]
        print(json.dumps(forecast_series, indent=2))

    plot_sybilion_forecast(random_ts, final_data["forecast.json"])