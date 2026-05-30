"""
Data Ingestion Pipeline for GridPilot MVP.

This script fetches weather, natural gas, carbon proxy data, and live CO2 intensity.
It harmonizes disparate frequencies into a clean monthly dataset, calculates proxy
electricity prices using the European Merit Order, and exports artifacts for both
the Sybilion forecasting API and the GridPilot CVaR Optimizer.
"""

import json
import os
from datetime import datetime

import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv

# Load environment variables (API keys)
load_dotenv()

# --- Configuration Constants ---
START_DATE = "2019-01-01"
END_DATE = datetime.today().strftime("%Y-%m-%d")
CDD_THRESHOLD = (
    22.0  # Temperature (Celsius) above which data center cooling is required
)

# Grid Stress Calculation Weights for the synthetic Sybilion target
WEIGHT_GAS = 0.5
WEIGHT_CARBON = 0.3
WEIGHT_CDD = 0.2

# Target regions and their coordinates
REGIONS = {
    "Frankfurt": {"lat": 50.1109, "lon": 8.6821},
    "Madrid": {"lat": 40.4168, "lon": -3.7038},
    "Helsinki": {"lat": 60.1695, "lon": 24.9354},
}


def fetch_openmeteo_cdd(region_name: str, lat: float, lon: float) -> pd.DataFrame:
    print(f"Fetching weather data for {region_name}...")
    url = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}"
        f"&start_date={START_DATE}&end_date={END_DATE}"
        f"&daily=temperature_2m_max&timezone=auto"
    )

    response = requests.get(url)
    response.raise_for_status()
    data = response.json()

    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(data["daily"]["time"]),
            f"{region_name}_Tmax": data["daily"]["temperature_2m_max"],
        }
    )

    df[f"{region_name}_CDD"] = df[f"{region_name}_Tmax"].apply(
        lambda x: max(0, x - CDD_THRESHOLD) if pd.notnull(x) else 0
    )

    df.set_index("Date", inplace=True)
    return df[[f"{region_name}_CDD"]].resample("MS").sum()


def fetch_yfinance_gas() -> pd.DataFrame:
    print("Fetching Natural Gas proxy (NG=F)...")
    df = yf.download("NG=F", start=START_DATE, end=END_DATE, progress=False)

    if df.empty:
        print("Warning: Gas data empty. Using synthetic fallback.")
        dates = pd.date_range(start=START_DATE, end=END_DATE, freq="MS")
        return pd.DataFrame({"Gas_Price_EUR": [3.5] * len(dates)}, index=dates)

    raw_values = (
        df["Close"].iloc[:, 0].values
        if isinstance(df.columns, pd.MultiIndex)
        else df["Close"].values
    )

    df_clean = pd.DataFrame(index=df.index, data={"Gas_Price_EUR": raw_values})
    df_clean.index.name = "Date"

    return df_clean.resample("MS").mean().ffill()


def fetch_carbon_price() -> pd.DataFrame:
    print("Fetching Global Carbon proxy (KRBN)...")
    df = yf.download("KRBN", start=START_DATE, end=END_DATE, progress=False)

    if df.empty:
        print("Warning: Carbon data empty. Using synthetic fallback.")
        dates = pd.date_range(start=START_DATE, end=END_DATE, freq="MS")
        return pd.DataFrame({"Carbon_Price": [40.0] * len(dates)}, index=dates)

    raw_values = (
        df["Close"].iloc[:, 0].values
        if isinstance(df.columns, pd.MultiIndex)
        else df["Close"].values
    )

    df_clean = pd.DataFrame(index=df.index, data={"Carbon_Price": raw_values})
    df_clean.index.name = "Date"

    return df_clean.resample("MS").mean().ffill().bfill()


