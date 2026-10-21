"""
Unit tests for live GloFAS mode, the forecast block and POST /what-if.

No network: live.fetch_live's HTTP call is replaced by a fake series built
from the committed calibration. Runs in-process with FastAPI's TestClient.

Usage:
    python tests/test_live.py unit
    pytest tests/test_live.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

import live  # noqa: E402
import main  # noqa: E402
import routing  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from test_routing import SITUATION_KEYS, assert_situation_shape  # noqa: E402

client = TestClient(main.app)
ORDER = ["Tarbela", "Kalabagh", "Chashma", "Taunsa", "Guddu", "Sukkur", "Kotri"]


def _series(peaks: dict | None = None) -> dict:
    """60 daily rows per barrage (today-30 .. today+29) at 100k cusecs,
    with optional {barrage: (day_offset, cusecs)} spikes."""
    today = live.today_clock().date()
    out = {}
    for name in ORDER:
        rows = []
        for i in range(-30, 30):
            q = 100000.0
            if peaks and name in peaks and peaks[name][0] == i:
                q = float(peaks[name][1])
            rows.append({"date": (today + timedelta(days=i)).isoformat(), "cusecs": q})
        out[name] = rows
    return out


def _patch_fetch(series=None, exc=None):
    original = live.fetch_live

    def fake(calibration):
        if exc:
            live.last_fetch = "failed"
            raise exc
        live.last_fetch = "ok"
        return series

    live.fetch_live = fake
    return original


def _core_shape(body: dict) -> None:
    """Contract keys hold the replay shape; live/what-if add their own blocks."""
    assert_situation_shape({k: body[k] for k in SITUATION_KEYS})


def _err(r, status: int, code: str) -> None:
    assert r.status_code == status, f"{r.status_code}: {r.text}"
    assert r.json()["error"]["code"] == code, r.text


# --------------------------------------------------------------------- tests

def test_calibration_loaded():
    cal = main.CALIBRATION
    assert cal is not None
    for name in ORDER:
        row = cal[name]
        assert row["scale"] > 0 and -1 <= row["corr"] <= 1
        assert row["calibrated"] == (0.25 <= row["scale"] <= 4 and row["corr"] >= 0.3)
    assert "_notes" in cal


def test_calibration_missing_barrage_raises(tmp_path=None):
    import json
    import tempfile
    d = Path(tmp_path or tempfile.mkdtemp())
    p = d / "cal.json"
    p.write_text(json.dumps({"Tarbela": main.CALIBRATION["Tarbela"]}))
    try:
        live.load_calibration(p, main.DATA.barrages)
    except live.LiveUnavailable:
        return
    raise AssertionError("expected LiveUnavailable")


def test_live_situation_shape():
    original = _patch_fetch(_series({"Guddu": (3, 400000)}))
    try:
        r = client.get("/flood-situation", params={"mode": "live"})
    finally:
        live.fetch_live = original
    assert r.status_code == 200, r.text
    body = r.json()
    _core_shape(body)
    assert body["mode"] == "live"
    assert body["as_of"] == routing.fmt_time(live.today_clock())
    assert "GloFAS" in body["data_provenance"]["flows"]
    assert "not FFC gauge readings" in body["data_provenance"]["flows"]
    assert [f["name"] for f in body["forecast"]] == ORDER
    for f in body["forecast"]:
        assert f["series"][0]["date"] == live.today_clock().date().isoformat()
        assert len(f["series"]) == 30
        assert f["confidence"] in ("bias-scaled", "low confidence")
    assert [o["name"] for o in body["outlook"]] == ["Guddu"]


def test_forecast_first_crossing():
    today = date(2026, 10, 21)
    barrages = [b for b in main.DATA.barrages if b["name"] in ("Guddu", "Sukkur", "Kotri")]
    rows = lambda vals: [{"date": (today + timedelta(days=i)).isoformat(), "cusecs": v}  # noqa: E731
                         for i, v in enumerate(vals)]
    series = {
        "Guddu": rows([150000, 210000, 360000, 300000]),   # Low on day 1, peak Medium day 2
        "Sukkur": rows([250000, 240000, 230000, 220000]),  # already Low today
        "Kotri": rows([100000, 120000, 150000, 199999]),   # never reaches Low
    }
    out, outlook = live.forecast_rows(barrages, series, today.isoformat())
    by = {r["name"]: r for r in out}
    assert by["Guddu"]["first_crossing"] == {"category": "Low Flood", "date": "2026-10-22"}
    assert by["Guddu"]["forecast_peak_category"] == "Medium Flood"
    assert by["Guddu"]["forecast_peak_date"] == "2026-10-23"
    assert by["Sukkur"]["first_crossing"] == {"category": "Low Flood", "date": "2026-10-21"}
    assert by["Kotri"]["first_crossing"] is None
    assert [r["name"] for r in outlook] == ["Sukkur", "Guddu"]


def test_live_503_on_fetch_failure():
    original = _patch_fetch(exc=live.LiveUnavailable("GloFAS forecast unavailable: timeout"))
    try:
        r = client.get("/flood-situation", params={"mode": "live"})
        _err(r, 503, "live_unavailable")
        assert client.get("/health").json()["live_available"] == "failed"
    finally:
        live.fetch_live = original


def test_health_fields():
    body = client.get("/health").json()
    assert body["live_available"] in ("ok", "failed", "never")
    assert body["calibration_loaded"] is True


def test_what_if_taunsa_650k():
    r = client.post("/what-if", json={"barrage": "Taunsa", "peak_cusecs": 650000,
                                      "peak_time": "2026-10-21T06:00"})
    assert r.status_code == 200, r.text
    body = r.json()
    _core_shape(body)
    assert body["mode"] == "what_if"
    assert body["as_of"] == "2026-10-22T06:00"
    sc = body["scenario"]
    assert sc["peak_category"] == "Very High Flood"
    assert sc["peak_time"] == "2026-10-21T06:00"
    assert "not modelled" in sc["assumption"]
    downstream = ORDER[ORDER.index("Taunsa") + 1:]
    assert {e["barrage"] for e in body["etas"]} == set(downstream)
    taunsa_km = next(b for b in main.DATA.barrages if b["name"] == "Taunsa")["river_km"]
    assert body["at_risk_villages"], "expected villages downstream of Taunsa"
    by_id = {v["id"]: v for v in main.DATA.villages}
    for v in body["at_risk_villages"]:
        assert by_id[v["id"]]["river_km"] >= taunsa_km, v


def test_what_if_below_medium_lists_no_villages():
    r = client.post("/what-if", json={"barrage": "Taunsa", "peak_cusecs": 300000})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scenario"]["peak_category"] == "Low Flood"
    assert body["at_risk_villages"] == []
    assert body["note"] == "Below Medium Flood: villages not listed"
    assert body["etas"], "etas are kept below Medium Flood"


def test_what_if_422():
    for payload in ({"barrage": "Nowhere", "peak_cusecs": 650000},
                    {"barrage": "Taunsa", "peak_cusecs": 0},
                    {"barrage": "Taunsa", "peak_cusecs": -5},
                    {"barrage": "Taunsa", "peak_cusecs": 2000001}):
        r = client.post("/what-if", json=payload)
        assert r.status_code == 422, (payload, r.text)
        assert "error" in r.json(), r.text


class _FakeResponse:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


def _fetch_with_api_start(first_day: date):
    """fetch_live against a mocked Open-Meteo reply whose 60 daily dates
    start at first_day (the API counts past_days from its GMT date)."""
    times = [(first_day + timedelta(days=i)).isoformat() for i in range(60)]
    names = [n for n in main.CALIBRATION if not n.startswith("_")]
    body = [{"daily": {"time": times, "river_discharge": [1000.0] * 60}} for _ in names]
    original_get, original_cache = live.requests.get, live._cache
    live.requests.get = lambda *a, **k: _FakeResponse(body)
    live._cache = None
    try:
        return live.fetch_live(main.CALIBRATION)
    finally:
        live.requests.get, live._cache = original_get, original_cache


def test_fetch_live_gmt_date_is_yesterday():
    # 00:00-05:00 PKT: GMT is still yesterday, so the API's window starts a day early.
    today = live.today_clock().date()
    series = _fetch_with_api_start(today - timedelta(days=31))
    for name, rows in series.items():
        assert len(rows) == 60
        assert rows[0]["date"] == (today - timedelta(days=31)).isoformat()
        assert any(r["date"] == today.isoformat() for r in rows), name
        scale = main.CALIBRATION[name]["scale"]
        assert abs(rows[0]["cusecs"] - round(1000.0 * live.CUSECS * scale, 2)) < 0.01
    assert live.last_fetch == "ok"


def test_fetch_live_rejects_series_without_today():
    today = live.today_clock().date()
    try:
        _fetch_with_api_start(today - timedelta(days=90))
    except live.LiveUnavailable as exc:
        assert "today" in str(exc)
        return
    raise AssertionError("expected LiveUnavailable")


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]
    passed, failed = 0, 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {fn.__name__}: {exc!r}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
