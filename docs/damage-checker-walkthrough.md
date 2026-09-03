# Damage-Checker — Walkthrough

## Summary
Built the complete damage-checker pipeline on `feat/damage-checker`: data loading, model, training, and FastAPI serving endpoint for satellite imagery damage classification.

## Commits (6 total, all pushed)

| # | Commit | Description |
|---|--------|-------------|
| 1 | `8b1cd4c` | `requirements.txt` + local `.gitignore` |
| 2 | `dea4f7a` | `data_loader.py` — single-image dataset + bi-temporal stub |
| 3 | `bf96440` | `model.py` — ResNet-18 with separable `build_backbone(in_channels)` |
| 4 | `e26e36e` | `train.py` — training loop with auto dummy-data generation |
| 5 | `2c6552b` | `main.py` — FastAPI `/classify-damage` endpoint |
| 6 | `45eacc2` | Unicode fix in train.py + plan added to `docs/` |

## Files Created

### [`damage-checker/data_loader.py`](file:///e:/Hackathon/nigraan-ai/damage-checker/data_loader.py)
- `DamageDataset` — loads single post-disaster images + `labels.csv`
- `BiTemporalDamageDataset` — stub (`NotImplementedError`) for future pre/post pair upgrade
- `generate_dummy_data()` — creates colour-tinted synthetic images (green=none, yellow=partial, red=destroyed)
- Label mapping: `none | partial | destroyed` (3 classes, matching API_CONTRACT.md)

### [`damage-checker/model.py`](file:///e:/Hackathon/nigraan-ai/damage-checker/model.py)
- `build_backbone(in_channels=3)` — **the swap point** for bi-temporal upgrade (change to `6`)
- `DamageClassifier` — ResNet-18 backbone + dropout + 3-class linear head
- Pretrained ImageNet weights; first conv layer auto-adapted for non-3-channel input

### [`damage-checker/train.py`](file:///e:/Hackathon/nigraan-ai/damage-checker/train.py)
- CLI-driven with argparse (`--data_dir`, `--epochs`, `--batch_size`, `--lr`)
- Auto-generates dummy data if none found
- Train/val split, per-epoch loss+accuracy logging
- Saves best checkpoint to `checkpoints/best_model.pth`

### [`damage-checker/main.py`](file:///e:/Hackathon/nigraan-ai/damage-checker/main.py)
- `POST /classify-damage` — multipart `image` field, optional `?area=` query param
- Response: `{"damage_level": "none|partial|destroyed", "confidence": float, "area": string}`
- Loads checkpoint on startup; serves with untrained weights + warning header if missing
- `GET /health` — status check

## Verification Results

### Training (end-to-end on dummy data)
```
Epoch  Train Loss  Train Acc    Val Loss    Val Acc    Time
------------------------------------------------------------
    1      0.2512     89.58%      0.7887     75.00%    6.1s
       -> Saved best checkpoint (val_acc=75.00%)
    2      0.0458     97.92%      0.1863    100.00%    5.1s
       -> Saved best checkpoint (val_acc=100.00%)
    3      0.0070    100.00%      0.0000    100.00%    5.0s
       -> Saved best checkpoint (val_acc=100.00%)
```

### Serving (FastAPI endpoint)
```bash
curl -X POST "http://127.0.0.1:8001/classify-damage?area=test-district" -F "image=@data/images/0001.png"
```
```json
{"damage_level":"partial","confidence":0.9999,"area":"test-district"}
```

> [!NOTE]
> **Bi-temporal upgrade path** is documented in code comments and the `BiTemporalDamageDataset` stub. The swap points are:
> 1. `build_backbone(in_channels=6)` in `model.py`
> 2. Implement `BiTemporalDamageDataset.__getitem__` in `data_loader.py`
> 3. Add `pre_image` field to `/classify-damage` endpoint in `main.py`

## Flagged Assumptions

> [!IMPORTANT]
> **`area` field**: Treated as a passthrough string from the caller (query param), not computed by the model. API_CONTRACT.md doesn't specify how it's determined. Flagged in code comments.

## .gitignore
- Local `damage-checker/.gitignore` excludes `data/`, `checkpoints/`, `__pycache__/`, `.venv/`
- Root `.gitignore` (on `dev` branch) already covers `*.pth`, `*.onnx`, `data/raw/`, `data/maxar/`
