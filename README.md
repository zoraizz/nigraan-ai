# Nigraan AI

Disaster damage assessment & aid-priority platform for NDMA/PDMA — Bano Qabil × Alibaba Cloud AI Hackathon.

## Structure
- `risk-flag/` — pre-storm risk scoring (rainfall + LLM)
- `damage-checker/` — post-storm damage classification (xBD + Alibaba PAI)
- `aid-priority/` — urgency ranking (risk + damage scoring)
- `dashboard/` — frontend
- `infra/` — cloud deployment configs

See `API_CONTRACT.md` for interface definitions.

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
