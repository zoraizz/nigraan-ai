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

Error responses use a unified structure:
    { "error": { "code": "<machine-readable>", "message": "<human-readable>" } }
Schema-level validation errors surface as FastAPI's standard 422 detail.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

# Load .env from the aid-priority directory (same pattern as risk-flag).
load_dotenv(Path(__file__).parent / ".env")

from scoring import (  # noqa: E402
    DAMAGE_SEVERITY_SCORES,
    DEFAULT_DAMAGE_WEIGHT,
    DEFAULT_RISK_WEIGHT,
    HAZARD_TYPES,
    RISK_LEVEL_SCORES,
    low_coverage_warning,
    rank_districts,
    score_breakdown,
    score_single_tile,
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

# CORS -- allow the dashboard frontend (Vite dev server,
# http://localhost:5173) to call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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


class ScoringInfo(BaseModel):
    formula: str
    risk_weight: float
    damage_weight: float
    risk_level_scores: dict
    damage_severity_scores: dict
    tie_breaker: str
    photo_count_note: str
    low_coverage_note: str


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

    ranked = rank_districts(
        entries, risk_weight=RISK_WEIGHT, damage_weight=DAMAGE_WEIGHT
    )

    logger.info(
        "Ranked %d district(s); top: %s (%.4f)",
        len(ranked),
        ranked[0]["district"] if ranked else "-",
        ranked[0]["priority_score"] if ranked else 0.0,
    )

    return RankPriorityResponse(
        ranked_districts=[RankedDistrict(**r) for r in ranked],
        scoring=ScoringInfo(
            formula=(
                "priority = (risk_weight * risk_score + damage_weight * "
                "damage_score) / (risk_weight + damage_weight)"
            ),
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
        ),
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "risk_weight": RISK_WEIGHT,
        "damage_weight": DAMAGE_WEIGHT,
        "low_coverage_tile_threshold": LOW_COVERAGE_TILE_THRESHOLD,
    }
