"""
Tests for the River Flood Tracker routing module (routing.py).

Usage:
    # Unit tests (no server needed):
    python tests/test_routing.py unit

Also pytest-compatible:  pytest tests/test_routing.py

Everything except test_real_flows_2022 runs on a synthetic two-wave series
built here, so the tests do not depend on the real CSV. That test runs on
data/flows_2022.csv and skips itself when the file is absent.

Synthetic series: daily 06:00 readings from 2022-08-01 (day 0). Each wave
is a triangle on 150000 cusecs base: 300000 / 450000 / 600000 / 450000 /
300000 at peak-2 .. peak+2 days. Wave 1 peaks at Tarbela on day 3, wave 2
on day 12, and each barrage downstream sees the crest one day later (every
reach's lag_median_h is 24), so wave 1 reaches Kotri on day 9 and wave 2
on day 18. Between waves the flow returns to 150000, below every Low
threshold, so the two waves are separate events at every barrage.
"""

from __future__ import annotations

import copy
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import routing  # noqa: E402
from routing import (  # noqa: E402
    CATEGORIES,
    FloodData,
    Reading,
    category,
    detect_events,
    fmt_time,
    replay_2022,
    situation,
    trend,
)

DATA_DIR = Path(__file__).parent.parent / "data"

DAY0 = datetime(2022, 8, 1, 6, 0)
N_DAYS = 23
WAVE_PEAK_DAYS = (3, 12)          # at Tarbela; +1 day per barrage downstream
BASE, AMP = 150000, 450000

NAMES = ["Tarbela", "Kalabagh", "Chashma", "Taunsa", "Guddu", "Sukkur", "Kotri"]
RIVER_KM = [0, 200, 300, 500, 700, 900, 1400]
UPPER = {"low": 250000, "medium": 375000, "high": 500000,
         "very_high": 650000, "exceptionally_high": 800000}
GUDDU_SUKKUR = {"low": 200000, "medium": 350000, "high": 500000,
                "very_high": 700000, "exceptionally_high": 900000}
KOTRI = {"low": 200000, "medium": 300000, "high": 450000,
         "very_high": 650000, "exceptionally_high": 800000}
THRESHOLDS = [UPPER] * 4 + [GUDDU_SUKKUR, GUDDU_SUKKUR, KOTRI]

LAG_MEDIAN = [24, 24, 24, 24, 24, 24]
LAG_MIN = [12, 18, 0, 12, 6, 24]
LAG_MAX = [36, 30, 48, 36, 42, 60]

TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")


def day(d: float) -> datetime:
    return DAY0 + timedelta(days=d)


def t(d: float) -> str:
    return fmt_time(day(d))


def _bump(x: float) -> float:
    return max(0.0, 1.0 - abs(x) / 3.0)


def synthetic_outflow(order: int, d: int) -> int:
    lag_days = order - 1
    return int(BASE + sum(AMP * _bump(d - p - lag_days) for p in WAVE_PEAK_DAYS))


def peak_day(order: int, wave: int) -> int:
    return WAVE_PEAK_DAYS[wave - 1] + order - 1


def make_data(villages=None, n_days: int = N_DAYS) -> FloodData:
    barrages = [
        {"name": n, "order": i + 1, "lat": 34.0 - i, "lon": 72.0 - 0.5 * i,
         "river_km": RIVER_KM[i], "thresholds": dict(THRESHOLDS[i])}
        for i, n in enumerate(NAMES)
    ]
    reaches = [
        {"from": NAMES[i], "to": NAMES[i + 1], "lag_median_h": LAG_MEDIAN[i],
         "lag_min_h": LAG_MIN[i], "lag_max_h": LAG_MAX[i]}
        for i in range(6)
    ]
    readings = {
        n: [
            Reading(day(d), synthetic_outflow(i + 1, d) + 5000,
                    synthetic_outflow(i + 1, d), "https://ffc.gov.pk/synthetic")
            for d in range(n_days)
        ]
        for i, n in enumerate(NAMES)
    }
    return FloodData(barrages=barrages, reaches=reaches, readings=readings,
                     villages=villages, river_coords=None)


