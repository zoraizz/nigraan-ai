"""
Open-Meteo weather bundle for /predict-risk.

One forecast request carries the 3-day metrics (including snow). Drought
districts add a single 90-day archive call; 30-day rainfall is the last 30
days of that series. Flood districts add one GloFAS river-discharge call.
No API key. Raw hourly arrays stay on the server and are reduced to scalars.
"""

from __future__ import annotations

import logging
import time
import threading

import requests
from pydantic import BaseModel

logger = logging.getLogger("risk_flag.weather")

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_FLOOD_URL = "https://flood-api.open-meteo.com/v1/flood"

_REQUEST_TIMEOUT = 10  # seconds
_MAX_RETRIES = 2
_BASE_BACKOFF = 1.0  # seconds

_OPENMETEO_HEADERS = {
    "User-Agent": "NigraanAI-RiskFlag/1.0 (disaster-risk-assessment; github.com/nigraan-ai)",
}

# Daily humidity is not a documented forecast aggregation. Humidity, soil
# moisture, and snow depth are requested hourly and reduced here.
_FORECAST_DAILY = ",".join((
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "snowfall_sum",
))
_FORECAST_HOURLY = ",".join((
    "relative_humidity_2m",
    "soil_moisture_0_to_1cm",
    "snow_depth",
))

FORECAST_WINDOW = "forecast_bundle_3d"
ARCHIVE_WINDOW = "archive_90d"
DISCHARGE_WINDOW = "discharge_3d"

WEATHER_CACHE_TTL_SECS = 3 * 60 * 60  # 3 hours

_cache: dict[tuple, tuple[dict, float]] = {}
_cache_lock = threading.Lock()


class WeatherMetrics(BaseModel):
    """Compact scalars. Legacy rainfall fields are repeated at the top level."""

    rainfall_forecast_mm: float | None = None
    rainfall_30d_mm: float | None = None
    rainfall_90d_mm: float | None = None
    temperature_max_c_3d: float | None = None
    temperature_min_c_3d: float | None = None
    precip_probability_max_pct_3d: float | None = None
    wind_speed_max_kmh_3d: float | None = None
    wind_gust_max_kmh_3d: float | None = None
    humidity_mean_pct_3d: float | None = None
    soil_moisture_0_1cm_m3m3: float | None = None
    snowfall_cm_3d: float | None = None
    snow_depth_cm: float | None = None
    river_discharge_max_m3s_3d: float | None = None


def clear_weather_cache() -> None:
    with _cache_lock:
        _cache.clear()


def cache_put(
    lat: float,
    lon: float,
    window: str,
    payload: dict,
    *,
    written_at: float | None = None,
) -> None:
    """Store a summary dict. ``written_at`` lets tests insert a stale entry."""
    stamp = time.time() if written_at is None else written_at
    with _cache_lock:
        _cache[(lat, lon, window)] = (dict(payload), stamp)


def _cache_get(lat: float, lon: float, window: str, *, allow_stale: bool = False) -> dict | None:
    key = (lat, lon, window)
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        payload, stamp = entry
        age = time.time() - stamp
        if age <= WEATHER_CACHE_TTL_SECS:
            return dict(payload)
        if allow_stale:
            logger.info(
                "Serving stale weather cache for (%s, %s, %s) — age %.0fs",
                lat, lon, window, age,
            )
            return dict(payload)
        return None


