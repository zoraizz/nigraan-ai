"""
Open-Meteo weather bundle for /predict-risk.

One forecast request carries the 3-day metrics (including snow). Drought
districts add one archive call for 90 inclusive calendar dates. The end date
is the earlier of the Asia/Karachi date and the UTC date, because Best Match
is documented only as available "to present" and a Karachi date still ahead
of UTC is rejected. A date-range HTTP 400 that names a latest allowed day
gets one recovery request ending on that day. The 30-day total is the last
30 dates of the accepted window when every one of them is numeric. Flood
districts add one GloFAS river-discharge call.
No API key. Raw hourly arrays stay on the server and are reduced to scalars.
"""

from __future__ import annotations

import logging
import re
import time
import threading
from datetime import date, datetime, timedelta, timezone

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
# Every covered district is in Pakistan. Asia/Karachi is UTC+5 with no
# daylight-saving shift, so the calendar below matches that zone without
# requiring the host's zoneinfo database. The archive request sends the
# same timezone name.
DISTRICT_TIMEZONE = "Asia/Karachi"
_DISTRICT_UTC_OFFSET = timezone(timedelta(hours=5))
ARCHIVE_DAYS = 90

WEATHER_CACHE_TTL_SECS = 3 * 60 * 60  # 3 hours

_cache: dict[tuple, tuple[dict, float]] = {}
_cache_lock = threading.Lock()
# Latest archive end date learned from a date-range HTTP 400. Not a rainfall
# total. Same lifetime as the weather cache so a rejected end date is not
# requested again for every drought district.
_archive_end_ceiling: tuple[date, float] | None = None
_ARCHIVE_RANGE_RE = re.compile(
    r"end_date['\"]?\s+is out of allowed range from "
    r"(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)


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
    global _archive_end_ceiling
    with _cache_lock:
        _cache.clear()
        _archive_end_ceiling = None


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


def _openmeteo_exchange(url: str, params: dict) -> tuple[dict | None, int | None, str]:
    """GET Open-Meteo with the shared retry policy.

    Returns parsed JSON, the last HTTP status, and the last response text.
    Retryable statuses stay 429 and 5xx. A 400 is returned once, with its
    body, so the archive caller can decide whether one date-range recovery
    is possible. Other callers ignore the status and text.
    """
    last_exc: Exception | None = None
    last_status: int | None = None
    last_text = ""

    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = requests.get(
                url, params=params, timeout=_REQUEST_TIMEOUT,
                headers=_OPENMETEO_HEADERS,
            )
            last_status = response.status_code
            last_text = response.text or ""

            if response.ok:
                body = response.json()
                return (body if isinstance(body, dict) else None), last_status, last_text

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
                return None, last_status, last_text

            logger.error(
                "Open-Meteo %s returned non-retryable %d: %s",
                url, response.status_code, last_text[:300],
            )
            return None, last_status, last_text

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
    return None, last_status, last_text


def _openmeteo_request_with_retry(url: str, params: dict) -> dict | None:
    """GET Open-Meteo. Returns parsed JSON, or None after retries are exhausted."""
    data, _status, _text = _openmeteo_exchange(url, params)
    return data


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


def archive_date_window(
    today: date | None = None,
    *,
    days: int = ARCHIVE_DAYS,
    utc_today: date | None = None,
) -> tuple[str, str]:
    """Inclusive ISO dates for ``days`` calendar days.

    The end date is the earlier of the Asia/Karachi date and the UTC date.
    ``start_date`` is that end date minus ``days - 1``. Open-Meteo documents
    Best Match as available "to present": IFS has no delay, and the ERA5
    five-day delay is not the Best Match cutoff. The docs do not define
    present as the Asia/Karachi calendar day. A Karachi date that is still
    the next UTC day is not requested. This does not assume the UTC day
    itself is published.
    """
    if days < 1:
        raise ValueError("archive window must cover at least one day")
    if today is None:
        today = datetime.now(_DISTRICT_UTC_OFFSET).date()
    if utc_today is None:
        utc_today = datetime.now(timezone.utc).date()
    end = min(today, utc_today)
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def _archive_end_ceiling_get() -> date | None:
    with _cache_lock:
        if _archive_end_ceiling is None:
            return None
        day, stamp = _archive_end_ceiling
        if time.time() - stamp > WEATHER_CACHE_TTL_SECS:
            return None
        return day


def _archive_end_ceiling_put(day: date) -> None:
    global _archive_end_ceiling
    with _cache_lock:
        _archive_end_ceiling = (day, time.time())


def latest_allowed_archive_end(
    status_code: int | None,
    body: str,
    *,
    requested_end: str,
) -> date | None:
    """Parse one archive date-range HTTP 400.

    Returns the named latest allowed day only when it is a real calendar
    date strictly before the end date we sent. Any other 400, including a
    malformed date, returns None so the caller does not recover.
    """
    if status_code != 400 or not body:
        return None
    match = _ARCHIVE_RANGE_RE.search(body)
    if match is None:
        return None
    try:
        range_start = date.fromisoformat(match.group(1))
        range_end = date.fromisoformat(match.group(2))
        requested = date.fromisoformat(requested_end)
    except ValueError:
        return None
    if range_end < range_start or range_end >= requested:
        return None
    return range_end


def _initial_archive_window() -> tuple[str, str]:
    """Planned 90-day window, capped by a recently learned archive end date."""
    start, end = archive_date_window()
    ceiling = _archive_end_ceiling_get()
    if ceiling is not None and ceiling.isoformat() < end:
        return archive_date_window(ceiling, utc_today=ceiling)
    return start, end


def inclusive_dates(start_date: str, end_date: str) -> list[str]:
    """Every calendar date from start through end, inclusive."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        return []
    count = (end - start).days + 1
    return [(start + timedelta(days=offset)).isoformat() for offset in range(count)]


def _finite(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number:  # NaN
        return None
    return number


def _complete_sum(values) -> float | None:
    """Sum a window only when every day is numeric. A gap stays missing. Zero is kept."""
    if not isinstance(values, list) or not values:
        return None
    total = 0.0
    for value in values:
        number = _finite(value)
        if number is None:
            return None
        total += number
    return total


def _pair_by_date(times, values) -> dict[str, object] | None:
    """Pair each YYYY-MM-DD with one precipitation value.

    Returns None when the arrays cannot be paired. A repeated date is marked
    missing so it is neither summed twice nor filled from one of the copies.
    """
    if not isinstance(times, list) or not isinstance(values, list):
        return None
    if len(times) != len(values):
        return None
    paired: dict[str, object] = {}
    duplicated: set[str] = set()
    for stamp, value in zip(times, values):
        if not isinstance(stamp, str) or len(stamp) < 10:
            return None
        day = stamp[:10]
        if day in paired:
            duplicated.add(day)
        paired[day] = value
    for day in duplicated:
        paired[day] = None
    return paired


def summarize_archive(
    data: dict | None,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """90-day and 30-day precipitation totals from one archive payload.

    Totals require the requested calendar dates, each appearing once and
    paired with a numeric value. Ninety numbers without those dates are not
    a 90-day total. Days outside the window are ignored. A gap or duplicate
    in the older dates drops the 90-day total and can still leave a complete
    last-30-day total. Zero is a real amount.
    """
    if not isinstance(data, dict) or not start_date or not end_date:
        return {}
    daily = data.get("daily") if isinstance(data.get("daily"), dict) else {}
    paired = _pair_by_date(daily.get("time"), daily.get("precipitation_sum"))
    if paired is None:
        return {}
    expected = inclusive_dates(start_date, end_date)
    if not expected:
        return {}
    series = [paired.get(day) for day in expected]
    summary: dict[str, float] = {}
    if len(series) == ARCHIVE_DAYS:
        _put(summary, "rainfall_90d_mm", _complete_sum(series), 1)
    if len(series) >= 30:
        _put(summary, "rainfall_30d_mm", _complete_sum(series[-30:]), 1)
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


def _archive_params(lat: float, lon: float, start_date: str, end_date: str) -> dict:
    return {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": "precipitation_sum",
        "timezone": DISTRICT_TIMEZONE,
    }


def fetch_historical_rainfall(lat: float, lon: float) -> dict | None:
    """90-day archive precipitation. One date-range recovery at most.

    Summaries are cached only when at least one total is numeric. A rejected
    end date is remembered for the weather-cache lifetime so the next
    district does not repeat it. A failed recovery leaves history missing.
    """
    cached = _cache_get(lat, lon, ARCHIVE_WINDOW)
    if cached is not None:
        logger.info("Weather cache hit for (%s, %s, %s)", lat, lon, ARCHIVE_WINDOW)
        return cached

    start_date, end_date = _initial_archive_window()
    data, status, text = _openmeteo_exchange(
        _ARCHIVE_URL, _archive_params(lat, lon, start_date, end_date),
    )
    if data is None:
        latest = latest_allowed_archive_end(status, text, requested_end=end_date)
        if latest is not None:
            rejected_end = end_date
            _archive_end_ceiling_put(latest)
            start_date, end_date = archive_date_window(latest, utc_today=latest)
            logger.warning(
                "Archive end_date %s is past the allowed range ending %s; one recovery request",
                rejected_end, end_date,
            )
            data, _status, _text = _openmeteo_exchange(
                _ARCHIVE_URL, _archive_params(lat, lon, start_date, end_date),
            )

    if data is not None:
        summary = summarize_archive(data, start_date=start_date, end_date=end_date)
        if summary:
            cache_put(lat, lon, ARCHIVE_WINDOW, summary)
            return summary

    return _cache_get(lat, lon, ARCHIVE_WINDOW, allow_stale=True)


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


_NOTE_STATIC_ONLY = (
    "Live weather data was unavailable; this assessment is "
    "based on static NDMA hazard context only."
)
_NOTE_PARTIAL = (
    "Some required weather data is unavailable. This assessment uses "
    "the available weather and static NDMA hazard context."
)
_NOTE_DROUGHT_HISTORY = (
    "Historical rainfall is unavailable, so this drought assessment "
    "is limited. It uses the available forecast and static NDMA hazard context."
)

_USABLE_METRICS = (
    "rainfall_forecast_mm",
    "rainfall_30d_mm",
    "rainfall_90d_mm",
    "temperature_max_c_3d",
    "temperature_min_c_3d",
    "precip_probability_max_pct_3d",
    "wind_speed_max_kmh_3d",
    "wind_gust_max_kmh_3d",
    "humidity_mean_pct_3d",
    "soil_moisture_0_1cm_m3m3",
    "snowfall_cm_3d",
    "snow_depth_cm",
    "river_discharge_max_m3s_3d",
)


def _has_usable_weather(metrics: WeatherMetrics | None) -> bool:
    if metrics is None:
        return False
    return any(getattr(metrics, name, None) is not None for name in _USABLE_METRICS)


def availability_note(
    hazard_types: list[str],
    metrics: WeatherMetrics | None,
    weather_unavailable: bool,
    rainfall_unavailable: bool,
) -> str:
    """Reason prefix. Empty when both availability flags are false.

    ``weather_unavailable`` still means a critical hazard input is missing.
    The sentence says static context only when no usable weather value remains.
    The dashboard banner in availabilityNote.js uses the same three sentences.
    """
    if not weather_unavailable and not rainfall_unavailable:
        return ""
    history_missing = (
        "drought" in hazard_types
        and metrics is not None
        and metrics.temperature_max_c_3d is not None
        and (metrics.rainfall_30d_mm is None or metrics.rainfall_90d_mm is None)
    )
    if history_missing:
        sentence = _NOTE_DROUGHT_HISTORY
    elif _has_usable_weather(metrics):
        sentence = _NOTE_PARTIAL
    else:
        sentence = _NOTE_STATIC_ONLY
    return f"[Note: {sentence}] "