FAKE_VILLAGES = [
    {"id": "v-a", "name": "A", "district": "X", "lat": 32.5, "lon": 71.4,
     "river_km": 250, "bank": "left", "population": 1000,
     "population_source": "synthetic test figure"},
    {"id": "v-b", "name": "B", "district": "Y", "lat": 29.5, "lon": 70.2,
     "river_km": 600, "bank": "right", "population": 500,
     "population_source": "synthetic test figure"},
    {"id": "v-c", "name": "C", "district": "X", "lat": 29.4, "lon": 70.1,
     "river_km": 600, "bank": "left", "population": 9000,
     "population_source": "synthetic test figure"},
]


def _skip(msg: str) -> None:
    if "pytest" in sys.modules:
        import pytest
        pytest.skip(msg)
    print(f"  [skip] {msg}")


# ---------------------------------------------------------------------------
# Contract shape (shared with test_api.py)
# ---------------------------------------------------------------------------
SITUATION_KEYS = {"as_of", "mode", "barrages", "reaches", "peaks", "etas",
                  "at_risk_villages", "district_eta_hours", "data_provenance"}
BARRAGE_KEYS = {"name", "order", "lat", "lon", "inflow_cusecs", "outflow_cusecs",
                "category", "trend"}
REACH_KEYS = {"from", "to", "category", "coords"}
PEAK_KEYS = {"barrage", "wave_id", "status", "peak_time", "peak_outflow_cusecs"}
ETA_KEYS = {"wave_id", "from_barrage", "barrage", "status", "eta", "eta_low",
            "eta_high", "hours_from_now", "observed_time"}
VILLAGE_KEYS = {"id", "name", "district", "lat", "lon", "eta", "eta_low",
                "eta_high", "hours_to_arrival", "population", "population_source"}
PROVENANCE_KEYS = {"flows", "etas", "villages", "population"}
SCORECARD_KEYS = {"barrage", "wave_id", "actual_peak_time", "predicted_time",
                  "predicted_low", "predicted_high", "error_hours"}


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def assert_situation_shape(s: dict) -> None:
    assert set(s) == SITUATION_KEYS, f"top-level keys: {sorted(s)}"
    assert TIME_RE.match(s["as_of"]), s["as_of"]
    assert s["mode"] in ("replay", "live")
    for b in s["barrages"]:
        assert set(b) == BARRAGE_KEYS, sorted(b)
        assert isinstance(b["name"], str) and isinstance(b["order"], int)
        assert all(_num(b[k]) for k in ("lat", "lon", "inflow_cusecs", "outflow_cusecs"))
        assert b["category"] in CATEGORIES
        assert b["trend"] in ("rising", "falling", "stable")
    for r in s["reaches"]:
        assert set(r) == REACH_KEYS, sorted(r)
        assert r["category"] in CATEGORIES
        assert len(r["coords"]) >= 2
        assert all(len(p) == 2 and all(_num(c) for c in p) for p in r["coords"])
    for p in s["peaks"]:
        assert set(p) == PEAK_KEYS, sorted(p)
        assert p["status"] in ("forming", "passed")
        assert TIME_RE.match(p["peak_time"]) and _num(p["peak_outflow_cusecs"])
    for e in s["etas"]:
        assert set(e) == ETA_KEYS, sorted(e)
        assert e["status"] in ("estimated", "arrived")
        for k in ("eta", "eta_low", "eta_high"):
            assert TIME_RE.match(e[k]), e[k]
        assert e["eta_low"] <= e["eta"] <= e["eta_high"]
        assert _num(e["hours_from_now"])
        if e["status"] == "arrived":
            assert TIME_RE.match(e["observed_time"])
        else:
            assert e["observed_time"] is None
    for v in s["at_risk_villages"]:
        assert set(v) == VILLAGE_KEYS, sorted(v)
        for k in ("eta", "eta_low", "eta_high"):
            assert TIME_RE.match(v[k]), v[k]
        assert v["eta_low"] <= v["eta"] <= v["eta_high"]
        assert _num(v["hours_to_arrival"]) and _num(v["population"])
    assert isinstance(s["district_eta_hours"], dict)
    assert all(_num(h) for h in s["district_eta_hours"].values())
    assert set(s["data_provenance"]) == PROVENANCE_KEYS
    assert all(isinstance(x, str) and x for x in s["data_provenance"].values())


