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

OPTIONAL SIGNALS -- extra, auditable ranking terms:
    New features (River Flood Tracker, Ground Photo Intake, ...) add a term
    to the ranking by registering an entry in OPTIONAL_SIGNALS instead of
    editing the formula. Each entry declares:

        request_field   -- per-district request key carrying the raw value
                           (e.g. "flood_eta_hours")
        weight_env      -- env var holding the signal's weight W_k
        default_weight  -- weight used when weight_env is unset/invalid
        score_fn        -- raw value -> score in [0, 1]; raises ValueError
                           (or TypeError) for an invalid value
        missing_policy  -- "zero" or "skip" (see below)
        curve           -- human-readable description of score_fn
        note            -- why the signal exists / how to read it

    The general formula, per district, is

        priority = (W_risk * risk_score + W_damage * damage_score
                    + sum_k W_k * score_k)
                   / (W_risk + W_damage + sum_k W_k)

    where k runs over the ACTIVE signals for that request.

    "ACTIVE ONLY WHEN PRESENT": a signal is active for a request only when
    at least one district in that request carries its request_field with a
    non-null value. A request that never mentions a signal is scored by
    exactly the base formula above -- registering a signal can never
    silently shift the scores of callers that don't know about it, and with
    no active signals the arithmetic is identical (same operations, same
    order) to the two-term formula.

    Once a signal is active, districts WITHOUT a value follow the signal's
    missing_policy:
        "zero" -- the district scores 0 for the signal and W_k still counts
                  in the denominator. Use when absence is itself information
                  (no flood ETA = no water coming), so the district is
                  pulled down relative to districts that do have the signal.
        "skip" -- W_k leaves BOTH numerator and denominator for that
                  district. Use when absence means "no evidence" rather than
                  "zero" (no ground photos != zero damage): the district
                  keeps exactly the score it would have without the signal.

    Because every active weight is in the denominator, the score stays in
    [0, 1] for any non-negative weights. Each signal's raw value and score
    are echoed per district, and the scoring block lists every registered
    signal with its weight, curve, note and whether it was active, so the
    extra terms are as auditable as risk and damage.

FLOOD SIGNAL ("flood") -- hours until a river flood peak:
    Registered at import (see the bottom of this module) so the serving
    layer reads PRIORITY_FLOOD_WEIGHT during startup. A later registration
    would miss that one-time env read and silently keep default_weight.

    flood_eta_hours is an estimate from the River Flood Tracker, not a
    gauge reading. flood_urgency_score(h) maps hours-until-peak onto [0, 1]:

        1.0                 if h <= 12
        (120 - h) / 108     if 12 < h < 120
        0.0                 if h >= 120 or h is None

    The plateau through 12 hours treats an imminent peak as maximum
    urgency. The line is continuous with that plateau: (120 - 12) / 108
    is 1, and it reaches 0 at 120 hours (five days). Beyond that the ETA
    does not raise priority. Negative hours and non-numeric values raise
    ValueError so the request is rejected instead of clamped.

    missing_policy is "zero": once any district in the request carries an
    ETA, a district with no ETA scores 0 and the weight still counts
    (no ETA means no water coming). A request that omits the field on
    every district does not activate the signal, so its scores stay on
    the two-term formula. Default weight is 0.3 (PRIORITY_FLOOD_WEIGHT).

TIE-BREAKING: equal scores are ordered by district name (ascending) so
    rankings are deterministic across runs.
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional

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

# ---------------------------------------------------------------------------
# Optional signal registry (see "OPTIONAL SIGNALS" in the module docstring).
# name -> {request_field, weight_env, default_weight, score_fn,
#          missing_policy, curve, note}
# ---------------------------------------------------------------------------
MISSING_POLICIES = ("zero", "skip")

OPTIONAL_SIGNALS: dict = {}


class SignalValueError(ValueError):
    """A request carried a value that a signal's score_fn rejected."""


