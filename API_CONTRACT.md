# API Contract -- Nigraan AI

## POST /predict-risk
Request:
{ "district": "string" }

Rainfall is fetched server-side from Open-Meteo (forecast, 30-day, and 90-day
totals); the caller only identifies the district.

Response:
{ "district": "string", "hazard_types": ["string"], "rainfall_forecast_mm": number | null,
  "rainfall_30d_mm": number | null, "rainfall_90d_mm": number | null,
  "risk_level": "low|medium|high|unknown", "reason": "string", "cached": boolean,
  "reasoning_source": "gemini|grok|fallback|cache" | null,
  "reasoning_error": "api_error|bad_json" | null }

reasoning_source is null for an unknown district. reasoning_error is a short
code only (never a stack trace or secret) and is null when scoring succeeded.

## POST /classify-damage
Request: multipart/form-data, field "image"

Response:
{ "damage_level": "none|partial|destroyed", "confidence": number, "area": "string" }

Out-of-distribution guard: if the upload doesn't resemble satellite disaster
imagery (two distance checks against the training distribution — a texture
check on our model's early-layer embedding and a photo check against a
stock ImageNet ResNet-18's embedding of the training tiles; see
damage-checker/ood_reference.json), the response additionally carries
"is_out_of_domain": true, "classification": "irrelevant", a human-readable
"message", and an "ood" object:

{ "cosine": number, "mahalanobis": number,               // texture signal (our model, layer1)
  "cosine_threshold": number, "mahalanobis_threshold": number,
  "photo_cosine": number, "photo_mahalanobis": number,  // photo signal (stock ImageNet model)
  "photo_score": number, "photo_score_threshold": number,
  "signals": ["texture"|"photo_content"|"low_confidence", ...] }  // which checks fired

"damage_level"/"confidence" still hold the raw model prediction for
transparency — treat it as unreliable when flagged.

## POST /classify-scene
Request: multipart/form-data, field "image"

Query: `tile_size` (default 512, allowed 256–1024), `area` (optional
passthrough label, default "unknown")

Response:
{ "tile_size": 512, "grid": { "rows": 0, "cols": 0 }, "tile_count": 0,
  "tiles_processed": 0, "tiles_total": 0, "truncated": false,
  "skipped_count": 0,
  "damage_breakdown": { "none": 0, "partial": 0, "destroyed": 0, "uncertain": 0 },
  "percent_damaged": number | null, "overall_damage_level": "none|partial|destroyed" | null,
  "tiles": [ { "row": 0, "col": 0, "x": 0, "y": 0,
               "label": "none|partial|destroyed|uncertain",
               "confidence": number, "uncertain": boolean } ],
  "area": "string" }

No image bytes are returned. Tiles do not overlap. A ragged edge tile under
half of `tile_size` in either dimension is skipped (`skipped_count`) and
omitted from `tiles`. `tile_count` and `tiles_processed` are the number of
tiles run through the model. `tiles_total` is the number of kept tiles in
the full grid. When the request hits `SCENE_TIME_BUDGET_SECONDS` (default
40) it returns HTTP 200 with `truncated: true` and only the tiles finished
so far (`tiles_processed` < `tiles_total`). OOD-flagged tiles have `label`
"uncertain" and `uncertain` true, and are excluded from `percent_damaged`
and `overall_damage_level`. Those fields, and `damage_breakdown`, count
only tiles that finished.

`percent_damaged` = (partial + destroyed) / (none + partial + destroyed),
rounded to 4 decimal places, or null when that denominator is 0.
`overall_damage_level` is the worst class among classified tiles
(none < partial < destroyed), or null when none were classified.

Tile labels are a proxy. The model was trained on worst-building-per-tile
labels at two scales (1024 px xBD and 512 px EBD), so `percent_damaged` is
a tile-level estimate, not a building-level damage rate.

Errors: pixels over `SCENE_MAX_PIXELS` (default 16777216) → HTTP 413
{ "error": "string", "code": "image_too_large" }. More tiles than
`SCENE_MAX_TILES` (default 111) → HTTP 422
{ "error": "string", "code": "too_many_tiles" }. Invalid image → HTTP 400.
A truncated scene is not an error.

Passing the result to POST /rank-priority: the scoring input is
`damage_breakdown` for none, partial, and destroyed, plus this response's
`tile_count` when the caller wants coverage. /rank-priority accepts exactly
one damage source, so a scene submission uses the breakdown on its own.
This response's `overall_damage_level` means the worst class across
classified tiles; /rank-priority's `overall_damage_level` means the label
of one tile. `uncertain` is not a field of /rank-priority's DamageBreakdown
(the current model ignores that extra key). `skipped_count` has no field
there. A scene with zero classified tiles has nothing to submit:
/rank-priority requires at least one classified tile.

## POST /rank-priority
Request: JSON body
{
  "districts": [
    {
      "district": "string",
      "hazard_type": "flood|glof|avalanche|landslide|drought",
      "risk_level": "low|medium|high|unknown",          // from /predict-risk
      // Damage assessment -- exactly ONE of:
      "damage_breakdown": { "none": 0, "partial": 0, "destroyed": 0 },  // aggregated /classify-damage tile counts
      "overall_damage_level": "none|partial|destroyed",                 // single-tile mode
      // Optional (breakdown mode only): total tiles incl. unclassified; coverage info, never scored
      "tile_count": 0,
      // Optional (single-tile mode only): /classify-damage confidence
      "confidence": 0.0
    }
  ]
}

Response:
{
  "ranked_districts": [
    {
      "rank": 1,
      "district": "string",
      "hazard_type": "string",
      "risk_level": "string", "risk_score": 0.0,
      "damage_score": 0.0, "percent_damaged": 0.0,
      "tile_count": 0, "classified_tiles": 0,
      "damage_source": "damage_breakdown|overall_damage_level",
      "priority_score": 0.0,
      "low_coverage_warning": "low coverage — based on 1 tile" | null,
      "damage_breakdown": { ... }, "overall_damage_level": "string", "confidence": 0.0
    }
  ],
  "scoring": {
    "formula": "priority = (risk_weight * risk_score + damage_weight * damage_score) / (risk_weight + damage_weight)",
    "risk_weight": 0.4, "damage_weight": 0.6,
    "risk_level_scores": { "low": 0.0, "medium": 0.5, "high": 1.0, "unknown": 0.0 },
    "damage_severity_scores": { "none": 0.0, "partial": 0.5, "destroyed": 1.0 },
    "tie_breaker": "equal scores ordered by district name (ascending)",
    "photo_count_note": "damage_score is a per-tile average, never a sum",
    "low_coverage_note": "transparency signal only; never a scoring input"
  }
}

Errors: unified structure { "error": { "code": "string", "message": "string" } }
with HTTP 422 for domain violations (duplicate district, conflicting damage
fields); schema-level problems use FastAPI's standard 422 detail format.

Scoring notes:
- damage_score is normalized per classified tile, so the number of assessed
  tiles never skews priority ("more photos != more damage").
- hazard_type is carried through for multi-hazard context and response-team
  logistics; it does not multiply the score because hazard-specific danger
  is already encoded in risk_level from Risk Flag.
- low_coverage_warning is set when the tile count backing a district's
  damage assessment is below LOW_COVERAGE_TILE_THRESHOLD (default 5,
  env-configurable). It is a TRANSPARENCY SIGNAL for response teams -- a
  rank-1 district assessed from one photo deserves more skepticism than
  one assessed from 100 tiles -- and is NOT a scoring input: it never
  affects priority_score, rank order, or any other computed value.
