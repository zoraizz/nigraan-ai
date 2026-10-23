"""POST /intake: route one upload to the satellite classifier or a ground report.

The satellite path is the existing /classify-damage behaviour and must stay
that way. Every upload first goes through classify_pil (main.py's
_classify_pil, passed in so this module never imports main). When the OOD
guard does not flag the image, the response is {"route": "satellite"} with
the same fields /classify-damage returns for that image, and the vision model
is never called. /classify-damage itself is not refactored to share this
code: the dict is rebuilt here and a test compares the two responses.

Only an OOD-flagged image reaches the vision model, and it becomes a ground
report only when the model says ground_disaster with image_confidence at or
above GROUND_MIN_CONFIDENCE. Everything else (irrelevant, aerial, low
confidence, no provider, timeout, bad JSON) is rejected the way
/classify-damage rejects it today: the same OOD message and ood fields, plus
a machine-readable reason.

The model observes; this module decides. Urgency comes from
rules.urgent_reasons, place from geo.resolve_location, duplicates from
phash.hamming. EXIF GPS is read from the ORIGINAL upload before any
conversion, because convert() and prepare_image() drop it.

Duplicates: a new report is compared with existing non-rejected reports that
share its district, or that lie within DUPLICATE_RADIUS_KM when both have
coordinates. The first one within GROUND_DUPLICATE_MAX_HAMMING bits wins and
duplicate_of points at that group's first report, so a group is always one
canonical report plus copies. Scoring later counts the canonical only.

Reports and their JPEGs live in a ReportStore. The default is the JSON
directory in ground_intake.store, so a restart keeps officer reviews. The
stored photo is the upright JPEG the model saw: EXIF removed, long side at
most 1024 px.

Officer review does not call the vision model again. verify, correct, and
reject change status, the allowed correction fields, and review.history.
correct recomputes urgent from the edited observation. The first model
output stays in review.ai_original; a later correction does not replace it.

GET /ground-reports hides copies under the group's first report unless
include_duplicates is true, and sets duplicate_count to how many stored
reports point at that first id. Rows are ordered urgent-and-unverified,
then other unverified, then already-reviewed, newest first inside each
group. GET /ground-summary is rules.district_summary over the store.

Officer access: the five /ground-reports routes need the shared officer PIN
(OFFICER_REVIEW_KEY) in the X-Officer-Key header, or in an officer_key query
param for the photo, because <img src> cannot send headers. POST /intake and
GET /ground-summary stay open: anyone may upload, and the summary is
aggregate counts only. The one exception is reporter_role=officer on
/intake, which needs the same PIN so a field worker cannot claim to be an
officer. This is a demo-grade shared PIN, not real accounts.

DELETE /ground-reports/{id} removes the report and its photo for good;
reject is the way to keep a record that a report was false. Copies of a
deleted report are re-pointed by the store, so duplicate_count stays right.
"""

from __future__ import annotations

import copy
import hmac
import io
import os
import tempfile
from datetime import datetime, timezone
from typing import Callable, Optional

from fastapi import APIRouter, Depends, File, Header, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.routing import APIRoute
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, ImageOps
from pydantic import BaseModel, ValidationError

from ground_intake.geo import haversine_km, read_exif_gps, resolve_location
from ground_intake.phash import dhash, hamming
from ground_intake.rules import district_summary, urgent_reasons
from ground_intake.schema import (
    DamageLevel,
    GroundReport,
    ImageKind,
    Need,
    ReporterRole,
    ReportStatus,
    Review,
    ReviewAction,
    SceneType,
    VlmObservation,
    WaterDepth,
)
from ground_intake.store import JsonReportStore, ReportStore, open_store
from ground_intake.vlm import (
    VlmUnavailable,
    _configured_chain,
    describe_with_chain,
    prepare_image,
)

# ---------------------------------------------------------------------------
# Limits (env-overridable, safe defaults)
# ---------------------------------------------------------------------------
DEFAULT_MAX_UPLOAD_BYTES = 10_485_760
DEFAULT_MIN_CONFIDENCE = 0.6
DEFAULT_DISTRICT_MAX_KM = 60.0
DEFAULT_DUPLICATE_MAX_HAMMING = 8
# Two GPS-tagged photos this close are candidates for the same scene even
# when their districts differ (or one has none).
DUPLICATE_RADIUS_KM = 1.0

