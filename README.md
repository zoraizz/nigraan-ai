# Nigraan AI

Disaster damage assessment & aid-priority platform for NDMA/PDMA — Bano Qabil × Alibaba Cloud AI Hackathon.

## Structure
- `risk-flag/` — pre-storm risk scoring (rainfall + LLM)
- `damage-checker/` — post-storm damage classification (xBD + EBD Pakistan + Alibaba PAI)
- `aid-priority/` — urgency ranking (risk + damage scoring)
- `dashboard/` — frontend
- `infra/` — cloud deployment configs

See `API_CONTRACT.md` for interface definitions.

## Damage Checker — Current Baseline (v3)

**See it run:** `damage-checker/sample-images/` holds five post-disaster tiles
with known ground-truth labels — three from the held-out EBD Pakistan test
split, two from the xBD validation split (tornado, wildfire). Each was run
through a live `POST /classify-damage` with the v3 checkpoint; the folder's
README lists ground truth vs. prediction side by side, so the model's real
input/output behavior can be inspected without any dataset setup.

**Model:** ResNet-18 (ImageNet-pretrained), 3-class head (none / partial / destroyed),
single post-disaster image input. v3 is fine-tuned from the v2 checkpoint on combined
data, so all v2 features are retained.

**Training data (combined, 5,125 tiles):**
- **5,000 xBD tiles** spanning 19 disaster types (floods, hurricanes, tornadoes,
  wildfires, tsunamis, earthquakes, volcanic eruptions) from the xBD tier1 train
  split and tier3. 4-class labels remapped to our 3-class contract; each tile gets
  the worst-building label present.
- **1,124 EBD Pakistan Flooding tiles** from the July 2022 Pakistan floods
  (Wang, Wu, Zhang & Xia 2025, *Journal of Remote Sensing*, DOI 10.34133/remotesensing.0733;
  Figshare 10.6084/m9.figshare.25285009). Real Pakistan satellite imagery (512×512 RGB,
  Maxar Open Data), pixel-level damage masks with the same 4-level scale as xBD,
  converted via the same worst-label heuristic.
- Classes handled with inverse-frequency class weighting recomputed for the
  combined set (none 2,095 / partial 447 / destroyed 2,583; partial weight 3.82×).

**Evaluation — xBD held-out validation (n=999):**

| Class      | v2 F1 | v3 F1 | Δ     |
|------------|-------|-------|-------|
| none       | 0.709 | 0.736 | +0.03 |
| partial    | 0.343 | 0.350 | +0.01 |
| destroyed  | 0.737 | 0.749 | +0.01 |
| **macro**  | 0.597 | **0.612** | **+0.02** |

**Evaluation — EBD Pakistan test split (n=240, held out from training):**

| Class      | v2 F1 | v3 F1 | Δ     |
|------------|-------|-------|-------|
| none       | 0.662 | 0.721 | +0.06 |
| partial    | 0.000 | 0.342 | **+0.34** |
| destroyed  | 0.511 | 0.500 | −0.01 |
| **macro**  | 0.391 | **0.521** | **+0.13** |

**Key improvement — "partial" class recovery on Pakistan data:** v2 scored
F1 = 0.000 on partial damage in Pakistan flood imagery (it never predicted
"partial" correctly — every prediction collapsed to none or destroyed). v3
recovers this class to F1 = 0.342. This matters most for aid-priority triage:
partial damage is the middle severity band that distinguishes "needs assessment
soon" from "needs urgent aid now."

**Known weak points (future work):**
- *partial* remains the bottleneck class on xBD (F1 0.350) — rare in the source
  data and inherently ambiguous against both neighbors.
- destroyed F1 on Pakistan data (0.500) did not improve — flood-submerged
  buildings read as intact at 224×224 downsampling.
- Tile-level labels use a worst-building heuristic; a tile with 1 destroyed
  building out of hundreds is labeled "destroyed," which injects label noise.
- 1,936 of 3,540 EBD Pakistan tiles contain no buildings and were excluded;
  the model has no negative-sample training for that region.

**Serving:** `CHECKPOINT_PATH=checkpoints/xbd_ebd_v3.pth` (see
`damage-checker/.env`). The v2 checkpoint remains on disk
(`checkpoints/xbd_real_model_v2.pth`) as a rollback option.

**Reproduction:** `prepare_ebd_data.py` converts the raw EBD ZIP to our
labels.csv format; `train_v3.py` runs the combined fine-tune (seed=42,
splits in `data/splits_v3.json`, full metrics in `v3_training_report.md`).

## Aid Priority -- Scoring & Ranking

Ranks affected districts by aid urgency, combining Risk Flag's forecast risk
with Damage Checker's observed severity. Exposed as `POST /rank-priority`
(see `API_CONTRACT.md`); stateless -- the caller submits each district's
risk level and damage assessment, and the response echoes every input plus
the computed scores so the ranking is fully auditable.

### Scoring formula

```
priority = (risk_weight * risk_score + damage_weight * damage_score)
           / (risk_weight + damage_weight)
```

- `risk_score` (from `/predict-risk`): low = 0.0, medium = 0.5, high = 1.0,
  unknown = 0.0 (out-of-coverage districts still rank on damage alone)
- `damage_score` (from aggregated `/classify-damage` calls):
  `(0.5 * partial + 1.0 * destroyed) / classified_tiles`
  (single-tile mode: none = 0.0, partial = 0.5, destroyed = 1.0)
- Default weights 0.4 risk / 0.6 damage (env-configurable via
  `PRIORITY_RISK_WEIGHT` / `PRIORITY_DAMAGE_WEIGHT`): observed damage is
  ground truth and should dominate post-event triage, while forecast risk
  still surfaces districts that are intact *so far*. The formula normalizes
  by the weight sum, so scores always stay in [0, 1].

### Design decision: "more photos != more damage"

`damage_score` is a per-tile **average**, never a sum. A district assessed
with 10 tiles at 40% damaged scores identically to one assessed with 100
tiles at 40% damaged. Tile counts are echoed in the response for coverage
awareness but never enter the score, so better-photographed districts are
not systematically over-prioritized. This is covered by an explicit test
(`test_photo_count_does_not_skew_priority`).

Ties are broken alphabetically by district name (deterministic across runs).

### Low-coverage caveat (transparency only)

`low_coverage_warning` flags any district whose damage assessment rests on
fewer tiles than `LOW_COVERAGE_TILE_THRESHOLD` (default 5), e.g.
`"low coverage — based on 1 tile"`. It is a transparency signal for
response teams — a rank-1 district assessed from a single photo deserves
more skepticism than one assessed from 100 tiles — and never affects the
priority score, rank order, or any other computed value.

### Run & test

```
cd aid-priority
python -m uvicorn main:app --port 8002
python tests/test_rank_priority.py          # full suite (server-dependent tests included)
python tests/test_rank_priority.py unit     # scoring unit tests only
```
