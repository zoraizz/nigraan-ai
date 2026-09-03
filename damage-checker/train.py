"""
Training script for the damage-checker classifier.

Usage:
    python train.py --data_dir ./data --epochs 10 --batch_size 8 --lr 1e-3

If --data_dir is empty or doesn't exist, synthetic dummy data will be
generated automatically so the pipeline can be verified end-to-end.

Augmentation:
    Training uses RandomHorizontalFlip, RandomVerticalFlip, RandomRotation,
    and ColorJitter to reduce overfitting on small datasets. Validation
    uses the clean DEFAULT_TRANSFORM (no augmentation).
"""

import argparse
import csv
import os
import sys
import time
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, random_split

from data_loader import (
    DamageDataset,
    DEFAULT_TRANSFORM,
    LABEL_TO_IDX,
    TRAIN_TRANSFORM,
    generate_dummy_data,
    NUM_CLASSES,
    IDX_TO_LABEL,
)
from model import DamageClassifier


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train damage classifier")
    parser.add_argument("--data_dir", type=str, default="./data",
                        help="Path to dataset directory")
    parser.add_argument("--epochs", type=int, default=10,
                        help="Number of training epochs")
    parser.add_argument("--batch_size", type=int, default=8,
                        help="Batch size")
    parser.add_argument("--lr", type=float, default=1e-3,
                        help="Learning rate")
    parser.add_argument("--weight_decay", type=float, default=1e-4,
                        help="Weight decay for AdamW optimizer (default: 1e-4)")
    parser.add_argument("--val_split", type=float, default=0.2,
                        help="Fraction of data for validation")
    parser.add_argument("--checkpoint_dir", type=str, default="./checkpoints",
                        help="Directory to save model checkpoints")
    parser.add_argument("--dummy_samples", type=int, default=60,
                        help="Number of dummy samples to generate if no data")
    parser.add_argument("--checkpoint_name", type=str, default="best_model.pth",
                        help="Checkpoint filename (default: best_model.pth)")
    return parser.parse_args()


def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
) -> tuple[float, float]:
    """Run one training epoch. Returns (avg_loss, accuracy)."""
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0

    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad()
        logits = model(images)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()

        total_loss += loss.item() * images.size(0)
        preds = logits.argmax(dim=1)
        correct += (preds == labels).sum().item()
        total += images.size(0)

    return total_loss / total, correct / total


@torch.no_grad()
def evaluate(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> tuple[float, float]:
    """Evaluate on validation set. Returns (avg_loss, accuracy)."""
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0

    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        logits = model(images)
        loss = criterion(logits, labels)

        total_loss += loss.item() * images.size(0)
        preds = logits.argmax(dim=1)
        correct += (preds == labels).sum().item()
        total += images.size(0)

    return total_loss / total, correct / total


def main():
    args = parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[train] Device: {device}")
    if device.type == "cuda":
        print(f"[train] GPU: {torch.cuda.get_device_name(0)}")

    # ------------------------------------------------------------------
    # Data: generate dummy data if needed
    # ------------------------------------------------------------------
    data_dir = Path(args.data_dir)
    labels_csv = data_dir / "labels.csv"
    if not labels_csv.exists():
        print(f"[train] No data found at {data_dir}, generating dummy data...")
        generate_dummy_data(str(data_dir), n=args.dummy_samples)

    # Train/val split with DIFFERENT transforms:
    #   - Train: augmented (RandomHorizontalFlip, ColorJitter, etc.)
    #   - Val:   clean (no augmentation, matches inference)
    # We create two datasets pointing at the same data but with different transforms,
    # then use the same random_split indices for both so they share the split.
    full_aug = DamageDataset(str(data_dir), train=True)
    full_clean = DamageDataset(str(data_dir), train=False)

    val_size = int(len(full_aug) * args.val_split)
    train_size = len(full_aug) - val_size
    gen = torch.Generator().manual_seed(42)

    train_ds, _ = random_split(full_aug, [train_size, val_size], generator=gen)
    _, val_ds = random_split(full_clean, [train_size, val_size], generator=gen)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                              num_workers=0, pin_memory=(device.type == "cuda"))
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False,
                            num_workers=0, pin_memory=(device.type == "cuda"))
    print(f"[train] Dataset size: {len(full_aug)} samples, {NUM_CLASSES} classes")
    print(f"[train] Split: {train_size} train (augmented) / {val_size} val (clean)")

    # ------------------------------------------------------------------
    # Compute class weights from labels.csv for imbalanced datasets
    # ------------------------------------------------------------------
    class_counts = [0] * NUM_CLASSES
    with open(labels_csv, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            idx = LABEL_TO_IDX[row["label"]]  # noqa: need LABEL_TO_IDX
            class_counts[idx] += 1

    total_samples = sum(class_counts)
    # Inverse-frequency weighting: weight_i = total / (num_classes * count_i)
    class_weights = torch.tensor(
        [total_samples / (NUM_CLASSES * max(c, 1)) for c in class_counts],
        dtype=torch.float32,
    ).to(device)
    print(f"[train] Class counts: {dict(zip(IDX_TO_LABEL.values(), class_counts))}")
    print(f"[train] Class weights: {dict(zip(IDX_TO_LABEL.values(), [round(w.item(), 4) for w in class_weights]))}")

    # ------------------------------------------------------------------
    # Model, loss, optimizer
    # ------------------------------------------------------------------
    model = DamageClassifier(in_channels=3).to(device)
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr,
                                  weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    # ------------------------------------------------------------------
    # Training loop
    # ------------------------------------------------------------------
    ckpt_dir = Path(args.checkpoint_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    best_val_acc = 0.0
    total_start = time.time()

    print(f"\n{'Epoch':>5}  {'Train Loss':>10}  {'Train Acc':>9}  "
          f"{'Val Loss':>10}  {'Val Acc':>9}  {'Time':>6}  {'LR':>10}")
    print("-" * 72)

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        train_loss, train_acc = train_one_epoch(
            model, train_loader, criterion, optimizer, device
        )
        val_loss, val_acc = evaluate(model, val_loader, criterion, device)
        elapsed = time.time() - t0
        current_lr = optimizer.param_groups[0]["lr"]
        scheduler.step()

        print(f"{epoch:5d}  {train_loss:10.4f}  {train_acc:9.2%}  "
              f"{val_loss:10.4f}  {val_acc:9.2%}  {elapsed:5.1f}s  {current_lr:10.6f}")

        # Save best checkpoint
        if val_acc >= best_val_acc:
            best_val_acc = val_acc
            ckpt_path = ckpt_dir / args.checkpoint_name
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "val_acc": val_acc,
                "val_loss": val_loss,
                "num_classes": NUM_CLASSES,
                "in_channels": 3,
            }, ckpt_path)
            print(f"       -> Saved best checkpoint (val_acc={val_acc:.2%})")

    total_time = time.time() - total_start
    print(f"\n[train] Done. Best val accuracy: {best_val_acc:.2%}")
    print(f"[train] Total training time: {total_time:.1f}s")
    print(f"[train] Checkpoint: {ckpt_dir / args.checkpoint_name}")


if __name__ == "__main__":
    main()