# DEMO ONLY: remove this default after the hackathon
DEMO_OFFICER_REVIEW_KEY = "2026"
OFFICER_PIN_MESSAGE = "Officer PIN required or wrong."
OFFICER_PIN_CODE = "officer_pin_required"

# Copied verbatim from /classify-damage. A test asserts they stay equal.
INVALID_IMAGE_MESSAGE = "Invalid image file. Expected a valid image format."
OOD_MESSAGE = (
    "This image doesn't resemble a satellite disaster-imagery "
    "tile -- the damage result may be unreliable."
)


def _env_int(name: str, default: int) -> int:
    """Read a non-negative integer env var, or return default."""
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(str(raw).strip())
    except ValueError:
        return default
    return value if value >= 0 else default


def _env_float(name: str, default: float) -> float:
    """Read a non-negative float env var, or return default."""
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = float(str(raw).strip())
    except ValueError:
        return default
    return value if value >= 0 else default


# ---------------------------------------------------------------------------
# Officer PIN
# ---------------------------------------------------------------------------
class OfficerPinRequired(Exception):
    """Raised by require_officer; _GroundRoute turns it into the 401 body."""


def officer_review_key() -> str:
    """OFFICER_REVIEW_KEY, or the demo default when unset or blank."""
    raw = os.environ.get("OFFICER_REVIEW_KEY")
    if raw is None or not raw.strip():
        return DEMO_OFFICER_REVIEW_KEY
    return raw.strip()


def require_officer(
    x_officer_key: Optional[str] = Header(default=None),
    officer_key: Optional[str] = Query(
        default=None,
        description="Officer PIN for <img src>, which cannot send headers",
    ),
) -> None:
    """Pass when the header (or else the query param) equals OFFICER_REVIEW_KEY."""
    supplied = x_officer_key if x_officer_key is not None else officer_key
    if not officer_key_matches(supplied):
        raise OfficerPinRequired()


def officer_key_matches(supplied: object) -> bool:
    """True when supplied is a string equal to OFFICER_REVIEW_KEY."""
    if not isinstance(supplied, str):
        return False
    return hmac.compare_digest(
        supplied.strip().encode("utf-8"), officer_review_key().encode("utf-8")
    )


class _GroundRoute(APIRoute):
    """Answers OfficerPinRequired with the usual {"error", "code"} body.

    Handled per route so main.py needs no app-level exception handler.
    """

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request):
            try:
                return await handler(request)
            except OfficerPinRequired:
                return _error(401, OFFICER_PIN_CODE, OFFICER_PIN_MESSAGE)

        return guarded


_OFFICER_ONLY = [Depends(require_officer)]


# ---------------------------------------------------------------------------
# Store (JSON directory by default; tests swap in a temp directory)
# ---------------------------------------------------------------------------
_store: ReportStore = open_store()
_owned_test_dir: Optional[tempfile.TemporaryDirectory] = None


def get_store() -> ReportStore:
    return _store


def set_store_for_tests(store: Optional[ReportStore] = None) -> ReportStore:
    """Point the process at `store`, or at a fresh throwaway directory.

    The no-arg form is isolated from GROUND_REPORTS_DIR so intake tests do
    not write the service's real reports folder. Passing a store leaves
    that directory alone; the caller owns its cleanup.
    """
    global _store, _owned_test_dir
    previous = _owned_test_dir
    _owned_test_dir = None
    if store is None:
        _owned_test_dir = tempfile.TemporaryDirectory(prefix="ground-reports-")
        store = JsonReportStore(_owned_test_dir.name)
    _store = store
    if previous is not None:
        previous.cleanup()
    return _store


def ground_health() -> dict:
    """Extra /health fields. Names only: never a key or an env value."""
    chain = _configured_chain()
    return {
        "ground_vlm_providers": [provider.name for provider in chain],
        "ground_vlm_configured": any(provider.configured for provider in chain),
        "ground_report_count": get_store().count(),
    }


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def _ood_fields(ood: dict) -> dict:
    """The ood object exactly as /classify-damage shapes it."""
    fields = {
        "cosine": ood["cosine"],
        "mahalanobis": ood["mahalanobis"],
        "cosine_threshold": ood["cosine_threshold"],
        "mahalanobis_threshold": ood["mahalanobis_threshold"],
        "signals": ood["signals"],
    }
    for key in ("photo_cosine", "photo_mahalanobis", "photo_score",
                "photo_score_threshold"):
        if key in ood:
            fields[key] = ood[key]
    return fields


