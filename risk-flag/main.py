from fastapi import FastAPI
from pydantic import BaseModel
import requests

app = FastAPI()

# Rough district → coordinates lookup (expand this as you add more districts)
DISTRICT_COORDS = {
    "Dadu": (26.7300, 67.7758),
    "Khairpur": (27.5295, 68.7595),
    "Jaffarabad": (28.2833, 68.4500),
}

class RiskRequest(BaseModel):
    district: str

class RiskResponse(BaseModel):
    district: str
    rainfall_forecast_mm: float
    risk_level: str
    reason: str

def get_rainfall_forecast(lat: float, lon: float) -> float:
    """Pull next-3-day total rainfall forecast from Open-Meteo."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "precipitation_sum",
        "forecast_days": 3,
        "timezone": "auto",
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    return sum(data["daily"]["precipitation_sum"])

def score_risk(district: str, rainfall_mm: float) -> tuple[str, str]:
    """Placeholder risk logic — swap this for the LLM call once that's wired up."""
    if rainfall_mm > 100:
        return "high", f"{district} is forecast {rainfall_mm:.0f}mm of rain over 3 days — high flood/roof-collapse risk."
    elif rainfall_mm > 40:
        return "medium", f"{district} is forecast {rainfall_mm:.0f}mm of rain over 3 days — moderate risk."
    else:
        return "low", f"{district} is forecast {rainfall_mm:.0f}mm of rain over 3 days — low risk."

@app.post("/predict-risk", response_model=RiskResponse)
def predict_risk(req: RiskRequest):
    if req.district not in DISTRICT_COORDS:
        return {"district": req.district, "rainfall_forecast_mm": 0, "risk_level": "unknown", "reason": "District not in coordinate lookup yet."}

    lat, lon = DISTRICT_COORDS[req.district]
    rainfall_mm = get_rainfall_forecast(lat, lon)
    risk_level, reason = score_risk(req.district, rainfall_mm)

    return {
        "district": req.district,
        "rainfall_forecast_mm": round(rainfall_mm, 1),
        "risk_level": risk_level,
        "reason": reason,
    }

@app.get("/")
def health_check():
    return {"status": "ok"}