def assert_replay_shape(r: dict) -> None:
    assert set(r) == {"steps", "scorecard"}
    assert r["steps"], "replay must have steps"
    for s in r["steps"]:
        assert_situation_shape(s)
        assert s["as_of"].endswith("T06:00")
    for row in r["scorecard"]:
        assert set(row) == SCORECARD_KEYS, sorted(row)
        assert _num(row["error_hours"])


# ---------------------------------------------------------------------------
# Category and trend
# ---------------------------------------------------------------------------
def _check_boundaries(barrage: dict) -> None:
    th = barrage["thresholds"]
    keys = routing.THRESHOLD_KEYS
    assert category(barrage, 0) == "Normal"
    for idx, key in enumerate(keys):
        below, at = CATEGORIES[idx], CATEGORIES[idx + 1]
        assert category(barrage, th[key] - 1) == below, (barrage["name"], key, "below")
        assert category(barrage, th[key]) == at, (barrage["name"], key, "at")
    assert category(barrage, 10_000_000) == "Exceptionally High Flood"


def test_category_boundaries_upstream_and_sindh():
    data = make_data()
    by_name = {b["name"]: b for b in data.barrages}
    _check_boundaries(by_name["Taunsa"])     # 250000/375000/500000/650000/800000
    _check_boundaries(by_name["Kotri"])      # 200000/300000/450000/650000/800000
    _check_boundaries(by_name["Sukkur"])     # 200000/350000/500000/700000/900000
    # Same outflow, different category up- vs downstream:
    assert category(by_name["Taunsa"], 300000) == "Low Flood"
    assert category(by_name["Kotri"], 300000) == "Medium Flood"


def test_trend_two_percent_band():
    assert trend(None, 100) == "stable"
    assert trend(100000, 102000) == "stable"
    assert trend(100000, 98000) == "stable"
    assert trend(100000, 102001) == "rising"
    assert trend(100000, 97999) == "falling"
    assert trend(0, 5000) == "rising"


# ---------------------------------------------------------------------------
# Peak detection
# ---------------------------------------------------------------------------
def _series(values):
    return [Reading(day(i), v, v) for i, v in enumerate(values)]


UPPER_BARRAGE = {"name": "Taunsa", "order": 4, "thresholds": UPPER}


def test_dip_of_ten_percent_starts_new_wave():
    # 500k -> 440k is a 12% dip, then it rises again: two events.
    evs = detect_events(_series([300000, 400000, 500000, 440000, 460000, 520000, 480000]),
                        UPPER_BARRAGE)
    assert len(evs) == 2, evs
    assert evs[0].peak_outflow == 500000 and evs[0].status == "passed"
    assert evs[1].start_time == day(4) and evs[1].peak_time == day(5)

    # 500k -> 460k is only an 8% dip: still one event, whose max moves on.
    evs = detect_events(_series([300000, 400000, 500000, 460000, 480000, 520000, 480000]),
                        UPPER_BARRAGE)
    assert len(evs) == 1, evs
    assert evs[0].peak_outflow == 520000 and evs[0].peak_time == day(5)


def test_drop_below_low_starts_new_wave():
    evs = detect_events(_series([300000, 400000, 200000, 300000, 400000, 300000]),
                        UPPER_BARRAGE)
    assert len(evs) == 2
    assert [e.peak_time for e in evs] == [day(1), day(4)]
    assert all(e.status == "passed" for e in evs)


