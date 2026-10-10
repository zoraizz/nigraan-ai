from __future__ import annotations

import logging
import os
import time
import threading
import traceback
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Load .env from the risk-flag directory (before other imports that read env vars)
load_dotenv(Path(__file__).parent / ".env")

from risk_reasoning import assess_risk_with_gemini  # noqa: E402
from weather_bundle import (  # noqa: E402
    WeatherMetrics,
    assemble_weather,
    availability_flags,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("risk_flag")


# ---------------------------------------------------------------------------
# Response cache -- demo-pace mitigation for the ~3 min Gemini latency.
# Keyed by district; fresh entries (< 15 min old) are served with cached=True.
# Unknown-district responses are not cached (deterministic error message).
# ---------------------------------------------------------------------------
_CACHE_TTL_SECS = 15 * 60
_cache: dict[str, tuple["RiskResponse", float]] = {}
_cache_lock = threading.Lock()


def _cache_get(district: str) -> "RiskResponse | None":
    with _cache_lock:
        entry = _cache.get(district)
        if entry is None:
            return None
        body, ts = entry
        if time.time() - ts > _CACHE_TTL_SECS:
            del _cache[district]
            return None
        return body.model_copy(update={"cached": True, "reasoning_source": "cache"})


def _cache_set(district: str, body: "RiskResponse") -> None:
    with _cache_lock:
        _cache[district] = (body, time.time())


# ---------------------------------------------------------------------------
# FastAPI app + global exception handler
# ---------------------------------------------------------------------------
app = FastAPI()


@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler — returns a JSON body so the dashboard can display
    a real error message instead of a browser-level 'Failed to fetch'."""
    logger.error(
        "Unhandled exception on %s %s: %s\n%s",
        request.method, request.url.path,
        exc, traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"Internal server error: {exc}",
        },
    )


# CORS -- allow the dashboard frontend to call this API from the browser.
# Origins come from CORS_ORIGINS (comma-separated) so the deployed dashboard
# (Render; see README "Live Deployment") can be allow-listed without code
# changes. Default: the local Vite dev server.
# NOTE: CORS middleware is added *after* the exception handler so that
# FastAPI's middleware stack wraps the handler — 500 responses get CORS headers.
_allowed_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
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
    weather_metrics: WeatherMetrics | None = None
    risk_level: str
    reason: str
    cached: bool = False
    rainfall_unavailable: bool = False
    weather_unavailable: bool = False
    reasoning_source: str | None = None  # "gemini" | "grok" | "fallback" | "cache"
    reasoning_error: str | None = None  # "api_error" | "bad_json" | null


_WEATHER_NOTE = (
    "[Note: Live weather data was unavailable; this assessment is "
    "based on static NDMA hazard context only.] "
)
_RAIN_NOTE = (
    "[Note: Live rainfall data was unavailable; this assessment is "
    "based on static NDMA hazard context only.] "
)


# Weather fetch, retry, and the 3-hour bundle cache live in weather_bundle.py.


# ---------------------------------------------------------------------------
# Risk scoring — rule-based fallback (used when Gemini is unavailable)
# ---------------------------------------------------------------------------
def _metric_value(weather_metrics, name: str) -> float | None:
    if weather_metrics is None:
        return None
    if isinstance(weather_metrics, dict):
        value = weather_metrics.get(name)
    else:
        value = getattr(weather_metrics, name, None)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _raise_level(level: str, new: str) -> str:
    rank = {"low": 0, "medium": 1, "high": 2}
    if rank.get(new, 0) > rank.get(level, 0):
        return new
    return level


def score_risk_fallback(
    district: str,
    hazard_types: list[str],
    rainfall_3d: float | None,
    rainfall_30d: float | None,
    rainfall_90d: float | None,
    weather_metrics=None,
) -> tuple[str, str]:
    """Rule-based risk scoring — used as fallback when LLM is unavailable.

    Flood level still follows 3-day rainfall. Discharge is mentioned and is
    not a level threshold (GloFAS is not a gauge). Drought can rise on
    extreme heat with a short rainfall total. Northern hazards can rise on
    heavy snow or a warm spell over a deep snowpack. Landslide can rise on
    heavy rain or rain on wet soil. The LLM remains the primary scorer.
    """
    temp_max = _metric_value(weather_metrics, "temperature_max_c_3d")
    humidity = _metric_value(weather_metrics, "humidity_mean_pct_3d")
    soil = _metric_value(weather_metrics, "soil_moisture_0_1cm_m3m3")
    snowfall = _metric_value(weather_metrics, "snowfall_cm_3d")
    snow_depth = _metric_value(weather_metrics, "snow_depth_cm")
    discharge = _metric_value(weather_metrics, "river_discharge_max_m3s_3d")

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
        if discharge is not None:
            parts.append(
                f"Nearest GloFAS river cell peaks at {discharge:.0f} m³/s (modelled)."
            )

    northern = [ht for ht in ("glof", "avalanche") if ht in hazard_types]
    if northern:
        ctx = HAZARD_CONTEXT.get(northern[0], {})
        detail: list[str] = []
        if temp_max is not None:
            detail.append(f"max temperature {temp_max:.0f} °C")
        if snowfall is not None:
            detail.append(f"snowfall {snowfall:.0f} cm over 3 days")
        if snow_depth is not None:
            detail.append(f"snow depth {snow_depth:.0f} cm")
        suffix = f"; {', '.join(detail)}" if detail else ""
        label = "/".join(ht.upper() for ht in northern)
        parts.append(
            f"{district} is flagged for {label} vulnerability "
            f"({ctx.get('source', 'NDMA reference')}){suffix}."
        )

    if "landslide" in hazard_types:
        ctx = HAZARD_CONTEXT.get("landslide", {})
        detail = []
        if rainfall_3d is not None:
            detail.append(f"rainfall {rainfall_3d:.0f} mm over 3 days")
        if soil is not None:
            detail.append(f"soil moisture {soil:.2f} m³/m³")
        suffix = f"; {', '.join(detail)}" if detail else ""
        parts.append(
            f"{district} is flagged for LANDSLIDE vulnerability "
            f"({ctx.get('source', 'NDMA reference')}){suffix}."
        )

    if "drought" in hazard_types:
        deficit_info = ""
        if rainfall_30d is not None:
            deficit_info += f" 30-day rainfall: {rainfall_30d:.1f} mm."
        if rainfall_90d is not None:
            deficit_info += f" 90-day rainfall: {rainfall_90d:.1f} mm."
        if temp_max is not None:
            deficit_info += f" 3-day max temperature: {temp_max:.0f} °C."
        if humidity is not None:
            deficit_info += f" Mean humidity: {humidity:.0f}%."
        if soil is not None:
            deficit_info += f" Soil moisture (0-1 cm): {soil:.2f} m³/m³."
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

    if "drought" in hazard_types and temp_max is not None:
        if rainfall_30d is not None and rainfall_30d < 10 and temp_max >= 45:
            level = _raise_level(level, "high")
        elif temp_max >= 40 and (rainfall_30d is None or rainfall_30d < 15):
            level = _raise_level(level, "medium")

    if northern:
        heavy_snow = snowfall is not None and snowfall >= 30
        warm_on_snow = (
            temp_max is not None
            and temp_max >= 25
            and snow_depth is not None
            and snow_depth >= 40
        )
        if heavy_snow or warm_on_snow:
            level = _raise_level(level, "high")

    if "landslide" in hazard_types and rainfall_3d is not None:
        saturated = soil is not None and soil >= 0.4 and rainfall_3d > 40
        if rainfall_3d > 80 or saturated:
            level = _raise_level(level, "high")

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
            weather_metrics=None,
            weather_unavailable=False,
            risk_level="unknown",
            reason=f"District '{req.district}' not in coverage list. "
                   f"Available: {', '.join(sorted(DISTRICTS.keys()))}",
        )

    # ── Cache check: serve a fresh copy if < TTL old ───────────────
    cached = _cache_get(req.district)
    if cached is not None:
        logger.info(
            "Risk for %s: %s (source=cache)", req.district, cached.risk_level,
        )
        return cached

    info = DISTRICTS[req.district]
    lat, lon = info["coords"]
    hazard_types = info["hazard_types"]
    province = info["province"]

    metrics = assemble_weather(lat, lon, hazard_types)
    rainfall_3d = metrics.rainfall_forecast_mm
    rainfall_30d = metrics.rainfall_30d_mm
    rainfall_90d = metrics.rainfall_90d_mm
    rainfall_unavailable, weather_unavailable = availability_flags(
        hazard_types, metrics,
    )
    if weather_unavailable or rainfall_unavailable:
        logger.warning(
            "Weather bundle incomplete for %s (weather_unavailable=%s, "
            "rainfall_unavailable=%s) — assessment may use NDMA context only",
            req.district, weather_unavailable, rainfall_unavailable,
        )

    # ── Risk reasoning: Gemini, then Grok if configured, then rules ──
    result = assess_risk_with_gemini(
        district=req.district,
        hazard_types=hazard_types,
        hazard_context=HAZARD_CONTEXT,
        province=province,
        rainfall_3d=rainfall_3d,
        rainfall_30d=rainfall_30d,
        rainfall_90d=rainfall_90d,
        weather_metrics=metrics.model_dump(),
    )

    reasoning_error: str | None = None
    if result is not None and result.error is None:
        risk_level = result.risk_level
        reason = result.rationale
        reasoning_source = result.source
        logger.info(
            "Risk for %s: %s (source=%s, tokens=%s/%s)",
            req.district, risk_level, result.source,
            result.prompt_tokens, result.completion_tokens,
        )
    else:
        if result is not None:
            reasoning_error = result.error
        risk_level, reason = score_risk_fallback(
            req.district, hazard_types, rainfall_3d, rainfall_30d, rainfall_90d,
            weather_metrics=metrics,
        )
        reasoning_source = "fallback"
        logger.info("Risk for %s: %s (source=fallback)", req.district, risk_level)

    if weather_unavailable:
        reason = _WEATHER_NOTE + reason
    elif rainfall_unavailable:
        reason = _RAIN_NOTE + reason

    body = RiskResponse(
        district=req.district,
        hazard_types=hazard_types,
        rainfall_forecast_mm=rainfall_3d,
        rainfall_30d_mm=rainfall_30d,
        rainfall_90d_mm=rainfall_90d,
        weather_metrics=metrics,
        risk_level=risk_level,
        reason=reason,
        rainfall_unavailable=rainfall_unavailable,
        weather_unavailable=weather_unavailable,
        reasoning_source=reasoning_source,
        reasoning_error=reasoning_error,
    )
    _cache_set(req.district, body)
    return body


@app.get("/")
def health_check():
    return {
        "status": "ok",
        "districts_available": sorted(DISTRICTS.keys()),
    }