def satellite_response(pred: dict, area: str) -> dict:
    """Rebuild the /classify-damage body for one classify_pil prediction."""
    response = {
        "damage_level": pred["damage_level"],
        "confidence": pred["confidence"],
        "area": area,
    }
    ood = pred["ood"]
    if ood is not None:
        response["is_out_of_domain"] = ood["is_out_of_domain"]
        response["ood"] = _ood_fields(ood)
        if ood["is_out_of_domain"]:
            response["classification"] = "irrelevant"
            response["message"] = OOD_MESSAGE
    return response


def rejection_reason(obs: VlmObservation, min_confidence: float) -> Optional[str]:
    """None when the observation may become a ground report."""
    if obs.image_kind == ImageKind.aerial_or_satellite:
        return "vlm_aerial"
    if obs.image_kind != ImageKind.ground_disaster:
        return "vlm_irrelevant"
    if obs.image_confidence < min_confidence:
        return "vlm_low_confidence"
    return None


def find_duplicate(
    phash: str,
    location: dict,
    existing: list[GroundReport],
    max_hamming: int,
) -> Optional[str]:
    """Id of the group's first report, or None. Rejected reports are skipped."""
    district = (location.get("district") or "").strip()
    lat, lon = location.get("lat"), location.get("lon")
    for other in existing:
        if other.status == ReportStatus.rejected or not other.phash:
            continue
        same_district = bool(district) and (other.location.district or "").strip() == district
        nearby = (
            lat is not None and lon is not None
            and other.location.lat is not None and other.location.lon is not None
            and haversine_km(lat, lon, other.location.lat, other.location.lon)
            <= DUPLICATE_RADIUS_KM
        )
        if not (same_district or nearby):
            continue
        if hamming(phash, other.phash) <= max_hamming:
            return other.duplicate_of or other.id
    return None


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code,
                        content={"error": message, "code": code})


NOT_FOUND_MESSAGE = "Ground report not found."


def _not_found() -> JSONResponse:
    return _error(404, "not_found", NOT_FOUND_MESSAGE)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _created_epoch(stamp: str) -> float:
    """Unix time for an ISO stamp. Unparseable stamps sort as the oldest."""
    if not stamp:
        return float("-inf")
    text = stamp[:-1] + "+00:00" if stamp.endswith("Z") else stamp
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return float("-inf")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _review_bucket(report: GroundReport) -> int:
    """0 urgent+unverified, 1 other unverified, 2 already reviewed."""
    if report.status == ReportStatus.unverified:
        return 0 if report.urgent else 1
    return 2


def present_reports(
    reports: list[GroundReport],
    *,
    district: Optional[str] = None,
    status: Optional[ReportStatus] = None,
    urgent: Optional[bool] = None,
    include_duplicates: bool = False,
) -> list[dict]:
    """JSON reports for GET /ground-reports.

    Folding hides a row whose duplicate_of points at another id in this
    list, and stamps the parent's duplicate_count. A copy whose parent is
    missing stays visible so the photo is not dropped. Filters apply to the
    rows that remain. duplicate_count is not written back to the store.
    """
    known = {report.id for report in reports}
    counts: dict[str, int] = {}
    for report in reports:
        parent = (report.duplicate_of or "").strip()
        if parent and parent in known:
            counts[parent] = counts.get(parent, 0) + 1

    chosen: list[tuple[int, GroundReport]] = []
    for index, report in enumerate(reports):
        parent = (report.duplicate_of or "").strip()
        if not include_duplicates and parent and parent in known:
            continue
        if district is not None and (report.location.district or "").strip() != district:
            continue
        if status is not None and report.status != status:
            continue
        if urgent is not None and report.urgent != urgent:
            continue
        if not include_duplicates:
            report = report.model_copy(update={"duplicate_count": counts.get(report.id, 0)})
        chosen.append((index, report))

    chosen.sort(key=lambda pair: (
        _review_bucket(pair[1]),
        -_created_epoch(pair[1].created_at),
        -pair[0],
    ))
    return [report.model_dump(mode="json") for _, report in chosen]


# ---------------------------------------------------------------------------
# Officer review
# ---------------------------------------------------------------------------
_CORRECTION_FIELDS = {"damage_level", "scene_type", "needs", "people", "water", "district"}
_PEOPLE_FIELDS = {"visible", "count_estimate", "stranded_or_trapped", "on_rooftop", "injured"}
_PEOPLE_FLAGS = ("visible", "stranded_or_trapped", "on_rooftop", "injured")
_WATER_FIELDS = {"present", "flowing", "depth"}
_OBSERVATION_FIELDS = tuple(VlmObservation.model_fields)