def fetch_co2_intensity() -> pd.DataFrame:
    print("Fetching Regional Carbon Intensity via Ember API...")
    api_key = os.getenv("EMBER_API_KEY")

    dates = pd.date_range(start=START_DATE, end=END_DATE, freq="MS")
    fallback_df = pd.DataFrame(
        {
            "Frankfurt_CO2_Intensity": [
                400 + (40 if d.month in [11, 12, 1, 2] else -20) for d in dates
            ],
            "Madrid_CO2_Intensity": [
                200 + (-60 if d.month in [5, 6, 7, 8] else 20) for d in dates
            ],
            "Helsinki_CO2_Intensity": [
                70 + (15 if d.month in [1, 2] else -5) for d in dates
            ],
        },
        index=dates,
    )
    fallback_df.index.name = "Date"

    if not api_key:
        print("Warning: EMBER_API_KEY missing. Using synthetic structural fallback.")
        return fallback_df

    ember_entities = {"Frankfurt": "DEU", "Madrid": "ESP", "Helsinki": "FIN"}
    df_list = []

    for region, code in ember_entities.items():
        try:
            base_url = "https://api.ember-energy.org/v1"
            intensity_url = f"{base_url}/carbon-intensity/monthly?entity_code={code}&start_date={START_DATE}&api_key={api_key}"

            response = requests.get(intensity_url)
            response.raise_for_status()
            intensity_data = response.json().get("data", [])
            df_intensity = pd.DataFrame(intensity_data)

            if df_intensity.empty:
                raise ValueError("Ember returned empty data for this region.")

            if "fuel_category" in df_intensity.columns:
                df_intensity = df_intensity[
                    df_intensity["fuel_category"].str.lower() == "total"
                ]
            elif "entity" in df_intensity.columns:
                df_intensity = (
                    df_intensity.groupby("date").sum(numeric_only=True).reset_index()
                )

            df_intensity["Date"] = pd.to_datetime(df_intensity["date"])
            df_intensity.set_index("Date", inplace=True)

            # --- DYNAMIC COLUMN FINDER (FIXED) ---
            # Prioritize known data columns, fallback to first float column
            target_cols = ["emissions_intensity_gco2_per_kwh", "intensity", "value"]
            val_col = next(
                (col for col in target_cols if col in df_intensity.columns), None
            )

            if not val_col:
                # Find any float column just in case Ember renamed it again
                float_cols = df_intensity.select_dtypes(include=["float64"]).columns
                if not float_cols.empty:
                    val_col = float_cols[0]
                else:
                    raise ValueError(
                        f"Could not find numeric data column in: {list(df_intensity.columns)}"
                    )

            df_region = pd.DataFrame(
                {f"{region}_CO2_Intensity": df_intensity[val_col].resample("MS").mean()}
            )

            df_list.append(df_region)
            print(
                f"  -> Successfully processed {region} ({code}) using column '{val_col}'"
            )

        except Exception as e:
            print(f"  -> Ember API fetch failed for {region}: {e}. Using fallback.")
            df_list.append(fallback_df[[f"{region}_CO2_Intensity"]])

    final_df = pd.concat(df_list, axis=1)
    return final_df


def calculate_regional_power_prices(df_master: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates proxy wholesale electricity prices using the European Merit Order effect.
    """
    print("Calculating Regional Power Prices via Merit Order Proxy...")

    # Base formula: (Gas Price / Plant Efficiency) + (Carbon Price * Emission Factor)
    base_generation_cost = (df_master["Gas_Price_EUR"] / 0.5) + (
        df_master["Carbon_Price"] * 0.4
    )

    df_master["Frankfurt_Power_Price_EUR"] = base_generation_cost * 1.1 + (
        df_master.index.month.isin([11, 12, 1, 2]) * 15.0
    )

    df_master["Madrid_Power_Price_EUR"] = base_generation_cost * 0.85 - (
        df_master.index.month.isin([5, 6, 7, 8]) * 20.0
    )

    df_master["Helsinki_Power_Price_EUR"] = base_generation_cost * 0.65 + (
        df_master.index.month.isin([1, 2]) * 25.0
    )

    for col in [
        "Frankfurt_Power_Price_EUR",
        "Madrid_Power_Price_EUR",
        "Helsinki_Power_Price_EUR",
    ]:
        df_master[col] = df_master[col].clip(lower=5.0)

    return df_master


def build_dataset() -> pd.DataFrame:
    print("--- Starting Data Ingestion Pipeline ---")

    weather_dfs = [
        fetch_openmeteo_cdd(region, coords["lat"], coords["lon"])
        for region, coords in REGIONS.items()
    ]
    df_weather = pd.concat(weather_dfs, axis=1)

    df_gas = fetch_yfinance_gas()
    df_carbon = fetch_carbon_price()
    df_co2 = fetch_co2_intensity()

    print("Harmonizing base datasets...")
    df_master = df_weather.join([df_gas, df_carbon, df_co2], how="outer")

    df_master.ffill(inplace=True)
    df_master.bfill(inplace=True)
    df_master.dropna(inplace=True)

    # Calling the power prices function!
    df_master = calculate_regional_power_prices(df_master)

    return df_master


if __name__ == "__main__":
    master_data = build_dataset()
    print("\n--- Pipeline Complete ---")
    print(master_data.tail())

    for region in REGIONS:
        master_data[f"{region}_Grid_Stress"] = (
            (master_data["Gas_Price_EUR"] * WEIGHT_GAS)
            + (master_data["Carbon_Price"] * WEIGHT_CARBON)
            + (master_data[f"{region}_CDD"] * WEIGHT_CDD)
        )

    csv_file = "gridpilot_historical_context.csv"
    master_data.to_csv(csv_file)
    print(f"\nSaved full context to '{csv_file}'")

    master_data.index = master_data.index.strftime("%Y-%m-01")
    sybilion_timeseries = master_data["Frankfurt_Grid_Stress"].to_dict()

    output_file = "sybilion_ready_data.json"
    with open(output_file, "w") as f:
        json.dump(sybilion_timeseries, f, indent=4)

    print(f"Saved {len(sybilion_timeseries)} observations to '{output_file}'")