def test_forming_needs_two_rises_and_passed_needs_two_percent_drop():
    s = _series([150000, 300000, 450000, 600000, 595000, 580000])
    assert detect_events(s, UPPER_BARRAGE, day(1))[0].status == "none"     # one rise
    assert detect_events(s, UPPER_BARRAGE, day(2))[0].status == "forming"  # two rises
    assert detect_events(s, UPPER_BARRAGE, day(4))[0].status == "forming"  # -0.8%: not yet
    ev = detect_events(s, UPPER_BARRAGE, day(5))[0]                        # -3.3%: passed
    assert ev.status == "passed" and ev.peak_time == day(3) and ev.confirmed_time == day(5)


def test_both_waves_found_at_every_barrage():
    data = make_data()
    _, waves = routing._waves_at(data, day(N_DAYS - 1))
    assert [w.wave_id for w in waves] == ["indus-2022-w1", "indus-2022-w2"]
    for n, w in enumerate(waves, start=1):
        assert sorted(w.events) == list(range(1, 8)), w.events
        for order, e in w.events.items():
            assert e.status == "passed"
            assert e.peak_time == day(peak_day(order, n)), (order, n, e.peak_time)
            assert e.peak_outflow == BASE + AMP
    # Wave 2 crests at Kotri on day 18. Two days later it is still shown
    # (FINAL_DISPLAY_H = 72) with six arrived rows; four days later it is not.
    kotri_peak = peak_day(7, 2)
    w2 = _etas(situation(data, day(kotri_peak + 2)), "indus-2022-w2")
    assert len(w2) == 6 and all(e["status"] == "arrived" for e in w2.values())
    assert not _etas(situation(data, day(kotri_peak + 4)), "indus-2022-w2")


def test_no_peak_before_its_confirming_reading_day_by_day():
    data = make_data()
    first_seen: dict = {}
    for d in range(N_DAYS):
        as_of = day(d)
        s = situation(data, as_of)
        for p in s["peaks"]:
            assert p["peak_time"] <= s["as_of"], p
            key = (p["barrage"], p["wave_id"], p["status"])
            first_seen.setdefault(key, d)

    for order, name in enumerate(NAMES, start=1):
        for wave in (1, 2):
            wid = f"indus-2022-w{wave}"
            pk = peak_day(order, wave)
            # forming after the second rise (peak-1), passed on the first
            # reading below the max (peak+1), never earlier.
            assert first_seen[(name, wid, "forming")] == pk - 1, (name, wid)
            assert first_seen[(name, wid, "passed")] == pk + 1, (name, wid)


def test_situation_ignores_readings_after_as_of():
    full = make_data(villages=FAKE_VILLAGES)
    for d in range(N_DAYS):
        truncated = make_data(villages=FAKE_VILLAGES, n_days=d + 1)
        assert situation(full, day(d)) == situation(truncated, day(d)), f"day {d}"


# ---------------------------------------------------------------------------
# ETAs
# ---------------------------------------------------------------------------
def _etas(s, wave_id):
    return {e["barrage"]: e for e in s["etas"] if e["wave_id"] == wave_id}


def test_eta_ranges_add_up():
    data = make_data()
    s = situation(data, day(4))     # Tarbela's wave-1 peak (day 3) confirmed on day 4
    rows = _etas(s, "indus-2022-w1")
    assert sorted(rows, key=NAMES.index) == NAMES[1:]
    peak = day(3)
    for j in range(2, 8):
        e = rows[NAMES[j - 1]]
        assert e["from_barrage"] == "Tarbela"
        assert e["eta"] == fmt_time(peak + timedelta(hours=sum(LAG_MEDIAN[: j - 1])))
        assert e["eta_low"] == fmt_time(peak + timedelta(hours=sum(LAG_MIN[: j - 1])))
        assert e["eta_high"] == fmt_time(peak + timedelta(hours=sum(LAG_MAX[: j - 1])))
        expected_h = sum(LAG_MEDIAN[: j - 1]) - 24
        assert e["hours_from_now"] == expected_h
    # Kalabagh is forming at its crest but has not confirmed it: still estimated.
    assert rows["Kalabagh"]["status"] == "estimated"


