"""
FastAPI serving endpoint for the damage-checker classifier.

Exposes POST /classify-damage matching API_CONTRACT.md:
    Request:  multipart/form-data, field "image"
    Response: { "damage_level": "none|partial|destroyed",
                "confidence": float, "area": "string" }

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

Out-of-distribution guard:
    Uploads that don't resemble satellite disaster imagery are flagged via
    distance of the layer1 (texture) embedding from the training distribution
    (ood_reference.json, built by build_ood_reference.py). A response is
    flagged only when BOTH the cosine and diagonal-Mahalanobis distances
    exceed their 99th-percentile training thresholds. Flagged responses
    carry is_out_of_domain=true, classification="irrelevant", and a warning
    message; the raw model prediction is still returned for transparency.

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

# CORS -- allow the dashboard frontend (Vite dev server,
# http://localhost:5173) to call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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
_ood_reference: Optional[dict] = None
_ood_centroid: Optional[torch.Tensor] = None
_ood_mean: Optional[torch.Tensor] = None
_ood_std: Optional[torch.Tensor] = None
_last_layer1: Optional[torch.Tensor] = None  # set by forward hook per request

# Preprocessing (must match training DEFAULT_TRANSFORM -- no augmentation at inference)
_preprocess = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225]),
])

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


def _load_ood_reference() -> None:
    """Load ood_reference.json (built offline by build_ood_reference.py)."""
    global _ood_reference, _ood_centroid, _ood_mean, _ood_std
    if not OOD_REFERENCE_PATH.exists():
        print(f"[main] OOD reference not found at {OOD_REFERENCE_PATH} -- "
              "out-of-distribution detection disabled")
        return
    _ood_reference = json.loads(OOD_REFERENCE_PATH.read_text())
    _ood_centroid = torch.tensor(
        _ood_reference["centroid"], dtype=torch.float32).to(DEVICE)
    _ood_mean = torch.tensor(
        _ood_reference["mean"], dtype=torch.float32).to(DEVICE)
    _ood_std = torch.tensor(
        _ood_reference["std"], dtype=torch.float32).to(DEVICE)
    t = _ood_reference["thresholds"]
    print(f"[main] OOD reference loaded: layer={_ood_reference['layer']} "
          f"flag when cosine>{t['cosine']:.4f} AND "
          f"mahalanobis>{t['mahalanobis']:.4f} "
          f"(from {_ood_reference['n_train_images']} training images)")


def _ood_check(layer1_feats: Optional[torch.Tensor]) -> Optional[dict]:
    """Distance of the layer1 embedding from the training distribution.

    Returns {cosine, mahalanobis, ...thresholds, is_out_of_domain} when a
    reference is loaded, else None. An image is flagged only when BOTH
    distances exceed their thresholds -- some legitimate tiles sit at one
    extreme, so a single large distance is not enough.
    """
    if _ood_reference is None or layer1_feats is None:
        return None
    f = layer1_feats.to(DEVICE)[0]
    cos = float(1 - torch.nn.functional.cosine_similarity(f, _ood_centroid, dim=0))
    maha = float(((f - _ood_mean) / _ood_std).pow(2).sum().sqrt())
    t = _ood_reference["thresholds"]
    return {
        "cosine": round(cos, 4),
        "mahalanobis": round(maha, 4),
        "cosine_threshold": t["cosine"],
        "mahalanobis_threshold": t["mahalanobis"],
        "is_out_of_domain": (cos > t["cosine"] and maha > t["mahalanobis"]),
    }


@app.on_event("startup")
async def startup():
    _build_ground_truth_lookup()
    _load_model()
    _load_ood_reference()


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

    tensor = _preprocess(pil_image).unsqueeze(0).to(DEVICE)  # (1, 3, 224, 224)

    # Inference (backbone then head, so the layer1 hook captures the
    # embedding used by the out-of-distribution check)
    with torch.no_grad():
        features = _model.backbone(tensor)
        logits = _model.head(features)
        probs = torch.softmax(logits, dim=1)
        confidence, pred_idx = probs.max(dim=1)

    ood = _ood_check(_last_layer1)

    damage_level = IDX_TO_LABEL[pred_idx.item()]
    confidence_val = round(confidence.item(), 4)

    response = {
        "damage_level": damage_level,
        "confidence": confidence_val,
        "area": area,
    }
    if ood is not None:
        response["is_out_of_domain"] = ood["is_out_of_domain"]
        response["ood"] = {
            "cosine": ood["cosine"],
            "mahalanobis": ood["mahalanobis"],
            "cosine_threshold": ood["cosine_threshold"],
            "mahalanobis_threshold": ood["mahalanobis_threshold"],
        }
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
