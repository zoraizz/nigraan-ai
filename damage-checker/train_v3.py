"""
train_v3.py — Fine-tune damage-checker v2 on combined xBD + EBD Pakistan data.

Loads the existing v2 checkpoint, fine-tunes on combined training data,
evaluates on separate xBD val, EBD Pakistan test, and combined sets.

Output: checkpoints/xbd_ebd_v3.pth + evaluation report.

Does NOT modify:
  - checkpoints/xbd_real_model_v2.pth (live serving checkpoint)
  - .env or CHECKPOINT_PATH
  - data/xbd/ (existing dataset, read-only)
"""

import csv
import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader, ConcatDataset
from torchvision import transforms
from PIL import Image

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SEED = 42
NUM_CLASSES = 3
LABELS = ["none", "partial", "destroyed"]
LABEL_TO_IDX = {l: i for i, l in enumerate(LABELS)}
IDX_TO_LABEL = {i: l for l, i in LABEL_TO_IDX.items()}

XBD_DATA_DIR = Path("data/xbd")
EBD_DATA_DIR = Path("data/ebd")
V2_CHECKPOINT = Path("checkpoints/xbd_real_model_v2.pth")
V3_CHECKPOINT = Path("checkpoints/xbd_ebd_v3.pth")
REPORT_PATH = Path("v3_training_report.md")

# Training hyperparameters
BATCH_SIZE = 32
NUM_EPOCHS = 25
LR = 1e-4
WEIGHT_DECAY = 5e-3
NUM_WORKERS = 0  # Windows compatibility
PATIENCE = 7     # Early stopping patience (epochs without val improvement)

# Split ratios
XBD_VAL_FRAC = 0.20
EBD_VAL_FRAC = 0.15
EBD_TEST_FRAC = 0.15

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
torch.cuda.manual_seed_all(SEED)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False


# ---------------------------------------------------------------------------
# Transforms (same as data_loader.py)
# ---------------------------------------------------------------------------
TRAIN_TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.RandomHorizontalFlip(p=0.5),
    transforms.RandomVerticalFlip(p=0.2),
    transforms.RandomRotation(degrees=15),
    transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

VAL_TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


