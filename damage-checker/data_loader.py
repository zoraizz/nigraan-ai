"""
Data loading for damage-checker.

Current mode: single post-disaster image classification.
A bi-temporal (pre+post) dataset stub is included for future upgrade —
see BiTemporalDamageDataset below.
"""

import csv
import os
import random
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset
from torchvision import transforms

# ---------------------------------------------------------------------------
# Label mapping — matches API_CONTRACT.md: none | partial | destroyed
# ---------------------------------------------------------------------------
DAMAGE_LABELS = ["none", "partial", "destroyed"]
LABEL_TO_IDX = {label: idx for idx, label in enumerate(DAMAGE_LABELS)}
IDX_TO_LABEL = {idx: label for label, idx in LABEL_TO_IDX.items()}
NUM_CLASSES = len(DAMAGE_LABELS)

# Inference transforms — no augmentation (used for val/test/serving)
DEFAULT_TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225]),
])

# Training transforms — with augmentation to reduce overfitting on small data
TRAIN_TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.RandomHorizontalFlip(p=0.5),
    transforms.RandomVerticalFlip(p=0.2),
    transforms.RandomRotation(degrees=15),
    transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225]),
])


# ---------------------------------------------------------------------------
# Single-image dataset  (active — used for training / inference)
# ---------------------------------------------------------------------------
class DamageDataset(Dataset):
    """Loads single post-disaster images with labels from a CSV.

    Expected folder layout:
        data_dir/
            images/
                0001.png
                0002.png
                ...
            labels.csv          # columns: id,label

    Args:
        data_dir:   Path to dataset directory.
        transform:  Explicit transform override. If None, uses DEFAULT_TRANSFORM.
        train:      If True and transform is None, uses TRAIN_TRANSFORM instead.
    """

    def __init__(
        self,
        data_dir: str,
        transform: Optional[transforms.Compose] = None,
        train: bool = False,
    ):
        self.data_dir = Path(data_dir)
        self.image_dir = self.data_dir / "images"
        if transform is not None:
            self.transform = transform
        else:
            self.transform = TRAIN_TRANSFORM if train else DEFAULT_TRANSFORM

        # Parse labels.csv
        self.samples: list[Tuple[str, int]] = []
        labels_path = self.data_dir / "labels.csv"
        with open(labels_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                img_id = row["id"]
                label_idx = LABEL_TO_IDX[row["label"]]
                self.samples.append((img_id, label_idx))

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, int]:
        img_id, label = self.samples[idx]
        img_path = self.image_dir / f"{img_id}.png"
        image = Image.open(img_path).convert("RGB")
        if self.transform:
            image = self.transform(image)
        return image, label


# ---------------------------------------------------------------------------
# Bi-temporal dataset  (STUB — not wired up yet)
# ---------------------------------------------------------------------------
class BiTemporalDamageDataset(Dataset):
    """TODO: Stretch-goal upgrade for pre/post satellite pair classification.

    When activated, this dataset would:
    - Load {id}_pre.png and {id}_post.png pairs
    - Stack them into a 6-channel tensor (RGB_pre ++ RGB_post)
    - Require model.build_backbone(in_channels=6) — see model.py

    This class is intentionally minimal right now.  The upgrade path is:
    1. Implement __getitem__ to load & stack both images.
    2. Update train.py to use this dataset class.
    3. Change build_backbone(in_channels=6) in model.py.
    4. Add a second "pre_image" field to the /classify-damage endpoint.
    """

    def __init__(self, data_dir: str, transform=None):
        raise NotImplementedError(
            "BiTemporalDamageDataset is a stub for future pre/post pair "
            "classification. See the docstring for upgrade steps."
        )

    def __len__(self):
        raise NotImplementedError

    def __getitem__(self, idx):
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Synthetic / dummy data generator
# ---------------------------------------------------------------------------
def generate_dummy_data(data_dir: str, n: int = 60) -> str:
    """Create *n* synthetic post-disaster images + labels.csv for testing.

    Images are 256x256 random noise with a colour tint per damage class so
    the model has *something* learnable even on fake data:
        none      -> greenish tint
        partial   -> yellowish tint
        destroyed -> reddish tint

    Returns the path to the generated data directory.
    """
    data_path = Path(data_dir)
    image_dir = data_path / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    labels_path = data_path / "labels.csv"
    samples_per_class = n // NUM_CLASSES

    # Colour tint offsets (added to random noise) per class
    tints = {
        "none": np.array([0, 40, 0], dtype=np.uint8),       # green
        "partial": np.array([40, 40, 0], dtype=np.uint8),    # yellow
        "destroyed": np.array([60, 0, 0], dtype=np.uint8),   # red
    }

    with open(labels_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "label"])

        idx = 0
        for label in DAMAGE_LABELS:
            count = samples_per_class if label != DAMAGE_LABELS[-1] else (n - idx)
            for _ in range(count):
                img_id = f"{idx:04d}"
                # Random base noise + class-specific tint
                noise = np.random.randint(0, 180, (256, 256, 3), dtype=np.uint8)
                tinted = np.clip(noise.astype(np.int16) + tints[label], 0, 255).astype(np.uint8)
                img = Image.fromarray(tinted)
                img.save(image_dir / f"{img_id}.png")
                writer.writerow([img_id, label])
                idx += 1

    print(f"[data_loader] Generated {n} dummy images in {data_path}")
    return str(data_path)


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        generate_dummy_data(tmp, n=12)
        ds = DamageDataset(tmp)
        img, lbl = ds[0]
        print(f"Sample: tensor shape={img.shape}, label={lbl} ({IDX_TO_LABEL[lbl]})")
        print(f"Dataset length: {len(ds)}")
