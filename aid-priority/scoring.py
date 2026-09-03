"""
Scoring logic for the Aid Priority Ranking module.

Pure functions -- no FastAPI/IO dependencies -- so the ranking math can be
unit-tested and audited independently of the serving layer.

SCORING MODEL
=============

Each district receives a priority score in [0, 1]:

    priority = (W_risk * risk_score + W_damage * damage_score) / (W_risk + W_damage)

1. risk_score -- from Risk Flag's /predict-risk response:
       low=0.0, medium=0.5, high=1.0, unknown=0.0
   ("unknown" is what Risk Flag returns for districts outside its coverage
   list; scoring it 0.0 lets the district still rank on damage alone.)

2. damage_score -- from Damage Checker's /classify-damage output,
   aggregated per district. Two input modes:

   a) damage_breakdown (preferred): per-level counts of assessed tiles.
          damage_score = (0.5 * partial + 1.0 * destroyed) / classified
      where classified = none + partial + destroyed. Severity weights
      mirror the class ordering: none=0.0, partial=0.5, destroyed=1.0.

   b) overall_damage_level (single-tile fallback): the raw level of one
      /classify-damage call.
          damage_score = {none: 0.0, partial: 0.5, destroyed: 1.0}[level]

DESIGN DECISION -- "more photos != more damage":
    damage_score is a per-tile AVERAGE, never a sum. A district assessed
    with 10 tiles at 40% damaged scores identically to one assessed with
    100 tiles at 40% damaged. Raw tile counts are echoed in the response
    for situational awareness (assessment coverage) but never enter the
    score, so better-photographed districts are not systematically
    over-prioritized.

WEIGHTING RATIONALE -- default W_risk=0.4, W_damage=0.6:
    Damage is *observed* ground truth of what has already happened; risk
    is a *forecast* of what may happen. For post-event aid triage the
    observed severity should dominate, but a district with high forecast
    risk and low current damage (e.g. flood heading toward an intact
    area) must still surface. Both weights are configurable via
    environment variables; the formula normalizes by their sum so the
    score always stays in [0, 1] regardless of weight magnitudes.

TIE-BREAKING: equal scores are ordered by district name (ascending) so
    rankings are deterministic across runs.
"""

from __future__ import annotations

from typing import Optional

# ---------------------------------------------------------------------------
# Scoring constants -- single source of truth for level-to-score maps.
# Mirrored into the /rank-priority response so callers can audit the math.
# ---------------------------------------------------------------------------

RISK_LEVEL_SCORES: dict = {
    "low": 0.0,
    "medium": 0.5,
    "high": 1.0,
    # Risk Flag returns "unknown" for districts outside its coverage list.
    "unknown": 0.0,
}

DAMAGE_SEVERITY_SCORES: dict = {
    "none": 0.0,
    "partial": 0.5,
    "destroyed": 1.0,
}

# The five hazard types Nigraan AI covers (matches risk-flag district config).
HAZARD_TYPES = {"flood", "glof", "avalanche", "landslide", "drought"}

DEFAULT_RISK_WEIGHT = 0.4
DEFAULT_DAMAGE_WEIGHT = 0.6


def score_breakdown(
    none_count: int, partial_count: int, destroyed_count: int
) -> tuple:
    """Damage score + percent-damaged from per-level tile counts.

    Returns (damage_score, percent_damaged), both in [0, 1].

    Normalized by the number of *classified* tiles, NOT by how many
    photos exist -- this is the "more photos != more damage" safeguard.
    """
    classified = none_count + partial_count + destroyed_count
    if classified <= 0:
        raise ValueError("damage_breakdown must contain at least one classified tile")

    damage_score = (
        DAMAGE_SEVERITY_SCORES["partial"] * partial_count
        + DAMAGE_SEVERITY_SCORES["destroyed"] * destroyed_count
    ) / classified
    percent_damaged = (partial_count + destroyed_count) / classified
    return damage_score, percent_damaged


def score_single_tile(level: str) -> tuple:
    """Damage score + percent-damaged for a single-tile damage level.

    Returns (damage_score, percent_damaged), both in [0, 1].
    """
    level = level.strip().lower()
    if level not in DAMAGE_SEVERITY_SCORES:
        raise ValueError(
            f"overall_damage_level must be one of {sorted(DAMAGE_SEVERITY_SCORES)}, got {level!r}"
        )
    damage_score = DAMAGE_SEVERITY_SCORES[level]
    # A single assessed tile is either damaged (any level) or not.
    percent_damaged = 0.0 if level == "none" else 1.0
    return damage_score, percent_damaged


def priority_score(
    risk_level: str,
    damage_score: float,
    risk_weight: float = DEFAULT_RISK_WEIGHT,
    damage_weight: float = DEFAULT_DAMAGE_WEIGHT,
) -> float:
    """Combine risk level and damage severity into one priority score.

    Formula (see module docstring):
        (risk_weight * risk_score + damage_weight * damage_score) / (sum of weights)
    """
    risk_level = risk_level.strip().lower()
    if risk_level not in RISK_LEVEL_SCORES:
        raise ValueError(
            f"risk_level must be one of {sorted(RISK_LEVEL_SCORES)}, got {risk_level!r}"
        )
    total = risk_weight + damage_weight
    if total <= 0:
        raise ValueError("risk_weight + damage_weight must be > 0")
    return (
        risk_weight * RISK_LEVEL_SCORES[risk_level] + damage_weight * damage_score
    ) / total


def rank_districts(
    entries: list,
    risk_weight: float = DEFAULT_RISK_WEIGHT,
    damage_weight: float = DEFAULT_DAMAGE_WEIGHT,
) -> list:
    """Score and rank pre-validated district entries (highest priority first).

    Each entry is a dict with at least: district, hazard_type, risk_level,
    damage_score. Everything else is passed through unchanged so the
    response echoes the caller's inputs.

    Adds "priority_score" (rounded to 4 dp) and "rank" to each entry copy.
    Sorting: priority_score descending, ties broken by district name
    ascending (deterministic across runs).
    """
    scored = []
    for entry in entries:
        item = dict(entry)
        score = priority_score(
            item["risk_level"], item["damage_score"], risk_weight, damage_weight
        )
        item["priority_score"] = round(score, 4)
        scored.append(item)

    scored.sort(key=lambda x: (-x["priority_score"], x["district"]))
    for i, item in enumerate(scored, start=1):
        item["rank"] = i
    return scored


def low_coverage_warning(tile_count: int, threshold: int = 5) -> Optional[str]:
    """Transparency signal: warn when an assessment rests on very few tiles.

    INFORMATIONAL ONLY -- the returned value must NEVER enter the priority
    score, rank order, or any other computed number. It exists so response
    teams can see how much evidence backs a district's position: a rank-1
    district assessed from a single photo deserves more skepticism than one
    assessed from 100 tiles, even at the same score.

    Returns a short warning string when tile_count < threshold, else None.
    """
    if tile_count < threshold:
        plural = "tile" if tile_count == 1 else "tiles"
        return f"low coverage — based on {tile_count} {plural}"
    return None