# ---------------------------------------------------------------------------
# Dataset class (same as data_loader.py DamageDataset, self-contained here)
# ---------------------------------------------------------------------------
class DamageDataset(Dataset):
    def __init__(self, data_dir, indices=None, transform=None):
        self.data_dir = Path(data_dir)
        self.image_dir = self.data_dir / "images"
        self.transform = transform or VAL_TRANSFORM

        all_samples = []
        labels_path = self.data_dir / "labels.csv"
        with open(labels_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                all_samples.append((row["id"], LABEL_TO_IDX[row["label"]]))

        if indices is not None:
            self.samples = [all_samples[i] for i in indices]
        else:
            self.samples = all_samples

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_id, label = self.samples[idx]
        img_path = self.image_dir / f"{img_id}.png"
        image = Image.open(img_path).convert("RGB")
        if self.transform:
            image = self.transform(image)
        return image, label


# ---------------------------------------------------------------------------
# Stratified split (no sklearn dependency)
# ---------------------------------------------------------------------------
def stratified_split(data_dir, val_frac, test_frac=0.0, seed=SEED):
    """Split a dataset into train/val(/test) by stratified sampling.

    Returns dict of index lists: {train: [...], val: [...], test: [...]}
    """
    labels_path = Path(data_dir) / "labels.csv"
    samples = []
    with open(labels_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            samples.append((row["id"], LABEL_TO_IDX[row["label"]]))

    # Group indices by class
    class_indices = {c: [] for c in range(NUM_CLASSES)}
    for i, (_, label) in enumerate(samples):
        class_indices[label].append(i)

    rng = random.Random(seed)
    splits = {"train": [], "val": [], "test": []}

    for cls, indices in class_indices.items():
        rng.shuffle(indices)
        n = len(indices)
        n_val = max(1, int(n * val_frac))
        n_test = max(0, int(n * test_frac)) if test_frac > 0 else 0
        n_train = n - n_val - n_test

        splits["train"].extend(indices[:n_train])
        splits["val"].extend(indices[n_train:n_train + n_val])
        if n_test > 0:
            splits["test"].extend(indices[n_train + n_val:n_train + n_val + n_test])

    # Shuffle within each split
    for key in splits:
        rng.shuffle(splits[key])

    return splits


# ---------------------------------------------------------------------------
# Class weights computation
# ---------------------------------------------------------------------------
def compute_class_weights(datasets_info):
    """Compute inverse-frequency class weights from multiple datasets.

    datasets_info: list of (data_dir, indices) tuples
    """
    counts = np.zeros(NUM_CLASSES)
    for data_dir, indices in datasets_info:
        labels_path = Path(data_dir) / "labels.csv"
        with open(labels_path, newline="") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if indices is None or i in indices:
                    counts[LABEL_TO_IDX[row["label"]]] += 1

    total = counts.sum()
    weights = total / (NUM_CLASSES * counts)
    weights = torch.tensor(weights, dtype=torch.float32)
    return weights, counts


# ---------------------------------------------------------------------------
# Model builder
# ---------------------------------------------------------------------------
def build_model(num_classes=NUM_CLASSES, dropout=0.3):
    from torchvision import models
    backbone = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
    num_features = backbone.fc.in_features
    backbone.fc = nn.Identity()

    head = nn.Sequential(
        nn.Dropout(p=dropout),
        nn.Linear(num_features, num_classes),
    )

    model = nn.Sequential()  # wrapper
    class DamageClassifier(nn.Module):
        def __init__(self):
            super().__init__()
            self.backbone = backbone
            self.head = head
        def forward(self, x):
            features = self.backbone(x)
            return self.head(features)

    return DamageClassifier()


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def evaluate(model, dataloader, device, label=""):
    """Run evaluation and return metrics dict."""
    model.eval()
    all_preds = []
    all_labels = []
    correct = 0
    total = 0

    with torch.no_grad():
        for images, labels in dataloader:
            images = images.to(device)
            labels = labels.to(device)
            outputs = model(images)
            _, preds = torch.max(outputs, 1)
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(labels.cpu().numpy())
            correct += (preds == labels).sum().item()
            total += labels.size(0)

    all_preds = np.array(all_preds)
    all_labels = np.array(all_labels)
    accuracy = correct / max(total, 1)

    # Per-class F1
    per_class = {}
    for cls_idx in range(NUM_CLASSES):
        tp = np.sum((all_preds == cls_idx) & (all_labels == cls_idx))
        fp = np.sum((all_preds == cls_idx) & (all_labels != cls_idx))
        fn = np.sum((all_preds != cls_idx) & (all_labels == cls_idx))

        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-8)

        per_class[IDX_TO_LABEL[cls_idx]] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": int(np.sum(all_labels == cls_idx)),
            "tp": int(tp), "fp": int(fp), "fn": int(fn),
        }

    # Macro F1
    macro_f1 = np.mean([per_class[IDX_TO_LABEL[c]]["f1"] for c in range(NUM_CLASSES)])

    return {
        "label": label,
        "accuracy": round(accuracy, 4),
        "macro_f1": round(float(macro_f1), 4),
        "total_samples": total,
        "per_class": per_class,
    }