class ReviewRejected(Exception):
    """A review body the officer can fix. code is the API machine code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ReviewRequest(BaseModel):
    """PATCH /ground-reports/{id}/review. corrections is only applied for correct."""

    action: str
    corrections: Optional[dict] = None
    note: Optional[str] = None
    officer: Optional[str] = None


def _exact_enum(enum_cls: type, value: object, label: str) -> str:
    """Accept the closed value, including a different case. Unknown strings fail."""
    if isinstance(value, enum_cls):
        return value.value  # type: ignore[attr-defined]
    if isinstance(value, str):
        text = value.strip()
        for candidate in (text, text.lower()):
            try:
                return enum_cls(candidate).value  # type: ignore[attr-defined]
            except ValueError:
                continue
    raise ReviewRejected("invalid_corrections", f"Invalid {label}.")


def _apply_corrections(data: dict, corrections: object) -> None:
    """Write the officer's fields onto a JSON report dict. Unknown keys fail."""
    if not isinstance(corrections, dict):
        raise ReviewRejected("invalid_corrections", "Corrections must be an object.")
    unknown = set(corrections) - _CORRECTION_FIELDS
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ReviewRejected("invalid_corrections", f"Unknown correction fields: {names}.")

    if "damage_level" in corrections:
        data["damage_level"] = _exact_enum(
            DamageLevel, corrections["damage_level"], "damage_level"
        )
    if "scene_type" in corrections:
        data["scene_type"] = _exact_enum(SceneType, corrections["scene_type"], "scene_type")
    if "needs" in corrections:
        needs = corrections["needs"]
        if not isinstance(needs, list):
            raise ReviewRejected("invalid_corrections", "Invalid needs.")
        data["needs"] = [_exact_enum(Need, item, "needs") for item in needs]
    if "people" in corrections:
        data["people"] = _merge_people(data.get("people") or {}, corrections["people"])
    if "water" in corrections:
        data["water"] = _merge_water(data.get("water") or {}, corrections["water"])
    if "district" in corrections:
        district = corrections["district"]
        location = data.get("location")
        if not isinstance(location, dict):
            location = {}
            data["location"] = location
        if district is None:
            location["district"] = None
        elif isinstance(district, str):
            location["district"] = district.strip() or None
        else:
            raise ReviewRejected("invalid_corrections", "Invalid district.")


def _merge_people(current: dict, patch: object) -> dict:
    if not isinstance(patch, dict):
        raise ReviewRejected("invalid_corrections", "Invalid people.")
    unknown = set(patch) - _PEOPLE_FIELDS
    if unknown:
        raise ReviewRejected("invalid_corrections", "Invalid people.")
    merged = dict(current)
    for key, value in patch.items():
        if key == "count_estimate":
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ReviewRejected("invalid_corrections", "Invalid people.")
        elif key in _PEOPLE_FLAGS and not isinstance(value, bool):
            raise ReviewRejected("invalid_corrections", "Invalid people.")
        merged[key] = value
    return merged


def _merge_water(current: dict, patch: object) -> dict:
    if not isinstance(patch, dict):
        raise ReviewRejected("invalid_corrections", "Invalid water.")
    unknown = set(patch) - _WATER_FIELDS
    if unknown:
        raise ReviewRejected("invalid_corrections", "Invalid water.")
    merged = dict(current)
    if "present" in patch and not isinstance(patch["present"], bool):
        raise ReviewRejected("invalid_corrections", "Invalid water.")
    if "flowing" in patch and not isinstance(patch["flowing"], bool):
        raise ReviewRejected("invalid_corrections", "Invalid water.")
    if "depth" in patch:
        merged["depth"] = _exact_enum(WaterDepth, patch["depth"], "water.depth")
    for key in ("present", "flowing"):
        if key in patch:
            merged[key] = patch[key]
    return merged