def test_arrived_replaces_the_estimate():
    data = make_data()
    before = _etas(situation(data, day(4)), "indus-2022-w1")["Kalabagh"]
    assert before["status"] == "estimated" and before["observed_time"] is None

    after_s = situation(data, day(5))       # Kalabagh's day-4 peak confirmed
    rows = _etas(after_s, "indus-2022-w1")
    k = rows["Kalabagh"]
    assert k["status"] == "arrived"
    assert k["observed_time"] == t(4)
    assert k["hours_from_now"] == -24.0
    assert k["from_barrage"] == "Tarbela"
    assert (k["eta"], k["eta_low"], k["eta_high"]) == (
        before["eta"], before["eta_low"], before["eta_high"])
    # Estimates further down are re-issued from Kalabagh's observed peak.
    for name in NAMES[2:]:
        assert rows[name]["status"] == "estimated"
        assert rows[name]["from_barrage"] == "Kalabagh"
    assert rows["Chashma"]["eta"] == fmt_time(day(4) + timedelta(hours=LAG_MEDIAN[1]))
    assert sum(1 for e in after_s["etas"] if e["barrage"] == "Kalabagh"
               and e["wave_id"] == "indus-2022-w1") == 1


# ---------------------------------------------------------------------------
# Villages
# ---------------------------------------------------------------------------
def test_village_ordering_and_district_minimum():
    data = make_data(villages=FAKE_VILLAGES)
    s = situation(data, day(4))
    ids = [v["id"] for v in s["at_risk_villages"]]
    # A (km 250) first; B and C share km 600 and eta, so C (pop 9000) before B.
    assert ids == ["v-a", "v-c", "v-b"], ids

    a = s["at_risk_villages"][0]
    # Halfway between Kalabagh (eta day 4) and Chashma (eta day 5).
    assert a["eta"] == "2022-08-05T18:00"
    assert a["hours_to_arrival"] == 12.0
    peak = day(3)
    kal_lo, chas_lo = LAG_MIN[0], LAG_MIN[0] + LAG_MIN[1]
    kal_hi, chas_hi = LAG_MAX[0], LAG_MAX[0] + LAG_MAX[1]
    assert a["eta_low"] == fmt_time(peak + timedelta(hours=(kal_lo + chas_lo) / 2))
    assert a["eta_high"] == fmt_time(peak + timedelta(hours=(kal_hi + chas_hi) / 2))

    c = s["at_risk_villages"][1]
    assert c["eta"] == "2022-08-07T18:00" and c["hours_to_arrival"] == 60.0
    assert s["district_eta_hours"] == {"X": 12.0, "Y": 60.0}


def test_village_drops_off_once_the_wave_passes_it():
    data = make_data(villages=FAKE_VILLAGES)
    # Day 5: crest confirmed at Kalabagh (km 200), not yet at Chashma (km 300).
    # A (km 250): eta = day 4 + 12 h, and the 12 h minimum half-width puts
    # eta_high at day 5 exactly, so A is still inside its window.
    s5 = situation(data, day(5))
    a = next(v for v in s5["at_risk_villages"] if v["id"] == "v-a")
    assert a["hours_to_arrival"] == -12.0
    assert a["eta_high"] == t(5)
    # Day 6: Chashma confirms its crest, so A has been passed.
    s6 = situation(data, day(6))
    assert "v-a" not in [v["id"] for v in s6["at_risk_villages"]]
    assert s6["district_eta_hours"]["X"] == s6["district_eta_hours"]["Y"]


def test_village_window_closing_drops_it_before_confirmation():
    # Chashma never confirms wave 1 (flat at its day-5 value): A (km 250)
    # stays listed only until its eta_high (day 5), not until Chashma.
    data = make_data(villages=FAKE_VILLAGES)
    chashma = data.readings["Chashma"]
    hold = next(r.outflow for r in chashma if r.time == day(5))
    data.readings["Chashma"] = [
        Reading(r.time, r.inflow, hold) if day(5) <= r.time <= day(8) else r
        for r in chashma
    ]
    s5 = situation(data, day(5))
    assert "v-a" in [v["id"] for v in s5["at_risk_villages"]]
    s6 = situation(data, day(6))
    assert "v-a" not in [v["id"] for v in s6["at_risk_villages"]]
    assert all(v["eta_high"] >= s6["as_of"] for v in s6["at_risk_villages"])


