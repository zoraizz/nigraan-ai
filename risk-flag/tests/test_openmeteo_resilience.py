"""
Tests for Open-Meteo resilience: retry logic, stale-cache fallback, and
null-rainfall path.

Uses pytest + FastAPI TestClient so no live server or Open-Meteo calls are
needed.  All Open-Meteo HTTP calls are mocked via ``unittest.mock.patch``.

Usage:
    cd risk-flag
    python -m pytest tests/test_openmeteo_resilience.py -v
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
import requests
from fastapi.testclient import TestClient

# Import the app and internals we need to inspect / reset
import main as risk_main
import weather_bundle
from main import app


@pytest.fixture(autouse=True)
def _clear_caches():
    """Reset the response cache and the weather-bundle cache between tests."""
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code: int, json_data=None, headers=None):
    """Build a mock ``requests.Response``."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300
    resp.json.return_value = json_data or {}
    resp.headers = headers or {}
    resp.text = str(json_data)[:300] if json_data else ""
    return resp


_FORECAST_OK = {
    "daily": {"precipitation_sum": [10.0, 20.0, 30.0]},
}

def _archive_ok_90():
    start, end = weather_bundle.archive_date_window()
    dates = weather_bundle.inclusive_dates(start, end)
    return {
        "daily": {
            "time": dates,
            "precipitation_sum": [1.0] * len(dates),
        }
    }

_DISCHARGE_EMPTY = {"daily": {"river_discharge": [None, None, None]}}

_DROUGHT_FORECAST = {
    "daily": {
        "precipitation_sum": [1.0, 2.0, 3.0],
        "temperature_2m_max": [41.0, 42.0, 40.0],
    },
}


def _then_discharge(*responses):
    """Flood districts make a discharge call after the forecast bundle."""
    return [*responses, _mock_response(200, json_data=_DISCHARGE_EMPTY)]


# ---------------------------------------------------------------------------
# 1. Retry on 429
# ---------------------------------------------------------------------------

