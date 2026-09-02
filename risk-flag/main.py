from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests

# Load .env from the risk-flag directory (before other imports that read env vars)
load_dotenv(Path(__file__).parent / ".env")

from risk_reasoning import assess_risk_with_gemini  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("risk_flag")

app = FastAPI()

# CORS -- allow the dashboard frontend (Vite dev server,
# http://localhost:5173) to call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# District configuration
# Coordinates resolved via Open-Meteo Geocoding API
# (https://geocoding-api.open-meteo.com/v1/search?name=<district>&country=Pakistan)
# ---------------------------------------------------------------------------
DISTRICTS: dict[str, dict] = {
    # ── Flood (Sindh) ──────────────────────────────────────────────────────
    "Dadu": {
        "coords": (26.73033, 67.7769),
        "province": "Sindh",
        "hazard_types": ["flood"],
    },
    "Khairpur": {
        "coords": (27.52948, 68.75915),
        "province": "Sindh",
        "hazard_types": ["flood"],
    },
    "Sukkur": {
        "coords": (27.70323, 68.85889),
        "province": "Sindh",
        "hazard_types": ["flood"],
    },
    "Larkana": {
        "coords": (27.55898, 68.21204),
        "province": "Sindh",
        "hazard_types": ["flood"],
    },
    "Jacobabad": {
        "coords": (28.28187, 68.43761),
        "province": "Sindh",
        "hazard_types": ["flood"],
    },
    # ── Flood / hill-torrent (Balochistan & Punjab) ────────────────────────
    "Jaffarabad": {
        "coords": (28.37473, 68.35032),  # resolved via Dera Allah Yar (district HQ)
        "province": "Balochistan",
        "hazard_types": ["flood"],
    },
    "D.I. Khan": {
        "coords": (31.83129, 70.9017),
        "province": "Khyber Pakhtunkhwa",
        "hazard_types": ["flood"],
    },
    "D.G. Khan": {
        "coords": (30.04587, 70.64029),
        "province": "Punjab",
        "hazard_types": ["flood"],
    },
    "Rajanpur": {
        "coords": (29.10408, 70.32969),
        "province": "Punjab",
        "hazard_types": ["flood"],
    },
    # ── GLOF / Avalanche (Gilgit-Baltistan & KP north) ─────────────────────
    "Chitral": {
        "coords": (35.8518, 71.78636),
        "province": "Khyber Pakhtunkhwa",
        "hazard_types": ["glof", "avalanche"],
    },
    "Hunza": {
        "coords": (36.32692, 74.66141),  # resolved via Karimabad
        "province": "Gilgit-Baltistan",
        "hazard_types": ["glof", "avalanche"],
    },
    "Skardu": {
        "coords": (35.29787, 75.63372),
        "province": "Gilgit-Baltistan",
        "hazard_types": ["glof", "avalanche"],
    },
    # ── Landslide (KP north) ───────────────────────────────────────────────
    "Mansehra": {
        "coords": (34.33023, 73.19679),
        "province": "Khyber Pakhtunkhwa",
        "hazard_types": ["landslide"],
    },
    "Battagram": {
        "coords": (34.67719, 73.02329),
        "province": "Khyber Pakhtunkhwa",
        "hazard_types": ["landslide"],
    },
    # ── Drought (Balochistan & Sindh) ──────────────────────────────────────
    "Chagai": {
        "coords": (29.35393, 64.69751),
        "province": "Balochistan",
        "hazard_types": ["drought"],
    },
    "Tharparkar": {
        "coords": (24.73701, 69.79707),  # resolved via Mithi (district HQ)
        "province": "Sindh",
        "hazard_types": ["drought"],
    },
}

