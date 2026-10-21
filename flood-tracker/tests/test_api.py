"""
Endpoint tests for the River Flood Tracker API (main.py).

Usage:
    # Start the server first, from flood-tracker/:
    #   python -m uvicorn main:app --port 8003
    python tests/test_api.py

Also pytest-compatible:  pytest tests/test_api.py
(every test skips itself when the server is unreachable, and the data tests
skip when the server reports that flows_2022.csv is not loaded).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_routing import assert_replay_shape, assert_situation_shape  # noqa: E402

BASE_URL = os.environ.get("FLOOD_TRACKER_URL", "http://127.0.0.1:8003")


def _skip(msg: str) -> None:
    if "pytest" in sys.modules:
        import pytest
        pytest.skip(msg)
    print(f"  [skip] {msg}")


def _server_up() -> bool:
    try:
        import requests
        return requests.get(f"{BASE_URL}/health", timeout=3).status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _ready() -> bool:
    """Server up and flood data loaded; skips (and returns False) otherwise."""
    if not _server_up():
        _skip("server not running")
        return False
    import requests
    if requests.get(f"{BASE_URL}/health", timeout=5).json().get("status") != "ok":
        _skip("server has no flood data loaded")
        return False
    return True


def _assert_error(r, status: int, code: str) -> None:
    assert r.status_code == status, f"{r.status_code}: {r.text}"
    err = r.json().get("error", {})
    assert err.get("code") == code, r.text
    assert isinstance(err.get("message"), str) and err["message"]


def test_health():
    if not _server_up():
        _skip("server not running")
        return
    import requests

    r = requests.get(f"{BASE_URL}/health", timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert set(body["data_files"]) >= {"flows_2022.csv", "barrages.json", "reaches.json",
                                       "villages.json", "indus.geojson"}
    assert all(isinstance(v, bool) for v in body["data_files"].values())
    assert body["llm_provider"] in ("gemini", "qwen", "template")
    assert isinstance(body["llm_configured"], bool)
    for name in ("GEMINI_API_KEY", "DASHSCOPE_API_KEY"):
        key = os.environ.get(name, "").strip()
        if key:
            assert key not in r.text, f"/health must never echo {name}"


def test_flood_situation_replay():
    if not _ready():
        return
    import requests

    r = requests.get(f"{BASE_URL}/flood-situation",
                     params={"mode": "replay", "as_of": "2022-08-31T06:00"}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert_situation_shape(body)
    assert body["as_of"] == "2022-08-31T06:00" and body["mode"] == "replay"
    assert [b["order"] for b in body["barrages"]] == list(range(1, 8))


def test_flood_situation_default_as_of():
    if not _ready():
        return
    import requests

    r = requests.get(f"{BASE_URL}/flood-situation", timeout=30)
    assert r.status_code == 200, r.text
    assert_situation_shape(r.json())


def test_live_mode_not_enabled():
    if not _server_up():
        _skip("server not running")
        return
    import requests

    r = requests.get(f"{BASE_URL}/flood-situation", params={"mode": "live"}, timeout=10)
    _assert_error(r, 501, "live_not_enabled")


def test_bad_requests():
    if not _ready():
        return
    import requests

    url = f"{BASE_URL}/flood-situation"
    _assert_error(requests.get(url, params={"as_of": "2021-01-01T06:00"}, timeout=10),
                  422, "as_of_out_of_range")
    _assert_error(requests.get(url, params={"as_of": "2030-01-01T06:00"}, timeout=10),
                  422, "as_of_out_of_range")
    _assert_error(requests.get(url, params={"as_of": "31-08-2022"}, timeout=10),
                  422, "invalid_as_of")
    _assert_error(requests.get(url, params={"mode": "forecast"}, timeout=10),
                  422, "invalid_mode")


def test_replay_2022():
    if not _ready():
        return
    import requests

    r = requests.get(f"{BASE_URL}/replay/2022", timeout=120)
    assert r.status_code == 200, r.text
    body = r.json()
    assert_replay_shape(body)
    # Cached: a second call returns the identical body.
    again = requests.get(f"{BASE_URL}/replay/2022", timeout=30).json()
    assert again == body
    # Each step equals /flood-situation at the same as_of.
    step = body["steps"][len(body["steps"]) // 2]
    single = requests.get(f"{BASE_URL}/flood-situation",
                          params={"as_of": step["as_of"]}, timeout=30).json()
    assert single == step


if __name__ == "__main__":
    tests = [
        test_health,
        test_flood_situation_replay,
        test_flood_situation_default_as_of,
        test_live_mode_not_enabled,
        test_bad_requests,
        test_replay_2022,
    ]

    passed, failed = 0, 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
            passed += 1
        except AssertionError as exc:
            print(f"FAIL  {fn.__name__}: {exc}")
            failed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR {fn.__name__}: {exc!r}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
