# API Contract -- Nigraan AI

## POST /predict-risk
Request:
{ "district": "string" }

Rainfall is fetched server-side from Open-Meteo (forecast, 30-day, and 90-day
totals); the caller only identifies the district.

Response:
{ "district": "string", "hazard_types": ["string"], "rainfall_forecast_mm": number | null,
  "rainfall_30d_mm": number | null, "rainfall_90d_mm": number | null,
  "risk_level": "low|medium|high|unknown", "reason": "string", "cached": boolean }

## POST /classify-damage
Request: multipart/form-data, field "image"

Response:
{ "damage_level": "none|partial|destroyed", "confidence": number, "area": "string" }

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