def test_minimum_half_width_on_zero_width_reaches():
    data = make_data(villages=FAKE_VILLAGES)
    for r in data.reaches:
        r["lag_min_h"] = r["lag_max_h"] = r["lag_median_h"]
    s = situation(data, day(4))
    rows = _etas(s, "indus-2022-w1")
    assert rows
    for e in rows.values():
        eta = routing.parse_time(e["eta"])
        assert e["eta_low"] == fmt_time(eta - timedelta(hours=12)), e
        assert e["eta_high"] == fmt_time(eta + timedelta(hours=12)), e
    for v in s["at_risk_villages"]:
        eta = routing.parse_time(v["eta"])
        assert routing.parse_time(v["eta_low"]) <= eta - timedelta(hours=12), v
        assert routing.parse_time(v["eta_high"]) >= eta + timedelta(hours=12), v
    for row in routing.scorecard(data):
        eta = routing.parse_time(row["predicted_time"])
        assert row["predicted_low"] == fmt_time(eta - timedelta(hours=12)), row
        assert row["predicted_high"] == fmt_time(eta + timedelta(hours=12)), row
    assert "+/-12 h" in s["data_provenance"]["etas"]


def test_no_village_listed_after_its_window_closes():
    data = make_data(villages=FAKE_VILLAGES)
    for d in range(N_DAYS):
        s = situation(data, day(d))
        for v in s["at_risk_villages"]:
            assert v["eta_high"] >= s["as_of"], (s["as_of"], v)
        expected: dict = {}
        for v in s["at_risk_villages"]:
            h = v["hours_to_arrival"]
            expected[v["district"]] = min(h, expected.get(v["district"], h))
        assert s["district_eta_hours"] == expected, s["as_of"]


def test_villages_and_barrages_on_the_centreline_scale():
    # Villages measured on a centreline twice as long as the barrage table:
    # barrages are projected onto that line, so a village at line-km 500
    # (halfway Kalabagh 400 -> Chashma 600) times like table-km 250.
    data = make_data(villages=[dict(FAKE_VILLAGES[0], river_km=500)])
    data.river_coords = [[b["lat"], b["lon"]] for b in data.barrages]
    data.river_km_line = [2.0 * b["river_km"] for b in data.barrages]
    positions, on_line = routing.barrage_positions(data)
    assert on_line and positions == {o: 2.0 * k for o, k in enumerate(RIVER_KM, start=1)}
    s = situation(data, day(4))
    assert s["at_risk_villages"][0]["eta"] == "2022-08-05T18:00"
    assert "centreline" in s["data_provenance"]["villages"]

    # Without per-vertex km the table km are used, and provenance says so.
    data.river_km_line = None
    assert routing.barrage_positions(data) == (
        {o: float(k) for o, k in enumerate(RIVER_KM, start=1)}, False)
    assert "FFC travel-table" in situation(data, day(4))["data_provenance"]["villages"]


def test_missing_villages_file_is_reported():
    s = situation(make_data(villages=None), day(4))
    assert s["at_risk_villages"] == [] and s["district_eta_hours"] == {}
    assert "villages.json not found" in s["data_provenance"]["villages"]


def test_as_of_outside_data_raises():
    data = make_data()
    for bad in (day(-1), day(N_DAYS)):
        try:
            situation(data, bad)
        except routing.AsOfOutOfRange:
            continue
        raise AssertionError(f"as_of {bad} should be out of range")


