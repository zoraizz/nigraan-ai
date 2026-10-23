"""Pydantic models for a ground-photo report.

The vision model fills a closed set of observation fields (VlmObservation).
Everything an officer or the pipeline adds — id, urgency, place, duplicate
linkage, review — lives on GroundReport. The model does not decide URGENT
and does not write those fields.

Unknown enum strings from the model are coerced to a safe value instead of
failing the whole report:

- scene_type -> other_disaster
- damage_level and water depth -> none
- image_kind -> irrelevant (do not invent a ground-disaster photo)
- a hazard or need that is not in the list is dropped

Case and surrounding whitespace are ignored ("Destroyed" is destroyed).
A missing required field still fails validation. Coercion is only for a
present string that is not one of the closed values.

GroundReport subclasses VlmObservation, so the stored JSON is flat: the
observation fields and the code-added fields sit on one object. After an
officer corrects a report, the top-level fields ARE the corrected values.
review.ai_original keeps the model snapshot and is never what scoring reads.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, BeforeValidator, Field

# ---- enums ----


class ImageKind(str, Enum):
    ground_disaster = "ground_disaster"
    aerial_or_satellite = "aerial_or_satellite"
    irrelevant = "irrelevant"


class SceneType(str, Enum):
    flooded_street = "flooded_street"
    flooded_farmland = "flooded_farmland"
    collapsed_house = "collapsed_house"
    damaged_building = "damaged_building"
    damaged_road = "damaged_road"
    broken_bridge = "broken_bridge"
    landslide = "landslide"
    debris = "debris"
    relief_camp = "relief_camp"
    other_disaster = "other_disaster"


class DamageLevel(str, Enum):
    none = "none"
    partial = "partial"
    destroyed = "destroyed"


class WaterDepth(str, Enum):
    none = "none"
    ankle = "ankle"
    knee = "knee"
    waist = "waist"
    chest = "chest"
    above_head = "above_head"


class Hazard(str, Enum):
    blocked_road = "blocked_road"
    downed_power_lines = "downed_power_lines"
    unstable_structure = "unstable_structure"
    fast_water = "fast_water"
    fire = "fire"


class Need(str, Enum):
    rescue = "rescue"
    shelter = "shelter"
    medical = "medical"
    food_water = "food_water"
    road_clearance = "road_clearance"


class LocationSource(str, Enum):
    exif = "exif"
    device = "device"
    manual = "manual"
    unknown = "unknown"


class ReportStatus(str, Enum):
    unverified = "unverified"
    verified = "verified"
    corrected = "corrected"
    rejected = "rejected"


class ReporterRole(str, Enum):
    """citizen, field_worker, or officer. officer needs the PIN at intake.

    rescue_team is no longer offered anywhere. It stays so older stored
    reports still load.
    """

    citizen = "citizen"
    field_worker = "field_worker"
    officer = "officer"
    rescue_team = "rescue_team"


class ReviewAction(str, Enum):
    verify = "verify"
    correct = "correct"
    reject = "reject"


# ---- coercion ----


def _enum_coercer(enum_cls: type[Enum], fallback: Enum):
    """Map a stray string onto fallback. Non-strings pass through to Pydantic."""

    def coerce(value: object) -> object:
        if isinstance(value, enum_cls):
            return value
        if not isinstance(value, str):
            return value
        text = value.strip()
        for candidate in (text, text.lower()):
            try:
                return enum_cls(candidate)
            except ValueError:
                continue
        return fallback

    return coerce


def _enum_list_coercer(enum_cls: type[Enum]):
    """Keep known list entries. Drop unknown strings instead of failing."""

    def coerce(value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple)):
            return value
        kept: list[Enum] = []
        for item in value:
            if isinstance(item, enum_cls):
                kept.append(item)
                continue
            if not isinstance(item, str):
                continue
            text = item.strip()
            matched = None
            for candidate in (text, text.lower()):
                try:
                    matched = enum_cls(candidate)
                    break
                except ValueError:
                    continue
            if matched is not None:
                kept.append(matched)
        return kept

    return coerce


ImageKindField = Annotated[
    ImageKind,
    BeforeValidator(_enum_coercer(ImageKind, ImageKind.irrelevant)),
]
SceneTypeField = Annotated[
    SceneType,
    BeforeValidator(_enum_coercer(SceneType, SceneType.other_disaster)),
]
DamageLevelField = Annotated[
    DamageLevel,
    BeforeValidator(_enum_coercer(DamageLevel, DamageLevel.none)),
]
WaterDepthField = Annotated[
    WaterDepth,
    BeforeValidator(_enum_coercer(WaterDepth, WaterDepth.none)),
]
HazardListField = Annotated[
    list[Hazard],
    BeforeValidator(_enum_list_coercer(Hazard)),
]
NeedListField = Annotated[
    list[Need],
    BeforeValidator(_enum_list_coercer(Need)),
]
LocationSourceField = Annotated[
    LocationSource,
    BeforeValidator(_enum_coercer(LocationSource, LocationSource.unknown)),
]
ReportStatusField = Annotated[
    ReportStatus,
    BeforeValidator(_enum_coercer(ReportStatus, ReportStatus.unverified)),
]
ReporterRoleField = Annotated[
    ReporterRole,
    BeforeValidator(_enum_coercer(ReporterRole, ReporterRole.citizen)),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- observation (model fills these) ----


class WaterObservation(BaseModel):
    present: bool
    flowing: bool
    depth: WaterDepthField = WaterDepth.none


class PeopleObservation(BaseModel):
    visible: bool
    count_estimate: int | None = Field(default=None, ge=0)
    stranded_or_trapped: bool = False
    on_rooftop: bool = False
    injured: bool = False


class AnimalsObservation(BaseModel):
    livestock_visible: bool = False
    livestock_at_risk: bool = False


class VlmObservation(BaseModel):
    """Closed observation. Urgent, place, and ids are not the model's job."""

    image_kind: ImageKindField
    image_confidence: float = Field(ge=0.0, le=1.0)
    scene_type: SceneTypeField
    damage_level: DamageLevelField
    water: WaterObservation
    hazards: HazardListField = Field(default_factory=list)
    people: PeopleObservation
    animals: AnimalsObservation = Field(default_factory=AnimalsObservation)
    needs: NeedListField = Field(default_factory=list)
    summary: str = ""
    confidence: float = Field(ge=0.0, le=1.0)


