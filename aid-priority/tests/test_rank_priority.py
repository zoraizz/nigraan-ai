"""
Tests for the Aid Priority Ranking module.

Usage:
    # Unit tests only (no server needed):
    python tests/test_rank_priority.py unit

    # Full suite (start the server first, from aid-priority/):
    #   python -m uvicorn main:app --port 8002
    python tests/test_rank_priority.py

Also pytest-compatible:  pytest tests/test_rank_priority.py
(endpoint tests skip themselves when the server is unreachable).

Key behaviors covered:
    1. Higher risk + higher damage ranks above lower on both.
    2. "More photos != more damage": same damage RATE with different tile
       counts produces identical scores.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scoring import (  # noqa: E402
    DEFAULT_DAMAGE_WEIGHT,
    DEFAULT_RISK_WEIGHT,
    RISK_LEVEL_SCORES,
    priority_score,
    rank_districts,
    score_breakdown,
    score_single_tile,
)

BASE_URL = "http://127.0.0.1:8002"


def _entry(district, hazard, risk, damage_score, **extra):
    base = {
        "district": district,
        "hazard_type": hazard,
        "risk_level": risk,
        "damage_score": damage_score,
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# Unit tests (scoring.py -- no server needed)
# ---------------------------------------------------------------------------

def test_higher_risk_and_damage_ranks_first():
    """A district with higher risk AND higher damage must rank above one
    lower on both dimensions."""
    entries = [
        _entry("Sukkur", "flood", "low", 0.10),     # low risk, light damage
        _entry("Swat", "flood", "high", 0.70),      # high risk, heavy damage
    ]
    ranked = rank_districts(entries)
    assert ranked[0]["district"] == "Swat", "high risk + high damage must rank first"
    assert ranked[0]["rank"] == 1 and ranked[1]["rank"] == 2
    assert ranked[0]["priority_score"] > ranked[1]["priority_score"]


def test_photo_count_does_not_skew_priority():
    """THE 'more photos' bias test.

    District A: 10 assessed tiles -> damage_breakdown(none=6, partial=2, destroyed=2)
    District B: 100 assessed tiles -> damage_breakdown(none=60, partial=20, destroyed=20)

    Same damage RATE (40% damaged, same partial:destroyed mix) but 10x the
    tile count. Scores must be identical.
    """
    a_damage, a_pct = score_breakdown(6, 2, 2)
    b_damage, b_pct = score_breakdown(60, 20, 20)

    assert abs(a_damage - b_damage) < 1e-9, (
        f"damage_score must not depend on tile count: {a_damage} vs {b_damage}"
    )
    assert abs(a_pct - b_pct) < 1e-9

    entries = [
        _entry("FewPhotos", "flood", "medium", a_damage),
        _entry("ManyPhotos", "flood", "medium", b_damage),
    ]
    ranked = rank_districts(entries)
    assert ranked[0]["priority_score"] == ranked[1]["priority_score"], (
        "same damage rate + same risk must yield identical priority, "
        "regardless of how many tiles were assessed"
    )
    # Ties are broken alphabetically -> deterministic
    assert [r["district"] for r in ranked] == ["FewPhotos", "ManyPhotos"]


def test_single_tile_matches_equivalent_breakdown():
    """One tile classified 'destroyed' must score the same as a breakdown
    of {none: 0, partial: 0, destroyed: 1}."""
    single_score, single_pct = score_single_tile("destroyed")
    breakdown_score, breakdown_pct = score_breakdown(0, 0, 1)
    assert single_score == breakdown_score == 1.0
    assert single_pct == breakdown_pct == 1.0

    partial_single, _ = score_single_tile("partial")
    partial_breakdown, _ = score_breakdown(0, 1, 0)
    assert partial_single == partial_breakdown == 0.5


def test_score_math_matches_formula():
    """Hand-computed check of the full formula.

    breakdown(none=10, partial=5, destroyed=2) with risk=high,
    default weights 0.4/0.6:
        damage_score = (0.5*5 + 1.0*2) / 17 = 4.5/17 = 0.26470588...
        priority     = (0.4*1.0 + 0.6*0.26470588) / 1.0 = 0.55882352...
    """
    damage, pct = score_breakdown(10, 5, 2)
    assert abs(damage - 4.5 / 17) < 1e-9
    assert abs(pct - 7 / 17) < 1e-9

    p = priority_score("high", damage)
    assert abs(p - (0.4 * 1.0 + 0.6 * (4.5 / 17))) < 1e-9

    ranked = rank_districts([_entry("MathCheck", "flood", "high", round(damage, 4))])
    assert ranked[0]["priority_score"] == 0.5588  # rounded to 4 dp


def test_weight_normalization_keeps_score_in_range():
    """Non-default weights (e.g. 0.8/0.4) must still produce scores in
    [0, 1] because the formula divides by the weight sum."""
    for risk in ("low", "medium", "high", "unknown"):
        for damage in (0.0, 0.3, 1.0):
            p = priority_score(risk, damage, risk_weight=0.8, damage_weight=0.4)
            assert 0.0 <= p <= 1.0, f"score out of range: {p}"
            expected = (0.8 * RISK_LEVEL_SCORES[risk] + 0.4 * damage) / 1.2
            assert abs(p - expected) < 1e-12


def test_unknown_risk_scores_zero():
    """"unknown" risk (district outside Risk Flag coverage) scores like
    "low", so the district still ranks on damage alone."""
    p_unknown = priority_score("unknown", 0.5)
    p_low = priority_score("low", 0.5)
    assert p_unknown == p_low


def test_low_coverage_warning_thresholds():
    """Low-coverage flag: informational only, never a scoring input.

    Below threshold -> warning string; at/above threshold -> None. The
    field's presence must not change priority_score or rank order.
    """
    from scoring import low_coverage_warning

    # Single tile -> flagged, message includes the tile count
    assert low_coverage_warning(1, threshold=5) == "low coverage — based on 1 tile"
    # Below threshold -> flagged (plural form)
    assert low_coverage_warning(4, threshold=5) == "low coverage — based on 4 tiles"
    # At threshold -> not flagged
    assert low_coverage_warning(5, threshold=5) is None
    # Well above -> not flagged
    assert low_coverage_warning(100, threshold=5) is None

    # Zero score impact: entries carrying the warning field rank identically
    # to entries without it (pass-through metadata, nothing more).
    # (main.py always sets the key -- mirror that here for the control entry)
    with_flag = _entry("Flagged", "flood", "high", 0.5,
                       low_coverage_warning="low coverage — based on 1 tile")
    without_flag = _entry("Unflagged", "flood", "high", 0.5,
                          low_coverage_warning=None)
    ranked = rank_districts([with_flag, without_flag])
    assert ranked[0]["priority_score"] == ranked[1]["priority_score"] == 0.7
    assert ranked[0]["low_coverage_warning"] == "low coverage — based on 1 tile"
    assert ranked[1]["low_coverage_warning"] is None


def test_tie_break_is_deterministic():
    """Identical districts keep a stable, alphabetical order."""
    entries = [
        _entry("Ziarat", "landslide", "medium", 0.5),
        _entry("Abbottabad", "landslide", "medium", 0.5),
    ]
    first = rank_districts(entries)
    second = rank_districts(list(reversed(entries)))
    assert [r["district"] for r in first] == ["Abbottabad", "Ziarat"]
    assert [r["district"] for r in second] == ["Abbottabad", "Ziarat"]


# ---------------------------------------------------------------------------
# Optional signal registry (dummy signals in a private registry)
# ---------------------------------------------------------------------------

def _dummy_registry():
    """A "zero" signal (like a flood ETA) and a "skip" signal (like ground
    photos), each mapping a raw value in [0, 1] to itself."""
    from scoring import register_signal

    registry = {}
    register_signal(
        "dummy_zero", request_field="dummy_zero_value",
        weight_env="PRIORITY_DUMMY_ZERO_WEIGHT", default_weight=0.5,
        score_fn=lambda v: float(v), missing_policy="zero",
        curve="identity", note="test signal; missing scores 0",
        registry=registry,
    )
    register_signal(
        "dummy_skip", request_field="dummy_skip_value",
        weight_env="PRIORITY_DUMMY_SKIP_WEIGHT", default_weight=0.3,
        score_fn=lambda v: float(v), missing_policy="skip",
        curve="identity", note="test signal; missing is no evidence",
        registry=registry,
    )
    return registry


def test_signal_spec_validation():
    from scoring import register_signal

    registry = _dummy_registry()
    bad = dict(request_field="x", weight_env="X", default_weight=0.1,
               score_fn=float, curve="c", note="n")
    for kwargs in (
        dict(bad, missing_policy="ignore"),           # unknown policy
        dict(bad, missing_policy="zero", default_weight=-1),
        dict(bad, missing_policy="zero", score_fn="nope"),
        dict(bad, missing_policy="zero", request_field="dummy_zero_value"),
    ):
        try:
            register_signal("bad", registry=registry, **kwargs)
        except ValueError:
            continue
        raise AssertionError(f"register_signal accepted {kwargs}")
    try:
        register_signal("dummy_zero", registry=registry, **dict(bad, missing_policy="zero"))
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate signal name accepted")


def test_signal_inactive_when_no_district_carries_field():
    """Registered but absent signals change nothing: identical scores and
    ranks to the base formula, and no per-district signal entries."""
    from scoring import active_signals

    registry = _dummy_registry()
    entries = [
        _entry("Sukkur", "flood", "low", 0.10),
        _entry("Swat", "flood", "high", 0.70),
        _entry("Dadu", "flood", "medium", 0.35, dummy_zero_value=None),
    ]
    assert active_signals(entries, registry) == []
    base = rank_districts(entries, signals={})
    with_registry = rank_districts(entries, signals=registry)
    assert [(r["district"], r["priority_score"], r["rank"]) for r in base] == [
        (r["district"], r["priority_score"], r["rank"]) for r in with_registry
    ]
    assert all(r["signals"] == {} for r in with_registry)


def test_signal_activation_is_per_signal():
    from scoring import active_signals

    registry = _dummy_registry()
    entries = [
        _entry("A", "flood", "high", 0.5, dummy_skip_value=0.8),
        _entry("B", "flood", "low", 0.2),
    ]
    assert active_signals(entries, registry) == ["dummy_skip"]
    ranked = {r["district"]: r for r in rank_districts(entries, signals=registry)}
    assert set(ranked["A"]["signals"]) == {"dummy_skip"}
    assert ranked["A"]["signals"]["dummy_skip"] == {"value": 0.8, "score": 0.8}
    assert ranked["B"]["signals"]["dummy_skip"] == {"value": None, "score": None}


def test_signal_normalisation_hand_computed():
    """priority = (Wr*r + Wd*d + sum Wk*s_k) / (Wr + Wd + sum Wk), and all
    maxed-out inputs still score exactly 1.0 for any weights."""
    registry = _dummy_registry()
    weights = {"dummy_zero": 0.5, "dummy_skip": 0.3}
    entries = [
        _entry("Hand", "flood", "medium", 0.4,
               dummy_zero_value=0.9, dummy_skip_value=0.2),
        _entry("Max", "flood", "high", 1.0,
               dummy_zero_value=1.0, dummy_skip_value=1.0),
    ]
    ranked = {r["district"]: r for r in rank_districts(
        entries, signal_weights=weights, signals=registry)}
    expected = (0.4 * 0.5 + 0.6 * 0.4 + 0.5 * 0.9 + 0.3 * 0.2) / (0.4 + 0.6 + 0.5 + 0.3)
    assert ranked["Hand"]["priority_score"] == round(expected, 4)
    assert ranked["Max"]["priority_score"] == 1.0

    # Large weights stay in range thanks to the denominator.
    big = rank_districts(entries, risk_weight=3, damage_weight=7,
                         signal_weights={"dummy_zero": 50, "dummy_skip": 20},
                         signals=registry)
    assert all(0.0 <= r["priority_score"] <= 1.0 for r in big)

    # Unset weights fall back to default_weight.
    defaulted = {r["district"]: r for r in rank_districts(entries, signals=registry)}
    assert defaulted["Hand"]["priority_score"] == round(expected, 4)


def test_zero_signal_lowers_district_missing_value():
    """"zero": a district without the value scores 0 for the signal and the
    weight still counts, so its priority drops below the base formula."""
    registry = {"dummy_zero": _dummy_registry()["dummy_zero"]}
    entries = [
        _entry("HasEta", "flood", "low", 0.3, dummy_zero_value=1.0),
        _entry("NoEta", "flood", "high", 0.6),
    ]
    base = {r["district"]: r for r in rank_districts(entries, signals={})}
    with_sig = {r["district"]: r for r in rank_districts(entries, signals=registry)}

    assert with_sig["NoEta"]["priority_score"] < base["NoEta"]["priority_score"]
    expected = (0.4 * 1.0 + 0.6 * 0.6 + 0.5 * 0.0) / (0.4 + 0.6 + 0.5)
    assert with_sig["NoEta"]["priority_score"] == round(expected, 4)
    assert with_sig["NoEta"]["signals"]["dummy_zero"] == {"value": None, "score": 0.0}


def test_skip_signal_leaves_missing_district_unchanged():
    """"skip": a district without the value keeps EXACTLY the score it
    would have without the signal (weight leaves both sums)."""
    registry = {"dummy_skip": _dummy_registry()["dummy_skip"]}
    entries = [
        _entry("HasPhotos", "flood", "low", 0.3, dummy_skip_value=1.0),
        _entry("NoPhotos", "landslide", "high", 0.45),
    ]
    base = {r["district"]: r for r in rank_districts(entries, signals={})}
    with_sig = {r["district"]: r for r in rank_districts(entries, signals=registry)}

    assert with_sig["NoPhotos"]["priority_score"] == base["NoPhotos"]["priority_score"]
    assert priority_score("high", 0.45) == priority_score("high", 0.45, signal_terms=())
    # The district WITH the value does move.
    assert with_sig["HasPhotos"]["priority_score"] != base["HasPhotos"]["priority_score"]


def test_signal_invalid_value_and_bad_score_fn():
    from scoring import SignalValueError, register_signal

    registry = _dummy_registry()
    try:
        rank_districts([_entry("A", "flood", "low", 0.1, dummy_zero_value="soon")],
                       signals=registry)
    except SignalValueError as exc:
        assert "'A'" in str(exc) and "dummy_zero_value" in str(exc)
    else:
        raise AssertionError("non-numeric signal value accepted")

    out_of_range = {}
    register_signal("broken", request_field="broken_value", weight_env="X",
                    default_weight=1.0, score_fn=lambda v: 2.0,
                    missing_policy="zero", curve="c", note="n",
                    registry=out_of_range)
    try:
        rank_districts([_entry("A", "flood", "low", 0.1, broken_value=1)],
                       signals=out_of_range)
    except SignalValueError:
        raise AssertionError("a buggy score_fn is a server bug, not a caller error")
    except ValueError:
        pass
    else:
        raise AssertionError("score outside [0, 1] accepted")


def test_endpoint_signals_in_process():
    """main.rank_priority called directly (no server) with a dummy signal
    registered globally: response blocks, weights and 422 on bad values.
    Real registered signals are set aside for the test and restored."""
    import scoring
    import main

    saved = dict(scoring.OPTIONAL_SIGNALS)
    scoring.OPTIONAL_SIGNALS.clear()
    try:
        _run_endpoint_signals_in_process(scoring, main)
    finally:
        scoring.OPTIONAL_SIGNALS.clear()
        scoring.OPTIONAL_SIGNALS.update(saved)


def _run_endpoint_signals_in_process(scoring, main):

    payload = [
        {"district": "Dadu", "hazard_type": "flood", "risk_level": "high",
         "damage_breakdown": {"none": 5, "partial": 3, "destroyed": 2},
         "dummy_zero_value": 0.75},
        {"district": "Swat", "hazard_type": "flood", "risk_level": "medium",
         "overall_damage_level": "partial", "unrelated_extra": 1},
    ]

    # No registered signals: extra keys are ignored, response is the base one.
    body = main.rank_priority(main.RankPriorityRequest(districts=payload))
    assert body.scoring.signals == []
    assert all(d.signals == {} for d in body.ranked_districts)
    assert body.scoring.formula.startswith("priority = (risk_weight * risk_score")
    base_scores = {d.district: d.priority_score for d in body.ranked_districts}

    scoring.OPTIONAL_SIGNALS.update(_dummy_registry())
    body = main.rank_priority(main.RankPriorityRequest(districts=payload))
    by_name = {d.district: d for d in body.ranked_districts}
    info = {s.name: s for s in body.scoring.signals}
    assert info["dummy_zero"].active and not info["dummy_skip"].active
    assert info["dummy_zero"].weight == 0.5
    assert info["dummy_zero"].curve == "identity"
    assert set(by_name["Dadu"].signals) == {"dummy_zero"}
    assert by_name["Dadu"].signals["dummy_zero"].score == 0.75
    assert by_name["Swat"].signals["dummy_zero"].score == 0.0
    assert "dummy_zero" in body.scoring.formula

    rw, dw = main.RISK_WEIGHT, main.DAMAGE_WEIGHT
    dadu_damage = (0.5 * 3 + 1.0 * 2) / 10
    expected = (rw * 1.0 + dw * dadu_damage + 0.5 * 0.75) / (rw + dw + 0.5)
    assert by_name["Dadu"].priority_score == round(expected, 4)
    assert by_name["Swat"].priority_score < base_scores["Swat"]

    bad = [dict(payload[0], dummy_zero_value="soon")]
    resp = main.rank_priority(main.RankPriorityRequest(districts=bad))
    assert resp.status_code == 422
    assert b"invalid_signal_value" in resp.body


# ---------------------------------------------------------------------------
# Flood signal (River Flood Tracker) -- the real OPTIONAL_SIGNALS entry
# ---------------------------------------------------------------------------

def test_flood_12h_outranks_96h_all_else_equal():
    """A peak 12 h out is more urgent than one 96 h out when risk, damage
    and every other input match. 96 h sits on the linear segment:
    (120 - 96) / 108 = 24/108."""
    from scoring import flood_urgency_score

    assert flood_urgency_score(12) == 1.0
    assert abs(flood_urgency_score(96) - (24 / 108)) < 1e-12

    entries = [
        _entry("Far", "flood", "high", 0.5, flood_eta_hours=96),
        _entry("Near", "flood", "high", 0.5, flood_eta_hours=12),
    ]
    ranked = rank_districts(entries)
    assert [r["district"] for r in ranked] == ["Near", "Far"]
    assert ranked[0]["priority_score"] > ranked[1]["priority_score"]
    assert ranked[0]["signals"]["flood"] == {"value": 12, "score": 1.0}
    assert ranked[1]["signals"]["flood"]["score"] == round(24 / 108, 4)

    weight = 0.3
    near = (0.4 * 1.0 + 0.6 * 0.5 + weight * 1.0) / (0.4 + 0.6 + weight)
    far = (0.4 * 1.0 + 0.6 * 0.5 + weight * (24 / 108)) / (0.4 + 0.6 + weight)
    assert ranked[0]["priority_score"] == round(near, 4)
    assert ranked[1]["priority_score"] == round(far, 4)


def test_flood_urgency_boundaries_at_12_and_120():
    """Plateau through 12 h, zero at and beyond 120 h, line strictly between.
    The line meets both kinks: (120 - 12) / 108 == 1 and (120 - 120) / 108 == 0."""
    from scoring import SignalValueError, flood_urgency_score

    assert flood_urgency_score(12) == 1.0
    assert flood_urgency_score(0) == 1.0
    assert flood_urgency_score(11.9) == 1.0
    just_over_12 = 12.0 + 1e-6
    assert abs(flood_urgency_score(just_over_12) - (120.0 - just_over_12) / 108.0) < 1e-12
    assert flood_urgency_score(just_over_12) < 1.0

    assert flood_urgency_score(120) == 0.0
    assert flood_urgency_score(120.1) == 0.0
    assert flood_urgency_score(1000) == 0.0
    just_under_120 = 119.999
    assert abs(flood_urgency_score(just_under_120) - (120.0 - just_under_120) / 108.0) < 1e-12
    assert flood_urgency_score(just_under_120) > 0.0
    assert flood_urgency_score(None) == 0.0
    assert abs((120 - 12) / 108 - 1.0) < 1e-12

    ranked = rank_districts([
        _entry("At120", "flood", "medium", 0.4, flood_eta_hours=120),
        _entry("At12", "flood", "medium", 0.4, flood_eta_hours=12),
    ])
    by_name = {r["district"]: r for r in ranked}
    assert by_name["At12"]["signals"]["flood"]["score"] == 1.0
    assert by_name["At120"]["signals"]["flood"]["score"] == 0.0
    assert by_name["At12"]["rank"] < by_name["At120"]["rank"]

    try:
        rank_districts([_entry("Bad", "flood", "low", 0.1, flood_eta_hours=-1)])
    except SignalValueError as exc:
        assert "flood_eta_hours" in str(exc)
    else:
        raise AssertionError("negative flood_eta_hours accepted")


def test_flood_request_without_field_is_unchanged():
    """Omitting flood_eta_hours (or sending null on every district) leaves
    scores, ranks and the base formula identical to a registry with no
    signals. The flood entry is listed inactive; it does not enter the math."""
    from scoring import OPTIONAL_SIGNALS, active_signals, formula_text

    spec = OPTIONAL_SIGNALS["flood"]
    assert spec["request_field"] == "flood_eta_hours"
    assert spec["weight_env"] == "PRIORITY_FLOOD_WEIGHT"
    assert spec["default_weight"] == 0.3
    assert spec["missing_policy"] == "zero"
    assert spec["curve"] == "1.0 up to 12 h, falling linearly to 0 at 120 h"
    assert "River Flood Tracker estimate" in spec["note"]

    entries = [
        _entry("Sukkur", "flood", "low", 0.10),
        _entry("Swat", "flood", "high", 0.70),
        _entry("Dadu", "flood", "medium", 0.35, flood_eta_hours=None),
    ]
    base = rank_districts(entries, signals={})
    with_flood = rank_districts(entries)
    assert [(r["district"], r["priority_score"], r["rank"]) for r in base] == [
        (r["district"], r["priority_score"], r["rank"]) for r in with_flood
    ]
    assert all(r["signals"] == {} for r in with_flood)
    assert formula_text([]) == formula_text(active_signals(entries))

    import main

    payload = [
        {"district": "Dadu", "hazard_type": "flood", "risk_level": "high",
         "damage_breakdown": {"none": 5, "partial": 3, "destroyed": 2}},
        {"district": "Swat", "hazard_type": "flood", "risk_level": "medium",
         "overall_damage_level": "partial"},
    ]
    body = main.rank_priority(main.RankPriorityRequest(districts=payload))
    info = {s.name: s for s in body.scoring.signals}
    assert info["flood"].active is False
    assert info["flood"].weight == 0.3
    assert info["flood"].request_field == "flood_eta_hours"
    assert body.scoring.formula == formula_text([])
    rw, dw = main.RISK_WEIGHT, main.DAMAGE_WEIGHT
    by_name = {d.district: d for d in body.ranked_districts}
    dadu_damage = (0.5 * 3 + 1.0 * 2) / 10
    assert by_name["Dadu"].priority_score == round(
        (rw * 1.0 + dw * dadu_damage) / (rw + dw), 4
    )
    assert by_name["Swat"].priority_score == round(
        (rw * 0.5 + dw * 0.5) / (rw + dw), 4
    )
    assert all(d.signals == {} for d in body.ranked_districts)

    nulled = [dict(row, flood_eta_hours=None) for row in payload]
    nulled_body = main.rank_priority(main.RankPriorityRequest(districts=nulled))
    assert [d.priority_score for d in nulled_body.ranked_districts] == [
        d.priority_score for d in body.ranked_districts
    ]

    from pydantic import ValidationError
    try:
        main.DistrictAssessment(
            district="X", hazard_type="flood", risk_level="low",
            overall_damage_level="none", flood_eta_hours=-0.1,
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("negative flood_eta_hours passed validation")


def test_flood_signal_through_rank_priority():
    """The declared field is what the endpoint scores, and 12 h still
    outranks 96 h there. A district with no ETA scores 0 once the signal
    is active (missing_policy zero)."""
    import main
    from scoring import OPTIONAL_SIGNALS

    assert "flood" in OPTIONAL_SIGNALS
    assert main.SIGNAL_WEIGHTS["flood"] == 0.3

    payload = [
        {"district": "Far", "hazard_type": "flood", "risk_level": "high",
         "overall_damage_level": "partial", "flood_eta_hours": 96},
        {"district": "Near", "hazard_type": "flood", "risk_level": "high",
         "overall_damage_level": "partial", "flood_eta_hours": 12},
        {"district": "NoEta", "hazard_type": "flood", "risk_level": "high",
         "overall_damage_level": "partial"},
    ]
    body = main.rank_priority(main.RankPriorityRequest(districts=payload))
    by_name = {d.district: d for d in body.ranked_districts}
    assert [d.district for d in body.ranked_districts][:2] == ["Near", "Far"]
    assert by_name["Near"].rank < by_name["Far"].rank < by_name["NoEta"].rank
    assert by_name["Near"].signals["flood"].value == 12
    assert by_name["Near"].signals["flood"].score == 1.0
    assert by_name["Far"].signals["flood"].score == round(24 / 108, 4)
    assert by_name["NoEta"].signals["flood"].value is None
    assert by_name["NoEta"].signals["flood"].score == 0.0
    info = {s.name: s for s in body.scoring.signals}
    assert info["flood"].active is True
    assert info["flood"].missing_policy == "zero"
    assert "sum_k" in body.scoring.formula


# ---------------------------------------------------------------------------
# Ground signal (Ground Photo Intake) -- share of unique reports, skip if absent
# ---------------------------------------------------------------------------

def test_ground_absent_matches_score_without_the_signal():
    """Omitting ground_evidence (or sending null on every district) leaves
    scores and ranks identical to a registry with no signals."""
    entries = [
        _entry("Sukkur", "flood", "low", 0.10),
        _entry("Swat", "flood", "high", 0.70),
        _entry("Dadu", "flood", "medium", 0.35, ground_evidence=None),
    ]
    before = rank_districts(entries, signals={})
    after = rank_districts(entries)
    assert [(r["district"], r["priority_score"], r["rank"]) for r in before] == [
        (r["district"], r["priority_score"], r["rank"]) for r in after
    ]
    assert all(r["signals"] == {} for r in after)


def test_ground_signal_score_and_skip():
    """X is scored from the registry formula. Y, with no ground photos,
    keeps the priority it would have without the signal, and its
    signals.ground.score stays null."""
    import main
    from scoring import DAMAGE_SEVERITY_SCORES, OPTIONAL_SIGNALS, ground_score

    spec = OPTIONAL_SIGNALS["ground"]
    assert spec["request_field"] == "ground_evidence"
    assert spec["weight_env"] == "PRIORITY_GROUND_WEIGHT"
    assert spec["default_weight"] == 0.2
    assert spec["missing_policy"] == "skip"
    assert spec["score_fn"] is ground_score
    assert spec["curve"] == (
        "(0.5*partial + 1.0*destroyed) / unique reports, "
        "same severity weights as satellite damage"
    )
    assert spec["note"] == (
        "Share of severe ground photos (unique, non-rejected reports). "
        "Photo counts never enter the score. Districts without ground "
        "photos are skipped, not scored as zero."
    )
    assert main.SIGNAL_WEIGHTS["ground"] == 0.2

    evidence = {
        "none": 1, "partial": 2, "destroyed": 1,
        "verified_count": 4, "urgent_open": 9,
    }
    share = (
        DAMAGE_SEVERITY_SCORES["partial"] * 2
        + DAMAGE_SEVERITY_SCORES["destroyed"] * 1
    ) / 4
    assert ground_score(evidence) == share
    # Display counts are not inputs: a second object with the same mix
    # and different verified/urgent totals scores the same.
    assert ground_score({"none": 1, "partial": 2, "destroyed": 1}) == share

    payload = [
        {"district": "X", "hazard_type": "flood", "risk_level": "high",
         "overall_damage_level": "partial", "ground_evidence": evidence},
        {"district": "Y", "hazard_type": "flood", "risk_level": "high",
         "overall_damage_level": "partial"},
    ]
    body = main.rank_priority(main.RankPriorityRequest(districts=payload))
    by_name = {d.district: d for d in body.ranked_districts}
    assert by_name["X"].signals["ground"].value == evidence
    assert by_name["X"].signals["ground"].score == round(share, 4)
    assert by_name["Y"].signals["ground"].value is None
    assert by_name["Y"].signals["ground"].score is None

    rw, dw, gw = main.RISK_WEIGHT, main.DAMAGE_WEIGHT, 0.2
    y_without = (rw * 1.0 + dw * 0.5) / (rw + dw)
    x_with = (rw * 1.0 + dw * 0.5 + gw * share) / (rw + dw + gw)
    assert by_name["Y"].priority_score == round(y_without, 4)
    assert by_name["X"].priority_score == round(x_with, 4)

    info = {s.name: s for s in body.scoring.signals}
    assert info["ground"].weight == 0.2
    assert info["ground"].missing_policy == "skip"
    assert info["ground"].active is True


def test_ground_forty_at_25_percent_ranks_below_three_at_66_percent():
    """40 reports, 10 destroyed (25%) score 0.25. 3 reports, 2 destroyed
    (66%) score 2/3. Rank follows the share, not the photo count.
    verified_count and urgent_open on the larger set do not change that."""
    from scoring import ground_score

    many = {
        "none": 30, "partial": 0, "destroyed": 10,
        "verified_count": 40, "urgent_open": 40,
    }
    few = {
        "none": 1, "partial": 0, "destroyed": 2,
        "verified_count": 0, "urgent_open": 1,
    }
    assert ground_score(many) == 0.25
    assert abs(ground_score(few) - (2 / 3)) < 1e-12
    entries = [
        _entry("Forty", "flood", "medium", 0.4, ground_evidence=many),
        _entry("Three", "flood", "medium", 0.4, ground_evidence=few),
    ]
    by_name = {r["district"]: r for r in rank_districts(entries)}
    assert by_name["Forty"]["signals"]["ground"] == {"value": many, "score": 0.25}
    assert by_name["Three"]["signals"]["ground"]["score"] == round(2 / 3, 4)
    assert by_name["Three"]["rank"] < by_name["Forty"]["rank"]


def test_ground_zero_or_negative_is_invalid_signal_value():
    import main

    base = {
        "district": "X", "hazard_type": "flood", "risk_level": "low",
        "overall_damage_level": "none",
    }
    for evidence in (
        {"none": 0, "partial": 0, "destroyed": 0},
        {"none": -1, "partial": 0, "destroyed": 1},
        {"none": 0, "partial": -1, "destroyed": 1},
        {"none": 1, "partial": 0, "destroyed": -2},
    ):
        resp = main.rank_priority(main.RankPriorityRequest(
            districts=[dict(base, ground_evidence=evidence)]
        ))
        assert resp.status_code == 422, evidence
        assert b"invalid_signal_value" in resp.body


def test_ground_weight_env_before_import():
    """PRIORITY_GROUND_WEIGHT is applied when main is imported."""
    import os
    import subprocess
    import sys

    env = os.environ.copy()
    env["PRIORITY_GROUND_WEIGHT"] = "0.55"
    proc = subprocess.run(
        [sys.executable, "-c",
         "import main\n"
         "w = main.SIGNAL_WEIGHTS['ground']\n"
         "assert w == 0.55, w\n"],
        cwd=str(Path(__file__).parent.parent),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_signal_weights_loaded_from_env():
    import os
    import main

    registry = _dummy_registry()
    old = {k: os.environ.get(k) for k in
           ("PRIORITY_DUMMY_ZERO_WEIGHT", "PRIORITY_DUMMY_SKIP_WEIGHT")}
    try:
        os.environ["PRIORITY_DUMMY_ZERO_WEIGHT"] = "0.25"
        os.environ["PRIORITY_DUMMY_SKIP_WEIGHT"] = "-1"   # invalid -> default
        weights = main._load_signal_weights(registry)
        assert weights == {"dummy_zero": 0.25, "dummy_skip": 0.3}
        os.environ["PRIORITY_DUMMY_SKIP_WEIGHT"] = "abc"  # invalid -> default
        assert main._load_signal_weights(registry)["dummy_skip"] == 0.3
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# Endpoint tests (live server on BASE_URL; skipped when unreachable)
# ---------------------------------------------------------------------------

def _server_up() -> bool:
    try:
        import requests
        return requests.get(f"{BASE_URL}/health", timeout=2).ok
    except Exception:
        return False


def test_endpoint_ranks_correctly():
    if not _server_up():
        print("  [skip] server not running")
        return
    import requests

    payload = {
        "districts": [
            {
                "district": "Sukkur", "hazard_type": "flood", "risk_level": "low",
                "damage_breakdown": {"none": 9, "partial": 1, "destroyed": 0},
            },
            {
                "district": "Swat", "hazard_type": "flood", "risk_level": "high",
                "damage_breakdown": {"none": 2, "partial": 3, "destroyed": 5},
            },
        ]
    }
    r = requests.post(f"{BASE_URL}/rank-priority", json=payload, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ranked_districts"][0]["district"] == "Swat"
    assert body["ranked_districts"][0]["rank"] == 1
    # Scoring metadata must be present so the ranking is auditable
    s = body["scoring"]
    assert "priority" in s["formula"]
    assert s["risk_weight"] == DEFAULT_RISK_WEIGHT
    assert s["damage_weight"] == DEFAULT_DAMAGE_WEIGHT
    assert s["risk_level_scores"]["high"] == 1.0
    assert s["photo_count_note"]


def test_endpoint_photo_count_bias():
    if not _server_up():
        print("  [skip] server not running")
        return
    import requests

    payload = {
        "districts": [
            {
                "district": "FewPhotos", "hazard_type": "flood", "risk_level": "medium",
                "damage_breakdown": {"none": 6, "partial": 2, "destroyed": 2},
            },
            {
                "district": "ManyPhotos", "hazard_type": "flood", "risk_level": "medium",
                "damage_breakdown": {"none": 60, "partial": 20, "destroyed": 20},
                "tile_count": 100,
            },
        ]
    }
    r = requests.post(f"{BASE_URL}/rank-priority", json=payload, timeout=10)
    assert r.status_code == 200, r.text
    ranked = r.json()["ranked_districts"]
    by_name = {d["district"]: d for d in ranked}
    assert by_name["FewPhotos"]["priority_score"] == by_name["ManyPhotos"]["priority_score"], (
        "10x more assessed tiles must NOT change the priority score at the same damage rate"
    )
    # Coverage info is echoed but did not enter the score
    assert by_name["ManyPhotos"]["tile_count"] == 100
    assert by_name["FewPhotos"]["tile_count"] == 10
    # New transparency field is present; 10 tiles >= default threshold 5,
    # so neither district is flagged -- and the ranking is unchanged
    # by the field's presence (scores above are still asserted equal).
    assert "low_coverage_warning" in by_name["FewPhotos"]
    assert by_name["FewPhotos"]["low_coverage_warning"] is None
    assert by_name["ManyPhotos"]["low_coverage_warning"] is None


def test_endpoint_low_coverage_flag():
    """Single-tile district flagged; 100-tile district not; boundary at
    threshold (4 flagged, 5 not); flag changes NO computed value."""
    if not _server_up():
        print("  [skip] server not running")
        return
    import requests

    payload = {
        "districts": [
            {
                "district": "Mansehra", "hazard_type": "landslide",
                "risk_level": "high", "overall_damage_level": "partial",
                "confidence": 0.71,
            },
            {
                "district": "Swat", "hazard_type": "flood", "risk_level": "high",
                "damage_breakdown": {"none": 40, "partial": 25, "destroyed": 35},
            },
            {
                "district": "Boundary4", "hazard_type": "flood", "risk_level": "low",
                "damage_breakdown": {"none": 4},
            },
            {
                "district": "Boundary5", "hazard_type": "flood", "risk_level": "low",
                "damage_breakdown": {"none": 5},
            },
        ]
    }
    r = requests.post(f"{BASE_URL}/rank-priority", json=payload, timeout=10)
    assert r.status_code == 200, r.text
    by_name = {d["district"]: d for d in r.json()["ranked_districts"]}

    # Single-tile district: flagged, message includes tile count
    assert by_name["Mansehra"]["low_coverage_warning"] == "low coverage — based on 1 tile"
    # 100-tile district: not flagged
    assert by_name["Swat"]["low_coverage_warning"] is None
    # Threshold boundary (default 5): below flagged, at/above not
    assert by_name["Boundary4"]["low_coverage_warning"] == "low coverage — based on 4 tiles"
    assert by_name["Boundary5"]["low_coverage_warning"] is None

    # Flag has ZERO effect on computed values -- same hand-computed scores
    # as before the field existed:
    #   Mansehra: (0.4 * 1.0 + 0.6 * 0.5) / 1.0 = 0.7
    #   Swat:     (0.4 * 1.0 + 0.6 * ((0.5*25 + 1.0*35) / 100)) = 0.685
    assert by_name["Mansehra"]["priority_score"] == 0.7
    assert by_name["Swat"]["priority_score"] == 0.685
    # Rank order unchanged: flagged district still outranks by score alone
    assert by_name["Mansehra"]["rank"] < by_name["Swat"]["rank"]


def test_endpoint_validation_errors():
    if not _server_up():
        print("  [skip] server not running")
        return
    import requests

    def post(districts):
        return requests.post(
            f"{BASE_URL}/rank-priority", json={"districts": districts}, timeout=10
        )

    # Bad hazard_type -> 422
    r = post([{"district": "X", "hazard_type": "earthquake", "risk_level": "low",
               "overall_damage_level": "none"}])
    assert r.status_code == 422, f"bad hazard_type should fail: {r.text}"

    # Both damage sources -> 422
    r = post([{"district": "X", "hazard_type": "flood", "risk_level": "low",
               "overall_damage_level": "none",
               "damage_breakdown": {"none": 1}}])
    assert r.status_code == 422

    # No damage source -> 422
    r = post([{"district": "X", "hazard_type": "flood", "risk_level": "low"}])
    assert r.status_code == 422

    # Empty districts list -> 422
    r = post([])
    assert r.status_code == 422

    # Duplicate district -> unified error structure
    dup = {"district": "Swat", "hazard_type": "flood", "risk_level": "low",
           "overall_damage_level": "none"}
    r = post([dup, dict(dup)])
    assert r.status_code == 422
    err = r.json().get("error", {})
    assert err.get("code") == "duplicate_district", r.text


def test_health():
    if not _server_up():
        print("  [skip] server not running")
        return
    import requests

    r = requests.get(f"{BASE_URL}/health", timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "risk_weight" in body and "damage_weight" in body


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    args = sys.argv[1:]
    unit_only = bool(args) and args[0].lower() == "unit"

    tests = [
        test_higher_risk_and_damage_ranks_first,
        test_photo_count_does_not_skew_priority,
        test_single_tile_matches_equivalent_breakdown,
        test_score_math_matches_formula,
        test_weight_normalization_keeps_score_in_range,
        test_unknown_risk_scores_zero,
        test_low_coverage_warning_thresholds,
        test_tie_break_is_deterministic,
        test_signal_spec_validation,
        test_signal_inactive_when_no_district_carries_field,
        test_signal_activation_is_per_signal,
        test_signal_normalisation_hand_computed,
        test_zero_signal_lowers_district_missing_value,
        test_skip_signal_leaves_missing_district_unchanged,
        test_signal_invalid_value_and_bad_score_fn,
        test_endpoint_signals_in_process,
        test_flood_12h_outranks_96h_all_else_equal,
        test_flood_urgency_boundaries_at_12_and_120,
        test_flood_request_without_field_is_unchanged,
        test_flood_signal_through_rank_priority,
        test_ground_absent_matches_score_without_the_signal,
        test_ground_signal_score_and_skip,
        test_ground_forty_at_25_percent_ranks_below_three_at_66_percent,
        test_ground_zero_or_negative_is_invalid_signal_value,
        test_ground_weight_env_before_import,
        test_signal_weights_loaded_from_env,
    ]
    if not unit_only:
        tests += [
            test_endpoint_ranks_correctly,
            test_endpoint_photo_count_bias,
            test_endpoint_low_coverage_flag,
            test_endpoint_validation_errors,
            test_health,
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
            print(f"ERROR {fn.__name__}: {exc}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
