"""Offline script: build the out-of-distribution (OOD) reference (v3) for
/classify-damage.

v3 adds a second, independent signal to the v2 layer1 texture guard:

  1. texture signal (v2, unchanged): cosine AND diagonal-Mahalanobis
     distance of the pooled layer1 (64-d) embedding of OUR fine-tuned
     model from the training-tile distribution. Catches synthetic inputs
     (noise, text, gradients, solid colours).

  2. photo signal (new): distance of the image's avgpool embedding in a
     STOCK ImageNet-pretrained ResNet-18 from the satellite-tile centroid.
     WHY: production failure 2026-09-08 -- a photo of a person was
     classified "destroyed" with no flag. Measured distances showed photos
     of people/objects/embed INSIDE the layer1/2/3/4 clouds of the
     fine-tuned model (e.g. person-indoors: layer1 cosine 0.0603 vs
     threshold 0.1557 -- 0.39x, deeper inside than most real tiles), so no
     threshold on our model's spaces can separate them. ImageNet max-
     softmax alone also fails (aerial textures map to ImageNet classes
     with up to 0.99). The stock model's 512-d avgpool space, however,
     separates the domains: an upload is flagged when
        photo_score = photo_cosine/t99 + photo_maha/t99  >  score_threshold
     (t99 = the train-tile p99 of each metric; the sum lets one metric
     compensate for the other), or when the score is moderately elevated
     AND the model's own confidence is low (tie-breaker branch).

Calibration constants (derived on 2026-09-08 from 5,125 train tiles,
1,239 val tiles, 5 sample tiles, 11 realistic irrelevant images and 6
synthetic probes):
    score_threshold 1.9  -- between train score p99 (1.77) and p99.9
                            (1.95); every irrelevant image scores >= 1.91,
                            every sample tile <= 1.56. Train FPR ~1.05%.
    conf branch: score > 1.5 AND confidence < 0.45
                         -- flags borderline images the model is also
                            unsure about; adds ~0.3% train FPR.

Sanity checks (builder aborts on failure): sample tiles must never flag;
all synthetic probes must flag; every image in ood_test/irrelevant (if the
directory exists) must flag.

Run from damage-checker/ with the venv python:
    python build_ood_reference.py

Output: ood_reference.json (~35 KB, committed). Re-run after any future
checkpoint change to refresh the reference.
"""

import json
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from torchvision.models import ResNet18_Weights, resnet18

from data_loader import DamageDataset
from model import DamageClassifier

CHECKPOINT_PATH = Path("checkpoints/xbd_ebd_v3.pth")
IMAGENET_WEIGHTS_PATH = Path("checkpoints/imagenet_resnet18_v1.pth")
OUT_PATH = Path("ood_reference.json")
BATCH_SIZE = 64
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