def apply_review(report: GroundReport, request: ReviewRequest, *, at: Optional[str] = None) -> GroundReport:
    """Return the reviewed report. The caller's object is left unchanged.

    correct snapshots the observation into review.ai_original the first time
    that field is empty, then applies corrections and recomputes urgent.
    verify and reject only change status. Every action appends history.
    """
    try:
        action = ReviewAction(request.action.strip())
    except (AttributeError, ValueError):
        raise ReviewRejected(
            "invalid_action",
            "Review action must be verify, correct, or reject.",
        ) from None

    data = report.model_dump(mode="json")
    if action == ReviewAction.correct:
        original = data["review"].get("ai_original")
        if original is None:
            data["review"]["ai_original"] = copy.deepcopy(
                {key: data[key] for key in _OBSERVATION_FIELDS}
            )
        if request.corrections:
            _apply_corrections(data, request.corrections)
        try:
            draft = GroundReport.model_validate(data)
        except ValidationError:
            raise ReviewRejected("invalid_corrections", "Corrections could not be applied.") from None
        reasons = urgent_reasons(draft)
        data = draft.model_dump(mode="json")
        data["urgent"] = bool(reasons)
        data["urgent_reasons"] = reasons
        data["status"] = ReportStatus.corrected.value
    elif action == ReviewAction.verify:
        data["status"] = ReportStatus.verified.value
    else:
        data["status"] = ReportStatus.rejected.value

    data["review"]["history"].append({
        "action": action.value,
        "officer": request.officer,
        "note": request.note,
        "at": at or _utc_now(),
    })
    try:
        return GroundReport.model_validate(data)
    except ValidationError:
        raise ReviewRejected("invalid_corrections", "Corrections could not be applied.") from None


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
def build_router(
    classify_pil: Callable[[Image.Image], dict],
    model_loaded: Callable[[], bool] = lambda: True,
) -> APIRouter:
    """classify_pil is main._classify_pil. model_loaded drives X-Model-Warning."""
    router = APIRouter(route_class=_GroundRoute)

    def _headers() -> dict:
        return {} if model_loaded() else {"X-Model-Warning": "untrained-weights"}

    @router.post("/intake")
    async def intake(
        image: UploadFile = File(..., description="Satellite tile or ground photo"),
        district: Optional[str] = Query(default=None),
        village: Optional[str] = Query(default=None),
        lat: Optional[float] = Query(default=None, ge=-90, le=90),
        lon: Optional[float] = Query(default=None, ge=-180, le=180),
        reporter_role: Optional[str] = Query(
            default=None,
            description="field_worker | officer (missing or unknown -> field_worker; "
                        "citizen accepted for old clients). officer needs X-Officer-Key.",
        ),
        x_officer_key: Optional[str] = Header(default=None),
    ):
        """Route an upload: satellite result, ground report, or irrelevant."""
        # Checked first, so a failed claim never reaches the models.
        if ((reporter_role or "").strip().lower() == ReporterRole.officer.value
                and not officer_key_matches(x_officer_key)):
            return _error(401, OFFICER_PIN_CODE, OFFICER_PIN_MESSAGE)

        max_bytes = (_env_int("GROUND_MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES)
                     or DEFAULT_MAX_UPLOAD_BYTES)
        contents = await image.read(max_bytes + 1)
        if len(contents) > max_bytes:
            return _error(413, "image_too_large",
                          f"Upload exceeds the limit of {max_bytes} bytes.")

        try:
            original = Image.open(io.BytesIO(contents))
            # GPS must be read before convert(), which drops EXIF.
            exif_gps = read_exif_gps(original)
            pil_image = original.convert("RGB")
        except Image.DecompressionBombError:
            return _error(413, "image_too_large", "Image has too many pixels.")
        except Exception:
            return _error(400, "invalid_image", INVALID_IMAGE_MESSAGE)

        # Same call /classify-damage makes, on the same RGB conversion.
        pred = classify_pil(pil_image)
        ood = pred["ood"]
        if ood is None or not ood["is_out_of_domain"]:
            area = (district or "").strip() or "unknown"
            return JSONResponse(
                content={"route": "satellite",
                         "satellite": satellite_response(pred, area)},
                headers=_headers(),
            )

        # Phone photos carry their rotation in EXIF. The satellite path above
        # deliberately does not transpose, to match /classify-damage.
        try:
            upright = ImageOps.exif_transpose(original).convert("RGB")
        except Exception:
            upright = pil_image
        jpeg = prepare_image(upright)

        def _irrelevant(reason: str) -> JSONResponse:
            return JSONResponse(
                content={"route": "irrelevant", "message": OOD_MESSAGE,
                         "reason": reason, "ood": _ood_fields(ood)},
                headers=_headers(),
            )

        try:
            obs, vlm_source, vlm_model = await run_in_threadpool(
                describe_with_chain, jpeg)
        except VlmUnavailable:
            return _irrelevant("vlm_unavailable")
        except Exception:
            # Never surface provider errors: they can carry request details.
            return _irrelevant("vlm_unavailable")

        min_confidence = _env_float("GROUND_MIN_CONFIDENCE", DEFAULT_MIN_CONFIDENCE)
        reason = rejection_reason(obs, min_confidence)
        if reason is not None:
            return _irrelevant(reason)

        location = resolve_location(
            exif_gps, lat, lon, district, village,
            _env_float("GROUND_DISTRICT_MAX_KM", DEFAULT_DISTRICT_MAX_KM),
        )
        phash = dhash(upright)
        store = get_store()
        duplicate_of = find_duplicate(
            phash, location, store.list(),
            _env_int("GROUND_DUPLICATE_MAX_HAMMING", DEFAULT_DUPLICATE_MAX_HAMMING),
        )
        reasons = urgent_reasons(obs)
        report = GroundReport.model_validate({
            **obs.model_dump(),
            "urgent": bool(reasons),
            "urgent_reasons": reasons,
            "location": location,
            "phash": phash,
            "duplicate_of": duplicate_of,
            "status": ReportStatus.unverified,
            "review": Review(ai_original=obs),
            "reporter_role": reporter_role or ReporterRole.field_worker.value,
            "vlm_source": vlm_source,
            "vlm_model": vlm_model,
        })
        # Upright, EXIF-free JPEG the model saw. prepare_image caps the long side at 1024.
        store.add(report, jpeg)
        return JSONResponse(
            content={"route": "ground", "report": report.model_dump(mode="json")},
            headers=_headers(),
        )

    @router.get("/ground-reports", dependencies=_OFFICER_ONLY)
    async def list_ground_reports(
        district: Optional[str] = None,
        status: Optional[str] = None,
        urgent: Optional[bool] = None,
        include_duplicates: bool = False,
    ):
        """List reports. Copies are folded unless include_duplicates is true."""
        parsed_status: Optional[ReportStatus] = None
        if status is not None and status.strip():
            try:
                parsed_status = ReportStatus(status.strip())
            except ValueError:
                return _error(
                    422,
                    "invalid_status",
                    "Status must be unverified, verified, corrected, or rejected.",
                )
        district_name = district.strip() if district and district.strip() else None
        payload = present_reports(
            get_store().list(),
            district=district_name,
            status=parsed_status,
            urgent=urgent,
            include_duplicates=include_duplicates,
        )
        return JSONResponse(content=payload)

    @router.get("/ground-reports/{report_id}", dependencies=_OFFICER_ONLY)
    async def get_ground_report(report_id: str):
        """One report, including duplicates and rejected rows."""
        report = get_store().get(report_id)
        if report is None:
            return _not_found()
        return JSONResponse(content=report.model_dump(mode="json"))

    @router.get("/ground-reports/{report_id}/photo", dependencies=_OFFICER_ONLY)
    async def get_ground_photo(report_id: str):
        """The stored JPEG, already stripped of EXIF at intake."""
        path = get_store().photo_path(report_id)
        if path is None:
            return _not_found()
        return FileResponse(path, media_type="image/jpeg")

    @router.patch("/ground-reports/{report_id}/review", dependencies=_OFFICER_ONLY)
    async def review_ground_report(report_id: str, body: ReviewRequest):
        """verify, correct, or reject. correct recomputes urgent."""
        store = get_store()
        current = store.get(report_id)
        if current is None:
            return _not_found()
        try:
            updated = apply_review(current, body)
        except ReviewRejected as exc:
            return _error(422, exc.code, str(exc))
        try:
            store.update(updated)
        except KeyError:
            return _not_found()
        return JSONResponse(content=updated.model_dump(mode="json"))

    @router.delete("/ground-reports/{report_id}", dependencies=_OFFICER_ONLY)
    async def delete_ground_report(report_id: str):
        """Remove the report and its photo. Copies get a new first report."""
        try:
            get_store().delete(report_id)
        except KeyError:
            return _not_found()
        return JSONResponse(content={"deleted": report_id})

    @router.get("/ground-summary")
    async def ground_summary(district: Optional[str] = None):
        """Per-district shares. Rejected reports and duplicates stay out of the score."""
        reports = get_store().list()
        if district and district.strip():
            name = district.strip()
            reports = [
                report for report in reports
                if (report.location.district or "").strip() == name
            ]
        return JSONResponse(content=district_summary(reports))

    return router
