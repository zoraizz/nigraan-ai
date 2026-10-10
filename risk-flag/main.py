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
# Rainfall cache -- longer TTL (3 hours) keyed by (lat, lon, window).
# Survives across response-cache misses so stale rainfall data can be reused
# when Open-Meteo is unavailable.
# ---------------------------------------------------------------------------
_RAINFALL_CACHE_TTL_SECS = 3 * 60 * 60  # 3 hours
_rainfall_cache: dict[tuple[float, float, str], tuple[float, float]] = {}
_rainfall_cache_lock = threading.Lock()


def _rainfall_cache_get(
    lat: float, lon: float, window: str, *, allow_stale: bool = False,
) -> float | None:
    """Return cached rainfall value, or None.

    *allow_stale* returns expired entries as a last-resort fallback.
    """
    key = (lat, lon, window)
    with _rainfall_cache_lock:
        entry = _rainfall_cache.get(key)
        if entry is None:
            return None
        value, ts = entry
        age = time.time() - ts
        if age <= _RAINFALL_CACHE_TTL_SECS:
            return value
        if allow_stale:
            logger.info(
                "Serving stale rainfall cache for (%s, %s, %s) — age %.0fs",
                lat, lon, window, age,
            )
            return value
        return None


def _rainfall_cache_set(lat: float, lon: float, window: str, value: float) -> None:
    key = (lat, lon, window)
    with _rainfall_cache_lock:
        _rainfall_cache[key] = (value, time.time())


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
    risk_level: str
    reason: str
    cached: bool = False
    rainfall_unavailable: bool = False
    reasoning_source: str | None = None  # "gemini" | "grok" | "fallback" | "cache"
    reasoning_error: str | None = None  # "api_error" | "bad_json" | null


# ---------------------------------------------------------------------------
# Open-Meteo helpers — resilient with retry + cache
# ---------------------------------------------------------------------------
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_REQUEST_TIMEOUT = 10  # seconds
_MAX_RETRIES = 2
_BASE_BACKOFF = 1.0  # seconds

_OPENMETEO_HEADERS = {
    "User-Agent": "NigraanAI-RiskFlag/1.0 (disaster-risk-assessment; github.com/nigraan-ai)",
}


def _is_retryable(status_code: int) -> bool:
    """Return True for status codes that warrant a retry (429 or 5xx)."""
    return status_code == 429 or 500 <= status_code < 600


def _openmeteo_request_with_retry(url: str, params: dict) -> dict | None:
    """Make a GET request to Open-Meteo with retry on 429/5xx.

    Returns the parsed JSON dict on success, or None on failure after
    exhausting retries.
    """
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = requests.get(
                url, params=params, timeout=_REQUEST_TIMEOUT,
                headers=_OPENMETEO_HEADERS,
            )

            if response.ok:
                return response.json()

            # Retryable error — back off and retry
            if _is_retryable(response.status_code):
                retry_after = response.headers.get("Retry-After")
                if retry_after is not None:
                    try:
                        wait = float(retry_after)
                    except (ValueError, TypeError):
                        wait = _BASE_BACKOFF * (2 ** attempt)
                else:
                    wait = _BASE_BACKOFF * (2 ** attempt)

                logger.warning(
                    "Open-Meteo %s returned %d (attempt %d/%d), "
                    "retrying in %.1fs",
                    url, response.status_code, attempt + 1,
                    _MAX_RETRIES + 1, wait,
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(wait)
                    continue

                # Final attempt exhausted
                logger.error(
                    "Open-Meteo %s returned %d after %d attempts — giving up",
                    url, response.status_code, _MAX_RETRIES + 1,
                )
                return None

            # Non-retryable error (e.g. 400, 404)
            logger.error(
                "Open-Meteo %s returned non-retryable %d: %s",
                url, response.status_code, response.text[:300],
            )
            return None

        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                "Open-Meteo %s request error (attempt %d/%d): %s",
                url, attempt + 1, _MAX_RETRIES + 1, exc,
            )
            if attempt < _MAX_RETRIES:
                time.sleep(_BASE_BACKOFF * (2 ** attempt))
                continue

    logger.error(
        "Open-Meteo %s failed after %d attempts: %s",
        url, _MAX_RETRIES + 1, last_exc,
    )
    return None


