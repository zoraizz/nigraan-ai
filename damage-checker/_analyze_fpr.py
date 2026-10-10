"""
Analyze which training tiles trigger the OOD guard at threshold 1.65.
Uses the same data-loading approach as build_ood_reference.py.
"""
import json
import sys
from pathlib import Path
from collections import Counter

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms

from model import DamageClassifier
from data_loader import DamageDataset, IDX_TO_LABEL

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
CHECKPOINT = Path("checkpoints/xbd_ebd_v3.pth")
IMAGENET_WEIGHTS = Path("checkpoints/imagenet_resnet18_v1.pth")
OOD_REF = Path("ood_reference.json")

PREPROCESS = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

LABEL_MAP = {0: "none", 1: "partial", 2: "destroyed"}


def main():
    print(f"Device: {DEVICE}")

    ref = json.loads(OOD_REF.read_text())
    l1_centroid = torch.tensor(ref["layer1"]["centroid"], dtype=torch.float32)
    l1_mean = torch.tensor(ref["layer1"]["mean"], dtype=torch.float32)
    l1_std = torch.tensor(ref["layer1"]["std"], dtype=torch.float32)
    l1_t = ref["layer1"]["thresholds"]

    photo_ref = ref["photo"]
    ph_centroid = torch.tensor(photo_ref["centroid"], dtype=torch.float32)
    ph_mean = torch.tensor(photo_ref["mean"], dtype=torch.float32)
    ph_std = torch.tensor(photo_ref["std"], dtype=torch.float32)
    ph_t = photo_ref["thresholds"]
    score_threshold = photo_ref["score_threshold"]
    cb = photo_ref["confidence_branch"]

    print(f"score_threshold = {score_threshold}")

    # Load model
    model = DamageClassifier(in_channels=3).to(DEVICE)
    ckpt = torch.load(CHECKPOINT, map_location=DEVICE, weights_only=True)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    last_l1 = {}
    def hook_l1(m, i, o):
        last_l1["v"] = F.adaptive_avg_pool2d(o, 1).flatten(1)
    model.backbone.layer1.register_forward_hook(hook_l1)

    from torchvision.models import resnet18
    imagenet = resnet18(weights=None).to(DEVICE)
    imagenet.load_state_dict(torch.load(IMAGENET_WEIGHTS, map_location=DEVICE, weights_only=True))
    imagenet.eval()

    last_avg = {}
    def hook_avg(m, i, o):
        last_avg["v"] = torch.flatten(o, 1)
    imagenet.avgpool.register_forward_hook(hook_avg)

    # Load data using the same approach as build_ood_reference.py
    splits = json.loads(Path("data/splits_v3.json").read_text())
    ds_xbd = DamageDataset("data/xbd")
    ds_ebd = DamageDataset("data/ebd")

    # Build train entries: (path, label_idx, source)
    train_entries = []
    for idx in splits["xbd"]["train"]:
        img_id, label_idx = ds_xbd.samples[idx]
        path = ds_xbd.image_dir / f"{img_id}.png"
        train_entries.append((path, label_idx, "xbd"))
    for idx in splits["ebd"]["train"]:
        img_id, label_idx = ds_ebd.samples[idx]
        path = ds_ebd.image_dir / f"{img_id}.png"
        train_entries.append((path, label_idx, "ebd"))

    print(f"Train images: {len(train_entries)} "
          f"(xbd {len(splits['xbd']['train'])} + ebd {len(splits['ebd']['train'])})")

    false_positives = []
    scores_all = []

    for idx, (path, label_idx, source) in enumerate(train_entries):
        img = Image.open(path).convert("RGB")
        tensor = PREPROCESS(img).unsqueeze(0).to(DEVICE)

        with torch.no_grad():
            feats = model.backbone(tensor)
            logits = model.head(feats)
            probs = torch.softmax(logits, dim=1)
            conf, pred_idx = probs.max(dim=1)
            imagenet(tensor)

        conf_val = conf.item()
        pred_class = IDX_TO_LABEL[pred_idx.item()]
        gt_label = LABEL_MAP.get(label_idx, f"?{label_idx}")

        f = last_l1["v"].cpu()[0]
        cos = float(1 - F.cosine_similarity(f, l1_centroid, dim=0))
        maha = float(((f - l1_mean) / l1_std).pow(2).sum().sqrt())
        tex = cos > l1_t["cosine"] and maha > l1_t["mahalanobis"]

        g = last_avg["v"].cpu()[0]
        pcos = float(1 - F.cosine_similarity(g, ph_centroid, dim=0))
        pmaha = float(((g - ph_mean) / ph_std).pow(2).sum().sqrt())
        score = pcos / ph_t["cosine"] + pmaha / ph_t["mahalanobis"]
        photo = score > score_threshold
        branch = score > cb["score"] and conf_val < cb["max_confidence"]

        flagged = tex or photo or branch
        scores_all.append(score)

        if flagged:
            signals = []
            if tex: signals.append("TEX")
            if photo: signals.append("PHOTO")
            if branch: signals.append("LOWCONF")
            false_positives.append({
                "path": str(path),
                "filename": path.name,
                "label": gt_label,
                "source": source,
                "score": score,
                "cos": cos,
                "maha": maha,
                "conf": conf_val,
                "pred": pred_class,
                "signals": signals,
            })

        if (idx + 1) % 500 == 0:
            print(f"  Processed {idx+1}/{len(train_entries)}... "
                  f"({len(false_positives)} FP so far)")

    n = len(train_entries)
    nfp = len(false_positives)
    print(f"\n{'='*90}")
    print(f"FALSE POSITIVES: {nfp}/{n} ({100*nfp/n:.2f}%)")
    print(f"{'='*90}")

    by_source = Counter(fp["source"] for fp in false_positives)
    print(f"\nBy source: {dict(by_source)}")

    by_label = Counter(fp["label"] for fp in false_positives)
    print(f"By label: {dict(by_label)}")

    by_signal = Counter(tuple(fp["signals"]) for fp in false_positives)
    print(f"By signal combination: {dict(by_signal)}")

    fp_scores = [fp["score"] for fp in false_positives]
    if fp_scores:
        print(f"\nFP score distribution:")
        print(f"  min={min(fp_scores):.3f} "
              f"median={sorted(fp_scores)[len(fp_scores)//2]:.3f} "
              f"max={max(fp_scores):.3f}")
        marginal = [s for s in fp_scores if 1.65 < s <= 1.77]
        print(f"  In marginal range (1.65-1.77): {len(marginal)} tiles "
              f"(would be saved by raising threshold to ~1.77)")
        high = [s for s in fp_scores if s > 1.77]
        print(f"  Above old p99 (>1.77): {len(high)} tiles "
              f"(would still be FP even at old 1.9 threshold)")

    print(f"\nTop 30 false positives (highest score):")
    hdr = (f"  {'Score':>7} {'Cos':>7} {'Maha':>7} {'Conf':>5} {'Pred':>10} "
           f"{'Label':>10} {'Src':>4} {'Signals':>15} Filename")
    sep = (f"  {'-'*7} {'-'*7} {'-'*7} {'-'*5} {'-'*10} {'-'*10} "
           f"{'-'*4} {'-'*15} {'-'*45}")
    print(hdr); print(sep)
    for fp in sorted(false_positives, key=lambda x: -x["score"])[:30]:
        print(f"  {fp['score']:7.3f} {fp['cos']:7.4f} {fp['maha']:7.1f} "
              f"{fp['conf']:5.3f} {fp['pred']:>10} {fp['label']:>10} "
              f"{fp['source']:>4} {','.join(fp['signals']):>15} {fp['filename']}")

    print(f"\nBottom 20 false positives (most marginal):")
    print(hdr); print(sep)
    for fp in sorted(false_positives, key=lambda x: x["score"])[:20]:
        print(f"  {fp['score']:7.3f} {fp['cos']:7.4f} {fp['maha']:7.1f} "
              f"{fp['conf']:5.3f} {fp['pred']:>10} {fp['label']:>10} "
              f"{fp['source']:>4} {','.join(fp['signals']):>15} {fp['filename']}")

    scores_arr = np.array(scores_all)
    print(f"\nAll train scores: "
          f"p50={np.percentile(scores_arr, 50):.3f} "
          f"p90={np.percentile(scores_arr, 90):.3f} "
          f"p95={np.percentile(scores_arr, 95):.3f} "
          f"p99={np.percentile(scores_arr, 99):.3f} "
          f"max={scores_arr.max():.3f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
