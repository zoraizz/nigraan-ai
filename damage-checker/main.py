"""
FastAPI serving endpoint for the damage-checker classifier.

Exposes POST /classify-damage matching API_CONTRACT.md:
    Request:  multipart/form-data, field "image"
    Response: { "damage_level": "none|partial|destroyed",
                "confidence": float, "area": "string" }

Also exposes POST /classify-scene: one large image is cut into a
non-overlapping grid and each kept tile is classified with the same model
path and OOD check as /classify-damage. Tile labels are a proxy — the model
was trained on worst-building-per-tile labels at two scales (1024 px xBD
and 512 px EBD) — so percent_damaged is a tile-level estimate, not a
building-level damage rate.

Run:
    uvicorn main:app --host 0.0.0.0 --port 8001

Environment variables (loaded from .env if present):
    CHECKPOINT_PATH  -- path to trained model checkpoint
                       (default: checkpoints/best_model.pth)

Prediction logging:
    Every successful classification appends a row to predictions_log.csv
    (created automatically with headers on first write).  Columns:
        timestamp, image_id, predicted_class, confidence,
        ground_truth, match, checkpoint_path
    Ground truth is looked up from any labels.csv under data/.
    Logging failures are silently ignored so they never break the endpoint.

Out-of-distribution guard (v3):
    Uploads that don't resemble satellite disaster imagery are flagged by
    TWO independent signals (ood_reference.json, built by
    build_ood_reference.py):
    1. texture signal -- cosine AND diagonal-Mahalanobis distance of the
       layer1 (texture) embedding of OUR model from the training
       distribution. Catches synthetic/artificial inputs (noise, text,
       gradients, solid colors).
    2. photo signal -- distance of the image's embedding in a STOCK
       ImageNet-pretrained ResNet-18 from the satellite-tile centroid.
       Fine-tuning collapsed our own model's feature space (everyday photos
       embed INSIDE the satellite cloud at every layer -- verified
       empirically), but the stock model separates the domains: everyday
       photos are near ImageNet classes, overhead tiles are not. A response
       is flagged when the normalized distance sum (cosine/t99 + maha/t99)
       exceeds score_threshold, OR when the sum is moderately elevated AND
       the model's own confidence is low (tie-breaker: a low-confidence
       prediction on a distant image is doubly suspect).
    Flagged responses carry is_out_of_domain=true, classification=
    "irrelevant", the signals that fired, and a warning message; the raw
    model prediction is still returned for transparency.

NOTE -- Bi-temporal upgrade path:
    A future version could add a second "pre_image" form field and call
    the model with in_channels=6 (stacked pre+post).  Changes needed:
    1. Add UploadFile parameter `pre_image` to the endpoint.
    2. Stack pre+post into a 6-channel tensor.
    3. Load a checkpoint trained with in_channels=6.
    See model.build_backbone(in_channels=N) for the model-side swap.
"""

import csv
import io
import json
import os
import threading
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Load .env before any other imports that might use env vars
from dotenv import load_dotenv
load_dotenv()

import torch
from fastapi import FastAPI, File, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from PIL import Image
from torchvision import transforms

from data_loader import IDX_TO_LABEL, NUM_CLASSES
from model import DamageClassifier

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Nigraan AI - Damage Checker",
    description="Post-disaster satellite image damage classification",
    version="0.3.0",
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
# Model loading
# ---------------------------------------------------------------------------
CHECKPOINT_PATH = Path(os.environ.get("CHECKPOINT_PATH", "checkpoints/best_model.pth"))
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

_model: Optional[DamageClassifier] = None
_model_loaded: bool = False

# Out-of-distribution reference (ood_reference.json; see build_ood_reference.py)
OOD_REFERENCE_PATH = Path("ood_reference.json")
IMAGENET_WEIGHTS_PATH = Path("checkpoints/imagenet_resnet18_v1.pth")
_ood_reference: Optional[dict] = None
_ood_centroid: Optional[torch.Tensor] = None
_ood_mean: Optional[torch.Tensor] = None
_ood_std: Optional[torch.Tensor] = None
_last_layer1: Optional[torch.Tensor] = None  # set by forward hook per request