# ---------------------------------------------------------------------------
# Contract shape and replay
# ---------------------------------------------------------------------------
def test_situation_matches_contract():
    data = make_data(villages=FAKE_VILLAGES)
    for d in range(N_DAYS):
        assert_situation_shape(situation(data, day(d)))
    s = situation(data, day(4))
    assert s["as_of"] == "2022-08-05T06:00" and s["mode"] == "replay"
    assert [b["name"] for b in s["barrages"]] == NAMES
    assert [(r["from"], r["to"]) for r in s["reaches"]] == list(zip(NAMES, NAMES[1:]))
    # Reach category is the higher of its two ends.
    cats = {b["name"]: b["category"] for b in s["barrages"]}
    for r in s["reaches"]:
        assert r["category"] == max(cats[r["from"]], cats[r["to"]], key=CATEGORIES.index)
    assert "straight lines" in s["data_provenance"]["etas"]


def test_replay_and_scorecard():
    data = make_data(villages=FAKE_VILLAGES)
    rep = replay_2022(data)
    assert_replay_shape(rep)
    assert [s["as_of"] for s in rep["steps"]] == [t(d) for d in range(N_DAYS)]
    sc = rep["scorecard"]
    keys = {(r["barrage"], r["wave_id"]) for r in sc}
    assert keys == {(n, f"indus-2022-w{w}") for n in NAMES[1:] for w in (1, 2)}
    for r in sc:
        order = NAMES.index(r["barrage"]) + 1
        assert r["error_hours"] == 0.0, r
        up_peak = day(peak_day(order - 1, int(r["wave_id"][-1])))
        eta = up_peak + timedelta(hours=LAG_MEDIAN[order - 2])
        half = timedelta(hours=routing.MIN_HALF_WIDTH_H)
        low = min(up_peak + timedelta(hours=LAG_MIN[order - 2]), eta - half)
        high = max(up_peak + timedelta(hours=LAG_MAX[order - 2]), eta + half)
        assert r["predicted_low"] == fmt_time(low)
        assert r["predicted_high"] == fmt_time(high)


def test_scorecard_uses_only_upstream_data_before_the_peak():
    # Corrupt everything at and after Guddu's wave-2 peak upstream of Guddu;
    # Guddu's wave-2 prediction must not change.
    data = make_data()
    guddu_peak = day(peak_day(5, 2))
    base = {(r["barrage"], r["wave_id"]): r for r in routing.scorecard(data)}
    poisoned = copy.deepcopy(data)
    for name in NAMES[:4]:
        poisoned.readings[name] = [
            r if r.time < guddu_peak else Reading(r.time, 1, 999999)
            for r in poisoned.readings[name]
        ]
    after = {(r["barrage"], r["wave_id"]): r for r in routing.scorecard(poisoned)}
    key = ("Guddu", "indus-2022-w2")
    assert after[key]["predicted_time"] == base[key]["predicted_time"]


# ---------------------------------------------------------------------------
# Real data (skips when flows_2022.csv is absent)
# ---------------------------------------------------------------------------
def test_real_flows_2022():
    needed = [DATA_DIR / n for n in ("flows_2022.csv", "barrages.json", "reaches.json")]
    if not all(p.exists() for p in needed):
        _skip("data/flows_2022.csv (or barrages.json / reaches.json) not present")
        return
    data = routing.load_data(*[DATA_DIR / n for n in (
        "barrages.json", "reaches.json", "flows_2022.csv")],
        DATA_DIR / "villages.json", DATA_DIR / "indus.geojson")
    rep = replay_2022(data)
    assert_replay_shape(rep)

    steps = {s["as_of"]: s for s in rep["steps"]}
    s = steps["2022-08-31T06:00"]
    taunsa = [p for p in s["peaks"] if p["barrage"] == "Taunsa" and p["status"] == "passed"]
    # FFC 06:00: Taunsa 622000 on 30 Aug, 603000 on 31 Aug (-3%): passed.
    assert any(p["peak_time"] == "2022-08-30T06:00" and p["peak_outflow_cusecs"] == 622000
               for p in taunsa), taunsa
    # On 30 Aug the same crest is not yet confirmed.
    assert not any(p["barrage"] == "Taunsa" and p["status"] == "passed"
                   and p["peak_time"] == "2022-08-30T06:00"
                   for p in steps["2022-08-30T06:00"]["peaks"])
    for st in rep["steps"]:
        assert all(p["peak_time"] <= st["as_of"] for p in st["peaks"])
    assert rep["scorecard"], "expected at least one scored crest in 2022"


