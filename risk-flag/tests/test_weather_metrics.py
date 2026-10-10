"""
Multi-metric weather bundle: parse, hazard-aware fetches, prompt, fallback.

    cd risk-flag
    python -m pytest tests/test_weather_metrics.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import main as risk_main
import weather_bundle
from main import app, score_risk_fallback
from weather_bundle import (
    WeatherMetrics,
    availability_flags,
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

_ARCHIVE = {"daily": {"precipitation_sum": [1.0] * 90}}

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
        return _mock_response(200, _ARCHIVE)
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
    summary = summarize_archive(_ARCHIVE)
    assert summary["rainfall_30d_mm"] == 30.0
    assert summary["rainfall_90d_mm"] == 90.0


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
    assert "weather data was unavailable" in body["reason"].lower()
    assert "NDMA" in body["reason"]
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
            assert archive.kwargs["params"]["past_days"] == 90


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
