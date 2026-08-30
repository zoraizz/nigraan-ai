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

# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------
CHECKPOINT_PATH = Path(os.environ.get("CHECKPOINT_PATH", "checkpoints/best_model.pth"))
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

_model: Optional[DamageClassifier] = None
_model_loaded: bool = False

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


@app.on_event("startup")
async def startup():
    _build_ground_truth_lookup()
    _load_model()


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

    # Inference
    with torch.no_grad():
        logits = _model(tensor)
        probs = torch.softmax(logits, dim=1)
        confidence, pred_idx = probs.max(dim=1)

    damage_level = IDX_TO_LABEL[pred_idx.item()]
    confidence_val = round(confidence.item(), 4)

    response = {
        "damage_level": damage_level,
        "confidence": confidence_val,
        "area": area,
    }

    # Log prediction (never raises)
    _log_prediction(image_id, damage_level, confidence_val)

    # Add a header warning if no trained checkpoint was loaded
    headers = {}
    if not _model_loaded:
        headers["X-Model-Warning"] = "untrained-weights"

    return JSONResponse(content=response, headers=headers)