def _real_data():
    needed = [DATA_DIR / n for n in ("flows_2022.csv", "barrages.json", "reaches.json",
                                     "villages.json")]
    if not all(p.exists() for p in needed):
        _skip("real data files (flows_2022.csv, villages.json, ...) not present")
        return None
    return routing.load_data(*[DATA_DIR / n for n in (
        "barrages.json", "reaches.json", "flows_2022.csv")],
        DATA_DIR / "villages.json", DATA_DIR / "indus.geojson")


def test_real_31_aug_lists_villages_ahead_of_the_second_wave():
    # The first crest passed Sukkur on 25 Aug. On 31 Aug its Sindh villages
    # must not lead the list at about -143 h; the second crest (Taunsa
    # 30 Aug) heading for Muzaffargarh and Rajanpur must.
    data = _real_data()
    if data is None:
        return
    s = situation(data, routing.parse_time("2022-08-31T06:00"))
    villages = s["at_risk_villages"]
    assert villages[0]["district"] in ("Muzaffargarh", "Rajanpur"), villages[0]
    assert all(v["eta_high"] >= s["as_of"] for v in villages)
    # Negative only inside a village's window (crest due now), never days stale.
    assert min(s["district_eta_hours"].values()) > -12, s["district_eta_hours"]
    first_two = sorted(s["district_eta_hours"], key=s["district_eta_hours"].get)[:2]
    assert set(first_two) == {"Muzaffargarh", "Rajanpur"}, s["district_eta_hours"]


def test_real_villages_sit_between_their_barrages():
    # Kashmore lies around Guddu and above Sukkur, Matiari and Hyderabad
    # between Sukkur and Kotri: their ETAs must fall inside those bounds.
    data = _real_data()
    if data is None:
        return
    positions, on_line = routing.barrage_positions(data)
    assert on_line, "indus.geojson should carry per-vertex river_km"
    s = situation(data, routing.parse_time("2022-08-31T06:00"))
    est = {e["barrage"]: e["eta"] for e in s["etas"] if e["status"] == "estimated"
           and e["from_barrage"] == "Taunsa"}
    for v in s["at_risk_villages"]:
        if v["district"] == "Kashmore":
            assert v["eta"] <= est["Sukkur"], v
        if v["district"] in ("Matiari", "Hyderabad"):
            assert est["Sukkur"] <= v["eta"] <= est["Kotri"], v


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        test_category_boundaries_upstream_and_sindh,
        test_trend_two_percent_band,
        test_dip_of_ten_percent_starts_new_wave,
        test_drop_below_low_starts_new_wave,
        test_forming_needs_two_rises_and_passed_needs_two_percent_drop,
        test_both_waves_found_at_every_barrage,
        test_no_peak_before_its_confirming_reading_day_by_day,
        test_situation_ignores_readings_after_as_of,
        test_eta_ranges_add_up,
        test_arrived_replaces_the_estimate,
        test_village_ordering_and_district_minimum,
        test_village_drops_off_once_the_wave_passes_it,
        test_no_village_listed_after_its_window_closes,
        test_village_window_closing_drops_it_before_confirmation,
        test_minimum_half_width_on_zero_width_reaches,
        test_villages_and_barrages_on_the_centreline_scale,
        test_missing_villages_file_is_reported,
        test_as_of_outside_data_raises,
        test_situation_matches_contract,
        test_replay_and_scorecard,
        test_scorecard_uses_only_upstream_data_before_the_peak,
        test_real_flows_2022,
        test_real_31_aug_lists_villages_ahead_of_the_second_wave,
        test_real_villages_sit_between_their_barrages,
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