@patch("main.assess_risk_with_gemini", return_value=None)
@patch("time.sleep")  # Don't actually sleep in tests
@patch("requests.get")
def test_retry_on_429_then_success(mock_get, mock_sleep, _mock_gemini, client):
    """429 on first attempt → retry → 200 on second → returns rainfall."""
    mock_get.side_effect = _then_discharge(
        _mock_response(429, headers={"Retry-After": "1"}),
        _mock_response(200, json_data=_FORECAST_OK),
    )

    resp = client.post("/predict-risk", json={"district": "Dadu"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rainfall_forecast_mm"] == 60.0
    assert body["weather_metrics"]["rainfall_forecast_mm"] == 60.0
    assert body["rainfall_unavailable"] is False
    assert body["weather_unavailable"] is False
    # Forecast: 429 then 200. Discharge: one 200.
    assert mock_get.call_count == 3


@patch("main.assess_risk_with_gemini", return_value=None)
@patch("time.sleep")
@patch("requests.get")
def test_retry_exhausted_returns_unavailable(mock_get, mock_sleep, _mock_gemini, client):
    """429 on all attempts → rainfall unavailable, request still returns 200."""
    mock_get.return_value = _mock_response(429)

    resp = client.post("/predict-risk", json={"district": "Dadu"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rainfall_forecast_mm"] is None
    assert body["weather_metrics"]["rainfall_forecast_mm"] is None
    assert body["rainfall_unavailable"] is True
    assert body["weather_unavailable"] is True
    assert "unavailable" in body["reason"].lower()
    # Forecast 3 attempts + discharge 3 attempts.
    assert mock_get.call_count == 6


# ---------------------------------------------------------------------------
# 2. Retry on 5xx
# ---------------------------------------------------------------------------

@patch("main.assess_risk_with_gemini", return_value=None)
@patch("time.sleep")
@patch("requests.get")
def test_retry_on_500_then_success(mock_get, mock_sleep, _mock_gemini, client):
    """500 on first attempt → retry → 200 on second → returns rainfall."""
    mock_get.side_effect = _then_discharge(
        _mock_response(500),
        _mock_response(200, json_data=_FORECAST_OK),
    )

    resp = client.post("/predict-risk", json={"district": "Dadu"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rainfall_forecast_mm"] == 60.0
    assert body["rainfall_unavailable"] is False


# ---------------------------------------------------------------------------
# 3. Stale-cache fallback
# ---------------------------------------------------------------------------

@patch("main.assess_risk_with_gemini", return_value=None)
@patch("time.sleep")
@patch("requests.get")
def test_stale_cache_fallback(mock_get, mock_sleep, _mock_gemini, client):
    """Pre-populate rainfall cache with an expired entry. When Open-Meteo
    fails, the stale value should be served."""
    lat, lon = 26.73033, 67.7769  # Dadu coords
    # Insert a stale forecast bundle (expired 1 hour ago).
    stale_ts = time.time() - weather_bundle.WEATHER_CACHE_TTL_SECS - 3600
    weather_bundle.cache_put(
        lat, lon, weather_bundle.FORECAST_WINDOW,
        {"rainfall_forecast_mm": 42.5},
        written_at=stale_ts,
    )

    # Open-Meteo returns 429 on all attempts
    mock_get.return_value = _mock_response(429)

    resp = client.post("/predict-risk", json={"district": "Dadu"})
    assert resp.status_code == 200
    body = resp.json()
    # Should serve the stale cached value
    assert body["rainfall_forecast_mm"] == 42.5
    # Stale cache served successfully → rainfall is NOT marked unavailable
    assert body["rainfall_unavailable"] is False


# ---------------------------------------------------------------------------
# 4. Null-rainfall path returns 200 with unavailable note
# ---------------------------------------------------------------------------

@patch("main.assess_risk_with_gemini", return_value=None)
@patch("time.sleep")
@patch("requests.get")
def test_null_rainfall_returns_200(mock_get, mock_sleep, _mock_gemini, client):
    """When rainfall is fully unavailable (no cache, all retries exhausted),
    the response should be 200 with rainfall_unavailable=True."""
    mock_get.return_value = _mock_response(429)

    resp = client.post("/predict-risk", json={"district": "Dadu"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rainfall_forecast_mm"] is None
    assert body["rainfall_unavailable"] is True
    assert body["risk_level"] in {"low", "medium", "high"}
    assert "unavailable" in body["reason"].lower()
    assert "NDMA" in body["reason"]


# ---------------------------------------------------------------------------
# 5. Drought districts — archive calls with retry
# ---------------------------------------------------------------------------

@patch("main.assess_risk_with_gemini", return_value=None)
@patch("time.sleep")
@patch("requests.get")
def test_drought_archive_retry_success(mock_get, mock_sleep, _mock_gemini, client):
    """Drought district archive calls succeed after one retry."""
    mock_get.side_effect = [
        _mock_response(200, json_data=_DROUGHT_FORECAST),
        # 90-day archive: fail once, then succeed. 30-day is derived from it.
        _mock_response(503),
        _mock_response(200, json_data=_archive_ok_90()),
    ]

    resp = client.post("/predict-risk", json={"district": "Tharparkar"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rainfall_forecast_mm"] == 6.0
    assert body["rainfall_30d_mm"] == 30.0
    assert body["rainfall_90d_mm"] == 90.0
    assert body["weather_metrics"]["temperature_max_c_3d"] == 42.0
    assert body["rainfall_unavailable"] is False
    assert body["weather_unavailable"] is False
    archive_calls = [
        call for call in mock_get.call_args_list if "archive-api" in call.args[0]
    ]
    assert len(archive_calls) == 2
    start, end = weather_bundle.archive_date_window()
    for call in archive_calls:
        params = call.kwargs["params"]
        assert params["start_date"] == start
        assert params["end_date"] == end
        assert params["timezone"] == weather_bundle.DISTRICT_TIMEZONE
        assert "past_days" not in params


@patch("main.assess_risk_with_gemini", return_value=None)
@patch("time.sleep")
@patch("requests.get")
def test_drought_archive_fully_unavailable(mock_get, mock_sleep, _mock_gemini, client):
    """Drought district with all archive calls failing — still returns 200."""
    mock_get.return_value = _mock_response(429)

    resp = client.post("/predict-risk", json={"district": "Tharparkar"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rainfall_30d_mm"] is None
    assert body["rainfall_90d_mm"] is None
    assert body["rainfall_unavailable"] is True
    assert body["weather_unavailable"] is True
    assert body["weather_metrics"]["temperature_max_c_3d"] is None
    assert "static NDMA hazard context only" in body["reason"]


# ---------------------------------------------------------------------------
# 6. Request timeout handling
# ---------------------------------------------------------------------------

@patch("main.assess_risk_with_gemini", return_value=None)
@patch("time.sleep")
@patch("requests.get")
def test_request_timeout_triggers_retry(mock_get, mock_sleep, _mock_gemini, client):
    """requests.Timeout on first attempt → retry → 200."""
    import requests as req_lib
    mock_get.side_effect = _then_discharge(
        req_lib.Timeout("Connection timed out"),
        _mock_response(200, json_data=_FORECAST_OK),
    )

    resp = client.post("/predict-risk", json={"district": "Dadu"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rainfall_forecast_mm"] == 60.0
    assert body["rainfall_unavailable"] is False


# ---------------------------------------------------------------------------
# 7. Retry-After header is honored
# ---------------------------------------------------------------------------

@patch("main.assess_risk_with_gemini", return_value=None)
@patch("time.sleep")
@patch("requests.get")
def test_retry_after_header_honored(mock_get, mock_sleep, _mock_gemini, client):
    """Retry-After header value is passed to time.sleep."""
    mock_get.side_effect = _then_discharge(
        _mock_response(429, headers={"Retry-After": "3"}),
        _mock_response(200, json_data=_FORECAST_OK),
    )

    resp = client.post("/predict-risk", json={"district": "Dadu"})
    assert resp.status_code == 200
    # Verify sleep was called with the Retry-After value
    mock_sleep.assert_any_call(3.0)


# ---------------------------------------------------------------------------
# 8. Fresh rainfall cache is used without hitting Open-Meteo
# ---------------------------------------------------------------------------

@patch("main.assess_risk_with_gemini", return_value=None)
@patch("requests.get")
def test_fresh_cache_avoids_request(mock_get, _mock_gemini, client):
    """When a fresh rainfall cache entry exists, Open-Meteo is not called."""
    lat, lon = 26.73033, 67.7769  # Dadu coords
    weather_bundle.cache_put(
        lat, lon, weather_bundle.FORECAST_WINDOW,
        {"rainfall_forecast_mm": 55.0},
    )
    weather_bundle.cache_put(
        lat, lon, weather_bundle.DISCHARGE_WINDOW,
        {"river_discharge_max_m3s_3d": 10.0},
    )

    resp = client.post("/predict-risk", json={"district": "Dadu"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rainfall_forecast_mm"] == 55.0
    assert body["weather_metrics"]["river_discharge_max_m3s_3d"] == 10.0
    assert body["rainfall_unavailable"] is False
    # No HTTP call should have been made
    mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# 9. Global exception handler returns JSON 500
# ---------------------------------------------------------------------------

@patch("main.assess_risk_with_gemini", side_effect=RuntimeError("boom"))
@patch("requests.get", return_value=_mock_response(200, json_data=_FORECAST_OK))
def test_global_exception_handler(mock_get, _mock_gemini):
    """An unhandled exception in the endpoint returns JSON 500, not a crash."""
    # raise_server_exceptions=False so TestClient returns the 500 response
    # instead of re-raising the RuntimeError.
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post("/predict-risk", json={"district": "Dadu"})
    assert resp.status_code == 500
    body = resp.json()
    assert "detail" in body
    assert "boom" in body["detail"]


# ---------------------------------------------------------------------------
# 10. Non-retryable errors (e.g. 400) don't retry
# ---------------------------------------------------------------------------

@patch("main.assess_risk_with_gemini", return_value=None)
@patch("time.sleep")
@patch("requests.get")
def test_non_retryable_error_no_retry(mock_get, mock_sleep, _mock_gemini, client):
    """A 400 error should not trigger retries."""
    mock_get.return_value = _mock_response(400)

    resp = client.post("/predict-risk", json={"district": "Dadu"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rainfall_forecast_mm"] is None
    assert body["rainfall_unavailable"] is True
    assert body["weather_unavailable"] is True
    # Forecast 400 (no retry) plus discharge 400 (no retry).
    assert mock_get.call_count == 2


# ---------------------------------------------------------------------------
# 11. reasoning_source on the response (scoring unchanged)
# ---------------------------------------------------------------------------

def _gemini_result(level: str = "high", rationale: str = "Gemini assessment."):
    from risk_reasoning import ReasoningResult

    return ReasoningResult(risk_level=level, rationale=rationale, source="gemini")


@patch("main.assess_risk_with_gemini")
@patch("requests.get", return_value=_mock_response(200, json_data=_FORECAST_OK))
def test_reasoning_source_gemini_then_cache(mock_get, mock_gemini, client):
    """A successful Gemini call is labeled gemini; the next hit is cache."""
    mock_gemini.return_value = _gemini_result()

    first = client.post("/predict-risk", json={"district": "Dadu"})
    assert first.status_code == 200
    body = first.json()
    assert body["reasoning_source"] == "gemini"
    assert body["reasoning_error"] is None
    assert body["cached"] is False
    assert body["risk_level"] == "high"
    assert mock_gemini.call_count == 1

    second = client.post("/predict-risk", json={"district": "Dadu"})
    assert second.status_code == 200
    cached = second.json()
    assert cached["reasoning_source"] == "cache"
    assert cached["reasoning_error"] is None
    assert cached["cached"] is True
    assert cached["risk_level"] == "high"
    assert mock_gemini.call_count == 1
    mock_get.assert_called()


@patch("main.assess_risk_with_gemini")
@patch("requests.get", return_value=_mock_response(200, json_data=_FORECAST_OK))
def test_reasoning_source_fallback_on_api_error(mock_get, mock_gemini, client):
    """An API error keeps rule scoring and reports reasoning_error."""
    from risk_reasoning import ReasoningResult

    mock_gemini.return_value = ReasoningResult(
        risk_level="high",
        rationale="do not use this rationale",
        source="gemini",
        error="api_error",
    )

    resp = client.post("/predict-risk", json={"district": "Dadu"})
    assert resp.status_code == 200
    body = resp.json()
    # 60 mm over 3 days is the rule-based medium band, not the Gemini level.
    assert body["risk_level"] == "medium"
    assert "moderate flood risk" in body["reason"]
    assert "do not use this rationale" not in body["reason"]
    assert body["reasoning_source"] == "fallback"
    assert body["reasoning_error"] == "api_error"
    assert body["cached"] is False
    mock_get.assert_called()


# ---------------------------------------------------------------------------
# 12. Gemini → Grok → rules
# ---------------------------------------------------------------------------

def _llm(source: str, level: str = "high", rationale: str = "model assessment"):
    from risk_reasoning import ReasoningResult

    return ReasoningResult(risk_level=level, rationale=rationale, source=source)


def _llm_error(code: str):
    from risk_reasoning import ReasoningResult

    return ReasoningResult(
        risk_level="", rationale="", source="fallback", error=code,
    )


def test_default_model_ids(monkeypatch):
    import risk_reasoning

    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GROK_MODEL", raising=False)
    assert risk_reasoning._gemini_model() == "gemini-3.8-flash"
    assert risk_reasoning._grok_model() == "grok-4.3"
    monkeypatch.setenv("GEMINI_MODEL", "gemini-custom")
    monkeypatch.setenv("GROK_MODEL", "grok-custom")
    assert risk_reasoning._gemini_model() == "gemini-custom"
    assert risk_reasoning._grok_model() == "grok-custom"


@patch("main.assemble_weather")
@patch("risk_reasoning._call_grok")
@patch("risk_reasoning._call_gemini", return_value=_llm("gemini"))
def test_chain_gemini_ok(_gemini, mock_grok, mock_weather, client):
    from weather_bundle import WeatherMetrics

    mock_weather.return_value = WeatherMetrics(rainfall_forecast_mm=60.0)
    resp = client.post("/predict-risk", json={"district": "Dadu"})
    body = resp.json()
    assert resp.status_code == 200
    assert body["reasoning_source"] == "gemini"
    assert body["reasoning_error"] is None
    assert body["risk_level"] == "high"
    mock_grok.assert_not_called()


@patch("main.assemble_weather")
@patch("risk_reasoning._call_grok", return_value=_llm("grok", rationale="Grok assessment."))
@patch("risk_reasoning._call_gemini", return_value=_llm_error("api_error"))
def test_chain_gemini_fail_grok_ok(_gemini, _grok, mock_weather, client):
    from weather_bundle import WeatherMetrics

    mock_weather.return_value = WeatherMetrics(rainfall_forecast_mm=60.0)
    resp = client.post("/predict-risk", json={"district": "Dadu"})
    body = resp.json()
    assert body["reasoning_source"] == "grok"
    assert body["reasoning_error"] is None
    assert body["risk_level"] == "high"
    assert "Grok assessment." in body["reason"]


@patch("main.assemble_weather")
@patch("risk_reasoning._call_grok", return_value=_llm_error("bad_json"))
@patch("risk_reasoning._call_gemini", return_value=_llm_error("api_error"))
def test_chain_both_fail_uses_rules(_gemini, _grok, mock_weather, client):
    from weather_bundle import WeatherMetrics

    mock_weather.return_value = WeatherMetrics(rainfall_forecast_mm=60.0)
    resp = client.post("/predict-risk", json={"district": "Dadu"})
    body = resp.json()
    assert body["reasoning_source"] == "fallback"
    assert body["reasoning_error"] == "bad_json"
    assert body["risk_level"] == "medium"
    assert "moderate flood risk" in body["reason"]


@patch("risk_reasoning.requests.post")
@patch("main.assemble_weather")
@patch("risk_reasoning._call_gemini", return_value=_llm_error("api_error"))
def test_chain_no_grok_key_skips_grok(_gemini, mock_weather, mock_post, client, monkeypatch):
    from weather_bundle import WeatherMetrics

    mock_weather.return_value = WeatherMetrics(rainfall_forecast_mm=60.0)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    resp = client.post("/predict-risk", json={"district": "Dadu"})
    body = resp.json()
    assert body["reasoning_source"] == "fallback"
    assert body["reasoning_error"] == "api_error"
    assert body["risk_level"] == "medium"
    mock_post.assert_not_called()


@patch("risk_reasoning.requests.post")
def test_call_grok_reads_json(mock_post, monkeypatch):
    import risk_reasoning

    monkeypatch.setenv("XAI_API_KEY", "test-key-not-real")
    monkeypatch.delenv("GROK_MODEL", raising=False)
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{
            "message": {"content": '{"risk_level":"low","rationale":"dry week"}'},
        }],
        "usage": {"prompt_tokens": 3, "completion_tokens": 4},
    }
    mock_post.return_value = mock_resp

    result = risk_reasoning._call_grok("Dadu", "prompt")
    assert result is not None
    assert result.source == "grok"
    assert result.risk_level == "low"
    assert result.rationale == "dry week"
    assert result.error is None
    assert mock_post.call_args.args[0] == "https://api.x.ai/v1/chat/completions"
    assert mock_post.call_args.kwargs["timeout"] == 15
    assert mock_post.call_args.kwargs["json"]["model"] == "grok-4.3"
    assert mock_post.call_args.kwargs["json"]["reasoning_effort"] == "none"
    assert mock_post.call_args.kwargs["headers"]["Authorization"].startswith("Bearer ")


@patch("risk_reasoning.requests.post", side_effect=requests.RequestException("sk-secret-should-not-leak"))
def test_call_grok_error_is_a_short_code(mock_post, monkeypatch):
    """Provider failures stay as api_error. The exception text is not returned."""
    import risk_reasoning

    monkeypatch.setenv("XAI_API_KEY", "test-key-not-real")
    result = risk_reasoning._call_grok("Dadu", "prompt")
    assert result is not None
    assert result.error == "api_error"
    assert result.rationale == ""
    assert "sk-secret" not in repr(result)
    mock_post.assert_called_once()


def test_unknown_district_has_null_reasoning_fields(client):
    resp = client.post("/predict-risk", json={"district": "Nowhere"})
    body = resp.json()
    assert resp.status_code == 200
    assert body["risk_level"] == "unknown"
    assert body["reasoning_source"] is None
    assert body["reasoning_error"] is None
    assert body["weather_metrics"] is None
    assert body["weather_unavailable"] is False
