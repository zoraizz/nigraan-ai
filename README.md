# Nigraan AI

Disaster damage assessment & aid-priority platform for NDMA/PDMA — Bano Qabil × Alibaba Cloud AI Hackathon.

## Structure
- `risk-flag/` — pre-storm risk scoring (rainfall + LLM)
- `damage-checker/` — post-storm damage classification (xBD + Alibaba PAI)
- `aid-priority/` — urgency ranking
- `dashboard/` — frontend
- `infra/` — cloud deployment configs

See `API_CONTRACT.md` for interface definitions.

## Damage Checker — Current Baseline (v2)

**Model:** ResNet-18 (ImageNet-pretrained), 3-class head (none / partial / destroyed),
single post-disaster image input.

**Training data:** 5,000 xBD tiles spanning 19 disaster types (floods, hurricanes,
tornadoes, wildfires, tsunamis, earthquakes, volcanic eruptions) from both the xBD
tier1 train split (2,799 tiles) and tier3 (6,369 tiles). xBD's 4-class labels are
remapped to our 3-class contract; each tile gets the worst-building label present.
Classes are intentionally unbalanced (none 2,068 / partial 412 / destroyed 2,520) and
handled with inverse-frequency class weighting (partial weight: 4.05×).

**Validation (n=1,000 held-out tiles):**

| Class      | Precision | Recall | F1    |
|------------|-----------|--------|-------|
| none       | 0.667     | 0.763  | 0.712 |
| partial    | 0.291     | 0.430  | 0.347 |
| destroyed  | 0.812     | 0.654  | 0.725 |
| **overall** | —        | —      | **0.690 weighted F1, 68.2% accuracy** |

**Known weak points (future work):**
- *partial* is the bottleneck class (F1 0.347) — rare in the source data and
  inherently ambiguous against both neighbors.
- destroyed→none confusion is the largest single error mass (131/1,000 val tiles) —
  severe damage that reads as intact at 224×224 downsampling.
- Tile-level labels use a worst-building heuristic; a tile with 1 destroyed building
  out of hundreds is labeled "destroyed," which injects label noise.

**Serving:** `CHECKPOINT_PATH=checkpoints/xbd_real_model_v2.pth` (see
`damage-checker/.env.example`).