# Photo-detector half of the OOD guard: stock ImageNet ResNet-18 whose
# avgpool embedding is compared against the satellite-tile centroid
# (see build_ood_reference.py -- our fine-tuned model cannot separate
# everyday photos from tiles; the stock model can).
_imagenet_model: Optional[torch.nn.Module] = None
_imagenet_loaded: bool = False
_last_imagenet_feat: Optional[torch.Tensor] = None  # avgpool hook per request
_photo_centroid: Optional[torch.Tensor] = None
_photo_mean: Optional[torch.Tensor] = None
_photo_std: Optional[torch.Tensor] = None

# Preprocessing (must match training DEFAULT_TRANSFORM -- no augmentation at inference)
_preprocess = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225]),
])

# ---------------------------------------------------------------------------
# POST /classify-scene caps (Render free tier: 512 MB RAM, 0.5 vCPU)
# ---------------------------------------------------------------------------
# Decoded RGB is about 3 bytes per pixel. 16,777,216 pixels is ~48 MiB of
# pixels. Measured with scripts/measure_classify_scene.py on 2026-10-06.
# Scene-attributable private bytes were 69 MB for 3000x3000 (9M px,
# allowed) and 275 MB for 6000x6000 (36M px, rejected). At this cap that
# scales to about 128 MB, which stays well under 400 MB. The Windows
# working set on the measurement machine sits near 740 MB before any
# scene because torch/MKL are mapped in. Both caps are env-overridable.
DEFAULT_SCENE_MAX_PIXELS = 16_777_216
# CPU measurement, CUDA_VISIBLE_DEVICES=-1, 8 torch threads, 16 logical
# CPUs: median 0.0435 s/tile, p95 0.0449 s/tile over 36 tiles.
# Single-thread median 0.122 s (2.8x). A 0.5 vCPU instance is assumed
# another 2x slower than one full core, 6x versus the 8-thread p95.
# 111 tiles * 0.0449 s * 6 ≈ 30 s.
DEFAULT_SCENE_MAX_TILES = 111
# Stop classifying once this many seconds have elapsed and return the
# tiles finished so far. Above the ~30 s tile-cap budget so a full allowed
# scene can finish, and under a platform timeout if the instance is slower
# than the 6x assumption.
DEFAULT_SCENE_TIME_BUDGET_SECONDS = 40.0
# Worst-class order for overall_damage_level. Uncertain tiles are excluded.
_DAMAGE_SEVERITY = {"none": 0, "partial": 1, "destroyed": 2}

# ---------------------------------------------------------------------------
# Ground-truth lookup -- built at startup from labels.csv files under data/
# ---------------------------------------------------------------------------
_GROUND_TRUTH: dict[str, str] = {}
_predictions_lock = threading.Lock()
_LOG_PATH = Path("predictions_log.csv")
_LOG_HEADERS = [
    "timestamp", "image_id", "predicted_class", "confidence",
    "ground_truth", "match", "checkpoint_path",
]


