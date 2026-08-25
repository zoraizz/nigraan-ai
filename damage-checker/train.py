"""
Training script for the damage-checker classifier.

Usage:
    python train.py --data_dir ./data --epochs 10 --batch_size 8 --lr 1e-3

If --data_dir is empty or doesn't exist, synthetic dummy data will be
generated automatically so the pipeline can be verified end-to-end.
"""

import argparse
import os
import sys
import time
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, random_split

from data_loader import DamageDataset, generate_dummy_data, NUM_CLASSES, IDX_TO_LABEL
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
    parser.add_argument("--val_split", type=float, default=0.2,
                        help="Fraction of data for validation")
    parser.add_argument("--checkpoint_dir", type=str, default="./checkpoints",
                        help="Directory to save model checkpoints")
    parser.add_argument("--dummy_samples", type=int, default=60,
                        help="Number of dummy samples to generate if no data")
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

    # ------------------------------------------------------------------
    # Data: generate dummy data if needed
    # ------------------------------------------------------------------
    data_dir = Path(args.data_dir)
    labels_csv = data_dir / "labels.csv"
    if not labels_csv.exists():
        print(f"[train] No data found at {data_dir}, generating dummy data...")
        generate_dummy_data(str(data_dir), n=args.dummy_samples)

    dataset = DamageDataset(str(data_dir))
    print(f"[train] Dataset size: {len(dataset)} samples, {NUM_CLASSES} classes")

    # Train / val split
    val_size = int(len(dataset) * args.val_split)
    train_size = len(dataset) - val_size
    train_ds, val_ds = random_split(
        dataset, [train_size, val_size],
        generator=torch.Generator().manual_seed(42),
    )
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)
    print(f"[train] Split: {train_size} train / {val_size} val")

    # ------------------------------------------------------------------
    # Model, loss, optimizer
    # ------------------------------------------------------------------
    model = DamageClassifier(in_channels=3).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    # ------------------------------------------------------------------
    # Training loop
    # ------------------------------------------------------------------
    ckpt_dir = Path(args.checkpoint_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    best_val_acc = 0.0

    print(f"\n{'Epoch':>5}  {'Train Loss':>10}  {'Train Acc':>9}  "
          f"{'Val Loss':>10}  {'Val Acc':>9}  {'Time':>6}")
    print("-" * 60)

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        train_loss, train_acc = train_one_epoch(
            model, train_loader, criterion, optimizer, device
        )
        val_loss, val_acc = evaluate(model, val_loader, criterion, device)
        elapsed = time.time() - t0

        print(f"{epoch:5d}  {train_loss:10.4f}  {train_acc:9.2%}  "
              f"{val_loss:10.4f}  {val_acc:9.2%}  {elapsed:5.1f}s")

        # Save best checkpoint
        if val_acc >= best_val_acc:
            best_val_acc = val_acc
            ckpt_path = ckpt_dir / "best_model.pth"
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

    print(f"\n[train] Done. Best val accuracy: {best_val_acc:.2%}")
    print(f"[train] Checkpoint: {ckpt_dir / 'best_model.pth'}")


if __name__ == "__main__":
    main()
