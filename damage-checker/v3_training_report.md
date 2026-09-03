# v3 Training Report: xBD + EBD Pakistan Flooding

**Generated**: 2026-09-03 03:16:43

**Device**: CUDA NVIDIA GeForce RTX 3070 Laptop GPU

**Total training time**: 6142s (102.4 min)

**Best epoch**: 19 (combined val macro F1: 0.5971)


## Configuration

- Seed: 42
- Batch size: 32
- Epochs: 25 (early stopping patience: 7)
- Learning rate: 0.0001 (CosineAnnealingLR)
- Weight decay: 0.005
- Optimizer: AdamW
- Base checkpoint: checkpoints\xbd_real_model_v2.pth
- Output checkpoint: checkpoints\xbd_ebd_v3.pth

## Dataset Splits

| Dataset | Train | Val | Test |
|---------|-------|-----|------|
| xBD | 4001 | 999 | — |
| EBD Pakistan | 1124 | 240 | 240 |
| **Combined train** | **5125** | | |

### Class Distribution (combined training set)

| Class | Count | Weight |
|-------|-------|--------|
| none | 2095 | 0.8154 |
| partial | 447 | 3.8218 |
| destroyed | 2583 | 0.6614 |

## Training History

| Epoch | Train Loss | Train Acc | Val Acc | Val Macro F1 | LR |
|-------|------------|-----------|---------|--------------|-----|
| 1 | 0.926 | 0.5949 | 0.6166 | 0.538 | 9.961e-05 |
| 2 | 0.8941 | 0.591 | 0.6489 | 0.568 | 9.844e-05 |
| 3 | 0.8733 | 0.6045 | 0.636 | 0.5574 | 9.652e-05 |
| 4 | 0.8713 | 0.6043 | 0.6239 | 0.5558 | 9.388e-05 |
| 5 | 0.8633 | 0.6172 | 0.6077 | 0.5448 | 9.055e-05 |
| 6 | 0.8479 | 0.614 | 0.615 | 0.5476 | 8.658e-05 |
| 7 | 0.8515 | 0.617 | 0.5916 | 0.5266 | 8.205e-05 |
| 8 | 0.8298 | 0.6248 | 0.6433 | 0.5682 | 7.702e-05 |
| 9 | 0.8435 | 0.6185 | 0.6642 | 0.5777 | 7.158e-05 |
| 10 | 0.8337 | 0.6367 | 0.6513 | 0.5768 | 6.58e-05 |
| 11 | 0.8255 | 0.6287 | 0.6513 | 0.5832 | 5.978e-05 |
| 12 | 0.8205 | 0.6343 | 0.6618 | 0.5842 | 5.361e-05 |
| 13 | 0.8206 | 0.6355 | 0.6731 | 0.5951 | 4.739e-05 |
| 14 | 0.7919 | 0.6527 | 0.6651 | 0.5872 | 4.122e-05 |
| 15 | 0.7899 | 0.6513 | 0.6425 | 0.5767 | 3.52e-05 |
| 16 | 0.795 | 0.6396 | 0.6521 | 0.5809 | 2.942e-05 |
| 17 | 0.7957 | 0.6511 | 0.6529 | 0.5799 | 2.398e-05 |
| 18 | 0.776 | 0.6529 | 0.6416 | 0.5737 | 1.895e-05 |
| 19 | 0.7779 | 0.6494 | 0.6731 | 0.5971 | 1.442e-05 |
| 20 | 0.7911 | 0.642 | 0.6602 | 0.5907 | 1.045e-05 |
| 21 | 0.7796 | 0.6443 | 0.6529 | 0.5827 | 7.12e-06 |
| 22 | 0.7737 | 0.6517 | 0.661 | 0.5834 | 4.48e-06 |
| 23 | 0.7583 | 0.6648 | 0.6651 | 0.5897 | 2.56e-06 |
| 24 | 0.7639 | 0.6578 | 0.6691 | 0.5939 | 1.39e-06 |
| 25 | 0.7555 | 0.6702 | 0.657 | 0.5887 | 1e-06 |

## v2 vs v3 Comparison

### xBD Validation Set (no regression check)

| Metric | v2 | v3 | Delta |
|--------|-----|-----|-------|
| Accuracy | 0.6847 | 0.6957 | +0.0110 |
| Macro F1 | 0.5965 | 0.6119 | +0.0154 |

### EBD Pakistan Test Set

| Metric | v2 | v3 | Delta |
|--------|-----|-----|-------|
| Accuracy | 0.5708 | 0.5750 | +0.0042 |
| Macro F1 | 0.3911 | 0.5207 | +0.1296 |

### Combined (xBD val + EBD test)

| Metric | v2 | v3 | Delta |
|--------|-----|-----|-------|
| Accuracy | 0.6642 | 0.6731 | +0.0089 |
| Macro F1 | 0.5691 | 0.5971 | +0.0280 |

### Per-Class F1: xBD Validation

| Class | v2 F1 | v3 F1 | Delta | v2 Support | v3 Support |
|-------|-------|-------|-------|------------|------------|
| none | 0.7091 | 0.7364 | +0.0273 | 413 | 413 |
| partial | 0.3431 | 0.3500 | +0.0069 | 82 | 82 |
| destroyed | 0.7374 | 0.7492 | +0.0118 | 504 | 504 |

### Per-Class F1: EBD Pakistan Test

| Class | v2 F1 | v3 F1 | Delta | v2 Support | v3 Support |
|-------|-------|-------|-------|------------|------------|
| none | 0.6619 | 0.7207 | +0.0588 | 94 | 94 |
| partial | 0.0000 | 0.3415 | +0.3415 | 25 | 25 |
| destroyed | 0.5114 | 0.5000 | -0.0114 | 121 | 121 |

## Verdict

**OK**: v3 maintains xBD performance (within 2% macro F1).

**Improvement**: v3 gains +0.1296 macro F1 on Pakistan flooding data.


## Files

- Checkpoint: `checkpoints\xbd_ebd_v3.pth`
- Training splits: `data/splits_v3.json`
- This report: `v3_training_report.md`
- v2 checkpoint (UNTOUCHED): `checkpoints\xbd_real_model_v2.pth`