# ---------------------------------------------------------------------------
# Main training pipeline
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("  Nigraan AI — v3 Training: xBD + EBD Pakistan Flooding")
    print("=" * 70)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\nDevice: {device}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

    # ------------------------------------------------------------------
    # Step 1: Verify datasets exist
    # ------------------------------------------------------------------
    print("\n[Step 1] Verifying datasets ...")
    for name, path in [("xBD", XBD_DATA_DIR), ("EBD Pakistan", EBD_DATA_DIR)]:
        if not (path / "labels.csv").exists():
            print(f"[FATAL] {name} dataset not found at {path}")
            sys.exit(1)
        n = sum(1 for _ in open(path / "labels.csv")) - 1
        print(f"  {name}: {n} tiles at {path}")

    # ------------------------------------------------------------------
    # Step 2: Create stratified splits
    # ------------------------------------------------------------------
    print("\n[Step 2] Creating stratified splits (seed=42) ...")
    xbd_splits = stratified_split(XBD_DATA_DIR, val_frac=XBD_VAL_FRAC)
    ebd_splits = stratified_split(EBD_DATA_DIR, val_frac=EBD_VAL_FRAC, test_frac=EBD_TEST_FRAC)

    for name, splits in [("xBD", xbd_splits), ("EBD", ebd_splits)]:
        print(f"  {name}: train={len(splits['train'])}, val={len(splits['val'])}", end="")
        if "test" in splits and splits["test"]:
            print(f", test={len(splits['test'])}")
        else:
            print()

    # Save splits for reproducibility
    splits_data = {
        "seed": SEED,
        "xbd": {k: v for k, v in xbd_splits.items()},
        "ebd": {k: v for k, v in ebd_splits.items()},
    }
    splits_path = Path("data/splits_v3.json")
    splits_path.parent.mkdir(parents=True, exist_ok=True)
    with open(splits_path, "w") as f:
        json.dump(splits_data, f)
    print(f"  Splits saved to {splits_path}")

    # ------------------------------------------------------------------
    # Step 3: Build datasets and dataloaders
    # ------------------------------------------------------------------
    print("\n[Step 3] Building combined training dataset ...")
    xbd_train = DamageDataset(XBD_DATA_DIR, indices=xbd_splits["train"], transform=TRAIN_TRANSFORM)
    ebd_train = DamageDataset(EBD_DATA_DIR, indices=ebd_splits["train"], transform=TRAIN_TRANSFORM)
    combined_train = ConcatDataset([xbd_train, ebd_train])
    print(f"  Combined train: {len(combined_train)} samples (xBD:{len(xbd_train)} + EBD:{len(ebd_train)})")

    xbd_val = DamageDataset(XBD_DATA_DIR, indices=xbd_splits["val"], transform=VAL_TRANSFORM)
    ebd_test = DamageDataset(EBD_DATA_DIR, indices=ebd_splits["test"], transform=VAL_TRANSFORM)
    ebd_val = DamageDataset(EBD_DATA_DIR, indices=ebd_splits["val"], transform=VAL_TRANSFORM)

    # Combined val for early stopping monitoring
    combined_val = ConcatDataset([xbd_val, ebd_val])
    print(f"  xBD val: {len(xbd_val)}, EBD val: {len(ebd_val)}, EBD test: {len(ebd_test)}")
    print(f"  Combined val (for early stopping): {len(combined_val)}")

    train_loader = DataLoader(combined_train, batch_size=BATCH_SIZE, shuffle=True,
                              num_workers=NUM_WORKERS, pin_memory=True)
    xbd_val_loader = DataLoader(xbd_val, batch_size=BATCH_SIZE, shuffle=False, num_workers=NUM_WORKERS)
    ebd_test_loader = DataLoader(ebd_test, batch_size=BATCH_SIZE, shuffle=False, num_workers=NUM_WORKERS)
    ebd_val_loader = DataLoader(ebd_val, batch_size=BATCH_SIZE, shuffle=False, num_workers=NUM_WORKERS)
    combined_val_loader = DataLoader(combined_val, batch_size=BATCH_SIZE, shuffle=False, num_workers=NUM_WORKERS)

    # ------------------------------------------------------------------
    # Step 4: Compute class weights for combined training set
    # ------------------------------------------------------------------
    print("\n[Step 4] Computing class weights ...")
    train_indices_set = set(xbd_splits["train"])
    ebd_train_indices_set = set(ebd_splits["train"])

    # Count classes in combined training set
    class_counts = np.zeros(NUM_CLASSES)
    for data_dir, indices in [(XBD_DATA_DIR, train_indices_set), (EBD_DATA_DIR, ebd_train_indices_set)]:
        labels_path = data_dir / "labels.csv"
        with open(labels_path, newline="") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i in indices:
                    class_counts[LABEL_TO_IDX[row["label"]]] += 1

    total_train = class_counts.sum()
    class_weights = total_train / (NUM_CLASSES * class_counts)
    class_weights_tensor = torch.tensor(class_weights, dtype=torch.float32).to(device)

    print(f"  Class counts: {dict(zip(LABELS, [int(c) for c in class_counts]))}")
    print(f"  Class weights: {dict(zip(LABELS, [round(float(w), 4) for w in class_weights]))}")

    # ------------------------------------------------------------------
    # Step 5: Build model and load v2 weights
    # ------------------------------------------------------------------
    print("\n[Step 5] Building model and loading v2 checkpoint ...")
    model = build_model()

    if V2_CHECKPOINT.exists():
        state_dict = torch.load(V2_CHECKPOINT, map_location="cpu", weights_only=True)
        # Handle potential state_dict wrapping
        if "model_state_dict" in state_dict:
            state_dict = state_dict["model_state_dict"]
        elif "state_dict" in state_dict:
            state_dict = state_dict["state_dict"]

        missing, unexpected = model.load_state_dict(state_dict, strict=False)
        if missing:
            print(f"  [WARN] Missing keys: {missing}")
        if unexpected:
            print(f"  [WARN] Unexpected keys: {unexpected}")
        print(f"  Loaded v2 weights from {V2_CHECKPOINT}")
    else:
        print(f"  [WARN] v2 checkpoint not found at {V2_CHECKPOINT} — training from ImageNet weights")

    model = model.to(device)

    # ------------------------------------------------------------------
    # Step 6: Train
    # ------------------------------------------------------------------
    print("\n[Step 6] Training ...")
    criterion = nn.CrossEntropyLoss(weight=class_weights_tensor)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=NUM_EPOCHS, eta_min=1e-6)

    best_val_f1 = 0.0
    best_epoch = 0
    patience_counter = 0
    history = []
    start_time = time.time()

    for epoch in range(NUM_EPOCHS):
        epoch_start = time.time()
        model.train()
        running_loss = 0.0
        correct = 0
        total = 0

        for batch_idx, (images, labels) in enumerate(train_loader):
            images = images.to(device)
            labels = labels.to(device)

            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

            running_loss += loss.item() * images.size(0)
            _, preds = torch.max(outputs, 1)
            correct += (preds == labels).sum().item()
            total += labels.size(0)

        scheduler.step()

        train_loss = running_loss / max(total, 1)
        train_acc = correct / max(total, 1)
        epoch_time = time.time() - epoch_start

        # Evaluate on combined val for early stopping
        val_metrics = evaluate(model, combined_val_loader, device, label="combined_val")

        current_lr = optimizer.param_groups[0]["lr"]
        history.append({
            "epoch": epoch + 1,
            "train_loss": round(train_loss, 4),
            "train_acc": round(train_acc, 4),
            "val_acc": val_metrics["accuracy"],
            "val_macro_f1": val_metrics["macro_f1"],
            "lr": round(current_lr, 8),
            "epoch_time_s": round(epoch_time, 1),
        })

        print(f"  Epoch {epoch + 1:02d}/{NUM_EPOCHS} | "
              f"loss={train_loss:.4f} acc={train_acc:.4f} | "
              f"val_acc={val_metrics['accuracy']:.4f} val_f1={val_metrics['macro_f1']:.4f} | "
              f"lr={current_lr:.6f} | {epoch_time:.1f}s")

        # Early stopping check
        if val_metrics["macro_f1"] > best_val_f1:
            best_val_f1 = val_metrics["macro_f1"]
            best_epoch = epoch + 1
            patience_counter = 0
            # Save in the wrapped format main.py expects (model_state_dict key),
            # matching the v2 checkpoint convention so serving loads it directly.
            torch.save({
                "model_state_dict": model.state_dict(),
                "epoch": epoch + 1,
                "val_acc": val_metrics["accuracy"],
                "val_macro_f1": val_metrics["macro_f1"],
                "num_classes": NUM_CLASSES,
                "in_channels": 3,
                "note": "v3: xBD tier1+tier3 + EBD Pakistan Flooding, fine-tuned from v2",
            }, str(V3_CHECKPOINT))
            print(f"    >> New best val F1: {best_val_f1:.4f} — saved to {V3_CHECKPOINT}")
        else:
            patience_counter += 1
            if patience_counter >= PATIENCE:
                print(f"    >> Early stopping at epoch {epoch + 1} (no improvement for {PATIENCE} epochs)")
                break

    total_time = time.time() - start_time
    print(f"\nTraining complete. Total time: {total_time:.0f}s ({total_time / 60:.1f} min)")
    print(f"Best epoch: {best_epoch} with val F1: {best_val_f1:.4f}")

    # ------------------------------------------------------------------
    # Step 7: Load best model and run final evaluation
    # ------------------------------------------------------------------
    print("\n[Step 7] Loading best model and running final evaluation ...")
    best_state = torch.load(V3_CHECKPOINT, map_location="cpu", weights_only=True)
    # Handle both wrapped dict (v3 convention) and bare state_dict (older runs)
    if isinstance(best_state, dict) and "model_state_dict" in best_state:
        best_state = best_state["model_state_dict"]
    model.load_state_dict(best_state)
    model = model.to(device)

    # Also evaluate v2 for comparison
    v2_model = build_model()
    if V2_CHECKPOINT.exists():
        v2_state = torch.load(V2_CHECKPOINT, map_location="cpu", weights_only=True)
        if "model_state_dict" in v2_state:
            v2_state = v2_state["model_state_dict"]
        elif "state_dict" in v2_state:
            v2_state = v2_state["state_dict"]
        v2_model.load_state_dict(v2_state, strict=False)
    v2_model = v2_model.to(device)

    print("\n--- v3 Evaluation ---")
    v3_xbd = evaluate(model, xbd_val_loader, device, label="v3 xBD val")
    v3_ebd = evaluate(model, ebd_test_loader, device, label="v3 EBD Pakistan test")
    v3_combined = evaluate(model, combined_val_loader, device, label="v3 combined val+test")

    print(f"  xBD val:       acc={v3_xbd['accuracy']:.4f}  macro_f1={v3_xbd['macro_f1']:.4f}")
    print(f"  EBD test:      acc={v3_ebd['accuracy']:.4f}  macro_f1={v3_ebd['macro_f1']:.4f}")
    print(f"  Combined:      acc={v3_combined['accuracy']:.4f}  macro_f1={v3_combined['macro_f1']:.4f}")

    print("\n--- v2 Evaluation (baseline) ---")
    v2_xbd = evaluate(v2_model, xbd_val_loader, device, label="v2 xBD val")
    v2_ebd = evaluate(v2_model, ebd_test_loader, device, label="v2 EBD Pakistan test")
    v2_combined = evaluate(v2_model, combined_val_loader, device, label="v2 combined val+test")

    print(f"  xBD val:       acc={v2_xbd['accuracy']:.4f}  macro_f1={v2_xbd['macro_f1']:.4f}")
    print(f"  EBD test:      acc={v2_ebd['accuracy']:.4f}  macro_f1={v2_ebd['macro_f1']:.4f}")
    print(f"  Combined:      acc={v2_combined['accuracy']:.4f}  macro_f1={v2_combined['macro_f1']:.4f}")

    # ------------------------------------------------------------------
    # Step 8: Write report
    # ------------------------------------------------------------------
    print(f"\n[Step 8] Writing report to {REPORT_PATH} ...")
    write_report(
        history=history,
        v3_metrics={"xbd_val": v3_xbd, "ebd_test": v3_ebd, "combined": v3_combined},
        v2_metrics={"xbd_val": v2_xbd, "ebd_test": v2_ebd, "combined": v2_combined},
        class_counts=class_counts,
        class_weights=class_weights,
        xbd_splits=xbd_splits,
        ebd_splits=ebd_splits,
        total_time=total_time,
        best_epoch=best_epoch,
        best_val_f1=best_val_f1,
    )

    print("\nDone. Report written. Checkpoint saved at:", V3_CHECKPOINT)
    print("v2 checkpoint UNTOUCHED at:", V2_CHECKPOINT)