def _is_retryable(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code < 600


def _openmeteo_request_with_retry(url: str, params: dict) -> dict | None:
    """GET Open-Meteo. Returns parsed JSON, or None after retries are exhausted."""
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = requests.get(
                url, params=params, timeout=_REQUEST_TIMEOUT,
                headers=_OPENMETEO_HEADERS,
            )

            if response.ok:
                body = response.json()
                return body if isinstance(body, dict) else None

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
                    "Open-Meteo %s returned %d (attempt %d/%d), retrying in %.1fs",
                    url, response.status_code, attempt + 1, _MAX_RETRIES + 1, wait,
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(wait)
                    continue

                logger.error(
                    "Open-Meteo %s returned %d after %d attempts — giving up",
                    url, response.status_code, _MAX_RETRIES + 1,
                )
                return None

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


def _finite_numbers(values) -> list[float]:
    if not isinstance(values, list):
        return []
    numbers: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        number = float(value)
        if number != number:  # NaN
            continue
        numbers.append(number)
    return numbers


def _sum(values) -> float | None:
    numbers = _finite_numbers(values)
    if not numbers:
        return None
    return sum(numbers)


def _max(values) -> float | None:
    numbers = _finite_numbers(values)
    if not numbers:
        return None
    return max(numbers)


def _min(values) -> float | None:
    numbers = _finite_numbers(values)
    if not numbers:
        return None
    return min(numbers)


def _mean(values) -> float | None:
    numbers = _finite_numbers(values)
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _last(values) -> float | None:
    numbers = _finite_numbers(values)
    if not numbers:
        return None
    return numbers[-1]


def _put(target: dict, key: str, value: float | None, digits: int) -> None:
    if value is None:
        return
    target[key] = round(float(value), digits)


def summarize_forecast(data: dict | None) -> dict:
    """Reduce one forecast payload to scalar metrics. Empty dict = nothing usable."""
    if not isinstance(data, dict):
        return {}
    daily = data.get("daily") if isinstance(data.get("daily"), dict) else {}
    hourly = data.get("hourly") if isinstance(data.get("hourly"), dict) else {}
    summary: dict[str, float] = {}
    _put(summary, "rainfall_forecast_mm", _sum(daily.get("precipitation_sum")), 1)
    _put(summary, "temperature_max_c_3d", _max(daily.get("temperature_2m_max")), 1)
    _put(summary, "temperature_min_c_3d", _min(daily.get("temperature_2m_min")), 1)
    _put(summary, "precip_probability_max_pct_3d", _max(daily.get("precipitation_probability_max")), 1)
    _put(summary, "wind_speed_max_kmh_3d", _max(daily.get("wind_speed_10m_max")), 1)
    _put(summary, "wind_gust_max_kmh_3d", _max(daily.get("wind_gusts_10m_max")), 1)
    _put(summary, "snowfall_cm_3d", _sum(daily.get("snowfall_sum")), 1)
    _put(summary, "humidity_mean_pct_3d", _mean(hourly.get("relative_humidity_2m")), 1)
    _put(summary, "soil_moisture_0_1cm_m3m3", _mean(hourly.get("soil_moisture_0_to_1cm")), 3)
    depth_m = _last(hourly.get("snow_depth"))
    _put(summary, "snow_depth_cm", None if depth_m is None else depth_m * 100.0, 1)
    return summary


def summarize_archive(data: dict | None) -> dict:
    """90-day precipitation series → 30-day (last 30) and 90-day totals."""
    if not isinstance(data, dict):
        return {}
    daily = data.get("daily") if isinstance(data.get("daily"), dict) else {}
    values = daily.get("precipitation_sum")
    if not isinstance(values, list) or not values:
        return {}
    window = values[-90:]
    summary: dict[str, float] = {}
    _put(summary, "rainfall_90d_mm", _sum(window), 1)
    _put(summary, "rainfall_30d_mm", _sum(window[-30:]), 1)
    return summary


def summarize_discharge(data: dict | None) -> dict:
    """Max river discharge over the returned days. Empty when the cell has no value."""
    if not isinstance(data, dict):
        return {}
    daily = data.get("daily") if isinstance(data.get("daily"), dict) else {}
    summary: dict[str, float] = {}
    _put(summary, "river_discharge_max_m3s_3d", _max(daily.get("river_discharge")), 1)
    return summary


def _cached_or_fetch(lat: float, lon: float, window: str, url: str, params: dict, summarize) -> dict | None:
    cached = _cache_get(lat, lon, window)
    if cached is not None:
        logger.info("Weather cache hit for (%s, %s, %s)", lat, lon, window)
        return cached

    data = _openmeteo_request_with_retry(url, params)
    if data is not None:
        summary = summarize(data)
        if summary:
            cache_put(lat, lon, window, summary)
            return summary

    return _cache_get(lat, lon, window, allow_stale=True)


def fetch_forecast_bundle(lat: float, lon: float) -> dict | None:
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": _FORECAST_DAILY,
        "hourly": _FORECAST_HOURLY,
        "forecast_days": 3,
        "timezone": "auto",
    }
    return _cached_or_fetch(
        lat, lon, FORECAST_WINDOW, _FORECAST_URL, params, summarize_forecast,
    )