SCORE_THRESHOLD = 1.9       # photo_score flag level (see module docstring)
CONF_BRANCH_SCORE = 1.5     # confidence tie-breaker: elevated score ...
CONF_BRANCH_MAX_CONF = 0.45  # ... AND low model confidence

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
# Data pipeline (paths or already-loaded PIL images)
# ---------------------------------------------------------------------------
def build_loader(items) -> DataLoader:
    class Unified(Dataset):
        def __init__(self, entries):
            self.entries = entries

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

    if not IMAGENET_WEIGHTS_PATH.exists():
        raise SystemExit(
            f"ABORT: {IMAGENET_WEIGHTS_PATH} not found -- run "
            "download_imagenet_weights.py first (the photo signal needs the "
            "stock ImageNet ResNet-18 weights)")

    model = DamageClassifier(in_channels=3).to(DEVICE)
    ckpt = torch.load(CHECKPOINT_PATH, map_location=DEVICE, weights_only=True)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()
    print(f"Loaded {CHECKPOINT_PATH}")

    imagenet = resnet18(weights=None).to(DEVICE)
    imagenet.load_state_dict(
        torch.load(IMAGENET_WEIGHTS_PATH, map_location=DEVICE, weights_only=True))
    imagenet.eval()
    print(f"Loaded {IMAGENET_WEIGHTS_PATH}")

    # Hooks: pooled layer1 of our model + avgpool of the stock model
    captured_layer1: list[torch.Tensor] = []
    captured_avgpool: list[torch.Tensor] = []

    def hook_layer1(_module, _inputs, output):
        captured_layer1.append(F.adaptive_avg_pool2d(output, 1).flatten(1).cpu())

    def hook_avgpool(_module, _inputs, output):
        captured_avgpool.append(torch.flatten(output, 1).cpu())

    model.backbone.layer1.register_forward_hook(hook_layer1)
    imagenet.avgpool.register_forward_hook(hook_avgpool)

    @torch.no_grad()
    def embed(items):
        """One pass through BOTH models; returns layer1, avgpool, conf."""
        captured_layer1.clear()
        captured_avgpool.clear()
        confs = []
        for batch in build_loader(items):
            x = torch.stack([NORM(RESIZE(im)) for im in batch]).to(DEVICE)
            feats = model.backbone(x)               # fires layer1 hook
            probs = torch.softmax(model.head(feats), dim=1)
            confs.extend(probs.max(dim=1).values.cpu().tolist())
            imagenet(x)                              # fires avgpool hook
        return (torch.cat(captured_layer1), torch.cat(captured_avgpool),
                torch.tensor(confs))

    # Training / validation image paths
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

    tr_l1, tr_avg, tr_conf = embed(train_paths)
    va_l1, va_avg, va_conf = embed(val_paths)

    sample_dir = Path("sample-images")
    sample_paths = sorted(str(p) for p in sample_dir.glob("*.png"))
    sf_l1, sf_avg, sf_conf = embed(sample_paths)

    probes = make_probes()
    pf_l1, pf_avg, pf_conf = embed(list(probes.values()))

    irr_dir = Path("ood_test/irrelevant")
    irr_paths = sorted(str(p) for p in irr_dir.glob("*.png"))
    if irr_paths:
        if_l1, if_avg, if_conf = embed(irr_paths)
        print(f"Realistic irrelevant images: {len(irr_paths)} (calibration set)")
    else:
        if_l1 = if_avg = if_conf = None
        print("NOTE: ood_test/irrelevant/ not found -- skipping that sanity set")

    # --- layer1 (texture) statistics ---
    l1_centroid = tr_l1.mean(dim=0)
    l1_mean = tr_l1.mean(dim=0)
    l1_std = tr_l1.std(dim=0).clamp_min(1e-6)

    def cos_d(x, centroid):
        return (1 - F.normalize(x, dim=1) @ F.normalize(centroid, dim=0)).numpy()

    def maha_d(x, mean, std):
        return (((x - mean) / std) ** 2).sum(dim=1).sqrt().numpy()

    tr_l1_c, tr_l1_m = cos_d(tr_l1, l1_centroid), maha_d(tr_l1, l1_mean, l1_std)
    t_l1_c = float(np.percentile(tr_l1_c, 99))
    t_l1_m = float(np.percentile(tr_l1_m, 99))

    # --- stock-space (photo) statistics ---
    ph_centroid = tr_avg.mean(dim=0)
    ph_mean = tr_avg.mean(dim=0)
    ph_std = tr_avg.std(dim=0).clamp_min(1e-6)
    tr_ph_c = cos_d(tr_avg, ph_centroid)
    tr_ph_m = maha_d(tr_avg, ph_mean, ph_std)
    t_ph_c = float(np.percentile(tr_ph_c, 99))
    t_ph_m = float(np.percentile(tr_ph_m, 99))

    def photo_score(avg_feats):
        c = cos_d(avg_feats, ph_centroid)
        m = maha_d(avg_feats, ph_mean, ph_std)
        return c / t_ph_c + m / t_ph_m

    tr_score = photo_score(tr_avg)
    va_score = photo_score(va_avg)
    sf_score = photo_score(sf_avg)
    pf_score = photo_score(pf_avg)
    if_score = photo_score(if_avg) if if_avg is not None else None

    # --- full rule: texture OR photo OR confidence tie-breaker ---
    def full_rule(l1_feats, avg_feats, conf):
        c = cos_d(l1_feats, l1_centroid)
        m = maha_d(l1_feats, l1_mean, l1_std)
        texture = (c > t_l1_c) & (m > t_l1_m)
        score = photo_score(avg_feats)
        photo = score > SCORE_THRESHOLD
        conf_np = conf.numpy() if isinstance(conf, torch.Tensor) else conf
        branch = (score > CONF_BRANCH_SCORE) & (conf_np < CONF_BRANCH_MAX_CONF)
        return texture | photo | branch, texture, photo, branch, score, c, m

    (tr_flag, tr_tex, tr_ph, tr_br, tr_score, _, _) = full_rule(tr_l1, tr_avg, tr_conf)
    (va_flag, _, _, _, va_score, _, _) = full_rule(va_l1, va_avg, va_conf)
    (sf_flag, _, _, _, sf_score, sf_c, sf_m) = full_rule(sf_l1, sf_avg, sf_conf)
    (pf_flag, _, _, _, pf_score, pf_c, pf_m) = full_rule(pf_l1, pf_avg, pf_conf)
    if if_avg is not None:
        (if_flag, if_tex, if_ph, if_br, if_score, if_c, if_m) = full_rule(
            if_l1, if_avg, if_conf)

    print(f"\nlayer1 (texture): cosine p99={t_l1_c:.4f} max={tr_l1_c.max():.4f} | "
          f"maha p99={t_l1_m:.4f} max={tr_l1_m.max():.4f}")
    print(f"photo space: cosine p99={t_ph_c:.4f} max={tr_ph_c.max():.4f} | "
          f"maha p99={t_ph_m:.4f} max={tr_ph_m.max():.4f}")
    print(f"photo score: train p50={np.percentile(tr_score,50):.2f} "
          f"p99={np.percentile(tr_score,99):.2f} "
          f"p99.9={np.percentile(tr_score,99.9):.2f} max={tr_score.max():.2f}")
    print(f"full-rule false positives: train={int(tr_flag.sum())}/{len(tr_flag)} "
          f"({100 * tr_flag.mean():.2f}%), "
          f"val={int(va_flag.sum())}/{len(va_flag)} "
          f"({100 * va_flag.mean():.2f}%)")
    print(f"sample tiles flagged: {int(sf_flag.sum())}/{len(sf_flag)} (must be 0)")
    print(f"synthetic probes flagged: {int(pf_flag.sum())}/{len(pf_flag)} "
          "(must be all)")
    if if_avg is not None:
        print(f"irrelevant images flagged: {int(if_flag.sum())}/{len(if_flag)} "
              "(must be all)")

    print("\nprobe distances (texture | photo):")
    for i, name in enumerate(probes.keys()):
        print(f"  {name:16s} l1 cos={pf_c[i]:.4f} l1 maha={pf_m[i]:7.3f} | "
              f"score={pf_score[i]:.3f}")
    if if_avg is not None:
        print("irrelevant distances (texture | photo):")
        for i, p in enumerate(irr_paths):
            print(f"  {Path(p).name[:30]:30s} l1 cos={if_c[i]:.4f} "
                  f"l1 maha={if_m[i]:7.3f} | score={if_score[i]:.3f} "
                  f"conf={float(if_conf[i]):.3f} "
                  f"signals={'/'.join(s for s, f in (
                      ('texture', if_tex[i]), ('photo', if_ph[i]),
                      ('low_conf', if_br[i])) if f) or 'NONE'}")
    print("sample tile distances (texture | photo):")
    for i, p in enumerate(sample_paths):
        print(f"  {Path(p).name[:44]:44s} l1 cos={sf_c[i]:.4f} "
              f"l1 maha={sf_m[i]:7.3f} | score={sf_score[i]:.3f}")

    # --- sanity gates ---
    if sf_flag.sum() != 0:
        raise SystemExit("ABORT: sample tiles flagged -- reference invalid")
    if pf_flag.sum() != len(pf_flag):
        raise SystemExit("ABORT: not all probes flagged -- reference invalid")
    if if_avg is not None and if_flag.sum() != len(if_flag):
        raise SystemExit("ABORT: not all irrelevant images flagged -- "
                         "reference invalid")

    reference = {
        "version": 3,
        "checkpoint": str(CHECKPOINT_PATH),
        "n_train_images": len(train_paths),
        "sources": {
            "xbd_train": len(splits["xbd"]["train"]),
            "ebd_train": len(splits["ebd"]["train"]),
        },
        "rule": ("flag when ANY of: (a) layer1 cosine AND mahalanobis above "
                 "their p99 training thresholds [texture signal], (b) photo "
                 "score (stock-space cosine/t99 + maha/t99) above "
                 "score_threshold [photo signal], (c) photo score above "
                 "confidence_branch.score AND model confidence below "
                 "confidence_branch.max_confidence [tie-breaker]"),
        "layer1": {
            "layer": "layer1",
            "feature_dim": int(l1_centroid.shape[0]),
            "thresholds": {
                "cosine": round(t_l1_c, 6),
                "mahalanobis": round(t_l1_m, 6),
                "percentile": 99,
            },
            "train_distance_stats": {
                "cosine": {
                    "mean": round(float(tr_l1_c.mean()), 6),
                    "p99": round(t_l1_c, 6),
                    "max": round(float(tr_l1_c.max()), 6),
                },
                "mahalanobis": {
                    "mean": round(float(tr_l1_m.mean()), 6),
                    "p99": round(t_l1_m, 6),
                    "max": round(float(tr_l1_m.max()), 6),
                },
            },
            "centroid": [round(float(v), 6) for v in l1_centroid.tolist()],
            "mean": [round(float(v), 6) for v in l1_mean.tolist()],
            "std": [round(float(v), 6) for v in l1_std.tolist()],
        },
        "photo": {
            "model": "torchvision resnet18 IMAGENET1K_V1 (stock, not fine-tuned)",
            "feature": "avgpool (512-d)",
            "score_definition": ("photo_cosine / thresholds.cosine + "
                                 "photo_mahalanobis / thresholds.mahalanobis"),
            "thresholds": {
                "cosine": round(t_ph_c, 6),
                "mahalanobis": round(t_ph_m, 6),
                "percentile": 99,
            },
            "score_threshold": SCORE_THRESHOLD,
            "confidence_branch": {
                "score": CONF_BRANCH_SCORE,
                "max_confidence": CONF_BRANCH_MAX_CONF,
            },
            "train_score_stats": {
                "p50": round(float(np.percentile(tr_score, 50)), 4),
                "p99": round(float(np.percentile(tr_score, 99)), 4),
                "p99.9": round(float(np.percentile(tr_score, 99.9)), 4),
                "max": round(float(tr_score.max()), 4),
            },
            "centroid": [round(float(v), 6) for v in ph_centroid.tolist()],
            "mean": [round(float(v), 6) for v in ph_mean.tolist()],
            "std": [round(float(v), 6) for v in ph_std.tolist()],
        },
        "false_positive_rate": {
            "train": round(float(tr_flag.mean()), 6),
            "validation": round(float(va_flag.mean()), 6),
        },
        "sanity": {
            "sample_tiles_flagged": int(sf_flag.sum()),
            "probes_flagged": f"{int(pf_flag.sum())}/{len(pf_flag)}",
            "irrelevant_images_flagged": (f"{int(if_flag.sum())}/{len(if_flag)}"
                                          if if_avg is not None else "skipped"),
            "probe_scores": {
                name: {"photo_score": round(float(s), 4)}
                for name, s in zip(probes.keys(), pf_score)
            },
            **({"irrelevant_scores": {
                    Path(p).name: {
                        "photo_score": round(float(s), 4),
                        "confidence": round(float(c), 4),
                    }
                    for p, s, c in zip(irr_paths, if_score, if_conf)}
                } if if_avg is not None else {}),
        },
    }
    OUT_PATH.write_text(json.dumps(reference, indent=2))
    print(f"\nWrote {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
