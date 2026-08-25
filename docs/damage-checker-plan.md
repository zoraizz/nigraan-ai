# Damage-Checker Module — Implementation Plan

Build the satellite-image damage classifier for Nigraan AI: data loading, model, training, and FastAPI serving endpoint, all inside `damage-checker/`.

## User Review Required

> [!IMPORTANT]
> **API_CONTRACT.md specifies 3 damage classes (`none | partial | destroyed`), NOT the xBD 4-class convention (`no-damage | minor-damage | major-damage | destroyed`).** I will match the contract exactly (3 classes). If you intended xBD's 4-class scheme, let me know and I'll adjust.

> [!NOTE]
> The contract's `"area"` field in the response is ambiguous — it could mean geographic region or affected area. I'll default to an optional query-param / placeholder string that callers can set, and document this assumption.

## Proposed Changes

### 1. Environment & Dependencies

#### [NEW] [`requirements.txt`](file:///e:/Hackathon/nigraan-ai/damage-checker/requirements.txt)
- `torch`, `torchvision`, `pillow`, `numpy`, `fastapi`, `uvicorn`, `python-multipart` (needed for FastAPI file uploads)

---

### 2. Data Loading

#### [NEW] [`data_loader.py`](file:///e:/Hackathon/nigraan-ai/damage-checker/data_loader.py)
- `DamageDataset(torch.utils.data.Dataset)` — expects a folder with `{id}_pre.png` / `{id}_post.png` pairs and a simple `labels.csv` (`id,label`).
- Loads pre+post images, stacks them into a 6-channel tensor (RGB×2) so the model sees both temporal states.
- `generate_dummy_data(path, n=50)` — creates synthetic image pairs (random noise + color-coded damage cues) and a matching `labels.csv`, so training can run without real data.

---

### 3. Model

#### [NEW] [`model.py`](file:///e:/Hackathon/nigraan-ai/damage-checker/model.py)
- `DamageClassifier(nn.Module)` — ResNet-18 backbone with the first conv layer replaced to accept 6 input channels (pre+post stacked). Classification head outputs 3 classes matching the contract.
- Pretrained ImageNet weights loaded for layers 2+ of the backbone; the modified first conv is initialized from the pretrained 3-channel weights (duplicated).

---

### 4. Training Script

#### [NEW] [`train.py`](file:///e:/Hackathon/nigraan-ai/damage-checker/train.py)
- CLI-driven: `python train.py --data_dir ./data --epochs 10 --batch_size 8 --lr 1e-3`
- Auto-generates dummy data if `--data_dir` is empty/missing.
- Standard PyTorch training loop with CrossEntropyLoss, Adam optimizer.
- Logs loss + accuracy per epoch to stdout.
- Saves best checkpoint to `checkpoints/best_model.pth`.

---

### 5. Inference / Serving

#### [NEW] [`main.py`](file:///e:/Hackathon/nigraan-ai/damage-checker/main.py)
FastAPI app with `POST /classify-damage` matching API_CONTRACT.md exactly:

```
Request:  multipart/form-data, field "image"
Response: { "damage_level": "none|partial|destroyed", "confidence": float, "area": "string" }
```

- On startup, attempts to load `checkpoints/best_model.pth`. If missing, serves mock predictions with a warning header.
- Accepts a single post-disaster image (the pre-image comparison is a stretch goal — initial serving uses single-image inference).
- Optional `?area=<name>` query param to fill the `area` response field.

---

### 6. Gitignore

#### [MODIFY] [`.gitignore`](file:///e:/Hackathon/nigraan-ai/.gitignore)
Add damage-checker-specific patterns:
```
# damage-checker artifacts
damage-checker/data/
damage-checker/checkpoints/
```

*(The root `.gitignore` already covers `*.pth`, `*.onnx`, `venv/`, `__pycache__/`, etc.)*

---

### 7. Commit Strategy

| Commit | Contents |
|---|---|
| 1 | `requirements.txt` + `.gitignore` update |
| 2 | `data_loader.py` |
| 3 | `model.py` |
| 4 | `train.py` — run it on dummy data to prove it works |
| 5 | `main.py` (FastAPI serving) |

Each commit pushed to `feat/damage-checker`.

## Verification Plan

### Automated Tests
- `python train.py --data_dir ./data --epochs 2` — must complete without errors and produce a checkpoint file.
- `uvicorn main:app` — start server, verify `/classify-damage` endpoint responds to a test POST.

### Manual Verification
- Confirm `.pth` files and `data/` folder are not tracked by git after commits.
