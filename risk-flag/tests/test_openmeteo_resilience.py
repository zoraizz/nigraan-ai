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
from fastapi.testclient import TestClient

# Import the app and internals we need to inspect / reset
import main as risk_main
from main import app


@pytest.fixture(autouse=True)
def _clear_caches():
    """Reset both the response cache and rainfall cache between tests."""
    with risk_main._cache_lock:
        risk_main._cache.clear()
    with risk_main._rainfall_cache_lock:
        risk_main._rainfall_cache.clear()
    yield
    with risk_main._cache_lock:
        risk_main._cache.clear()
    with risk_main._rainfall_cache_lock:
        risk_main._rainfall_cache.clear()


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

_ARCHIVE_OK_30 = {
    "daily": {"precipitation_sum": [1.0] * 30},
}

_ARCHIVE_OK_90 = {
    "daily": {"precipitation_sum": [1.0] * 90},
}


# ---------------------------------------------------------------------------
# 1. Retry on 429
# ---------------------------------------------------------------------------

@patch("main.assess_risk_with_gemini", return_value=None)
@patch("time.sleep")  # Don't actually sleep in tests
@patch("requests.get")
def test_retry_on_429_then_success(mock_get, mock_sleep, _mock_gemini, client):
    """429 on first attempt → retry → 200 on second → returns rainfall."""
    mock_get.side_effect = [
        _mock_response(429, headers={"Retry-After": "1"}),
        _mock_response(200, json_data=_FORECAST_OK),
    ]

    resp = client.post("/predict-risk", json={"district": "Dadu"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rainfall_forecast_mm"] == 60.0
    assert body["rainfall_unavailable"] is False
    # Should have been called twice (first 429, then 200)
    assert mock_get.call_count == 2


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
    assert body["rainfall_unavailable"] is True
    assert "unavailable" in body["reason"].lower()
    # 1 initial + 2 retries = 3 calls
    assert mock_get.call_count == 3


# ---------------------------------------------------------------------------
# 2. Retry on 5xx
# ---------------------------------------------------------------------------

@patch("main.assess_risk_with_gemini", return_value=None)
@patch("time.sleep")
@patch("requests.get")
def test_retry_on_500_then_success(mock_get, mock_sleep, _mock_gemini, client):
    """500 on first attempt → retry → 200 on second → returns rainfall."""
    mock_get.side_effect = [
        _mock_response(500),
        _mock_response(200, json_data=_FORECAST_OK),
    ]

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
    window = "forecast_3d"
    # Insert a stale entry (expired 1 hour ago)
    stale_ts = time.time() - risk_main._RAINFALL_CACHE_TTL_SECS - 3600
    with risk_main._rainfall_cache_lock:
        risk_main._rainfall_cache[(lat, lon, window)] = (42.5, stale_ts)

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
        # 30-day: fail then succeed
        _mock_response(503),
        _mock_response(200, json_data=_ARCHIVE_OK_30),
        # 90-day: succeed immediately
        _mock_response(200, json_data=_ARCHIVE_OK_90),
    ]

    resp = client.post("/predict-risk", json={"district": "Tharparkar"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rainfall_30d_mm"] == 30.0
    assert body["rainfall_90d_mm"] == 90.0
    assert body["rainfall_unavailable"] is False


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
    assert "unavailable" in body["reason"].lower()


# ---------------------------------------------------------------------------
# 6. Request timeout handling
# ---------------------------------------------------------------------------

@patch("main.assess_risk_with_gemini", return_value=None)
@patch("time.sleep")
@patch("requests.get")
def test_request_timeout_triggers_retry(mock_get, mock_sleep, _mock_gemini, client):
    """requests.Timeout on first attempt → retry → 200."""
    import requests as req_lib
    mock_get.side_effect = [
        req_lib.Timeout("Connection timed out"),
        _mock_response(200, json_data=_FORECAST_OK),
    ]

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
    mock_get.side_effect = [
        _mock_response(429, headers={"Retry-After": "3"}),
        _mock_response(200, json_data=_FORECAST_OK),
    ]

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
    window = "forecast_3d"
    risk_main._rainfall_cache_set(lat, lon, window, 55.0)

    resp = client.post("/predict-risk", json={"district": "Dadu"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rainfall_forecast_mm"] == 55.0
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
    # Only 1 call — no retries for 400
    assert mock_get.call_count == 1