def get_rainfall_forecast(lat: float, lon: float, days: int = 3) -> float | None:
    """Cumulative rainfall forecast over *days* (1-16) from Open-Meteo.

    Returns None if the data cannot be fetched (after retries + stale-cache
    fallback).
    """
    window = f"forecast_{days}d"

    # Check fresh cache first
    cached = _rainfall_cache_get(lat, lon, window)
    if cached is not None:
        logger.info("Rainfall cache hit for (%s, %s, %s)", lat, lon, window)
        return cached

    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "precipitation_sum",
        "forecast_days": days,
        "timezone": "auto",
    }
    data = _openmeteo_request_with_retry(_FORECAST_URL, params)

    if data is not None:
        try:
            total = sum(data["daily"]["precipitation_sum"])
            _rainfall_cache_set(lat, lon, window, total)
            return total
        except (KeyError, TypeError) as exc:
            logger.error("Unexpected Open-Meteo forecast response: %s", exc)

    # Fallback: stale cache
    stale = _rainfall_cache_get(lat, lon, window, allow_stale=True)
    if stale is not None:
        return stale

    return None


def get_rainfall_historical(lat: float, lon: float, past_days: int) -> float | None:
    """Cumulative observed rainfall over the last *past_days* from Open-Meteo.

    Returns None if the data cannot be fetched (after retries + stale-cache
    fallback).
    """
    window = f"archive_{past_days}d"

    # Check fresh cache first
    cached = _rainfall_cache_get(lat, lon, window)
    if cached is not None:
        logger.info("Rainfall cache hit for (%s, %s, %s)", lat, lon, window)
        return cached

    params = {
        "latitude": lat,
        "longitude": lon,
        "past_days": past_days,
        "daily": "precipitation_sum",
        "timezone": "auto",
    }
    data = _openmeteo_request_with_retry(_ARCHIVE_URL, params)

    if data is not None:
        try:
            daily = data.get("daily", {}).get("precipitation_sum", [])
            total = sum(v for v in daily if v is not None)
            _rainfall_cache_set(lat, lon, window, total)
            return total
        except (KeyError, TypeError) as exc:
            logger.error("Unexpected Open-Meteo archive response: %s", exc)

    # Fallback: stale cache
    stale = _rainfall_cache_get(lat, lon, window, allow_stale=True)
    if stale is not None:
        return stale

    return None


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

    rainfall_unavailable = False

    # Rainfall: 3-day forecast for flood districts
    rainfall_3d: float | None = None
    if "flood" in hazard_types:
        rainfall_3d = get_rainfall_forecast(lat, lon, days=3)
        if rainfall_3d is None:
            rainfall_unavailable = True
            logger.warning(
                "Rainfall forecast unavailable for %s — "
                "assessing risk from NDMA context only",
                req.district,
            )

    # Rainfall: historical deficit for drought districts
    rainfall_30d: float | None = None
    rainfall_90d: float | None = None
    if "drought" in hazard_types:
        rainfall_30d = get_rainfall_historical(lat, lon, past_days=30)
        rainfall_90d = get_rainfall_historical(lat, lon, past_days=90)
        if rainfall_30d is None or rainfall_90d is None:
            rainfall_unavailable = True
            logger.warning(
                "Historical rainfall unavailable for %s — "
                "assessing risk from NDMA context only",
                req.district,
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
        )
        reasoning_source = "fallback"
        logger.info("Risk for %s: %s (source=fallback)", req.district, risk_level)

    # Annotate reason when rainfall was unavailable
    if rainfall_unavailable:
        reason = (
            "[Note: Live rainfall data was unavailable; this assessment is "
            "based on static NDMA hazard context only.] " + reason
        )

    body = RiskResponse(
        district=req.district,
        hazard_types=hazard_types,
        rainfall_forecast_mm=round(rainfall_3d, 1) if rainfall_3d is not None else None,
        rainfall_30d_mm=round(rainfall_30d, 1) if rainfall_30d is not None else None,
        rainfall_90d_mm=round(rainfall_90d, 1) if rainfall_90d is not None else None,
        risk_level=risk_level,
        reason=reason,
        rainfall_unavailable=rainfall_unavailable,
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
