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


def test_replay_scorecard_main_waves_in_barrage_order():
    import main

    previous = main._replay_cache
    try:
        main._replay_cache = None
        body = main.replay_2022()
        rows = body["scorecard"]
        order = ["Tarbela", "Kalabagh", "Chashma", "Taunsa", "Guddu", "Sukkur", "Kotri"]
        expected = [("Wave 1", b) for b in order[1:-1]]
        expected += [("Wave 2", b) for b in order[1:]]
        assert [(r["wave_label"], r["barrage"]) for r in rows] == expected
        assert main.replay_2022() == body
    finally:
        main._replay_cache = previous


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


DRAFT_KEYS = {"village_id", "name", "district", "urdu", "sindhi", "source", "model"}
AS_OF = "2022-08-31T06:00"


def _situation(as_of: str = AS_OF) -> dict:
    import requests
    r = requests.get(f"{BASE_URL}/flood-situation", params={"as_of": as_of}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _assert_drafts(body: dict, expected_ids: list, by_id: dict) -> None:
    assert set(body) == {"drafts"}, body
    drafts = body["drafts"]
    assert [d["village_id"] for d in drafts] == expected_ids
    for d in drafts:
        assert set(d) == DRAFT_KEYS, sorted(d)
        assert d["source"] in ("gemini", "qwen", "template")
        assert d["urdu"] and d["sindhi"]
        v = by_id[d["village_id"]]
        assert d["name"] == v["name"] and d["district"] == v["district"]
        # The draft carries the same ETA window the situation shows.
        for language in ("urdu", "sindhi"):
            text = d[language]
            assert len(text) <= 140
            if d["source"] == "template":
                from alerts import format_time_window
                assert format_time_window((v["eta_low"], v["eta_high"]), language) in text
            else:
                assert v["eta_low"] in text and v["eta_high"] in text, text


def test_alert_drafts_by_village_ids():
    if not _ready():
        return
    import requests

    villages = _situation()["at_risk_villages"]
    assert len(villages) >= 2
    ids = [villages[0]["id"], villages[1]["id"]]
    r = requests.post(f"{BASE_URL}/alert-drafts",
                      json={"village_ids": ids, "as_of": AS_OF}, timeout=60)
    assert r.status_code == 200, r.text
    _assert_drafts(r.json(), ids, {v["id"]: v for v in villages})


def test_alert_drafts_by_district():
    if not _ready():
        return
    import requests

    villages = _situation()["at_risk_villages"]
    district = villages[0]["district"]
    expected = [v["id"] for v in villages if v["district"] == district][:25]
    r = requests.post(f"{BASE_URL}/alert-drafts",
                      json={"district": district, "as_of": AS_OF}, timeout=300)
    assert r.status_code == 200, r.text
    _assert_drafts(r.json(), expected, {v["id"]: v for v in villages})


def test_alert_drafts_district_with_nobody_at_risk():
    if not _ready():
        return
    import requests

    # On 10 Sep 2022 the second wave has passed Kotri: no village is at risk.
    s = _situation("2022-09-10T06:00")
    assert s["at_risk_villages"] == []
    r = requests.post(f"{BASE_URL}/alert-drafts",
                      json={"district": "Hyderabad", "as_of": "2022-09-10T06:00"}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json() == {"drafts": []}


def test_alert_drafts_errors():
    if not _ready():
        return
    import requests

    url = f"{BASE_URL}/alert-drafts"
    villages = _situation()["at_risk_villages"]
    good_id = villages[0]["id"]
    _assert_error(requests.post(url, json={"village_ids": ["no-such-village"], "as_of": AS_OF},
                                timeout=10), 422, "unknown_village_ids")
    _assert_error(requests.post(url, json={"village_ids": [good_id, "nope"], "as_of": AS_OF},
                                timeout=10), 422, "unknown_village_ids")
    _assert_error(requests.post(url, json={"village_ids": [good_id], "as_of": "2021-01-01T06:00"},
                                timeout=10), 422, "as_of_out_of_range")
    _assert_error(requests.post(url, json={"village_ids": [good_id], "as_of": "2030-01-01T06:00"},
                                timeout=10), 422, "as_of_out_of_range")
    _assert_error(requests.post(url, json={"village_ids": [good_id], "as_of": "31-08-2022"},
                                timeout=10), 422, "invalid_as_of")
    _assert_error(requests.post(url, json={"district": "Nowhere", "as_of": AS_OF},
                                timeout=10), 422, "unknown_district")
    _assert_error(requests.post(url, json={"as_of": AS_OF}, timeout=10), 422, "missing_target")
    _assert_error(requests.post(url, json={"village_ids": [good_id]}, timeout=10),
                  422, "invalid_request")
    _assert_error(requests.post(url, json={"village_ids": [good_id], "as_of": "2022-09-10T06:00"},
                                timeout=10), 422, "village_not_at_risk")


if __name__ == "__main__":
    tests = [
        test_replay_scorecard_main_waves_in_barrage_order,
        test_health,
        test_flood_situation_replay,
        test_flood_situation_default_as_of,
        test_live_mode_not_enabled,
        test_bad_requests,
        test_replay_2022,
        test_alert_drafts_by_village_ids,
        test_alert_drafts_by_district,
        test_alert_drafts_district_with_nobody_at_risk,
        test_alert_drafts_errors,
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
