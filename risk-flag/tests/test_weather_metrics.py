"""
Multi-metric weather bundle: parse, hazard-aware fetches, prompt, fallback.

    cd risk-flag
    python -m pytest tests/test_weather_metrics.py -v
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import main as risk_main
import weather_bundle
from main import app, score_risk_fallback
from risk_reasoning import _build_prompt
from weather_bundle import (
    ARCHIVE_DAYS,
    DISTRICT_TIMEZONE,
    WeatherMetrics,
    archive_date_window,
    availability_flags,
    availability_note,
    inclusive_dates,
    summarize_archive,
    summarize_discharge,
    summarize_forecast,
)


@pytest.fixture(autouse=True)
def _clear_caches():
    with risk_main._cache_lock:
        risk_main._cache.clear()
    weather_bundle.clear_weather_cache()
    yield
    with risk_main._cache_lock:
        risk_main._cache.clear()
    weather_bundle.clear_weather_cache()


@pytest.fixture
def client():
    return TestClient(app)


def _mock_response(status_code: int, json_data=None, headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300
    resp.json.return_value = json_data or {}
    resp.headers = headers or {}
    resp.text = str(json_data)[:300] if json_data else ""
    return resp


_FULL_FORECAST = {
    "daily": {
        "time": ["2026-10-10", "2026-10-11", "2026-10-12"],
        "temperature_2m_max": [31.2, 33.0, 29.5],
        "temperature_2m_min": [22.0, 23.1, 21.4],
        "precipitation_sum": [10.0, None, 20.0],
        "precipitation_probability_max": [40, 80, 55],
        "wind_speed_10m_max": [12.0, 18.5, 9.0],
        "wind_gusts_10m_max": [20.0, 34.0, 15.0],
        "snowfall_sum": [0.0, 0.0, 0.0],
    },
    "hourly": {
        "time": ["2026-10-10T00:00", "2026-10-10T01:00", "2026-10-10T02:00"],
        "relative_humidity_2m": [60, 70, 80],
        "soil_moisture_0_to_1cm": [0.2, 0.3, 0.4],
        "snow_depth": [0.0, None, 0.01],
    },
}

_FLOOD = {"daily": {"river_discharge": [100.0, 250.5, 180.0]}}

def _dated_archive(params, fill=1.0):
    start = (params or {}).get("start_date")
    end = (params or {}).get("end_date")
    dates = inclusive_dates(start, end) if start and end else []
    return {
        "daily": {
            "time": dates,
            "precipitation_sum": [fill] * len(dates),
        }
    }

_CHITRAL_FORECAST = {
    "daily": {
        "temperature_2m_max": [6.0, 9.5, 4.0],
        "temperature_2m_min": [-4.0, -2.0, -6.0],
        "precipitation_sum": [2.0, 1.0, 0.0],
        "precipitation_probability_max": [30, 20, 10],
        "wind_speed_10m_max": [22.0, 15.0, 11.0],
        "wind_gusts_10m_max": [40.0, 28.0, 19.0],
        "snowfall_sum": [12.5, 10.0, 8.0],
    },
    "hourly": {
        "relative_humidity_2m": [70, 80],
        "soil_moisture_0_to_1cm": [0.25, 0.27],
        "snow_depth": [0.40, 0.42],
    },
}


def _router(url, params=None, timeout=None, headers=None):
    if "flood-api" in url:
        return _mock_response(200, _FLOOD)
    if "archive-api" in url:
        return _mock_response(200, _dated_archive(params))
    return _mock_response(200, _FULL_FORECAST)


def _urls(mock_get) -> list[str]:
    return [call.args[0] for call in mock_get.call_args_list]


def test_summarize_forecast_reduces_arrays_and_converts_snow_depth():
    summary = summarize_forecast(_FULL_FORECAST)
    assert summary["rainfall_forecast_mm"] == 30.0  # null day skipped
    assert summary["temperature_max_c_3d"] == 33.0
    assert summary["temperature_min_c_3d"] == 21.4
    assert summary["precip_probability_max_pct_3d"] == 80.0
    assert summary["wind_speed_max_kmh_3d"] == 18.5
    assert summary["wind_gust_max_kmh_3d"] == 34.0
    assert summary["humidity_mean_pct_3d"] == 70.0
    assert summary["soil_moisture_0_1cm_m3m3"] == 0.3
    assert summary["snowfall_cm_3d"] == 0.0
    assert summary["snow_depth_cm"] == 1.0  # 0.01 m
    assert "time" not in summary


def test_summarize_archive_derives_30d_from_90d_series():
    start, end = archive_date_window(date(2026, 10, 10))
    dates = inclusive_dates(start, end)
    summary = summarize_archive(
        {"daily": {"time": list(reversed(dates)), "precipitation_sum": [1.0] * len(dates)}},
        start_date=start,
        end_date=end,
    )
    assert summary["rainfall_30d_mm"] == 30.0
    assert summary["rainfall_90d_mm"] == 90.0
    assert summarize_archive(
        {"daily": {"precipitation_sum": [1.0] * 90}},
        start_date=start,
        end_date=end,
    ) == {}


def test_archive_window_is_90_inclusive_dates_including_today():
    start, end = archive_date_window(date(2026, 10, 10), utc_today=date(2026, 10, 10))
    dates = inclusive_dates(start, end)
    assert start == "2026-07-13"
    assert end == "2026-10-10"
    assert dates[0] == start
    assert dates[-1] == end
    assert len(dates) == ARCHIVE_DAYS
    assert len(set(dates)) == ARCHIVE_DAYS
    assert end == date(2026, 10, 10).isoformat()


def test_archive_window_stops_before_a_karachi_date_still_ahead_of_utc():
    """00:30 PKT on 11 October is still 10 October in UTC."""
    start, end = archive_date_window(date(2026, 10, 11), utc_today=date(2026, 10, 10))
    dates = inclusive_dates(start, end)
    assert start == "2026-07-13"
    assert end == "2026-10-10"
    assert len(dates) == ARCHIVE_DAYS
    assert dates[-1] == "2026-10-10"
    assert "2026-10-11" not in dates


def test_archive_window_is_90_days_across_month_and_year_boundaries():
    end_day = date(2026, 1, 1)
    start_day = end_day - timedelta(days=ARCHIVE_DAYS - 1)
    start, end = archive_date_window(end_day, utc_today=end_day)
    dates = inclusive_dates(start, end)
    assert start == start_day.isoformat() == "2025-10-04"
    assert end == "2026-01-01"
    assert len(dates) == ARCHIVE_DAYS
    assert dates[0] == start and dates[-1] == end
    assert dates[-30] == (end_day - timedelta(days=29)).isoformat()
    assert len(set(dates)) == ARCHIVE_DAYS


def test_archive_gap_drops_90d_and_keeps_complete_30d_zeros():
    start, end = archive_date_window(date(2026, 10, 10))
    dates = inclusive_dates(start, end)
    # Rain before the window must not enter either total. The first requested
    # day is missing; the last 30 days are genuine zeros.
    times = ["2026-07-12", *dates]
    values = [500.0, None, *([0.0] * (ARCHIVE_DAYS - 1))]
    summary = summarize_archive(
        {"daily": {"time": times, "precipitation_sum": values}},
        start_date=start,
        end_date=end,
    )
    assert "rainfall_90d_mm" not in summary
    assert summary["rainfall_30d_mm"] == 0.0


def test_archive_all_zero_days_stay_zero():
    start, end = archive_date_window(date(2026, 10, 10))
    dates = inclusive_dates(start, end)
    summary = summarize_archive(
        {"daily": {"time": dates, "precipitation_sum": [0.0] * ARCHIVE_DAYS}},
        start_date=start,
        end_date=end,
    )
    assert summary["rainfall_90d_mm"] == 0.0
    assert summary["rainfall_30d_mm"] == 0.0


def test_archive_date_defects_do_not_invent_coverage():
    start, end = archive_date_window(date(2026, 10, 10))
    dates = inclusive_dates(start, end)
    # 90 numeric values, but the first requested date is missing and the
    # second date is repeated. The last 30 dates are still one value each.
    gapped_times = [dates[1], *dates[1:]]
    gapped = summarize_archive(
        {"daily": {"time": gapped_times, "precipitation_sum": [1.0] * 90}},
        start_date=start,
        end_date=end,
    )
    assert "rainfall_90d_mm" not in gapped
    assert gapped["rainfall_30d_mm"] == 30.0

    shifted = inclusive_dates("2026-07-12", "2026-10-09")
    assert len(shifted) == 90
    moved = summarize_archive(
        {"daily": {"time": shifted, "precipitation_sum": [2.0] * 90}},
        start_date=start,
        end_date=end,
    )
    assert moved == {}

    extra = summarize_archive(
        {
            "daily": {
                "time": ["2026-07-12", *dates],
                "precipitation_sum": [999.0, *([1.0] * 90)],
            }
        },
        start_date=start,
        end_date=end,
    )
    assert extra["rainfall_90d_mm"] == 90.0
    assert extra["rainfall_30d_mm"] == 30.0

    assert summarize_archive(
        {"daily": {"time": dates, "precipitation_sum": [1.0] * 89}},
        start_date=start,
        end_date=end,
    ) == {}
    assert summarize_archive(
        {"daily": {"time": [*dates, "2026-10-11"], "precipitation_sum": [1.0] * 90}},
        start_date=start,
        end_date=end,
    ) == {}


_RANGE_400 = (
    '{"error":true,"reason":"Parameter \'end_date\' is out of allowed range '
    'from 1940-01-01 to 2026-10-10"}'
)


def _freeze_archive_clock(today=None, *, days=ARCHIVE_DAYS, utc_today=None):
    """Make an unfrozen window land on 11 October in both calendars."""
    if today is None:
        today = date(2026, 10, 11)
        utc_today = date(2026, 10, 11)
    elif utc_today is None:
        utc_today = today
    return archive_date_window(today, days=days, utc_today=utc_today)


def _text_response(status_code, text, json_data=None):
    resp = _mock_response(status_code, json_data)
    resp.text = text
    return resp


@patch("weather_bundle.archive_date_window", side_effect=_freeze_archive_clock)
@patch("requests.get")
def test_archive_date_range_400_recovers_once_and_is_reused(mock_get, _mock_window):
    allowed = date(2026, 10, 10)
    start, end = archive_date_window(allowed, utc_today=allowed)
    dates = inclusive_dates(start, end)
    assert end == "2026-10-10"
    assert len(dates) == 90
    assert "2026-10-11" not in dates
    recovered = _mock_response(200, {
        "daily": {"time": dates, "precipitation_sum": [0.0] * 90},
    })
    mock_get.side_effect = [
        _text_response(400, _RANGE_400),
        recovered,
        recovered,
    ]

    first = weather_bundle.fetch_historical_rainfall(29.3, 64.7)
    assert first["rainfall_90d_mm"] == 0.0
    assert first["rainfall_30d_mm"] == 0.0
    second_district = weather_bundle.fetch_historical_rainfall(24.7, 69.8)
    assert second_district["rainfall_90d_mm"] == 0.0
    same_place = weather_bundle.fetch_historical_rainfall(29.3, 64.7)
    assert same_place["rainfall_90d_mm"] == 0.0

    archive_params = [call.kwargs["params"] for call in mock_get.call_args_list]
    assert [params["end_date"] for params in archive_params] == [
        "2026-10-11", "2026-10-10", "2026-10-10",
    ]
    assert archive_params[1]["start_date"] == start
    assert archive_params[1]["start_date"] == (
        allowed - timedelta(days=ARCHIVE_DAYS - 1)
    ).isoformat()
    assert mock_get.call_count == 3


@patch("weather_bundle.archive_date_window", side_effect=_freeze_archive_clock)
@patch("requests.get")
def test_archive_unrelated_or_malformed_400_does_not_recover(mock_get, _mock_window):
    unrelated = _text_response(
        400, '{"error":true,"reason":"Latitude must be between -90 and 90"}',
    )
    mock_get.return_value = unrelated
    assert weather_bundle.fetch_historical_rainfall(1.0, 2.0) is None
    assert mock_get.call_count == 1

    mock_get.reset_mock()
    malformed = _text_response(
        400,
        '{"error":true,"reason":"Parameter \'end_date\' is out of allowed range '
        'from 1940-01-01 to 2026-02-31"}',
    )
    mock_get.return_value = malformed
    assert weather_bundle.fetch_historical_rainfall(1.0, 2.0) is None
    assert mock_get.call_count == 1

    mock_get.reset_mock()
    not_a_range = _text_response(400, "upstream unavailable 2026-10-10")
    mock_get.return_value = not_a_range
    assert weather_bundle.fetch_historical_rainfall(1.0, 2.0) is None
    assert mock_get.call_count == 1


@patch("weather_bundle.archive_date_window", side_effect=_freeze_archive_clock)
@patch("requests.get")
def test_archive_failed_recovery_keeps_history_missing(mock_get, _mock_window):
    second = _text_response(
        400,
        '{"error":true,"reason":"Parameter \'end_date\' is out of allowed range '
        'from 1940-01-01 to 2026-10-09"}',
    )
    mock_get.side_effect = [_text_response(400, _RANGE_400), second]
    assert weather_bundle.fetch_historical_rainfall(29.3, 64.7) is None
    assert mock_get.call_count == 2
    assert weather_bundle._cache_get(29.3, 64.7, weather_bundle.ARCHIVE_WINDOW) is None
    ends = [call.kwargs["params"]["end_date"] for call in mock_get.call_args_list]
    assert ends == ["2026-10-11", "2026-10-10"]


@patch("main.assess_risk_with_gemini", return_value=None)
@patch("weather_bundle.archive_date_window", side_effect=_freeze_archive_clock)
@patch("requests.get")
def test_recovered_archive_keeps_30d_when_older_days_are_incomplete(
    mock_get, _mock_window, _gemini, client,
):
    allowed = date(2026, 10, 10)
    start, end = archive_date_window(allowed, utc_today=allowed)
    dates = inclusive_dates(start, end)
    values = [None, *([0.0] * (ARCHIVE_DAYS - 1))]
    recovered = {
        "daily": {"time": dates, "precipitation_sum": values},
    }
    mock_get.side_effect = [
        _mock_response(200, {
            "daily": {
                "precipitation_sum": [0.0, 0.0, 0.0],
                "temperature_2m_max": [36.0, 37.0, 35.0],
            },
        }),
        _text_response(400, _RANGE_400),
        _mock_response(200, recovered),
    ]
    resp = client.post("/predict-risk", json={"district": "Chagai"})
    body = resp.json()
    assert body["rainfall_90d_mm"] is None
    assert body["rainfall_30d_mm"] == 0.0
    assert body["rainfall_unavailable"] is True
    assert "Historical rainfall is unavailable" in body["reason"]
    archive_ends = [
        call.kwargs["params"]["end_date"]
        for call in mock_get.call_args_list
        if "archive-api" in call.args[0]
    ]
    assert archive_ends == ["2026-10-11", end]


def test_archive_null_inside_last_30_days_drops_that_window():
    start, end = archive_date_window(date(2026, 10, 10))
    dates = inclusive_dates(start, end)
    values = [1.0] * ARCHIVE_DAYS
    values[-1] = None
    summary = summarize_archive(
        {"daily": {"time": dates, "precipitation_sum": values}},
        start_date=start,
        end_date=end,
    )
    assert "rainfall_90d_mm" not in summary
    assert "rainfall_30d_mm" not in summary


def test_summarize_discharge_uses_peak_and_ignores_empty():
    assert summarize_discharge(_FLOOD)["river_discharge_max_m3s_3d"] == 250.5
    assert summarize_discharge({"daily": {"river_discharge": [None, None]}}) == {}
    assert summarize_discharge({"daily": {}}) == {}


def test_availability_flags_by_hazard():
    full = WeatherMetrics(
        rainfall_forecast_mm=10,
        rainfall_30d_mm=5,
        rainfall_90d_mm=20,
        temperature_max_c_3d=30,
        snowfall_cm_3d=0,
    )
    assert availability_flags(["flood"], full) == (False, False)
    assert availability_flags(["glof", "avalanche"], full) == (False, False)
    assert availability_flags(["landslide"], full) == (False, False)
    assert availability_flags(["drought"], full) == (False, False)

    empty = WeatherMetrics()
    assert availability_flags(["flood"], empty) == (True, True)
    # Legacy rain flag stays false for northern districts; weather flag does not.
    assert availability_flags(["glof", "avalanche"], empty) == (False, True)
    assert availability_flags(["drought"], empty) == (True, True)

    rain_only = WeatherMetrics(rainfall_forecast_mm=12, rainfall_30d_mm=4, rainfall_90d_mm=9)
    assert availability_flags(["drought"], rain_only)[1] is True
    snow_gap = WeatherMetrics(temperature_max_c_3d=8)
    assert availability_flags(["glof"], snow_gap) == (False, True)


@patch("main.assess_risk_with_gemini", return_value=None)
@patch("time.sleep")
@patch("requests.get", return_value=_mock_response(429))
def test_weather_fetch_failure_still_uses_rules(mock_get, _sleep, _gemini, client):
    resp = client.post("/predict-risk", json={"district": "Dadu"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["reasoning_source"] == "fallback"
    assert body["rainfall_unavailable"] is True
    assert body["weather_unavailable"] is True
    assert body["weather_metrics"]["rainfall_forecast_mm"] is None
    assert body["weather_metrics"]["snowfall_cm_3d"] is None
    assert body["weather_metrics"]["river_discharge_max_m3s_3d"] is None
    assert body["risk_level"] in {"low", "medium", "high"}
    assert "static NDMA hazard context only" in body["reason"]
    assert "available weather" not in body["reason"]
    mock_get.assert_called()


@patch("time.sleep")
@patch("requests.get", return_value=_mock_response(429))
@patch("main.assess_risk_with_gemini", return_value=None)
def test_glof_outage_flags_weather_not_legacy_rainfall(_gemini, mock_get, _sleep, client):
    resp = client.post("/predict-risk", json={"district": "Chitral"})
    body = resp.json()
    assert resp.status_code == 200
    assert body["rainfall_unavailable"] is False
    assert body["weather_unavailable"] is True
    assert body["reasoning_source"] == "fallback"
    assert all("flood-api" not in url and "archive-api" not in url for url in _urls(mock_get))
    assert mock_get.call_count == 3


def _grab_prompt(store):
    from risk_reasoning import ReasoningResult

    def _grab(district, prompt):
        store["prompt"] = prompt
        return ReasoningResult(
            risk_level="medium",
            rationale="Rain and discharge keep flood risk moderate.",
            source="gemini",
        )

    return _grab


@patch("risk_reasoning._call_grok")
@patch("risk_reasoning._call_gemini")
@patch("requests.get", side_effect=_router)
def test_prompt_contains_flood_metrics_not_raw_hours(mock_get, mock_gemini, mock_grok, client):
    store: dict = {}
    mock_gemini.side_effect = _grab_prompt(store)

    resp = client.post("/predict-risk", json={"district": "Dadu"})
    body = resp.json()
    assert resp.status_code == 200
    metrics = body["weather_metrics"]
    assert metrics["rainfall_forecast_mm"] == 30.0
    assert metrics["temperature_max_c_3d"] == 33.0
    assert metrics["temperature_min_c_3d"] == 21.4
    assert metrics["precip_probability_max_pct_3d"] == 80.0
    assert metrics["wind_speed_max_kmh_3d"] == 18.5
    assert metrics["wind_gust_max_kmh_3d"] == 34.0
    assert metrics["humidity_mean_pct_3d"] == 70.0
    assert metrics["soil_moisture_0_1cm_m3m3"] == 0.3
    assert metrics["snowfall_cm_3d"] == 0.0
    assert metrics["snow_depth_cm"] == 1.0
    assert metrics["river_discharge_max_m3s_3d"] == 250.5
    assert body["rainfall_forecast_mm"] == 30.0
    assert body["rainfall_30d_mm"] is None
    assert body["weather_unavailable"] is False

    prompt = store["prompt"]
    assert "## Weather & snow metrics" in prompt
    assert "3-day maximum temperature: 33.0 °C" in prompt
    assert "3-day maximum wind speed: 18.5 km/h" in prompt
    assert "3-day mean relative humidity: 70.0 %" in prompt
    assert "Mean soil moisture at 0-1 cm: 0.300 m³/m³" in prompt
    assert "3-day snowfall: 0.0 cm" in prompt
    assert "Latest snow depth: 1.0 cm" in prompt
    assert "250.5 m³/s" in prompt
    assert "glof and avalanche: temperature (melt), snowfall, snow depth, and wind" in prompt
    assert "soil moisture" in prompt
    assert "2026-10-10" not in prompt
    mock_grok.assert_not_called()

    forecast_calls = [c for c in mock_get.call_args_list if c.args[0].endswith("/v1/forecast")]
    assert len(forecast_calls) == 1
    daily = forecast_calls[0].kwargs["params"]["daily"]
    hourly = forecast_calls[0].kwargs["params"]["hourly"]
    assert "snowfall_sum" in daily
    assert "precipitation_probability_max" in daily
    assert "wind_gusts_10m_max" in daily
    assert "relative_humidity_2m" in hourly
    assert "soil_moisture_0_to_1cm" in hourly
    assert "snow_depth" in hourly
    assert forecast_calls[0].kwargs["params"]["forecast_days"] == 3
    assert sum("flood-api" in url for url in _urls(mock_get)) == 1
    assert not any("archive-api" in url for url in _urls(mock_get))


def _chitral_router(url, params=None, timeout=None, headers=None):
    return _mock_response(200, _CHITRAL_FORECAST)


@patch("risk_reasoning._call_grok")
@patch("risk_reasoning._call_gemini")
@patch("requests.get", side_effect=_chitral_router)
def test_chitral_snow_metrics_and_single_forecast_call(mock_get, mock_gemini, mock_grok, client):
    store: dict = {}
    mock_gemini.side_effect = _grab_prompt(store)

    resp = client.post("/predict-risk", json={"district": "Chitral"})
    body = resp.json()
    metrics = body["weather_metrics"]
    assert metrics["snowfall_cm_3d"] == 30.5
    assert metrics["snow_depth_cm"] == 42.0
    assert metrics["temperature_max_c_3d"] == 9.5
    assert metrics["temperature_min_c_3d"] == -6.0
    assert metrics["wind_speed_max_kmh_3d"] == 22.0
    assert metrics["river_discharge_max_m3s_3d"] is None
    assert body["rainfall_forecast_mm"] == 3.0
    assert body["weather_unavailable"] is False
    assert "3-day snowfall: 30.5 cm" in store["prompt"]
    assert "Latest snow depth: 42.0 cm" in store["prompt"]
    assert "River discharge:" not in store["prompt"]
    assert len(mock_get.call_args_list) == 1
    assert mock_get.call_args_list[0].args[0].endswith("/v1/forecast")


@patch("requests.get", side_effect=_router)
@patch("main.assess_risk_with_gemini", return_value=None)
def test_hazard_call_plan(_gemini, mock_get, client):
    cases = {
        "Dadu": {"flood": True, "archive": False},
        "Chitral": {"flood": False, "archive": False},
        "Mansehra": {"flood": False, "archive": False},
        "Tharparkar": {"flood": False, "archive": True},
    }
    for district, expect in cases.items():
        mock_get.reset_mock()
        weather_bundle.clear_weather_cache()
        with risk_main._cache_lock:
            risk_main._cache.clear()
        resp = client.post("/predict-risk", json={"district": district})
        assert resp.status_code == 200
        urls = _urls(mock_get)
        assert sum(url.endswith("/v1/forecast") for url in urls) == 1
        assert any("flood-api" in url for url in urls) is expect["flood"]
        assert any("archive-api" in url for url in urls) is expect["archive"]
        if expect["archive"]:
            archive = next(c for c in mock_get.call_args_list if "archive-api" in c.args[0])
            params = archive.kwargs["params"]
            start, end = archive_date_window()
            assert params["start_date"] == start
            assert params["end_date"] == end
            assert params["timezone"] == DISTRICT_TIMEZONE
            assert "past_days" not in params
            assert len(inclusive_dates(start, end)) == ARCHIVE_DAYS


def test_fallback_keeps_flood_band_and_mentions_discharge():
    level, reason = score_risk_fallback(
        "Dadu", ["flood"], 60, None, None,
        weather_metrics={"river_discharge_max_m3s_3d": 8000},
    )
    assert level == "medium"
    assert "moderate flood risk" in reason
    assert "8000" in reason
    assert "GloFAS" in reason


def test_fallback_heavy_snow_and_warm_pack_raise_northern_risk():
    level, reason = score_risk_fallback(
        "Hunza", ["glof", "avalanche"], 5, None, None,
        weather_metrics={
            "temperature_max_c_3d": 2,
            "snowfall_cm_3d": 40,
            "snow_depth_cm": 80,
        },
    )
    assert level == "high"
    assert "snowfall 40 cm" in reason

    warm, warm_reason = score_risk_fallback(
        "Skardu", ["glof", "avalanche"], None, None, None,
        weather_metrics={"temperature_max_c_3d": 26, "snowfall_cm_3d": 2, "snow_depth_cm": 50},
    )
    assert warm == "high"
    assert "snow depth 50 cm" in warm_reason

    calm, _ = score_risk_fallback(
        "Chitral", ["glof", "avalanche"], None, None, None,
        weather_metrics={"temperature_max_c_3d": 8, "snowfall_cm_3d": 4, "snow_depth_cm": 10},
    )
    assert calm == "medium"


def test_fallback_extreme_heat_raises_drought_and_wet_soil_raises_landslide():
    level, reason = score_risk_fallback(
        "Tharparkar", ["drought"], 0, 2.0, 8.0,
        weather_metrics={"temperature_max_c_3d": 46, "humidity_mean_pct_3d": 12, "soil_moisture_0_1cm_m3m3": 0.05},
    )
    assert level == "high"
    assert "46" in reason
    assert "30-day rainfall: 2.0 mm" in reason

    slide, slide_reason = score_risk_fallback(
        "Mansehra", ["landslide"], 50, None, None,
        weather_metrics={"soil_moisture_0_1cm_m3m3": 0.45},
    )
    assert slide == "high"
    assert "soil moisture 0.45" in slide_reason


def _drought_forecast_only(url, params=None, timeout=None, headers=None):
    if "archive-api" in url:
        return _mock_response(429)
    return _mock_response(200, {
        "daily": {
            "precipitation_sum": [0.0, 0.0, 0.0],
            "temperature_2m_max": [36.0, 36.7, 35.0],
            "temperature_2m_min": [24.0, 25.0, 23.0],
            "precipitation_probability_max": [0, 0, 0],
            "wind_speed_10m_max": [21.5, 18.0, 16.0],
            "wind_gusts_10m_max": [39.2, 30.0, 28.0],
            "snowfall_sum": [0.0, 0.0, 0.0],
        },
        "hourly": {
            "relative_humidity_2m": [60, 62],
            "soil_moisture_0_to_1cm": [0.10, 0.106],
            "snow_depth": [0.0, 0.0],
        },
    })


@patch("requests.get", side_effect=_drought_forecast_only)
@patch("main.assess_risk_with_gemini", return_value=None)
def test_missing_drought_history_keeps_flags_and_limits_the_note(_gemini, mock_get, client):
    resp = client.post("/predict-risk", json={"district": "Tharparkar"})
    body = resp.json()
    assert resp.status_code == 200
    assert body["weather_unavailable"] is True
    assert body["rainfall_unavailable"] is True
    assert body["rainfall_30d_mm"] is None
    assert body["rainfall_90d_mm"] is None
    assert body["weather_metrics"]["temperature_max_c_3d"] == 36.7
    assert body["weather_metrics"]["rainfall_forecast_mm"] == 0.0
    assert "Historical rainfall is unavailable" in body["reason"]
    assert "drought assessment is limited" in body["reason"]
    assert "static NDMA hazard context only" not in body["reason"]
    note = availability_note(
        ["drought"],
        WeatherMetrics(**body["weather_metrics"]),
        True,
        True,
    )
    assert "context only" not in note


def test_drought_prompt_blocks_unsupported_deficit_and_soil_claims():
    prompt = _build_prompt(
        "Chagai",
        ["drought"],
        {"drought": {"description": "Arid district.", "high_risk_districts": ["Chagai"], "source": "NDMA"}},
        "Balochistan",
        0.0,
        None,
        None,
        weather_metrics={
            "rainfall_forecast_mm": 0.0,
            "temperature_max_c_3d": 37.0,
            "soil_moisture_0_1cm_m3m3": 0.064,
        },
    )
    assert "cannot establish a persistent drought" in prompt
    assert "30-day or 90-day rainfall deficit" in prompt
    assert "baseline for comparison" in prompt
    assert "critically low" in prompt
    assert "supported threshold" in prompt
    assert "Historical rainfall unavailable: 30-day and 90-day" in prompt
    assert "0.064" in prompt
    assert "3-day rainfall forecast: 0.0 mm" in prompt
