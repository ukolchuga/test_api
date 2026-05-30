import subprocess
import os
import sys

def run_step(name, command):
    print(f"\n{'='*20}")
    print(f"STEP: {name}")
    print(f"{'='*20}")
    try:
        subprocess.run(command, check=True, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"Error in {name}: {e}")
        sys.exit(1)

def main():
    # Step 1: Ingestion
    run_step("Data Ingestion", "python ingestion.py")
    
    # Step 2: Forecasting (Sybilion API)
    # Note: This requires SYBILION_API_TOKEN in .env
    if os.environ.get("SYBILION_API_TOKEN") or os.path.exists(".env"):
        print("\nNote: Sybilion API Token detected. Running live forecasts...")
        run_step("Sybilion Forecasting", "python main.py")
    else:
        print("\nWARNING: SYBILION_API_TOKEN not found. Skipping live forecasts.")
        print("Math model will use fallbacks.")

    # Step 3: Optimization
    run_step("Math Model Optimization", "python math_model.py")

    print("\n" + "="*40)
    print("PIPELINE COMPLETE")
    print("Open index.html in a browser to view the results.")
    print("="*40)

if __name__ == "__main__":
    main()