def _build_ground_truth_lookup() -> None:
    """Scan data/ for labels.csv files and build image_id -> label mapping."""
    global _GROUND_TRUTH
    data_root = Path("data")
    if not data_root.exists():
        return
    for labels_csv in data_root.rglob("labels.csv"):
        try:
            with open(labels_csv, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    img_id = row.get("id", "").strip()
                    label = row.get("label", "").strip()
                    if img_id and label:
                        _GROUND_TRUTH[img_id] = label
        except Exception as exc:
            print(f"[main] WARNING: Could not parse {labels_csv}: {exc}")
    if _GROUND_TRUTH:
        print(f"[main] Ground-truth lookup: loaded {len(_GROUND_TRUTH)} labels "
              f"from {data_root}")


def _log_prediction(
    image_id: str,
    predicted_class: str,
    confidence: float,
) -> None:
    """Append a prediction row to predictions_log.csv.

    Silently ignores all errors so logging never breaks the endpoint.
    """
    try:
        ground_truth = _GROUND_TRUTH.get(image_id, "")
        match = (predicted_class == ground_truth) if ground_truth else ""

        row = [
            datetime.now(timezone.utc).isoformat(),
            image_id,
            predicted_class,
            f"{confidence:.4f}",
            ground_truth,
            str(match).lower() if ground_truth else "",
            str(CHECKPOINT_PATH),
        ]

        with _predictions_lock:
            file_exists = _LOG_PATH.exists()
            with open(_LOG_PATH, "a", newline="") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(_LOG_HEADERS)
                writer.writerow(row)
    except Exception as exc:
        # Logging must NEVER break the classification response
        print(f"[main] WARNING: Prediction logging failed: {exc}")


def _load_model() -> None:
    """Attempt to load the trained checkpoint at startup."""
    global _model, _model_loaded

    _model = DamageClassifier(in_channels=3, num_classes=NUM_CLASSES).to(DEVICE)

    # Capture the pooled layer1 (texture) embedding per forward pass for the
    # out-of-distribution check. Inference below runs backbone + head
    # manually, so this hook adds the layer1 capture at zero extra cost.
    def _capture_layer1(_module, _inputs, output):
        global _last_layer1
        _last_layer1 = torch.nn.functional.adaptive_avg_pool2d(
            output, 1).flatten(1)

    _model.backbone.layer1.register_forward_hook(_capture_layer1)

    if CHECKPOINT_PATH.exists():
        checkpoint = torch.load(CHECKPOINT_PATH, map_location=DEVICE, weights_only=True)
        _model.load_state_dict(checkpoint["model_state_dict"])
        _model.eval()
        _model_loaded = True
        print(f"[main] Loaded checkpoint from {CHECKPOINT_PATH} "
              f"(epoch {checkpoint.get('epoch')}, "
              f"val_acc={checkpoint.get('val_acc', '?'):.2%})")
    else:
        _model.eval()
        _model_loaded = False
        print(f"[main] WARNING: No checkpoint found at {CHECKPOINT_PATH}. "
              f"Serving with untrained (random) weights.")


def _load_imagenet_detector() -> None:
    """Load the stock ImageNet ResNet-18 used by the photo signal.

    Weights come from checkpoints/imagenet_resnet18_v1.pth (saved by
    download_imagenet_weights.py; fetched by the Render build command).
    If the file is missing, the photo signal is disabled and only the
    texture signal remains -- the endpoint still works.
    """
    global _imagenet_model, _imagenet_loaded, _last_imagenet_feat
    if not IMAGENET_WEIGHTS_PATH.exists():
        print(f"[main] WARNING: ImageNet weights not found at "
              f"{IMAGENET_WEIGHTS_PATH} -- photo-detector signal disabled "
              f"(run download_imagenet_weights.py)")
        return
    from torchvision.models import resnet18
    model = resnet18(weights=None).to(DEVICE)
    state = torch.load(IMAGENET_WEIGHTS_PATH, map_location=DEVICE,
                       weights_only=True)
    model.load_state_dict(state)
    model.eval()

    def _capture_avgpool(_module, _inputs, output):
        global _last_imagenet_feat
        _last_imagenet_feat = torch.flatten(output, 1)

    model.avgpool.register_forward_hook(_capture_avgpool)
    _imagenet_model = model
    _imagenet_loaded = True
    print(f"[main] ImageNet photo-detector loaded from {IMAGENET_WEIGHTS_PATH}")


def _load_ood_reference() -> None:
    """Load ood_reference.json (built offline by build_ood_reference.py)."""
    global _ood_reference, _ood_centroid, _ood_mean, _ood_std
    global _photo_centroid, _photo_mean, _photo_std
    if not OOD_REFERENCE_PATH.exists():
        print(f"[main] OOD reference not found at {OOD_REFERENCE_PATH} -- "
              "out-of-distribution detection disabled")
        return
    _ood_reference = json.loads(OOD_REFERENCE_PATH.read_text())
    _ood_centroid = torch.tensor(
        _ood_reference["layer1"]["centroid"], dtype=torch.float32).to(DEVICE)
    _ood_mean = torch.tensor(
        _ood_reference["layer1"]["mean"], dtype=torch.float32).to(DEVICE)
    _ood_std = torch.tensor(
        _ood_reference["layer1"]["std"], dtype=torch.float32).to(DEVICE)
    t = _ood_reference["layer1"]["thresholds"]
    print(f"[main] OOD reference loaded: layer={_ood_reference['layer1']['layer']} "
          f"texture flag when cosine>{t['cosine']:.4f} AND "
          f"mahalanobis>{t['mahalanobis']:.4f} "
          f"(from {_ood_reference['n_train_images']} training images)")
    photo = _ood_reference.get("photo")
    if photo is not None:
        _photo_centroid = torch.tensor(
            photo["centroid"], dtype=torch.float32).to(DEVICE)
        _photo_mean = torch.tensor(
            photo["mean"], dtype=torch.float32).to(DEVICE)
        _photo_std = torch.tensor(
            photo["std"], dtype=torch.float32).to(DEVICE)
        pt = photo["thresholds"]
        cb = photo["confidence_branch"]
        print(f"[main] Photo signal: score threshold {photo['score_threshold']} "
              f"(cosine p99={pt['cosine']:.4f}, maha p99={pt['mahalanobis']:.3f}); "
              f"confidence tie-breaker score>{cb['score']} AND "
              f"confidence<{cb['max_confidence']}")


def _ood_check(
    layer1_feats: Optional[torch.Tensor],
    imagenet_feats: Optional[torch.Tensor],
    confidence: Optional[float],
) -> Optional[dict]:
    """Combine the texture and photo OOD signals for one upload.

    Returns the distance breakdown and is_out_of_domain when a reference is
    loaded, else None. Signals (any one flags the upload):
      - "texture": layer1 cosine AND mahalanobis above their p99 training
        thresholds (synthetic/artificial inputs).
      - "photo_content": stock-space distance sum (cosine/t99 + maha/t99)
        above score_threshold (everyday photos vs overhead tiles).
      - "low_confidence": distance sum above the branch score AND model
        confidence below max_confidence (tie-breaker for borderline
        inputs -- a distant image the model is unsure about is doubly
        suspect).
    """
    if _ood_reference is None or layer1_feats is None:
        return None
    f = layer1_feats.to(DEVICE)[0]
    cos = float(1 - torch.nn.functional.cosine_similarity(f, _ood_centroid, dim=0))
    maha = float(((f - _ood_mean) / _ood_std).pow(2).sum().sqrt())
    t = _ood_reference["layer1"]["thresholds"]
    result = {
        "cosine": round(cos, 4),
        "mahalanobis": round(maha, 4),
        "cosine_threshold": t["cosine"],
        "mahalanobis_threshold": t["mahalanobis"],
    }
    signals = []
    if cos > t["cosine"] and maha > t["mahalanobis"]:
        signals.append("texture")

    photo = _ood_reference.get("photo")
    if photo is not None and imagenet_feats is not None and _photo_std is not None:
        g = imagenet_feats.to(DEVICE)[0]
        pcos = float(1 - torch.nn.functional.cosine_similarity(
            g, _photo_centroid, dim=0))
        pmaha = float(((g - _photo_mean) / _photo_std).pow(2).sum().sqrt())
        pt = photo["thresholds"]
        score = pcos / pt["cosine"] + pmaha / pt["mahalanobis"]
        cb = photo["confidence_branch"]
        result.update({
            "photo_cosine": round(pcos, 4),
            "photo_mahalanobis": round(pmaha, 4),
            "photo_score": round(score, 4),
            "photo_score_threshold": photo["score_threshold"],
        })
        if score > photo["score_threshold"]:
            signals.append("photo_content")
        if confidence is not None and score > cb["score"] \
                and confidence < cb["max_confidence"]:
            signals.append("low_confidence")

    result["signals"] = signals
    result["is_out_of_domain"] = len(signals) > 0
    return result


@app.on_event("startup")
async def startup():
    _build_ground_truth_lookup()
    _load_model()
    _load_imagenet_detector()
    _load_ood_reference()


def _env_int(name: str, default: int) -> int:
    """Read a positive integer env var, or return default."""
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(str(raw).strip())
    except ValueError:
        return default
    return value if value >= 1 else default


def _env_float(name: str, default: float) -> float:
    """Read a non-negative float env var, or return default.

    Zero is valid: a budget of 0 returns before the first tile.
    """
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = float(str(raw).strip())
    except ValueError:
        return default
    return value if value >= 0 else default


def _scene_clock() -> float:
    """Monotonic clock for the scene time budget. Tests replace this."""
    return time.monotonic()


class _SceneReject(Exception):
    """A scene request that should be rejected before any tile is classified."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _scene_error(exc: _SceneReject) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "code": exc.code},
    )


def _classify_pil(pil_image: Image.Image) -> dict:
    """Run one image through the same model path and OOD check as /classify-damage.

    Tiles must be classified one at a time. The OOD hooks stash the latest
    embedding in module globals, which is the same single-request pattern
    /classify-damage already uses.
    """
    tensor = _preprocess(pil_image).unsqueeze(0).to(DEVICE)  # (1, 3, 224, 224)
    with torch.no_grad():
        features = _model.backbone(tensor)
        logits = _model.head(features)
        probs = torch.softmax(logits, dim=1)
        confidence, pred_idx = probs.max(dim=1)
        if _imagenet_loaded:
            _imagenet_model(tensor)  # avgpool hook captures the embedding

    confidence_val = round(confidence.item(), 4)
    return {
        "damage_level": IDX_TO_LABEL[pred_idx.item()],
        "confidence": confidence_val,
        "ood": _ood_check(_last_layer1, _last_imagenet_feat, confidence_val),
    }


def _decode_scene_image(contents: bytes, max_pixels: int) -> Image.Image:
    """Decode one scene under an explicit pixel cap.

    The caller crops tiles with Pillow one at a time. The full image is
    never converted to a NumPy array. Image.MAX_IMAGE_PIXELS is set to
    max_pixels for this decode only (never to None, which would disable
    Pillow's decompression-bomb guard) and then restored so
    /classify-damage keeps Pillow's default limit.
    """
    previous_cap = Image.MAX_IMAGE_PIXELS
    # Deliberate ceiling. Do not assign None.
    Image.MAX_IMAGE_PIXELS = max_pixels
    opened = None
    try:
        # Between 1x and 2x the cap Pillow only warns; the check below returns
        # 413. At 2x it raises DecompressionBombError, which we also map to 413.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            try:
                opened = Image.open(io.BytesIO(contents))
                width, height = opened.size
            except Image.DecompressionBombError:
                raise _SceneReject(
                    413,
                    "image_too_large",
                    f"Image exceeds the pixel cap of {max_pixels} pixels.",
                )
            pixels = width * height
            if width < 1 or height < 1 or pixels > max_pixels:
                raise _SceneReject(
                    413,
                    "image_too_large",
                    f"Image is {pixels} pixels, which exceeds the cap of {max_pixels} pixels.",
                )
            try:
                rgb = opened.convert("RGB")
            except Image.DecompressionBombError:
                raise _SceneReject(
                    413,
                    "image_too_large",
                    f"Image exceeds the pixel cap of {max_pixels} pixels.",
                )
        if rgb is not opened:
            opened.close()
        opened = None
        return rgb
    finally:
        if opened is not None:
            opened.close()
        Image.MAX_IMAGE_PIXELS = previous_cap


def _plan_tiles(width: int, height: int, tile_size: int) -> dict:
    """Non-overlapping grid. A ragged edge under half the tile size is skipped.

    "Under half" is strict: a remainder of exactly tile_size/2 is kept.
    grid rows/cols include a ragged slot even when that slot is skipped.
    tile_count counts slots that will be run through the model.
    """
    xs = list(range(0, width, tile_size))
    ys = list(range(0, height, tile_size))
    kept = []
    skipped = 0
    for row, y in enumerate(ys):
        for col, x in enumerate(xs):
            tw = min(tile_size, width - x)
            th = min(tile_size, height - y)
            if tw * 2 < tile_size or th * 2 < tile_size:
                skipped += 1
                continue
            kept.append({
                "row": row,
                "col": col,
                "x": x,
                "y": y,
                "width": tw,
                "height": th,
            })
    return {
        "rows": len(ys),
        "cols": len(xs),
        "kept": kept,
        "skipped_count": skipped,
        "tile_count": len(kept),
    }


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model_loaded": _model_loaded,
        "device": str(DEVICE),
        "checkpoint": str(CHECKPOINT_PATH),
        "ood_enabled": _ood_reference is not None,
        "photo_detector_loaded": _imagenet_loaded,
    }


# ---------------------------------------------------------------------------
# POST /classify-damage -- matches API_CONTRACT.md
# ---------------------------------------------------------------------------
@app.post("/classify-damage")
async def classify_damage(
    image: UploadFile = File(..., description="Post-disaster satellite image"),
    area: str = Query(
        default="unknown",
        description=(
            "Geographic area / district name. Passed through to the response. "
            "ASSUMPTION: API_CONTRACT.md's 'area' field is a passthrough label, "
            "not computed by the model. Flagged for review."
        ),
    ),
):
    """Classify damage severity of a post-disaster satellite image.

    Returns damage_level (none|partial|destroyed), confidence score, and area.
    """
    # Read & preprocess the uploaded image
    contents = await image.read()
    try:
        pil_image = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid image file. Expected a valid image format."},
        )

    # Derive image identifier from filename (strip extension)
    image_id = Path(image.filename or "unknown").stem

    # Same model path and OOD check as each tile of POST /classify-scene.
    pred = _classify_pil(pil_image)
    damage_level = pred["damage_level"]
    confidence_val = pred["confidence"]
    ood = pred["ood"]

    response = {
        "damage_level": damage_level,
        "confidence": confidence_val,
        "area": area,
    }
    if ood is not None:
        response["is_out_of_domain"] = ood["is_out_of_domain"]
        ood_fields = {
            "cosine": ood["cosine"],
            "mahalanobis": ood["mahalanobis"],
            "cosine_threshold": ood["cosine_threshold"],
            "mahalanobis_threshold": ood["mahalanobis_threshold"],
            "signals": ood["signals"],
        }
        for key in ("photo_cosine", "photo_mahalanobis", "photo_score",
                    "photo_score_threshold"):
            if key in ood:
                ood_fields[key] = ood[key]
        response["ood"] = ood_fields
        if ood["is_out_of_domain"]:
            # Non-satellite upload: keep the raw prediction for transparency
            # but clearly mark it as unreliable instead of silently returning
            # a confident misclassification.
            response["classification"] = "irrelevant"
            response["message"] = (
                "This image doesn't resemble a satellite disaster-imagery "
                "tile -- the damage result may be unreliable."
            )

    # Log prediction (never raises)
    _log_prediction(image_id, damage_level, confidence_val)

    # Add a header warning if no trained checkpoint was loaded
    headers = {}
    if not _model_loaded:
        headers["X-Model-Warning"] = "untrained-weights"

    return JSONResponse(content=response, headers=headers)


# ---------------------------------------------------------------------------
# POST /classify-scene
# ---------------------------------------------------------------------------
@app.post("/classify-scene")
async def classify_scene(
    image: UploadFile = File(..., description="Large post-disaster satellite image"),
    tile_size: int = Query(
        default=512,
        ge=256,
        le=1024,
        description="Tile edge length in pixels. Tiles do not overlap.",
    ),
    area: str = Query(
        default="unknown",
        description=(
            "Geographic area / district name. Passed through to the response, "
            "same as /classify-damage. Not computed by the model."
        ),
    ),
):
    """Classify a large scene by tiling it with the single-tile model.

    Tile-level labels are a proxy. The checkpoint was trained on
    worst-building-per-tile labels at two scales (1024 px xBD and 512 px
    EBD), so a tile is "destroyed" when its worst building was destroyed
    even if most of the tile is intact. percent_damaged is
    (partial + destroyed) / classified tiles: a tile-level estimate, not a
    building-level damage rate. OOD-flagged tiles are "uncertain" and are
    left out of that fraction. Ragged edge tiles under half the tile size
    in either dimension are skipped.

    damage_breakdown includes "uncertain". /rank-priority's DamageBreakdown
    only declares none, partial, and destroyed — those three counts are the
    scoring input. uncertain is not removed here to fit that schema.

    Classification stops once SCENE_TIME_BUDGET_SECONDS have elapsed.
    The response then has truncated=true, tiles_processed tiles, and
    tiles_total equal to the full kept-tile plan. Counts and
    percent_damaged cover only the tiles that finished.
    """
    contents = await image.read()
    max_pixels = _env_int("SCENE_MAX_PIXELS", DEFAULT_SCENE_MAX_PIXELS)
    max_tiles = _env_int("SCENE_MAX_TILES", DEFAULT_SCENE_MAX_TILES)
    time_budget_s = _env_float(
        "SCENE_TIME_BUDGET_SECONDS", DEFAULT_SCENE_TIME_BUDGET_SECONDS
    )

    try:
        pil_image = _decode_scene_image(contents, max_pixels)
    except _SceneReject as exc:
        return _scene_error(exc)
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid image file. Expected a valid image format."},
        )

    width, height = pil_image.size
    plan = _plan_tiles(width, height, tile_size)
    if plan["tile_count"] > max_tiles:
        pil_image.close()
        return _scene_error(_SceneReject(
            422,
            "too_many_tiles",
            (
                f"Scene produces {plan['tile_count']} tiles at "
                f"tile_size={tile_size}; the cap is {max_tiles}."
            ),
        ))

    counts = {"none": 0, "partial": 0, "destroyed": 0, "uncertain": 0}
    tiles_out = []
    truncated = False
    tiles_total = plan["tile_count"]
    started = _scene_clock()
    try:
        for slot in plan["kept"]:
            # Check before the tile so a slow tile still finishes, and so
            # a budget of 0 returns without running the model.
            if _scene_clock() - started >= time_budget_s:
                truncated = True
                break
            # Crop one tile. Do not materialise the whole scene as an array.
            crop = pil_image.crop((
                slot["x"],
                slot["y"],
                slot["x"] + slot["width"],
                slot["y"] + slot["height"],
            ))
            try:
                pred = _classify_pil(crop)
            finally:
                crop.close()

            ood = pred["ood"]
            uncertain = bool(ood and ood.get("is_out_of_domain"))
            if uncertain:
                counts["uncertain"] += 1
                label = "uncertain"
            else:
                label = pred["damage_level"]
                counts[label] += 1
            tiles_out.append({
                "row": slot["row"],
                "col": slot["col"],
                "x": slot["x"],
                "y": slot["y"],
                "label": label,
                "confidence": pred["confidence"],
                "uncertain": uncertain,
            })
    finally:
        pil_image.close()

    classified = counts["none"] + counts["partial"] + counts["destroyed"]
    if classified == 0:
        # Nothing /rank-priority can score. Do not invent a class.
        percent_damaged = None
        overall_damage_level = None
    else:
        # Same ratio as aid-priority score_breakdown. Rounded to 4 d.p.,
        # which is how /rank-priority reports percent_damaged. That endpoint
        # recomputes the ratio from the three counts; it does not read this
        # field. Null when no tile was classified.
        percent_damaged = round(
            (counts["partial"] + counts["destroyed"]) / classified, 4
        )
        present = [name for name in ("none", "partial", "destroyed") if counts[name]]
        overall_damage_level = max(present, key=_DAMAGE_SEVERITY.get)

    tiles_processed = len(tiles_out)
    response = {
        "tile_size": tile_size,
        "grid": {"rows": plan["rows"], "cols": plan["cols"]},
        "tile_count": tiles_processed,
        "tiles_processed": tiles_processed,
        "tiles_total": tiles_total,
        "truncated": truncated,
        "skipped_count": plan["skipped_count"],
        "damage_breakdown": counts,
        "percent_damaged": percent_damaged,
        "overall_damage_level": overall_damage_level,
        "tiles": tiles_out,
        "area": area,
    }
    headers = {}
    if not _model_loaded:
        headers["X-Model-Warning"] = "untrained-weights"
    return JSONResponse(content=response, headers=headers)
