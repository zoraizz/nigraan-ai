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

Storage is an in-memory list behind add/list/get. Step 5 replaces it with a
persistent store; nothing else here should need to change.
"""

from __future__ import annotations

import io
import os
from threading import Lock
from typing import Callable, Optional

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from PIL import Image, ImageOps

from ground_intake.geo import haversine_km, read_exif_gps, resolve_location
from ground_intake.phash import dhash, hamming
from ground_intake.rules import urgent_reasons
from ground_intake.schema import (
    GroundReport,
    ImageKind,
    ReportStatus,
    Review,
    VlmObservation,
)
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
# In-memory store (Step 5 replaces this)
# ---------------------------------------------------------------------------
class MemoryStore:
    """Reports in insertion order, photos keyed by report id. Not persistent."""

    def __init__(self) -> None:
        self._reports: list[GroundReport] = []
        self._photos: dict[str, bytes] = {}
        self._lock = Lock()

    def add(self, report: GroundReport, photo_jpeg: bytes) -> GroundReport:
        with self._lock:
            self._reports.append(report)
            self._photos[report.id] = photo_jpeg
        return report

    def list(self) -> list[GroundReport]:
        with self._lock:
            return list(self._reports)

    def get(self, report_id: str) -> Optional[GroundReport]:
        with self._lock:
            return next((r for r in self._reports if r.id == report_id), None)

    def photo(self, report_id: str) -> Optional[bytes]:
        with self._lock:
            return self._photos.get(report_id)


_store = MemoryStore()


def get_store() -> MemoryStore:
    return _store


def set_store_for_tests(store: Optional[MemoryStore] = None) -> MemoryStore:
    """Swap in a fresh store (or the one given) and return it."""
    global _store
    _store = store if store is not None else MemoryStore()
    return _store


def ground_health() -> dict:
    """Extra /health fields. Names only: never a key or an env value."""
    chain = _configured_chain()
    return {
        "ground_vlm_providers": [provider.name for provider in chain],
        "ground_vlm_configured": any(provider.configured for provider in chain),
        "ground_report_count": len(_store.list()),
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


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
def build_router(
    classify_pil: Callable[[Image.Image], dict],
    model_loaded: Callable[[], bool] = lambda: True,
) -> APIRouter:
    """classify_pil is main._classify_pil. model_loaded drives X-Model-Warning."""
    router = APIRouter()

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
            description="field_worker | rescue_team | citizen (unknown -> citizen)",
        ),
    ):
        """Route an upload: satellite result, ground report, or irrelevant."""
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
            "reporter_role": reporter_role or "citizen",
            "vlm_source": vlm_source,
            "vlm_model": vlm_model,
        })
        # The stored photo is the EXIF-free JPEG the model saw.
        store.add(report, jpeg)
        return JSONResponse(
            content={"route": "ground", "report": report.model_dump(mode="json")},
            headers=_headers(),
        )

    return router