def write_report(history, v3_metrics, v2_metrics, class_counts, class_weights,
                 xbd_splits, ebd_splits, total_time, best_epoch, best_val_f1):
    lines = []
    lines.append("# v3 Training Report: xBD + EBD Pakistan Flooding\n")
    lines.append(f"**Generated**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"**Device**: {'CUDA ' + torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}\n")
    lines.append(f"**Total training time**: {total_time:.0f}s ({total_time/60:.1f} min)\n")
    lines.append(f"**Best epoch**: {best_epoch} (combined val macro F1: {best_val_f1:.4f})\n")

    lines.append("\n## Configuration\n")
    lines.append(f"- Seed: {SEED}")
    lines.append(f"- Batch size: {BATCH_SIZE}")
    lines.append(f"- Epochs: {NUM_EPOCHS} (early stopping patience: {PATIENCE})")
    lines.append(f"- Learning rate: {LR} (CosineAnnealingLR)")
    lines.append(f"- Weight decay: {WEIGHT_DECAY}")
    lines.append(f"- Optimizer: AdamW")
    lines.append(f"- Base checkpoint: {V2_CHECKPOINT}")
    lines.append(f"- Output checkpoint: {V3_CHECKPOINT}")

    lines.append("\n## Dataset Splits\n")
    lines.append(f"| Dataset | Train | Val | Test |")
    lines.append(f"|---------|-------|-----|------|")
    lines.append(f"| xBD | {len(xbd_splits['train'])} | {len(xbd_splits['val'])} | — |")
    lines.append(f"| EBD Pakistan | {len(ebd_splits['train'])} | {len(ebd_splits['val'])} | {len(ebd_splits['test'])} |")
    lines.append(f"| **Combined train** | **{len(xbd_splits['train']) + len(ebd_splits['train'])}** | | |")

    lines.append("\n### Class Distribution (combined training set)\n")
    lines.append(f"| Class | Count | Weight |")
    lines.append(f"|-------|-------|--------|")
    for i, label in enumerate(LABELS):
        lines.append(f"| {label} | {int(class_counts[i])} | {float(class_weights[i]):.4f} |")

    lines.append("\n## Training History\n")
    lines.append("| Epoch | Train Loss | Train Acc | Val Acc | Val Macro F1 | LR |")
    lines.append("|-------|------------|-----------|---------|--------------|-----|")
    for h in history:
        lines.append(f"| {h['epoch']} | {h['train_loss']} | {h['train_acc']} | {h['val_acc']} | {h['val_macro_f1']} | {h['lr']} |")

    # Side-by-side comparison
    lines.append("\n## v2 vs v3 Comparison\n")
    lines.append("### xBD Validation Set (no regression check)\n")
    lines.append(f"| Metric | v2 | v3 | Delta |")
    lines.append(f"|--------|-----|-----|-------|")
    v2_xbd = v2_metrics["xbd_val"]
    v3_xbd = v3_metrics["xbd_val"]
    acc_delta = v3_xbd["accuracy"] - v2_xbd["accuracy"]
    f1_delta = v3_xbd["macro_f1"] - v2_xbd["macro_f1"]
    lines.append(f"| Accuracy | {v2_xbd['accuracy']:.4f} | {v3_xbd['accuracy']:.4f} | {acc_delta:+.4f} |")
    lines.append(f"| Macro F1 | {v2_xbd['macro_f1']:.4f} | {v3_xbd['macro_f1']:.4f} | {f1_delta:+.4f} |")

    lines.append("\n### EBD Pakistan Test Set\n")
    lines.append(f"| Metric | v2 | v3 | Delta |")
    lines.append(f"|--------|-----|-----|-------|")
    v2_ebd = v2_metrics["ebd_test"]
    v3_ebd = v3_metrics["ebd_test"]
    acc_delta = v3_ebd["accuracy"] - v2_ebd["accuracy"]
    f1_delta = v3_ebd["macro_f1"] - v2_ebd["macro_f1"]
    lines.append(f"| Accuracy | {v2_ebd['accuracy']:.4f} | {v3_ebd['accuracy']:.4f} | {acc_delta:+.4f} |")
    lines.append(f"| Macro F1 | {v2_ebd['macro_f1']:.4f} | {v3_ebd['macro_f1']:.4f} | {f1_delta:+.4f} |")

    lines.append("\n### Combined (xBD val + EBD test)\n")
    lines.append(f"| Metric | v2 | v3 | Delta |")
    lines.append(f"|--------|-----|-----|-------|")
    v2_comb = v2_metrics["combined"]
    v3_comb = v3_metrics["combined"]
    acc_delta = v3_comb["accuracy"] - v2_comb["accuracy"]
    f1_delta = v3_comb["macro_f1"] - v2_comb["macro_f1"]
    lines.append(f"| Accuracy | {v2_comb['accuracy']:.4f} | {v3_comb['accuracy']:.4f} | {acc_delta:+.4f} |")
    lines.append(f"| Macro F1 | {v2_comb['macro_f1']:.4f} | {v3_comb['macro_f1']:.4f} | {f1_delta:+.4f} |")

    # Per-class F1 breakdown
    for eval_name, v3m, v2m in [
        ("xBD Validation", v3_metrics["xbd_val"], v2_metrics["xbd_val"]),
        ("EBD Pakistan Test", v3_metrics["ebd_test"], v2_metrics["ebd_test"]),
    ]:
        lines.append(f"\n### Per-Class F1: {eval_name}\n")
        lines.append(f"| Class | v2 F1 | v3 F1 | Delta | v2 Support | v3 Support |")
        lines.append(f"|-------|-------|-------|-------|------------|------------|")
        for label in LABELS:
            v2_f1 = v2m["per_class"][label]["f1"]
            v3_f1 = v3m["per_class"][label]["f1"]
            delta = v3_f1 - v2_f1
            v2_sup = v2m["per_class"][label]["support"]
            v3_sup = v3m["per_class"][label]["support"]
            lines.append(f"| {label} | {v2_f1:.4f} | {v3_f1:.4f} | {delta:+.4f} | {v2_sup} | {v3_sup} |")

    lines.append("\n## Verdict\n")
    xbd_regression = v3_metrics["xbd_val"]["macro_f1"] - v2_metrics["xbd_val"]["macro_f1"]
    ebd_improvement = v3_metrics["ebd_test"]["macro_f1"] - v2_metrics["ebd_test"]["macro_f1"]

    if xbd_regression < -0.05:
        lines.append("**WARNING**: v3 shows >5% macro F1 regression on xBD validation. "
                      "Catastrophic forgetting may have occurred. Review training carefully.\n")
    elif xbd_regression < -0.02:
        lines.append("**CAUTION**: v3 shows slight regression on xBD (2-5%). "
                      "Consider adjusting training hyperparameters or freezing more layers.\n")
    else:
        lines.append("**OK**: v3 maintains xBD performance (within 2% macro F1).\n")

    if ebd_improvement > 0.02:
        lines.append(f"**Improvement**: v3 gains {ebd_improvement:+.4f} macro F1 on Pakistan flooding data.\n")
    else:
        lines.append(f"**Note**: v3 did not significantly improve on Pakistan data ({ebd_improvement:+.4f}). "
                      "The v2 model may already generalize reasonably.\n")

    lines.append("\n## Files\n")
    lines.append(f"- Checkpoint: `{V3_CHECKPOINT}`")
    lines.append(f"- Training splits: `data/splits_v3.json`")
    lines.append(f"- This report: `{REPORT_PATH}`")
    lines.append(f"- v2 checkpoint (UNTOUCHED): `{V2_CHECKPOINT}`")

    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
