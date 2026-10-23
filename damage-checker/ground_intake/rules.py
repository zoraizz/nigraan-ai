"""Pure decisions for ground-photo intake. No I/O, no model calls.

urgent_reasons() turns an observation into a list of reason codes. The model
records what it sees (a person on a roof, water at the waist). This function
is the only place those observations become URGENT. An empty list means the
report is not urgent.

district_summary() rolls reports up by district for the summary endpoint and,
later, for the aid-priority ground signal.

More photos is not more damage. Every figure that can feed a score is a share
over unique, non-rejected reports:

- a report with status rejected is dropped entirely
- a report with duplicate_of set belongs to a group that is already counted
  through its canonical report, so it is not a second report
- ground_score = (0.5 * partial + 1.0 * destroyed) / report_count
- share_destroyed and share_damaged use the same denominator

photo_count, report_count, verified_count, urgent_open, severity_mix, and
top_scene_types counts are display. low_sample_warning is display, the same
idea as low_coverage_warning in aid-priority: it tells an officer the share
rests on very few reports, and it is not itself a score.

Corrected reports are read as stored. Officer edits overwrite the observation
fields; review.ai_original is the model snapshot and is not consulted here.
"""

from __future__ import annotations

from collections import Counter
from typing import Sequence

from ground_intake.schema import (
    DamageLevel,
    GroundReport,
    ReportStatus,
    VlmObservation,
    WaterDepth,
)

# A share over one or two unique reports is too thin to treat as a district
# picture. The warning is text, not a penalty.
LOW_SAMPLE_THRESHOLD = 3

_DEEP_WATER = {WaterDepth.waist, WaterDepth.chest, WaterDepth.above_head}


def urgent_reasons(obs: VlmObservation) -> list[str]:
    """Reason codes, in a fixed order. Empty means not urgent.

    rising_water_near_people requires a visible person. Deep water or flowing
    water in an empty frame is damage, not a rescue flag. Knee-deep still
    water with nobody trapped, on a roof, or injured is not urgent.
    """
    reasons: list[str] = []
    if obs.people.stranded_or_trapped:
        reasons.append("people_trapped")
    if obs.people.on_rooftop:
        reasons.append("people_on_rooftop")
    if obs.people.injured:
        reasons.append("people_injured")
    deep = obs.water.depth in _DEEP_WATER
    if obs.people.visible and (deep or obs.water.flowing):
        reasons.append("rising_water_near_people")
    return reasons


def low_sample_warning(report_count: int, threshold: int = LOW_SAMPLE_THRESHOLD) -> str | None:
    """Display-only. None once the district has `threshold` unique reports."""
    if report_count < threshold:
        noun = "report" if report_count == 1 else "reports"
        return f"low sample — based on {report_count} {noun}"
    return None


def _as_report(item: GroundReport | dict) -> GroundReport:
    if isinstance(item, GroundReport):
        return item
    return GroundReport.model_validate(item)


def _is_duplicate(report: GroundReport) -> bool:
    return bool(report.duplicate_of and report.duplicate_of.strip())


def _scene_name(report: GroundReport) -> str:
    scene = report.scene_type
    return scene.value if hasattr(scene, "value") else str(scene)


def district_summary(reports: Sequence[GroundReport | dict]) -> dict:
    """Per-district shares over unique, non-rejected reports.

    Returns {"districts": {name: {...}}}. Districts with no surviving photo
    are omitted. A corrected report contributes its current damage_level,
    scene_type, and location.district, not review.ai_original.
    """
    grouped: dict[str, list[GroundReport]] = {}
    for item in reports:
        report = _as_report(item)
        if report.status == ReportStatus.rejected:
            continue
        district = (report.location.district or "").strip()
        if not district:
            continue
        grouped.setdefault(district, []).append(report)

    districts: dict[str, dict] = {}
    for name, photos in grouped.items():
        unique = [report for report in photos if not _is_duplicate(report)]
        report_count = len(unique)
        mix = {level.value: 0 for level in DamageLevel}
        scenes: Counter[str] = Counter()
        verified_count = 0
        urgent_open = 0
        for report in unique:
            mix[DamageLevel(report.damage_level).value] += 1
            scenes[_scene_name(report)] += 1
            if report.status in (ReportStatus.verified, ReportStatus.corrected):
                verified_count += 1
            if report.urgent:
                urgent_open += 1

        partial = mix[DamageLevel.partial.value]
        destroyed = mix[DamageLevel.destroyed.value]
        if report_count:
            ground_score = (0.5 * partial + 1.0 * destroyed) / report_count
            share_destroyed = destroyed / report_count
            share_damaged = (partial + destroyed) / report_count
        else:
            ground_score = 0.0
            share_destroyed = 0.0
            share_damaged = 0.0

        top_scene_types = [
            {"scene_type": scene_type, "count": count}
            for scene_type, count in sorted(
                scenes.items(), key=lambda item: (-item[1], item[0])
            )[:3]
        ]
        districts[name] = {
            "report_count": report_count,
            "photo_count": len(photos),
            "verified_count": verified_count,
            "severity_mix": mix,
            "share_destroyed": share_destroyed,
            "share_damaged": share_damaged,
            "ground_score": ground_score,
            "top_scene_types": top_scene_types,
            "urgent_open": urgent_open,
            "low_sample_warning": low_sample_warning(report_count),
        }
    return {"districts": districts}
