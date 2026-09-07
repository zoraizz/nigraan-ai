"""
One-time offline script: build the out-of-distribution (OOD) reference for
/classify-damage.

Runs the v3 model over the TRAINING images (splits_v3.json train splits for
both sources) and extracts the pooled layer1 embedding (64-d, the
texture-level feature map right after the first ResNet block) for each tile.

Why layer1 and not the penultimate (layer4) embedding: the penultimate space
of this model places non-satellite inputs (noise, text screenshots, photos)
*inside* the training cloud — single-centroid, k-means, and diagonal
Mahalanobis distances in layer4 all fail to separate them (verified
empirically; see the scheme-selection notes below). The layer1 texture space
separates them cleanly.

Reference computed here:
  - centroid: mean layer1 embedding of the training set
  - mean / std: per-feature statistics (diagonal Mahalanobis)
  - thresholds: 99th percentile of training distances, cosine AND
    diagonal-Mahalanobis — an upload is flagged only when BOTH distances
    exceed their thresholds (some legitimate tiles sit at one extreme; the
    AND rule keeps the false-positive rate near 0.9%).

Sanity checks printed and recorded: validation + sample-images tiles must
not be flagged; synthetic non-satellite probes (solid colour, noise, text
screenshot, gradient photo, checkerboard, dark night image) must be flagged.

Run from damage-checker/ with the venv python:
    python build_ood_reference.py

Output: ood_reference.json (~10 KB, committed to the repo). Re-run after
any future checkpoint change to refresh the reference.
"""

import json
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms

from data_loader import DamageDataset
from model import DamageClassifier

CHECKPOINT_PATH = Path("checkpoints/xbd_ebd_v3.pth")
OUT_PATH = Path("ood_reference.json")
BATCH_SIZE = 64
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

RESIZE = transforms.Resize((224, 224))
NORM = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225]),
])


# ---------------------------------------------------------------------------
# Synthetic non-satellite probes (the kind of input we want flagged as OOD)
# ---------------------------------------------------------------------------
def make_probes() -> dict[str, Image.Image]:
    probes = {}
    probes["solid_gray"] = Image.new("RGB", (512, 512), (128, 128, 128))

    rng = np.random.default_rng(42)
    probes["random_noise"] = Image.fromarray(
        rng.integers(0, 256, (512, 512, 3), dtype=np.uint8))

    text_img = Image.new("RGB", (512, 512), (255, 255, 255))
    draw = ImageDraw.Draw(text_img)
    lines = [
        "Nigraan Dashboard - System Log", "",
        "ERROR 500: Internal Server Error",
        "Traceback (most recent call last):",
        '  File "main.py", line 202, in classify_damage',
        "    tensor = _preprocess(pil_image)",
        "ConnectionError: service unreachable", "",
        "WARN: retrying in 5s...",
        "INFO: uvicorn running on port 8001",
    ] * 3
    y = 24
    for line in lines:
        draw.text((24, y), line, fill=(0, 0, 0))
        y += 20
    probes["text_screenshot"] = text_img

    photo = Image.new("RGB", (512, 512))
    px = photo.load()
    for yy in range(512):
        if yy < 300:
            t = yy / 300
            r, g, b = int(120 + 100 * t), int(160 + 60 * t), 255
        else:
            r, g, b = 60, 130, 60
        for xx in range(512):
            px[xx, yy] = (r, g, b)
    draw = ImageDraw.Draw(photo)
    draw.ellipse((380, 60, 460, 140), fill=(255, 230, 80))
    probes["gradient_photo"] = photo

    cb = np.zeros((512, 512, 3), dtype=np.uint8)
    cb[:] = (200, 200, 210)
    cb[::64, :] = (30, 30, 40)
    cb[:, ::64] = (30, 30, 40)
    probes["checkerboard"] = Image.fromarray(cb)

    night = np.zeros((512, 512, 3), dtype=np.uint8)
    yy, xx = np.mgrid[0:512, 0:512]
    night[(xx - 380) ** 2 + (yy - 120) ** 2 < 60 ** 2] = (240, 230, 200)
    probes["dark_night"] = Image.fromarray(night)

    return probes


# ---------------------------------------------------------------------------
# Data pipeline: unified access to both sources with row-position indices
# (same convention as train_v3.py's stratified_split)
# ---------------------------------------------------------------------------
def build_loader(items) -> DataLoader:
    class Unified(Dataset):
        def __init__(self, entries):
            self.entries = entries  # file paths or already-loaded PIL images

        def __len__(self):
            return len(self.entries)

        def __getitem__(self, i):
            item = self.entries[i]
            if isinstance(item, Image.Image):
                return item
            return Image.open(item).convert("RGB")

    ds = Unified(items)
    return DataLoader(ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0,
                      collate_fn=lambda b: b)


