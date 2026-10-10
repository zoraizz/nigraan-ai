"""
Diagnose the OOD guard: test with realistic irrelevant images.
Run from damage-checker/ with: .venv/Scripts/python.exe _diagnose_ood.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw
from torchvision import transforms

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


def make_realistic_probes():
    probes = {}
    rng = np.random.default_rng(123)

    # Person portrait (skin tones, clothing, indoor background)
    arr = np.full((512, 512, 3), [220, 200, 190], dtype=np.uint8)
    img = Image.fromarray(arr)
    draw = ImageDraw.Draw(img)
    draw.rectangle((180, 200, 330, 500), fill=(50, 50, 120))
    draw.ellipse((210, 100, 300, 200), fill=(200, 160, 130))
    draw.ellipse((230, 135, 245, 148), fill=(60, 40, 30))
    draw.ellipse((265, 135, 280, 148), fill=(60, 40, 30))
    draw.ellipse((205, 90, 305, 160), fill=(40, 30, 20))
    draw.rectangle((0, 350, 512, 512), fill=(180, 160, 140))
    a = np.array(img).astype(np.int16) + rng.integers(-15, 15, (512, 512, 3))
    probes["person_portrait"] = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

    # Person outdoors
    outdoor = np.zeros((512, 512, 3), dtype=np.uint8)
    for y in range(256):
        t = y / 256
        outdoor[y, :] = (int(100 + 100*t), int(150 + 70*t), 255)
    outdoor[256:, :] = (60, 120, 50)
    outdoor = np.clip(outdoor.astype(np.int16) + rng.integers(-10, 10, (512, 512, 3)), 0, 255).astype(np.uint8)
    img = Image.fromarray(outdoor)
    draw = ImageDraw.Draw(img)
    draw.rectangle((220, 180, 290, 400), fill=(100, 40, 40))
    draw.ellipse((230, 130, 280, 180), fill=(200, 160, 130))
    probes["person_outdoors"] = img

    # Cat
    cat = Image.new("RGB", (512, 512), (200, 190, 180))
    draw = ImageDraw.Draw(cat)
    draw.ellipse((120, 180, 390, 420), fill=(180, 130, 80))
    draw.ellipse((180, 100, 340, 260), fill=(190, 140, 90))
    draw.polygon([(190, 100), (210, 60), (230, 100)], fill=(190, 140, 90))
    draw.polygon([(280, 100), (300, 60), (320, 100)], fill=(190, 140, 90))
    draw.ellipse((220, 150, 250, 180), fill=(50, 180, 50))
    draw.ellipse((270, 150, 300, 180), fill=(50, 180, 50))
    a = np.array(cat).astype(np.int16) + rng.integers(-10, 10, (512, 512, 3))
    probes["cat"] = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

    # Food plate
    food = Image.new("RGB", (512, 512), (240, 230, 220))
    draw = ImageDraw.Draw(food)
    draw.ellipse((80, 80, 430, 430), fill=(245, 240, 235))
    draw.ellipse((150, 150, 280, 250), fill=(150, 80, 50))
    draw.ellipse((250, 200, 350, 300), fill=(80, 160, 50))
    draw.ellipse((180, 270, 300, 350), fill=(220, 200, 100))
    a = np.array(food).astype(np.int16) + rng.integers(-8, 8, (512, 512, 3))
    probes["food"] = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

    # Car on road
    car = np.zeros((512, 512, 3), dtype=np.uint8)
    for y in range(300):
        t = y / 300
        car[y, :] = (int(130 + 70*t), int(180 + 50*t), 255)
    car[300:, :] = (80, 80, 90)
    img = Image.fromarray(car)
    draw = ImageDraw.Draw(img)
    draw.rectangle((150, 250, 360, 350), fill=(180, 30, 30))
    draw.rectangle((170, 220, 340, 260), fill=(100, 150, 200))
    draw.ellipse((170, 330, 220, 380), fill=(40, 40, 40))
    draw.ellipse((300, 330, 350, 380), fill=(40, 40, 40))
    a = np.array(img).astype(np.int16) + rng.integers(-10, 10, (512, 512, 3))
    probes["car"] = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

    # Text document
    doc = Image.new("RGB", (512, 512), (250, 248, 245))
    draw = ImageDraw.Draw(doc)
    y = 30
    for i in range(25):
        width = int(rng.integers(200, 450))
        draw.rectangle((30, y, 30 + width, y + 8), fill=(30, 30, 30))
        y += 18
    probes["document"] = doc

    # Selfie close-up
    selfie = np.full((512, 512, 3), [200, 165, 135], dtype=np.uint8)
    img = Image.fromarray(selfie)
    draw = ImageDraw.Draw(img)
    draw.ellipse((100, 30, 410, 480), fill=(210, 175, 145))
    draw.ellipse((170, 160, 220, 200), fill=(40, 30, 25))
    draw.ellipse((290, 160, 340, 200), fill=(40, 30, 25))
    draw.arc((200, 250, 310, 320), start=0, end=180, fill=(150, 80, 70), width=3)
    draw.ellipse((80, 10, 430, 200), fill=(30, 25, 20))
    a = np.array(img).astype(np.int16) + rng.integers(-12, 12, (512, 512, 3))
    probes["selfie"] = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

    # Indoor room
    room = np.full((512, 512, 3), [230, 225, 215], dtype=np.uint8)
    room[350:, :] = (160, 140, 120)
    img = Image.fromarray(room)
    draw = ImageDraw.Draw(img)
    draw.rectangle((50, 280, 200, 350), fill=(120, 80, 50))
    draw.rectangle((350, 200, 480, 350), fill=(100, 70, 45))
    draw.rectangle((180, 100, 330, 250), fill=(140, 180, 220))
    a = np.array(img).astype(np.int16) + rng.integers(-12, 12, (512, 512, 3))
    probes["room"] = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

    # Laptop screen
    laptop = Image.new("RGB", (512, 512), (200, 200, 200))
    draw = ImageDraw.Draw(laptop)
    draw.rectangle((60, 40, 450, 320), fill=(30, 30, 40))
    draw.rectangle((80, 60, 430, 300), fill=(40, 45, 55))
    draw.rectangle((80, 60, 430, 80), fill=(60, 60, 80))
    draw.rectangle((100, 100, 300, 120), fill=(70, 120, 180))
    draw.rectangle((60, 330, 450, 350), fill=(180, 180, 180))
    probes["laptop"] = laptop

    # Mug on table
    mug = Image.new("RGB", (512, 512), (200, 180, 160))
    draw = ImageDraw.Draw(mug)
    draw.rectangle((0, 300, 512, 512), fill=(150, 120, 90))
    draw.rectangle((180, 180, 320, 350), fill=(220, 220, 230))
    draw.ellipse((320, 230, 370, 290), outline=(200, 200, 210), width=4)
    draw.ellipse((180, 170, 320, 200), fill=(100, 60, 30))
    probes["mug"] = mug

    return probes


def main():
    print(f"Device: {DEVICE}")

    ref = json.loads(OOD_REF.read_text())
    l1_centroid = torch.tensor(ref["layer1"]["centroid"], dtype=torch.float32)
    l1_mean = torch.tensor(ref["layer1"]["mean"], dtype=torch.float32)
    l1_std = torch.tensor(ref["layer1"]["std"], dtype=torch.float32)
    l1_t = ref["layer1"]["thresholds"]

    photo_ref = ref.get("photo")
    ph_centroid = torch.tensor(photo_ref["centroid"], dtype=torch.float32) if photo_ref else None
    ph_mean = torch.tensor(photo_ref["mean"], dtype=torch.float32) if photo_ref else None
    ph_std = torch.tensor(photo_ref["std"], dtype=torch.float32) if photo_ref else None
    ph_t = photo_ref["thresholds"] if photo_ref else None

    model = DamageClassifier(in_channels=3).to(DEVICE)
    ckpt = torch.load(CHECKPOINT, map_location=DEVICE, weights_only=True)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()
    print(f"Loaded {CHECKPOINT}")

    last_layer1 = {}
    def hook_l1(m, i, o):
        last_layer1["v"] = F.adaptive_avg_pool2d(o, 1).flatten(1)
    model.backbone.layer1.register_forward_hook(hook_l1)

    from torchvision.models import resnet18
    imagenet = resnet18(weights=None).to(DEVICE)
    imagenet.load_state_dict(
        torch.load(IMAGENET_WEIGHTS, map_location=DEVICE, weights_only=True))
    imagenet.eval()
    print(f"Loaded ImageNet {IMAGENET_WEIGHTS}")

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

        f = last_layer1["v"].cpu()[0]
        cos = float(1 - F.cosine_similarity(f, l1_centroid, dim=0))
        maha = float(((f - l1_mean) / l1_std).pow(2).sum().sqrt())
        tex = cos > l1_t["cosine"] and maha > l1_t["mahalanobis"]

        photo = False; score = 0; branch = False
        if ph_centroid is not None:
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
              f"| cos={cos:.4f} maha={maha:.1f} "
              f"| score={score:.3f} "
              f"| {status}")
        return flagged

    probes = make_realistic_probes()
    print(f"\n{'='*80}")
    print("IRRELEVANT IMAGES (should ALL be flagged)")
    print(f"{'='*80}")
    missed = 0
    for name, img in probes.items():
        if not check(img, name):
            missed += 1

    print(f"\n{'='*80}")
    print("SAMPLE TILES (should NONE be flagged)")
    print(f"{'='*80}")
    false_flags = 0
    for p in sorted(Path("sample-images").glob("*.png")):
        if check(Image.open(p).convert("RGB"), p.name[:22]):
            false_flags += 1

    print(f"\n{'='*80}")
    print(f"RESULT: {missed}/{len(probes)} irrelevant MISSED, "
          f"{false_flags}/{len(list(Path('sample-images').glob('*.png')))} tiles false-flagged")
    print(f"{'='*80}")
    return 1 if missed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
