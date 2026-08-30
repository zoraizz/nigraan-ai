"""
FastAPI serving endpoint for the damage-checker classifier.

Exposes POST /classify-damage matching API_CONTRACT.md:
    Request:  multipart/form-data, field "image"
    Response: { "damage_level": "none|partial|destroyed",
                "confidence": float, "area": "string" }

Run:
    uvicorn main:app --host 0.0.0.0 --port 8001

NOTE — Bi-temporal upgrade path:
    A future version could add a second "pre_image" form field and call
    the model with in_channels=6 (stacked pre+post).  Changes needed:
    1. Add UploadFile parameter `pre_image` to the endpoint.
    2. Stack pre+post into a 6-channel tensor.
    3. Load a checkpoint trained with in_channels=6.
    See model.build_backbone(in_channels=N) for the model-side swap.
"""

import io
import os
from pathlib import Path
from typing import Optional

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
    title="Nigraan AI — Damage Checker",
    description="Post-disaster satellite image damage classification",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------
CHECKPOINT_PATH = Path(os.environ.get("CHECKPOINT_PATH", "checkpoints/best_model.pth"))
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

_model: Optional[DamageClassifier] = None
_model_loaded: bool = False

# Preprocessing (must match training transforms)
_preprocess = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225]),
])


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
    }


# ---------------------------------------------------------------------------
# POST /classify-damage — matches API_CONTRACT.md
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

    tensor = _preprocess(pil_image).unsqueeze(0).to(DEVICE)  # (1, 3, 224, 224)

    # Inference
    with torch.no_grad():
        logits = _model(tensor)
        probs = torch.softmax(logits, dim=1)
        confidence, pred_idx = probs.max(dim=1)

    damage_level = IDX_TO_LABEL[pred_idx.item()]

    response = {
        "damage_level": damage_level,
        "confidence": round(confidence.item(), 4),
        "area": area,
    }

    # Add a header warning if no trained checkpoint was loaded
    headers = {}
    if not _model_loaded:
        headers["X-Model-Warning"] = "untrained-weights"

    return JSONResponse(content=response, headers=headers)