def main() -> None:
    print(f"Device: {DEVICE}")
    splits = json.loads(Path("data/splits_v3.json").read_text())

    model = DamageClassifier(in_channels=3).to(DEVICE)
    ckpt = torch.load(CHECKPOINT_PATH, map_location=DEVICE, weights_only=True)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()
    print(f"Loaded {CHECKPOINT_PATH}")

    # Capture pooled layer1 output via forward hook
    captured: list[torch.Tensor] = []

    def hook(_module, _inputs, output):
        captured.append(F.adaptive_avg_pool2d(output, 1).flatten(1).cpu())

    model.backbone.layer1.register_forward_hook(hook)

    @torch.no_grad()
    def embed(paths) -> torch.Tensor:
        captured.clear()
        loader = build_loader(paths)
        for batch in loader:
            model.backbone(torch.stack([NORM(RESIZE(im)) for im in batch]).to(DEVICE))
        return torch.cat(captured)

    # Training image paths
    ds_xbd = DamageDataset("data/xbd")
    ds_ebd = DamageDataset("data/ebd")
    xbd_paths = [str(ds_xbd.image_dir / f"{img_id}.png")
                 for img_id, _ in ds_xbd.samples]
    ebd_paths = [str(ds_ebd.image_dir / f"{img_id}.png")
                 for img_id, _ in ds_ebd.samples]
    train_paths = ([xbd_paths[i] for i in splits["xbd"]["train"]]
                   + [ebd_paths[i] for i in splits["ebd"]["train"]])
    val_paths = ([xbd_paths[i] for i in splits["xbd"]["val"]]
                 + [ebd_paths[i] for i in splits["ebd"]["val"]])
    print(f"Training images: {len(train_paths)} "
          f"(xbd {len(splits['xbd']['train'])} + ebd {len(splits['ebd']['train'])})")

    train_feats = embed(train_paths)
    val_feats = embed(val_paths)

    sample_dir = Path("sample-images")
    sample_paths = sorted(str(p) for p in sample_dir.glob("*.png"))
    sample_feats = embed(sample_paths)

    probes = make_probes()
    probe_feats = embed(list(probes.values()))

    # --- distances ---
    centroid = train_feats.mean(dim=0)
    mean = train_feats.mean(dim=0)
    std = train_feats.std(dim=0).clamp_min(1e-6)

    def cos_d(x: torch.Tensor) -> np.ndarray:
        return (1 - F.normalize(x, dim=1) @ F.normalize(
            centroid, dim=0)).numpy()

    def maha_d(x: torch.Tensor) -> np.ndarray:
        return (((x - mean) / std) ** 2).sum(dim=1).sqrt().numpy()

    tr_c, tr_m = cos_d(train_feats), maha_d(train_feats)
    va_c, va_m = cos_d(val_feats), maha_d(val_feats)
    sf_c, sf_m = cos_d(sample_feats), maha_d(sample_feats)
    pf_c, pf_m = cos_d(probe_feats), maha_d(probe_feats)

    t_c = float(np.percentile(tr_c, 99))
    t_m = float(np.percentile(tr_m, 99))

    train_fp = int(((tr_c > t_c) & (tr_m > t_m)).sum())
    val_fp = int(((va_c > t_c) & (va_m > t_m)).sum())
    samples_fp = int(((sf_c > t_c) & (sf_m > t_m)).sum())
    probes_flagged = int(((pf_c > t_c) & (pf_m > t_m)).sum())

    print(f"\ncosine:       p99={t_c:.4f} max={tr_c.max():.4f}")
    print(f"mahalanobis:  p99={t_m:.4f} max={tr_m.max():.4f}")
    print(f"train false positives (AND rule): {train_fp}/{len(tr_c)} "
          f"({100 * train_fp / len(tr_c):.2f}%)")
    print(f"val   false positives (AND rule): {val_fp}/{len(va_c)} "
          f"({100 * val_fp / len(va_c):.2f}%)")
    print(f"sample tiles flagged: {samples_fp}/{len(sf_c)} (must be 0)")
    print(f"probes flagged: {probes_flagged}/{len(pf_c)} (must be all)")
    print("\nprobe distances:")
    for name, c, m in zip(probes.keys(), pf_c, pf_m):
        print(f"  {name:16s} cosine={c:.4f} maha={m:.4f}")
    print("sample tile distances:")
    for p, c, m in zip(sample_paths, sf_c, sf_m):
        print(f"  {Path(p).name[:44]:44s} cosine={c:.4f} maha={m:.4f}")

    if samples_fp != 0:
        raise SystemExit("ABORT: sample tiles flagged — reference invalid")
    if probes_flagged != len(pf_c):
        raise SystemExit("ABORT: not all probes flagged — reference invalid")

    reference = {
        "version": 2,
        "checkpoint": str(CHECKPOINT_PATH),
        "layer": "layer1",
        "feature_dim": int(centroid.shape[0]),
        "rule": ("flag when BOTH cosine distance to the centroid AND "
                 "diagonal-Mahalanobis distance exceed their 99th-percentile "
                 "training thresholds"),
        "thresholds": {
            "cosine": round(t_c, 6),
            "mahalanobis": round(t_m, 6),
            "percentile": 99,
        },
        "n_train_images": len(train_paths),
        "sources": {
            "xbd_train": len(splits["xbd"]["train"]),
            "ebd_train": len(splits["ebd"]["train"]),
        },
        "train_distance_stats": {
            "cosine": {
                "mean": round(float(tr_c.mean()), 6),
                "p99": round(t_c, 6),
                "max": round(float(tr_c.max()), 6),
            },
            "mahalanobis": {
                "mean": round(float(tr_m.mean()), 6),
                "p99": round(t_m, 6),
                "max": round(float(tr_m.max()), 6),
            },
        },
        "false_positive_rate": {
            "train": round(train_fp / len(tr_c), 6),
            "validation": round(val_fp / len(va_c), 6),
        },
        "sanity": {
            "sample_tiles_flagged": samples_fp,
            "probes_flagged": f"{probes_flagged}/{len(pf_c)}",
            "probe_distances": {
                name: {"cosine": round(float(c), 6),
                       "mahalanobis": round(float(m), 6)}
                for name, c, m in zip(probes.keys(), pf_c, pf_m)
            },
        },
        "centroid": [round(float(v), 6) for v in centroid.tolist()],
        "mean": [round(float(v), 6) for v in mean.tolist()],
        "std": [round(float(v), 6) for v in std.tolist()],
    }
    OUT_PATH.write_text(json.dumps(reference, indent=2))
    print(f"\nWrote {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