def validate_signal_spec(name: str, spec: dict) -> None:
    """Raise ValueError if a registry entry is malformed."""
    if not isinstance(name, str) or not name:
        raise ValueError("signal name must be a non-empty string")
    for key in ("request_field", "weight_env", "curve", "note"):
        if not isinstance(spec.get(key), str) or not spec[key]:
            raise ValueError(f"signal {name!r}: {key} must be a non-empty string")
    weight = spec.get("default_weight")
    if not isinstance(weight, (int, float)) or isinstance(weight, bool) or weight < 0:
        raise ValueError(f"signal {name!r}: default_weight must be a number >= 0")
    if not callable(spec.get("score_fn")):
        raise ValueError(f"signal {name!r}: score_fn must be callable")
    if spec.get("missing_policy") not in MISSING_POLICIES:
        raise ValueError(
            f"signal {name!r}: missing_policy must be one of {MISSING_POLICIES}"
        )


def register_signal(
    name: str,
    *,
    request_field: str,
    weight_env: str,
    default_weight: float,
    score_fn: Callable,
    missing_policy: str,
    curve: str,
    note: str,
    registry: Optional[dict] = None,
) -> dict:
    """Validate and add a signal to `registry` (default OPTIONAL_SIGNALS)."""
    registry = OPTIONAL_SIGNALS if registry is None else registry
    spec = {
        "request_field": request_field,
        "weight_env": weight_env,
        "default_weight": default_weight,
        "score_fn": score_fn,
        "missing_policy": missing_policy,
        "curve": curve,
        "note": note,
    }
    validate_signal_spec(name, spec)
    if name in registry:
        raise ValueError(f"signal {name!r} is already registered")
    for other, other_spec in registry.items():
        if other_spec["request_field"] == request_field:
            raise ValueError(
                f"signal {name!r}: request_field {request_field!r} is already "
                f"used by signal {other!r}"
            )
    registry[name] = spec
    return spec


def active_signals(entries: list, signals: Optional[dict] = None) -> list:
    """Names of signals carried (non-null) by at least one entry, in
    registry order. Only these enter the formula for this request."""
    signals = OPTIONAL_SIGNALS if signals is None else signals
    return [
        name
        for name, spec in signals.items()
        if any(e.get(spec["request_field"]) is not None for e in entries)
    ]


def signal_weight(name: str, spec: dict, signal_weights: Optional[dict] = None) -> float:
    """Configured weight for a signal, falling back to its default_weight."""
    if signal_weights and name in signal_weights:
        return signal_weights[name]
    return spec["default_weight"]


def formula_text(active: Iterable = ()) -> str:
    """Human-readable formula for the response's scoring block."""
    base = (
        "priority = (risk_weight * risk_score + damage_weight * "
        "damage_score) / (risk_weight + damage_weight)"
    )
    active = list(active)
    if not active:
        return base
    return (
        "priority = (risk_weight * risk_score + damage_weight * damage_score"
        " + sum_k weight_k * score_k) / (risk_weight + damage_weight"
        f" + sum_k weight_k), k over active signals {active}; a district "
        "missing a 'skip' signal drops that signal from both sums"
    )


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
    signal_terms: Iterable = (),
) -> float:
    """Combine risk level, damage severity and optional signal terms.

    Formula (see module docstring):
        (risk_weight * risk_score + damage_weight * damage_score
         + sum(w * s for w, s in signal_terms))
        / (risk_weight + damage_weight + sum(w for w, _ in signal_terms))

    signal_terms holds (weight, score) pairs for the signals that count for
    this district. With none, the result is exactly the two-term formula.
    """
    risk_level = risk_level.strip().lower()
    if risk_level not in RISK_LEVEL_SCORES:
        raise ValueError(
            f"risk_level must be one of {sorted(RISK_LEVEL_SCORES)}, got {risk_level!r}"
        )
    total = risk_weight + damage_weight
    if total <= 0:
        raise ValueError("risk_weight + damage_weight must be > 0")
    numerator = (
        risk_weight * RISK_LEVEL_SCORES[risk_level] + damage_weight * damage_score
    )
    for weight, score in signal_terms:
        numerator += weight * score
        total += weight
    return numerator / total


