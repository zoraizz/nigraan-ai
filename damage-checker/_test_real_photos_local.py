"""
Test real downloaded photos against the LOCALLY updated ood_reference.json.
This verifies the fix catches the real person headshot that originally failed.
"""
import io
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms
import requests as http_requests

from model import DamageClassifier
from data_loader import IDX_TO_LABEL

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
CHECKPOINT = Path("checkpoints/xbd_ebd_v3.pth")
IMAGENET_WEIGHTS = Path("checkpoints/imagenet_resnet18_v1.pth")
OOD_REF = Path("ood_reference.json")

PREPROCESS = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

REAL_PHOTOS = {
    "person_headshot": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=512&h=512&fit=crop",
    "city_street": "https://images.unsplash.com/photo-1449824913935-59a10b8d2000?w=512&h=512&fit=crop",
    "office_desk": "https://images.unsplash.com/photo-1518455027359-f3f8164ba6bd?w=512&h=512&fit=crop",
    "food_plate": "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=512&h=512&fit=crop",
    "landscape": "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=512&h=512&fit=crop",
}

def main():
    print(f"Device: {DEVICE}")
    ref = json.loads(OOD_REF.read_text())
    l1_centroid = torch.tensor(ref["layer1"]["centroid"], dtype=torch.float32)
    l1_mean = torch.tensor(ref["layer1"]["mean"], dtype=torch.float32)
    l1_std = torch.tensor(ref["layer1"]["std"], dtype=torch.float32)
    l1_t = ref["layer1"]["thresholds"]
    photo_ref = ref.get("photo")
    ph_centroid = torch.tensor(photo_ref["centroid"], dtype=torch.float32)
    ph_mean = torch.tensor(photo_ref["mean"], dtype=torch.float32)
    ph_std = torch.tensor(photo_ref["std"], dtype=torch.float32)
    ph_t = photo_ref["thresholds"]

    print(f"score_threshold = {photo_ref['score_threshold']}")
    print(f"conf branch: score>{photo_ref['confidence_branch']['score']} "
          f"AND conf<{photo_ref['confidence_branch']['max_confidence']}")

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

    def check(pil_img, name):
        tensor = PREPROCESS(pil_img).unsqueeze(0).to(DEVICE)
        with torch.no_grad():
            feats = model.backbone(tensor)
            logits = model.head(feats)
            probs = torch.softmax(logits, dim=1)
            conf, pred_idx = probs.max(dim=1)
            imagenet(tensor)
        pred_class = IDX_TO_LABEL[pred_idx.item()]
        conf_val = conf.item()
        f = last_l1["v"].cpu()[0]
        cos = float(1 - F.cosine_similarity(f, l1_centroid, dim=0))
        maha = float(((f - l1_mean) / l1_std).pow(2).sum().sqrt())
        tex = cos > l1_t["cosine"] and maha > l1_t["mahalanobis"]
        g = last_avg["v"].cpu()[0]
        pcos = float(1 - F.cosine_similarity(g, ph_centroid, dim=0))
        pmaha = float(((g - ph_mean) / ph_std).pow(2).sum().sqrt())
        score = pcos / ph_t["cosine"] + pmaha / ph_t["mahalanobis"]
        photo = score > photo_ref["score_threshold"]
        cb = photo_ref["confidence_branch"]
        branch = score > cb["score"] and conf_val < cb["max_confidence"]
        flagged = tex or photo or branch
        signals = []
        if tex: signals.append("TEX")
        if photo: signals.append("PHOTO")
        if branch: signals.append("LOWCONF")
        status = f"FLAGGED[{','.join(signals)}]" if flagged else "** MISSED **"
        print(f"  {name:22s} pred={pred_class:10s} conf={conf_val:.3f} "
              f"| score={score:.3f} (t={photo_ref['score_threshold']}) | {status}")
        return flagged

    print(f"\n{'='*80}")
    print("REAL DOWNLOADED PHOTOS (should ALL be flagged)")
    print(f"{'='*80}")
    missed = 0
    tested = 0
    for name, url in REAL_PHOTOS.items():
        print(f"  Downloading {name}...")
        try:
            resp = http_requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).convert("RGB").resize((512, 512))
        except Exception as e:
            print(f"  [SKIP] {name}: {e}")
            continue
        tested += 1
        if not check(img, name):
            missed += 1

    print(f"\n{'='*80}")
    print("SAMPLE TILES (should NONE be flagged)")
    print(f"{'='*80}")
    false_flags = 0
    for p in sorted(Path("sample-images").glob("*.png")):
        img = Image.open(p).convert("RGB")
        if check(img, p.name[:22]):
            false_flags += 1

    print(f"\n{'='*80}")
    print(f"RESULT: {missed}/{tested} real photos MISSED, "
          f"{false_flags}/5 tiles false-flagged")
    print(f"{'='*80}")
    return 1 if (missed > 0 or false_flags > 0) else 0

if __name__ == "__main__":
    sys.exit(main())
