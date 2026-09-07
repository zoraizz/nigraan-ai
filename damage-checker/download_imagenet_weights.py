"""Fetch the stock ImageNet ResNet-18 weights for the OOD photo signal.

The out-of-distribution guard compares each upload's embedding in a STOCK
ImageNet-pretrained ResNet-18 against the satellite-tile centroid (see
build_ood_reference.py). The weights are NOT committed (45 MB); this script
fetches them once into checkpoints/imagenet_resnet18_v1.pth.

Used by:
  - local setup:  python download_imagenet_weights.py
  - Render build: part of the damage-checker build command

Idempotent: skips the download when the file already exists.
"""
from pathlib import Path

import torch
from torchvision.models import ResNet18_Weights, resnet18

OUT_PATH = Path("checkpoints/imagenet_resnet18_v1.pth")


def main() -> None:
    if OUT_PATH.exists():
        print(f"[imagenet] {OUT_PATH} already exists -- skipping download")
        return
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    model = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
    torch.save(model.state_dict(), OUT_PATH)
    print(f"[imagenet] saved ImageNet ResNet-18 weights to {OUT_PATH} "
          f"({OUT_PATH.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