def fetch_historical_rainfall(lat: float, lon: float) -> dict | None:
    params = {
        "latitude": lat,
        "longitude": lon,
        "past_days": 90,
        "daily": "precipitation_sum",
        "timezone": "auto",
    }
    return _cached_or_fetch(
        lat, lon, ARCHIVE_WINDOW, _ARCHIVE_URL, params, summarize_archive,
    )


def fetch_river_discharge(lat: float, lon: float) -> dict | None:
    """Nearest GloFAS river cell (~5 km). None means no usable value, not zero flow."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "river_discharge",
        "forecast_days": 3,
    }
    return _cached_or_fetch(
        lat, lon, DISCHARGE_WINDOW, _FLOOD_URL, params, summarize_discharge,
    )


def assemble_weather(lat: float, lon: float, hazard_types: list[str]) -> WeatherMetrics:
    """Fetch the hazard-aware bundle. At most three Open-Meteo calls before retries."""
    merged: dict = {}
    forecast = fetch_forecast_bundle(lat, lon)
    if forecast:
        merged.update(forecast)
    if "drought" in hazard_types:
        historical = fetch_historical_rainfall(lat, lon)
        if historical:
            merged.update(historical)
    if "flood" in hazard_types:
        discharge = fetch_river_discharge(lat, lon)
        if discharge:
            merged.update(discharge)
    return WeatherMetrics(**merged)


def availability_flags(
    hazard_types: list[str], metrics: WeatherMetrics,
) -> tuple[bool, bool]:
    """Return ``(rainfall_unavailable, weather_unavailable)``.

    ``rainfall_unavailable`` keeps the previous meaning: 3-day rain missing
    for a flood district, or 30/90-day rain missing for a drought district.

    ``weather_unavailable`` is set when a critical input for that district's
    hazards is missing. River discharge is optional. A missing soil-moisture
    or humidity series does not blank a forecast that still has the hazard's
    primary signal (rain for flood/landslide, rain+temperature for drought,
    temperature and snowfall for GLOF/avalanche).
    """
    rainfall_unavailable = False
    if "flood" in hazard_types and metrics.rainfall_forecast_mm is None:
        rainfall_unavailable = True
    if "drought" in hazard_types and (
        metrics.rainfall_30d_mm is None or metrics.rainfall_90d_mm is None
    ):
        rainfall_unavailable = True

    forecast_values = (
        metrics.rainfall_forecast_mm,
        metrics.temperature_max_c_3d,
        metrics.temperature_min_c_3d,
        metrics.precip_probability_max_pct_3d,
        metrics.wind_speed_max_kmh_3d,
        metrics.wind_gust_max_kmh_3d,
        metrics.humidity_mean_pct_3d,
        metrics.soil_moisture_0_1cm_m3m3,
        metrics.snowfall_cm_3d,
        metrics.snow_depth_cm,
    )
    weather_unavailable = all(value is None for value in forecast_values)
    if "flood" in hazard_types and metrics.rainfall_forecast_mm is None:
        weather_unavailable = True
    if "landslide" in hazard_types and metrics.rainfall_forecast_mm is None:
        weather_unavailable = True
    if "drought" in hazard_types and (
        metrics.rainfall_30d_mm is None
        or metrics.rainfall_90d_mm is None
        or metrics.temperature_max_c_3d is None
    ):
        weather_unavailable = True
    if any(hazard in hazard_types for hazard in ("glof", "avalanche")) and (
        metrics.temperature_max_c_3d is None or metrics.snowfall_cm_3d is None
    ):
        weather_unavailable = True
    return rainfall_unavailable, weather_unavailable
