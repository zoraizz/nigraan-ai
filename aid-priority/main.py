r"""
FastAPI serving endpoint for the aid-priority ranking module.

Endpoints:
    POST /rank-priority  -- score and rank districts by aid urgency
    GET  /health         -- service status + active scoring weights

Run:
    uvicorn main:app --host 0.0.0.0 --port 8002

Pipeline position (stateless by design):

    Risk Flag (/predict-risk)        --\
                                      \   >  POST /rank-priority  -->  ranked districts
    Damage Checker (/classify-damage) --/

The endpoint does NOT call the other services itself. The caller (dashboard
or integration layer) collects each district's risk_level and damage
assessment and submits them together, so every ranking is auditable
end-to-end from the response alone.

Environment variables (loaded from aid-priority/.env, see .env.example):
    PRIORITY_RISK_WEIGHT    -- weight of Risk Flag's risk level  (default 0.4)
    PRIORITY_DAMAGE_WEIGHT  -- weight of Damage Checker severity (default 0.6)
    LOW_COVERAGE_TILE_THRESHOLD -- flag districts assessed on fewer tiles
                       (transparency only; never affects the score)
    <signal weight_env>     -- one weight per registered optional signal
                       (scoring.OPTIONAL_SIGNALS), validated like
                       PRIORITY_RISK_WEIGHT

Error responses use a unified structure:
    { "error": { "code": "<machine-readable>", "message": "<human-readable>" } }
Schema-level validation errors surface as FastAPI's standard 422 detail.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Load .env from the aid-priority directory (same pattern as risk-flag).
load_dotenv(Path(__file__).parent / ".env")

from scoring import (  # noqa: E402
    DAMAGE_SEVERITY_SCORES,
    DEFAULT_DAMAGE_WEIGHT,
    DEFAULT_RISK_WEIGHT,
    HAZARD_TYPES,
    OPTIONAL_SIGNALS,
    RISK_LEVEL_SCORES,
    SignalValueError,
    active_signals,
    formula_text,
    low_coverage_warning,
    rank_districts,
    score_breakdown,
    score_single_tile,
    signal_weight,
    validate_signal_spec,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("aid_priority")

app = FastAPI(
    title="Nigraan AI - Aid Priority",
    description="Rank districts by aid urgency from Risk Flag + Damage Checker outputs",
    version="0.2.0",
)

# CORS -- allow the dashboard frontend to call this API from the browser.
# Origins come from CORS_ORIGINS (comma-separated) so the deployed dashboard
# (Render; see README "Live Deployment") can be allow-listed without code
# changes. Default: the local Vite dev server.
_allowed_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Scoring weights (env-configurable; see .env.example)
# ---------------------------------------------------------------------------
def _load_weight(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
        if value < 0:
            raise ValueError(f"{name} must be >= 0")
        return value
    except ValueError as exc:
        logger.warning("Invalid %s=%r (%s); using default %s", name, raw, exc, default)
        return default


RISK_WEIGHT = _load_weight("PRIORITY_RISK_WEIGHT", DEFAULT_RISK_WEIGHT)
DAMAGE_WEIGHT = _load_weight("PRIORITY_DAMAGE_WEIGHT", DEFAULT_DAMAGE_WEIGHT)
if RISK_WEIGHT + DAMAGE_WEIGHT <= 0:
    logger.warning(
        "PRIORITY_RISK_WEIGHT + PRIORITY_DAMAGE_WEIGHT is 0; using defaults"
    )
    RISK_WEIGHT = DEFAULT_RISK_WEIGHT
    DAMAGE_WEIGHT = DEFAULT_DAMAGE_WEIGHT


def _load_signal_weights(registry: dict) -> dict:
    """Weight per optional signal from its weight_env (same validation as
    PRIORITY_RISK_WEIGHT). Signals registered after startup fall back to
    their default_weight inside scoring.rank_districts."""
    weights = {}
    for name, spec in registry.items():
        validate_signal_spec(name, spec)
        weights[name] = _load_weight(spec["weight_env"], spec["default_weight"])
    return weights


SIGNAL_WEIGHTS = _load_signal_weights(OPTIONAL_SIGNALS)


def _load_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
        if value < 1:
            raise ValueError(f"{name} must be >= 1")
        return value
    except ValueError as exc:
        logger.warning("Invalid %s=%r (%s); using default %s", name, raw, exc, default)
        return default


# ---------------------------------------------------------------------------
# Low-coverage caveat -- INFORMATIONAL ONLY, never a scoring input.
# ---------------------------------------------------------------------------
# Districts whose damage assessment rests on fewer tiles than this get a
# low_coverage_warning string in the response. It is a transparency signal
# for response teams ("how much evidence backs this rank?") and does NOT
# alter priority_score, rank order, or any other computed value.
LOW_COVERAGE_TILE_THRESHOLD = _load_int("LOW_COVERAGE_TILE_THRESHOLD", 5)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class DamageBreakdown(BaseModel):
    """Per-level tile counts from aggregating /classify-damage calls."""

    none: int = Field(0, ge=0)
    partial: int = Field(0, ge=0)
    destroyed: int = Field(0, ge=0)

    @property
    def classified(self) -> int:
        return self.none + self.partial + self.destroyed


class DistrictAssessment(BaseModel):
    """One district's inputs, sourced from Risk Flag + Damage Checker."""

    # Optional-signal values arrive under each signal's request_field, which
    # this model does not declare; unregistered extra keys are never scored.
    model_config = ConfigDict(extra="allow")

    district: str = Field(..., min_length=1)
    hazard_type: str
    risk_level: str

    # Damage assessment -- provide damage_breakdown (aggregated tiles) OR
    # overall_damage_level (single tile), never both.
    damage_breakdown: Optional[DamageBreakdown] = None
    overall_damage_level: Optional[str] = None
    # Confidence of the single /classify-damage call (single-tile mode only).
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    # Optional assessment coverage: total tiles looked at, including any
    # that failed classification. Must be >= classified tile count.
    # NEVER enters the score -- echoed for situational awareness only.
    tile_count: Optional[int] = Field(None, ge=1)

    @field_validator("district")
    @classmethod
    def _strip_district(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("district must be a non-empty string")
        return v

    @field_validator("hazard_type")
    @classmethod
    def _normalize_hazard(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in HAZARD_TYPES:
            raise ValueError(
                f"hazard_type must be one of {sorted(HAZARD_TYPES)}, got {v!r}"
            )
        return v

    @field_validator("risk_level")
    @classmethod
    def _normalize_risk(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in RISK_LEVEL_SCORES:
            raise ValueError(
                f"risk_level must be one of {sorted(RISK_LEVEL_SCORES)}, got {v!r}"
            )
        return v

    @field_validator("overall_damage_level")
    @classmethod
    def _normalize_level(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().lower()
        if v not in DAMAGE_SEVERITY_SCORES:
            raise ValueError(
                "overall_damage_level must be one of "
                f"{sorted(DAMAGE_SEVERITY_SCORES)}, got {v!r}"
            )
        return v

    @model_validator(mode="after")
    def _check_damage_source(self) -> "DistrictAssessment":
        has_breakdown = self.damage_breakdown is not None
        has_level = self.overall_damage_level is not None

        if has_breakdown and has_level:
            raise ValueError(
                "provide either damage_breakdown or overall_damage_level, not both"
            )
        if not has_breakdown and not has_level:
            raise ValueError(
                "a damage assessment is required: damage_breakdown (aggregated "
                "tiles) or overall_damage_level (single tile)"
            )

        if has_breakdown:
            if self.damage_breakdown.classified < 1:
                raise ValueError(
                    "damage_breakdown must contain at least one classified tile "
                    "(none + partial + destroyed >= 1)"
                )
            if (
                self.tile_count is not None
                and self.tile_count < self.damage_breakdown.classified
            ):
                raise ValueError(
                    f"tile_count ({self.tile_count}) must be >= classified tiles "
                    f"({self.damage_breakdown.classified})"
                )
            if self.confidence is not None:
                raise ValueError(
                    "confidence applies to overall_damage_level (single-tile) "
                    "mode only; a breakdown aggregates many tiles"
                )
        else:
            if self.tile_count is not None:
                raise ValueError(
                    "tile_count applies to damage_breakdown mode only; "
                    "overall_damage_level describes exactly one tile"
                )
        return self


class RankPriorityRequest(BaseModel):
    districts: list[DistrictAssessment] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------
class SignalValue(BaseModel):
    value: Any = None
    score: Optional[float] = None


class RankedDistrict(BaseModel):
    rank: int
    district: str
    hazard_type: str
    risk_level: str
    risk_score: float
    damage_score: float
    percent_damaged: float
    tile_count: int
    classified_tiles: int
    damage_source: str
    priority_score: float
    damage_breakdown: Optional[DamageBreakdown] = None
    overall_damage_level: Optional[str] = None
    confidence: Optional[float] = None
    # Transparency signal: non-null when the damage assessment rests on
    # fewer tiles than LOW_COVERAGE_TILE_THRESHOLD. INFORMATIONAL ONLY --
    # never a scoring input (see scoring.low_coverage_warning).
    low_coverage_warning: Optional[str] = None
    # Active optional signals only: raw request value and its [0, 1] score
    # (score is null when a "skip" signal is missing for this district).
    signals: dict[str, SignalValue] = Field(default_factory=dict)


class SignalInfo(BaseModel):
    name: str
    request_field: str
    weight: float
    missing_policy: str
    curve: str
    note: str
    active: bool


class ScoringInfo(BaseModel):
    formula: str
    risk_weight: float
    damage_weight: float
    risk_level_scores: dict
    damage_severity_scores: dict
    tie_breaker: str
    photo_count_note: str
    low_coverage_note: str
    signals: list[SignalInfo] = Field(default_factory=list)


class RankPriorityResponse(BaseModel):
    ranked_districts: list[RankedDistrict]
    scoring: ScoringInfo


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
    )


@app.post("/rank-priority", response_model=RankPriorityResponse)
def rank_priority(req: RankPriorityRequest):
    """Rank districts by aid urgency (highest priority first).

    Combines Risk Flag's risk_level with Damage Checker's damage severity.
    The response echoes every input alongside the computed scores and
    includes the full scoring configuration, so the ranking is transparent
    rather than a black box.
    """
    # Reject duplicates: double-listing a district is almost certainly a
    # caller bug and would double-count it in the ranked output.
    seen = set()
    for d in req.districts:
        key = d.district.lower()
        if key in seen:
            return _error(
                422,
                "duplicate_district",
                f"district {d.district!r} appears more than once in the request",
            )
        seen.add(key)

    entries = []
    for d in req.districts:
        if d.damage_breakdown is not None:
            b = d.damage_breakdown
            damage_score, percent_damaged = score_breakdown(
                b.none, b.partial, b.destroyed
            )
            entries.append({
                "district": d.district,
                "hazard_type": d.hazard_type,
                "risk_level": d.risk_level,
                "risk_score": RISK_LEVEL_SCORES[d.risk_level],
                "damage_score": round(damage_score, 4),
                "percent_damaged": round(percent_damaged, 4),
                "tile_count": d.tile_count if d.tile_count is not None else b.classified,
                "classified_tiles": b.classified,
                # Informational only -- never enters the score.
                "low_coverage_warning": low_coverage_warning(
                    d.tile_count if d.tile_count is not None else b.classified,
                    LOW_COVERAGE_TILE_THRESHOLD,
                ),
                "damage_source": "damage_breakdown",
                "damage_breakdown": b.model_dump(),
                "overall_damage_level": None,
                "confidence": None,
            })
        else:
            damage_score, percent_damaged = score_single_tile(d.overall_damage_level)
            entries.append({
                "district": d.district,
                "hazard_type": d.hazard_type,
                "risk_level": d.risk_level,
                "risk_score": RISK_LEVEL_SCORES[d.risk_level],
                "damage_score": round(damage_score, 4),
                "percent_damaged": round(percent_damaged, 4),
                "tile_count": 1,
                "classified_tiles": 1,
                # Informational only -- never enters the score.
                "low_coverage_warning": low_coverage_warning(
                    1, LOW_COVERAGE_TILE_THRESHOLD
                ),
                "damage_source": "overall_damage_level",
                "damage_breakdown": None,
                "overall_damage_level": d.overall_damage_level,
                "confidence": d.confidence,
            })

    for d, entry in zip(req.districts, entries):
        for spec in OPTIONAL_SIGNALS.values():
            value = _signal_value(d, spec["request_field"])
            if value is not None:
                entry[spec["request_field"]] = value

    active = active_signals(entries)
    try:
        ranked = rank_districts(
            entries,
            risk_weight=RISK_WEIGHT,
            damage_weight=DAMAGE_WEIGHT,
            signal_weights=SIGNAL_WEIGHTS,
        )
    except SignalValueError as exc:
        return _error(422, "invalid_signal_value", str(exc))

    logger.info(
        "Ranked %d district(s); top: %s (%.4f)",
        len(ranked),
        ranked[0]["district"] if ranked else "-",
        ranked[0]["priority_score"] if ranked else 0.0,
    )

    return RankPriorityResponse(
        ranked_districts=[RankedDistrict(**r) for r in ranked],
        scoring=ScoringInfo(
            formula=formula_text(active),
            risk_weight=RISK_WEIGHT,
            damage_weight=DAMAGE_WEIGHT,
            risk_level_scores=RISK_LEVEL_SCORES,
            damage_severity_scores=DAMAGE_SEVERITY_SCORES,
            tie_breaker="equal scores ordered by district name (ascending)",
            photo_count_note=(
                "damage_score is a per-tile average, never a sum -- districts "
                "with more assessed tiles are not prioritized over districts "
                "with fewer tiles at the same damage rate"
            ),
            low_coverage_note=(
                "low_coverage_warning flags districts whose damage assessment "
                "rests on fewer tiles than LOW_COVERAGE_TILE_THRESHOLD "
                f"(currently {LOW_COVERAGE_TILE_THRESHOLD}); it is a "
                "transparency signal for response teams only and never "
                "affects priority_score or rank order"
            ),
            signals=[
                SignalInfo(
                    name=name,
                    request_field=spec["request_field"],
                    weight=signal_weight(name, spec, SIGNAL_WEIGHTS),
                    missing_policy=spec["missing_policy"],
                    curve=spec["curve"],
                    note=spec["note"],
                    active=name in active,
                )
                for name, spec in OPTIONAL_SIGNALS.items()
            ],
        ),
    )


def _signal_value(d: DistrictAssessment, field: str):
    """A signal's raw value from a district, whether the field is declared
    on the model or arrived as an extra key; None when absent."""
    if field in type(d).model_fields:
        return getattr(d, field)
    return (d.model_extra or {}).get(field)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "risk_weight": RISK_WEIGHT,
        "damage_weight": DAMAGE_WEIGHT,
        "low_coverage_tile_threshold": LOW_COVERAGE_TILE_THRESHOLD,
        "signal_weights": {
            name: signal_weight(name, spec, SIGNAL_WEIGHTS)
            for name, spec in OPTIONAL_SIGNALS.items()
        },
    }
