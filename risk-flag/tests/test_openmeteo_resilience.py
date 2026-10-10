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

import threading
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
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
    """A 429 does not retry inside the request, and it is not stored as rain."""
    blocked = _mock_response(429, headers={"Retry-After": "1"})
    blocked.text = "minutely API limit exceeded"
    mock_get.side_effect = [
        blocked,
        _mock_response(200, json_data=_DISCHARGE_EMPTY),
    ]

    resp = client.post("/predict-risk", json={"district": "Dadu"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rainfall_forecast_mm"] is None
    assert body["weather_metrics"]["rainfall_forecast_mm"] is None
    assert body["rainfall_unavailable"] is True
    assert body["weather_unavailable"] is True
    assert "minutely" not in body["reason"]
    assert "limit exceeded" not in body["reason"]
    # One forecast 429. Discharge is a different endpoint and still runs once.
    assert mock_get.call_count == 2
    mock_sleep.assert_not_called()
    assert weather_bundle.rate_limit_remaining(weather_bundle._FORECAST_URL) > 0
    assert weather_bundle.rate_limit_remaining(weather_bundle._FLOOD_URL) == 0


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
    # One attempt per endpoint. A 429 is not retried inside the request.
    assert mock_get.call_count == 2
    mock_sleep.assert_not_called()


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
    """A numeric Retry-After sets the cooldown and is not slept inside the request."""
    mock_get.side_effect = [
        _mock_response(429, headers={"Retry-After": "3"}),
        _mock_response(200, json_data=_DISCHARGE_EMPTY),
    ]

    resp = client.post("/predict-risk", json={"district": "Dadu"})
    assert resp.status_code == 200
    mock_sleep.assert_not_called()
    remaining = weather_bundle.rate_limit_remaining(weather_bundle._FORECAST_URL)
    assert 2.5 <= remaining <= 3.0


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


# ---------------------------------------------------------------------------
# 12. 429 cooldown and in-flight deduplication
# ---------------------------------------------------------------------------

def test_retry_after_parser_accepts_seconds_and_http_dates():
    now = datetime(2026, 10, 11, tzinfo=timezone.utc).timestamp()
    assert weather_bundle.retry_after_delay("1.5", now=now) == 1.5
    assert weather_bundle.retry_after_delay("0", now=now) == 0.0
    assert weather_bundle.retry_after_delay("-5", now=now) is None
    assert weather_bundle.retry_after_delay("soon", now=now) is None
    assert weather_bundle.retry_after_delay("", now=now) is None
    assert weather_bundle.retry_after_delay(None, now=now) is None
    future = format_datetime(datetime(2026, 10, 11, 0, 2, tzinfo=timezone.utc), usegmt=True)
    assert weather_bundle.retry_after_delay(future, now=now) == 120
    past = format_datetime(datetime(2020, 1, 1, tzinfo=timezone.utc), usegmt=True)
    assert weather_bundle.retry_after_delay(past, now=now) < 0


@patch("time.sleep")
@patch("requests.get")
def test_long_retry_after_returns_without_sleeping(mock_get, mock_sleep):
    mock_get.return_value = _mock_response(429, headers={"Retry-After": "100000"})
    started = time.perf_counter()
    data, status, text = weather_bundle._openmeteo_exchange(
        weather_bundle._FORECAST_URL, {"latitude": 1, "longitude": 2},
    )
    elapsed = time.perf_counter() - started
    assert data is None
    assert status == 429
    assert text == ""
    assert elapsed < 0.5
    mock_sleep.assert_not_called()
    assert mock_get.call_count == 1
    remaining = weather_bundle.rate_limit_remaining(weather_bundle._FORECAST_URL)
    assert remaining == weather_bundle.MAX_429_COOLDOWN_SECS or (
        weather_bundle.MAX_429_COOLDOWN_SECS - 1 <= remaining <= weather_bundle.MAX_429_COOLDOWN_SECS
    )
    assert weather_bundle._cache_get(1, 2, weather_bundle.FORECAST_WINDOW) is None


@patch("time.sleep")
@patch("requests.get")
def test_invalid_retry_after_uses_the_default_cooldown(mock_get, mock_sleep):
    mock_get.return_value = _mock_response(429, headers={"Retry-After": "soon"})
    assert weather_bundle.fetch_forecast_bundle(1.0, 2.0) is None
    remaining = weather_bundle.rate_limit_remaining(weather_bundle._FORECAST_URL)
    assert 59 <= remaining <= weather_bundle.DEFAULT_429_COOLDOWN_SECS
    assert weather_bundle.fetch_forecast_bundle(9.0, 9.0) is None
    assert mock_get.call_count == 1
    mock_sleep.assert_not_called()


@patch("time.sleep")
@patch("requests.get")
def test_forecast_cooldown_does_not_block_archive(mock_get, mock_sleep):
    def router(url, params=None, timeout=None, headers=None):
        if "archive-api" in url:
            start = params["start_date"]
            end = params["end_date"]
            dates = weather_bundle.inclusive_dates(start, end)
            return _mock_response(200, {
                "daily": {"time": dates, "precipitation_sum": [1.0] * len(dates)},
            })
        return _mock_response(429, headers={"Retry-After": "30"})

    mock_get.side_effect = router
    assert weather_bundle.fetch_forecast_bundle(29.3, 64.7) is None
    historical = weather_bundle.fetch_historical_rainfall(29.3, 64.7)
    assert historical["rainfall_90d_mm"] == 90.0
    assert historical["rainfall_30d_mm"] == 30.0
    assert weather_bundle.fetch_forecast_bundle(24.7, 69.8) is None
    urls = [call.args[0] for call in mock_get.call_args_list]
    assert urls.count(weather_bundle._FORECAST_URL) == 1
    assert urls.count(weather_bundle._ARCHIVE_URL) == 1
    mock_sleep.assert_not_called()


@patch("time.sleep")
@patch("requests.get")
def test_archive_cooldown_does_not_block_forecast(mock_get, mock_sleep):
    def router(url, params=None, timeout=None, headers=None):
        if "archive-api" in url:
            return _mock_response(429)
        return _mock_response(200, json_data=_FORECAST_OK)

    mock_get.side_effect = router
    assert weather_bundle.fetch_historical_rainfall(29.3, 64.7) is None
    forecast = weather_bundle.fetch_forecast_bundle(29.3, 64.7)
    assert forecast["rainfall_forecast_mm"] == 60.0
    assert weather_bundle.fetch_historical_rainfall(24.7, 69.8) is None
    urls = [call.args[0] for call in mock_get.call_args_list]
    assert urls.count(weather_bundle._ARCHIVE_URL) == 1
    assert urls.count(weather_bundle._FORECAST_URL) == 1


@patch("requests.get")
def test_cooldown_expiry_allows_a_new_call(mock_get):
    mock_get.return_value = _mock_response(200, json_data=_FORECAST_OK)
    weather_bundle._rate_limit_until[weather_bundle._FORECAST_URL] = time.monotonic() - 1
    summary = weather_bundle.fetch_forecast_bundle(1.0, 2.0)
    assert summary["rainfall_forecast_mm"] == 60.0
    assert mock_get.call_count == 1
    assert weather_bundle.rate_limit_remaining(weather_bundle._FORECAST_URL) == 0


@patch("time.sleep")
@patch("requests.get")
def test_past_http_date_does_not_keep_the_endpoint_closed(mock_get, mock_sleep):
    past = format_datetime(datetime.now(timezone.utc) - timedelta(minutes=5), usegmt=True)
    mock_get.side_effect = [
        _mock_response(429, headers={"Retry-After": past}),
        _mock_response(200, json_data=_FORECAST_OK),
    ]
    assert weather_bundle.fetch_forecast_bundle(1.0, 2.0) is None
    summary = weather_bundle.fetch_forecast_bundle(1.0, 2.0)
    assert summary["rainfall_forecast_mm"] == 60.0
    assert mock_get.call_count == 2
    mock_sleep.assert_not_called()


def test_identical_inflight_requests_share_one_upstream_call():
    entered = threading.Event()
    release = threading.Event()
    calls = {"n": 0}

    def slow_get(url, params=None, timeout=None, headers=None):
        calls["n"] += 1
        entered.set()
        assert release.wait(2)
        return _mock_response(200, json_data=_FORECAST_OK)

    results = []
    errors = []

    def run():
        try:
            results.append(weather_bundle.fetch_forecast_bundle(1.0, 2.0))
        except Exception as exc:  # pragma: no cover - failure is asserted below
            errors.append(exc)

    with patch("requests.get", side_effect=slow_get):
        first = threading.Thread(target=run)
        second = threading.Thread(target=run)
        first.start()
        assert entered.wait(2)
        second.start()
        time.sleep(0.05)
        assert calls["n"] == 1
        release.set()
        first.join(2)
        second.join(2)

    assert errors == []
    assert calls["n"] == 1
    assert [row["rainfall_forecast_mm"] for row in results] == [60.0, 60.0]
    assert weather_bundle._inflight == {}


def test_inflight_waiter_gives_up_without_a_second_call():
    entered = threading.Event()
    release = threading.Event()
    calls = {"n": 0}

    def slow_get(url, params=None, timeout=None, headers=None):
        calls["n"] += 1
        entered.set()
        assert release.wait(2)
        return _mock_response(200, json_data=_FORECAST_OK)

    waiter_result = []

    def lead():
        weather_bundle.fetch_forecast_bundle(4.0, 5.0)

    def follow():
        waiter_result.append(weather_bundle.fetch_forecast_bundle(4.0, 5.0))

    with patch("requests.get", side_effect=slow_get), patch.object(
        weather_bundle, "INFLIGHT_WAIT_SECS", 0.05,
    ):
        leader = threading.Thread(target=lead)
        leader.start()
        assert entered.wait(2)
        follower = threading.Thread(target=follow)
        follower.start()
        follower.join(2)
        assert waiter_result == [None]
        assert calls["n"] == 1
        release.set()
        leader.join(2)

    assert calls["n"] == 1
    assert weather_bundle._inflight == {}
    cached = weather_bundle._cache_get(4.0, 5.0, weather_bundle.FORECAST_WINDOW)
    assert cached["rainfall_forecast_mm"] == 60.0


def test_inflight_failure_clears_the_slot_for_a_later_call():
    def boom():
        raise RuntimeError("upstream failed")

    with pytest.raises(RuntimeError, match="upstream failed"):
        weather_bundle._join_or_lead(8.0, 8.0, weather_bundle.FORECAST_WINDOW, boom)
    assert weather_bundle._inflight == {}

    ran = {"n": 0}

    def recover():
        ran["n"] += 1
        return {"rainfall_forecast_mm": 4.0}

    assert weather_bundle._join_or_lead(
        8.0, 8.0, weather_bundle.FORECAST_WINDOW, recover,
    ) == {"rainfall_forecast_mm": 4.0}
    assert ran["n"] == 1
    assert weather_bundle._inflight == {}
