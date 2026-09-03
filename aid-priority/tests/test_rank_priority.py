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
