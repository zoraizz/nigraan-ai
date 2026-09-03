"""
Damage severity classifier for satellite imagery.

Using single-image classification for initial build (per Day-3 fallback plan
in onboarding doc). Bi-temporal pre/post upgrade is a planned stretch goal
if time allows before Sept 3 — see build_backbone(in_channels=N) for the
swap point.

Architecture:
    ResNet-18 backbone (pretrained on ImageNet) → adaptive avg pool → 3-class
    classification head matching API_CONTRACT.md (none | partial | destroyed).
"""

import torch
import torch.nn as nn
from torchvision import models

from data_loader import NUM_CLASSES


# ---------------------------------------------------------------------------
# Backbone builder — THE SWAP POINT for bi-temporal upgrade
# ---------------------------------------------------------------------------
def build_backbone(in_channels: int = 3) -> nn.Module:
    """Return a ResNet-18 backbone, optionally adapted for >3 input channels.

    For bi-temporal upgrade:
        backbone = build_backbone(in_channels=6)
    This duplicates the pretrained conv1 weights across the extra channels so
    transfer learning still benefits from ImageNet features.

    Args:
        in_channels: Number of input channels. 3 for single RGB image,
                     6 for stacked pre+post RGB pair.
    """
    backbone = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)

    if in_channels != 3:
        old_conv = backbone.conv1
        new_conv = nn.Conv2d(
            in_channels,
            old_conv.out_channels,
            kernel_size=old_conv.kernel_size,
            stride=old_conv.stride,
            padding=old_conv.padding,
            bias=False,
        )
        # Initialize by repeating the pretrained 3-channel weights
        with torch.no_grad():
            repeats = in_channels // 3
            remainder = in_channels % 3
            weight_parts = [old_conv.weight] * repeats
            if remainder:
                weight_parts.append(old_conv.weight[:, :remainder])
            new_conv.weight.copy_(torch.cat(weight_parts, dim=1))
        backbone.conv1 = new_conv

    # Remove the original fully-connected layer — we attach our own head
    num_features = backbone.fc.in_features
    backbone.fc = nn.Identity()

    return backbone, num_features


# ---------------------------------------------------------------------------
# Full classifier
# ---------------------------------------------------------------------------
class DamageClassifier(nn.Module):
    """ResNet-18 based damage severity classifier.

    Args:
        in_channels:  Input channels (3 = single image, 6 = pre+post pair).
        num_classes:  Number of output classes (default from data_loader).
        dropout:      Dropout rate before the final linear layer.
    """

    def __init__(
        self,
        in_channels: int = 3,
        num_classes: int = NUM_CLASSES,
        dropout: float = 0.3,
    ):
        super().__init__()
        self.backbone, feat_dim = build_backbone(in_channels)
        self.head = nn.Sequential(
            nn.Dropout(p=dropout),
            nn.Linear(feat_dim, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            x: Tensor of shape (B, C, H, W).
        Returns:
            Logits of shape (B, num_classes).
        """
        features = self.backbone(x)
        return self.head(features)


# ---------------------------------------------------------------------------
# Quick sanity check
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    model = DamageClassifier(in_channels=3)
    dummy = torch.randn(2, 3, 224, 224)
    logits = model(dummy)
    print(f"Input:  {dummy.shape}")
    print(f"Output: {logits.shape}  (expected [2, {NUM_CLASSES}])")
    print(f"Params: {sum(p.numel() for p in model.parameters()):,}")