# ---------------------------------------------------------------------------
# Static NDMA-sourced hazard context
# Reference data for LLM risk reasoning.
# Sources: NDMA Disaster Early Warning reports, NDMA GLOF/Avalanche
#          Guidelines 2026, NDMA SITREP archives.
# ---------------------------------------------------------------------------
HAZARD_CONTEXT: dict[str, dict] = {
    "flood": {
        "description": (
            "Monsoon and hill-torrent flooding in low-lying districts of "
            "Sindh, southern Punjab, and Balochistan plains."
        ),
        "high_risk_districts": [
            "Dadu", "Khairpur", "Sukkur", "Larkana", "Jacobabad",
            "Jaffarabad", "D.I. Khan", "D.G. Khan", "Rajanpur",
        ],
        "source": "NDMA Monsoon Contingency Plan; NDMA SITREP reports",
    },
    "glof": {
        "description": (
            "Glacial Lake Outburst Floods from the Hindukush-Karakoram-"
            "Himalaya glacier belt. Seasonal risk peaks May-August when "
            "temperatures drive rapid glacial melt."
        ),
        "high_risk_districts": ["Chitral", "Hunza", "Skardu"],
        "source": "NDMA GLOF/Avalanche Guidelines 2026",
    },
    "avalanche": {
        "description": (
            "Snow avalanches in high-altitude districts of Gilgit-Baltistan "
            "and upper KP, primarily December-April."
        ),
        "high_risk_districts": ["Chitral", "Hunza", "Skardu"],
        "source": "NDMA GLOF/Avalanche Guidelines 2026",
    },
    "landslide": {
        "description": (
            "Rainfall-triggered landslides in mountainous KP districts, "
            "especially February-April when spring rains saturate steep slopes."
        ),
        "high_risk_districts": ["Mansehra", "Battagram"],
        "source": "NDMA Disaster Early Warning reports",
    },
    "drought": {
        "description": (
            "Chronic water deficit in arid districts of Balochistan and "
            "Sindh's Thar desert. Groundwater reliance with low infrastructure "
            "storage capacity amplifies vulnerability."
        ),
        "high_risk_districts": ["Chagai", "Tharparkar"],
        "source": "NDMA drought assessments; PDMA Balochistan/Sindh reports",
    },
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class RiskRequest(BaseModel):
    district: str


class RiskResponse(BaseModel):
    district: str
    hazard_types: list[str]
    rainfall_forecast_mm: float | None
    rainfall_30d_mm: float | None
    rainfall_90d_mm: float | None
    risk_level: str
    reason: str


# ---------------------------------------------------------------------------
# Open-Meteo helpers
# ---------------------------------------------------------------------------
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def get_rainfall_forecast(lat: float, lon: float, days: int = 3) -> float:
    """Cumulative rainfall forecast over *days* (1-16) from Open-Meteo."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "precipitation_sum",
        "forecast_days": days,
        "timezone": "auto",
    }
    response = requests.get(_FORECAST_URL, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    return sum(data["daily"]["precipitation_sum"])


def get_rainfall_historical(lat: float, lon: float, past_days: int) -> float:
    """Cumulative observed rainfall over the last *past_days* from Open-Meteo
    historical weather API."""
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "past_days": past_days,
        "daily": "precipitation_sum",
        "timezone": "auto",
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    daily = data.get("daily", {}).get("precipitation_sum", [])
    return sum(v for v in daily if v is not None)


# ---------------------------------------------------------------------------
# Risk scoring — rule-based fallback (used when Gemini is unavailable)
# ---------------------------------------------------------------------------
def score_risk_fallback(
    district: str,
    hazard_types: list[str],
    rainfall_3d: float | None,
    rainfall_30d: float | None,
    rainfall_90d: float | None,
) -> tuple[str, str]:
    """Rule-based risk scoring — used as fallback when LLM is unavailable.

    Flood districts use 3-day rainfall thresholds; static-risk districts
    (GLOF/avalanche/landslide) default to medium; drought districts report
    rainfall deficit context.
    """
    parts: list[str] = []

    if "flood" in hazard_types and rainfall_3d is not None:
        if rainfall_3d > 100:
            parts.append(
                f"{district} is forecast {rainfall_3d:.0f} mm over 3 days "
                f"— high flood/roof-collapse risk."
            )
        elif rainfall_3d > 40:
            parts.append(
                f"{district} is forecast {rainfall_3d:.0f} mm over 3 days "
                f"— moderate flood risk."
            )
        else:
            parts.append(
                f"{district} is forecast {rainfall_3d:.0f} mm over 3 days "
                f"— low flood risk."
            )

    for ht in ("glof", "avalanche", "landslide"):
        if ht in hazard_types:
            ctx = HAZARD_CONTEXT.get(ht, {})
            parts.append(
                f"{district} is flagged for {ht.upper()} vulnerability "
                f"({ctx.get('source', 'NDMA reference')})."
            )

    if "drought" in hazard_types:
        deficit_info = ""
        if rainfall_30d is not None:
            deficit_info += f" 30-day rainfall: {rainfall_30d:.1f} mm."
        if rainfall_90d is not None:
            deficit_info += f" 90-day rainfall: {rainfall_90d:.1f} mm."
        parts.append(
            f"{district} is in a drought-prone zone "
            f"(NDMA-flagged).{deficit_info}"
        )

    reason = " ".join(parts) if parts else f"{district}: no specific hazard data."

    if "flood" in hazard_types and rainfall_3d is not None and rainfall_3d > 100:
        level = "high"
    elif "flood" in hazard_types and rainfall_3d is not None and rainfall_3d > 40:
        level = "medium"
    elif any(ht in hazard_types for ht in ("glof", "avalanche", "landslide")):
        level = "medium"
    else:
        level = "low"

    return level, reason


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.post("/predict-risk", response_model=RiskResponse)
def predict_risk(req: RiskRequest):
    if req.district not in DISTRICTS:
        return RiskResponse(
            district=req.district,
            hazard_types=[],
            rainfall_forecast_mm=None,
            rainfall_30d_mm=None,
            rainfall_90d_mm=None,
            risk_level="unknown",
            reason=f"District '{req.district}' not in coverage list. "
                   f"Available: {', '.join(sorted(DISTRICTS.keys()))}",
        )

    info = DISTRICTS[req.district]
    lat, lon = info["coords"]
    hazard_types = info["hazard_types"]
    province = info["province"]

    # Rainfall: 3-day forecast for flood districts
    rainfall_3d: float | None = None
    if "flood" in hazard_types:
        rainfall_3d = get_rainfall_forecast(lat, lon, days=3)

    # Rainfall: historical deficit for drought districts
    rainfall_30d: float | None = None
    rainfall_90d: float | None = None
    if "drought" in hazard_types:
        rainfall_30d = get_rainfall_historical(lat, lon, past_days=30)
        rainfall_90d = get_rainfall_historical(lat, lon, past_days=90)

    # ── Risk reasoning: try Gemini first, fall back to rules ───────────
    result = assess_risk_with_gemini(
        district=req.district,
        hazard_types=hazard_types,
        hazard_context=HAZARD_CONTEXT,
        province=province,
        rainfall_3d=rainfall_3d,
        rainfall_30d=rainfall_30d,
        rainfall_90d=rainfall_90d,
    )

    if result is not None:
        risk_level = result.risk_level
        reason = result.rationale
        logger.info(
            "Risk for %s: %s (source=%s, tokens=%s/%s)",
            req.district, risk_level, result.source,
            result.prompt_tokens, result.completion_tokens,
        )
    else:
        risk_level, reason = score_risk_fallback(
            req.district, hazard_types, rainfall_3d, rainfall_30d, rainfall_90d,
        )
        logger.info("Risk for %s: %s (source=fallback)", req.district, risk_level)

    return RiskResponse(
        district=req.district,
        hazard_types=hazard_types,
        rainfall_forecast_mm=round(rainfall_3d, 1) if rainfall_3d is not None else None,
        rainfall_30d_mm=round(rainfall_30d, 1) if rainfall_30d is not None else None,
        rainfall_90d_mm=round(rainfall_90d, 1) if rainfall_90d is not None else None,
        risk_level=risk_level,
        reason=reason,
    )


@app.get("/")
def health_check():
    return {
        "status": "ok",
        "districts_available": sorted(DISTRICTS.keys()),
    }