def score_signal(name: str, spec: dict, value) -> float:
    """Run a signal's score_fn and check the result is in [0, 1]."""
    try:
        score = float(spec["score_fn"](value))
    except (TypeError, ValueError) as exc:
        raise SignalValueError(
            f"invalid value for {spec['request_field']!r}: {exc}"
        ) from exc
    if not 0.0 <= score <= 1.0:
        raise ValueError(
            f"signal {name!r} score_fn returned {score}, expected a value in [0, 1]"
        )
    return score


def rank_districts(
    entries: list,
    risk_weight: float = DEFAULT_RISK_WEIGHT,
    damage_weight: float = DEFAULT_DAMAGE_WEIGHT,
    signal_weights: Optional[dict] = None,
    signals: Optional[dict] = None,
) -> list:
    """Score and rank pre-validated district entries (highest priority first).

    Each entry is a dict with at least: district, hazard_type, risk_level,
    damage_score. Optional signal values sit under each signal's
    request_field key. Everything else is passed through unchanged so the
    response echoes the caller's inputs.

    signals defaults to OPTIONAL_SIGNALS; signal_weights maps signal name
    -> weight (missing names use the signal's default_weight).

    Adds "priority_score" (rounded to 4 dp), "signals" ({name: {value,
    score}} for active signals; score is None for a district skipping the
    signal) and "rank" to each entry copy. Sorting: priority_score
    descending, ties broken by district name ascending (deterministic).
    Raises SignalValueError when a signal's score_fn rejects a value.
    """
    signals = OPTIONAL_SIGNALS if signals is None else signals
    active = active_signals(entries, signals)

    scored = []
    for entry in entries:
        item = dict(entry)
        terms = []
        item_signals = {}
        for name in active:
            spec = signals[name]
            weight = signal_weight(name, spec, signal_weights)
            value = item.get(spec["request_field"])
            if value is not None:
                try:
                    sig_score = score_signal(name, spec, value)
                except SignalValueError as exc:
                    raise SignalValueError(
                        f"district {item['district']!r}: {exc}"
                    ) from exc
                terms.append((weight, sig_score))
            elif spec["missing_policy"] == "zero":
                sig_score = 0.0
                terms.append((weight, sig_score))
            else:
                sig_score = None
            item_signals[name] = {
                "value": value,
                "score": None if sig_score is None else round(sig_score, 4),
            }
        score = priority_score(
            item["risk_level"], item["damage_score"], risk_weight, damage_weight,
            signal_terms=terms,
        )
        item["priority_score"] = round(score, 4)
        item["signals"] = item_signals
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


# --- flood signal (River Flood Tracker) ---

def flood_urgency_score(h):
    """Urgency in [0, 1] from hours until the river flood peak arrives.

    1.0 up to 12 h, then a straight line down to 0 at 120 h:

        1.0                 if h <= 12
        (120 - h) / 108     if 12 < h < 120
        0.0                 if h >= 120 or h is None

    None scores 0 here for callers that invoke the curve directly. The
    ranker does not call this for a missing value; missing_policy "zero"
    supplies that 0 and still counts the weight, and only after the signal
    is active. h < 0 and non-numeric h raise ValueError (a bad ETA is a
    caller error, not "already here").
    """
    if h is None:
        return 0.0
    if isinstance(h, bool):
        raise ValueError(
            f"flood_eta_hours must be a number >= 0 or null, got {h!r}"
        )
    try:
        hours = float(h)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"flood_eta_hours must be a number >= 0 or null, got {h!r}"
        ) from exc
    # NaN compares false against every bound and would slip through as a
    # non-score; reject it with the same error as a negative ETA.
    if hours != hours or hours < 0:
        raise ValueError(
            f"flood_eta_hours must be a number >= 0 or null, got {h!r}"
        )
    if hours <= 12:
        return 1.0
    if hours >= 120:
        return 0.0
    return (120.0 - hours) / 108.0


register_signal(
    "flood",
    request_field="flood_eta_hours",
    weight_env="PRIORITY_FLOOD_WEIGHT",
    default_weight=0.3,
    score_fn=flood_urgency_score,
    missing_policy="zero",
    curve="1.0 up to 12 h, falling linearly to 0 at 120 h",
    note=(
        "Hours until the river flood peak reaches the district "
        "(River Flood Tracker estimate)."
    ),
)
