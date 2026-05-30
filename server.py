from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import os
import asyncio
from typing import Dict, List
from main import GridPilotForecaster
import math_model
import database

app = FastAPI()
app.is_forecasting = False

# Initialize DB on startup
@app.on_event("startup")
async def startup_event():
    database.init_db()

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class PredictRequest(BaseModel):
    weights: Dict[str, float]

class NodeCreate(BaseModel):
    id: str
    name: str
    lat: float
    lng: float
    carbon: float
    capacity: float
    security: float
    cost: float

@app.get("/")
def read_root():
    return {"status": "GridPilot API Active", "is_forecasting": app.is_forecasting}

@app.get("/nodes")
def get_nodes():
    return database.get_nodes()

@app.post("/nodes")
def create_node(node: NodeCreate):
    success = database.add_node(node.dict())
    if not success:
        raise HTTPException(status_code=400, detail="Node ID already exists or invalid data")
    return {"status": "Node added successfully"}

def run_actual_forecasts():
    """Reads JSON files and sends to Sybilion."""
    forecaster = GridPilotForecaster()
    regions = ["Frankfurt", "Madrid", "Helsinki"]
    metrics = ["power_price", "carbon_intensity", "grid_stress"]
    
    metric_map = {
        "power_price": "cost",
        "carbon_intensity": "eco",
        "grid_stress": "sicherheit"
    }
    
    all_results = {}
    for region in regions:
        all_results[region] = {}
        for m in metrics:
            filename = f"data_{region.lower()}_{m}.json"
            if os.path.exists(filename):
                with open(filename, "r") as f:
                    ts_data = json.load(f)
                
                res = forecaster.run_forecast(ts_data, metric_map[m], region)
                if res:
                    all_results[region][metric_map[m]] = res
    
    with open("sybilion_forecast_results.json", "w") as f:
        json.dump(all_results, f, indent=4)
    return all_results

def run_actual_forecasts_wrapper():
    """Wrapper to run forecasts and manage the lock flag."""
    app.is_forecasting = True
    try:
        print("\n[BACKGROUND] Starting real Sybilion API run...")
        run_actual_forecasts()
        print("[BACKGROUND] Forecasting completed and saved.")
    except Exception as e:
        print(f"[BACKGROUND] Error during forecasting: {e}")
    finally:
        app.is_forecasting = False

@app.post("/predict")
async def predict(req: PredictRequest, background_tasks: BackgroundTasks):
    token = os.environ.get("SYBILION_API_TOKEN")
    results_path = "sybilion_forecast_results.json"
    
    if token and not os.path.exists(results_path) and not app.is_forecasting:
        background_tasks.add_task(run_actual_forecasts_wrapper)
    
    # Very short sleep to allow the event loop to breathe
    await asyncio.sleep(0.05)

    result = math_model.run_optimization_with_weights(req.weights)
    result["is_live_data"] = os.path.exists(results_path)
    result["is_calculating"] = app.is_forecasting
    
    return result

@app.post("/forecast")
async def trigger_forecast(background_tasks: BackgroundTasks):
    """Manually trigger a full Sybilion refresh."""
    if os.environ.get("SYBILION_API_TOKEN") and not app.is_forecasting:
        background_tasks.add_task(run_actual_forecasts_wrapper)
        return {"status": "Forecasting started in background"}
    else:
        return {"status": "Ignored", "reason": "Already forecasting or token missing"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