# ---- code-added fields ----


class Location(BaseModel):
    lat: float | None = None
    lon: float | None = None
    source: LocationSourceField = LocationSource.unknown
    district: str | None = None
    village: str | None = None


class ReviewEvent(BaseModel):
    """One officer action appended to review.history."""

    action: ReviewAction
    note: str | None = None
    officer: str | None = None
    at: str | None = None
    corrections: dict | None = None


class Review(BaseModel):
    history: list[ReviewEvent] = Field(default_factory=list)
    ai_original: VlmObservation | None = None


class GroundReport(VlmObservation):
    """One ground photo: the observation plus everything the code decides.

    On a corrected report the observation fields (and location.district)
    already hold the officer's values. review.ai_original is the unmodified
    model output.
    """

    id: str = Field(default_factory=lambda: uuid4().hex)
    created_at: str = Field(default_factory=_utc_now)
    urgent: bool = False
    urgent_reasons: list[str] = Field(default_factory=list)
    location: Location = Field(default_factory=Location)
    phash: str = ""
    duplicate_of: str | None = None
    duplicate_count: int = Field(default=0, ge=0)
    status: ReportStatusField = ReportStatus.unverified
    review: Review = Field(default_factory=Review)
    reporter_role: ReporterRoleField = ReporterRole.citizen
    vlm_source: str = ""
    vlm_model: str = ""
