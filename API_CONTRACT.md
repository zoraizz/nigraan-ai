# API Contract -- Nigraan AI

## POST /predict-risk
Request:
{ "district": "string" }

Rainfall is fetched server-side from Open-Meteo (forecast, 30-day, and 90-day
totals); the caller only identifies the district.

Response:
{ "district": "string", "hazard_types": ["string"],
  "rainfall_forecast_mm": number | null,
  "rainfall_30d_mm": number | null, "rainfall_90d_mm": number | null,
  "weather_metrics": {
    "rainfall_forecast_mm": number | null,
    "rainfall_30d_mm": number | null,
    "rainfall_90d_mm": number | null,
    "temperature_max_c_3d": number | null,
    "temperature_min_c_3d": number | null,
    "precip_probability_max_pct_3d": number | null,
    "wind_speed_max_kmh_3d": number | null,
    "wind_gust_max_kmh_3d": number | null,
    "humidity_mean_pct_3d": number | null,
    "soil_moisture_0_1cm_m3m3": number | null,
    "snowfall_cm_3d": number | null,
    "snow_depth_cm": number | null,
    "river_discharge_max_m3s_3d": number | null
  } | null,
  "risk_level": "low|medium|high|unknown", "reason": "string", "cached": boolean,
  "rainfall_unavailable": boolean, "weather_unavailable": boolean,
  "reasoning_source": "gemini|grok|fallback|cache" | null,
  "reasoning_error": "api_error|bad_json" | null }

`weather_metrics` is null for an unknown district and an object for every
covered district (individual fields may be null). The top-level `rainfall_*`
fields mirror the same keys inside `weather_metrics`.

Units: rainfall mm; temperature °C; precipitation probability and humidity %;
wind km/h; soil moisture m³/m³ at 0–1 cm (3-day mean); snowfall cm (3-day
sum); snow depth cm (latest forecast hour, converted from metres); river
discharge m³/s (3-day maximum).

Fetch plan (free Open-Meteo, no API key), before retries: one forecast call
per district (`/v1/forecast`, daily + hourly variables, 3 days). Drought
districts add one archive call (`/v1/archive`). That call sends `start_date`
and `end_date` for 90 inclusive dates in timezone `Asia/Karachi`. The end
date is the earlier of the Asia/Karachi calendar day and the UTC calendar
day, and `start_date` is that end date minus 89 days. Open-Meteo documents
the default Best Match as available "to present" (ECMWF IFS has no delay;
ERA5's five-day delay is not applied as a Best Match cutoff) but does not
define present as the Asia/Karachi date, so a Karachi day that is still the
next UTC day is not requested. The UTC day is not assumed to be published.
If that request returns HTTP 400 and the body says `end_date` is outside an
allowed range ending on a real earlier date, one recovery request uses that
date as the end of a new 90-day window. The returned days are checked
against the dates that were actually requested, including a recovery. No
other HTTP 400 is recovered, and a failed recovery leaves both rainfall
totals null. A learned end date is remembered for the 3-hour weather-cache
lifetime so later districts do not repeat the rejected date. A failed
response is not stored as rainfall. The call does not use `past_days`.
`precipitation_sum` is millimetres. A historical total counts a day only
when that requested date appears once and is paired with a numeric
precipitation value. Ninety numbers without those dates, a mismatched
`time` array, or a repeated date do not form a total and are not filled in.
The 90-day total needs all 90 dates. The 30-day total is the last 30 dates
of that same window and can stand on its own when only older dates are
missing or duplicated, including genuine zeros. A gap is not turned into
zero. Flood districts add one Flood API call
(`flood-api.open-meteo.com/v1/flood`, `river_discharge`). Hourly series are
reduced to scalars before the response and the LLM prompt.

`rainfall_forecast_mm` is set for every district when the forecast bundle
succeeds, including GLOF, landslide, and drought. `rainfall_30d_mm` and
`rainfall_90d_mm` are set for drought districts. `river_discharge_max_m3s_3d`
is set only for flood districts, and only when GloFAS returns a number. Null
means no usable value. It is the nearest ~5 km model cell, and the rule
scorer does not turn that number into a risk level.

`rainfall_unavailable` keeps its previous meaning: 3-day rain missing for a
flood district, or 30/90-day rain missing for a drought district.
`weather_unavailable` is true when a critical input for that district's
hazards is missing (forecast bundle for flood, landslide, and GLOF/avalanche;
historical rain or 3-day max temperature for drought). A missing discharge,
humidity, or soil-moisture series does not by itself set the flag when the
primary signal is present. Missing drought history still sets
`weather_unavailable` true.

The reason text, not a new response field, says which case applies. When no
usable weather value was returned, it says the assessment uses static NDMA
hazard context only. When some metrics are present, it says some required
weather data is unavailable and the assessment uses the available weather
plus static hazard context. For a drought district with forecast max
temperature and a missing 30-day or 90-day total, it says historical rainfall
is unavailable and the drought assessment is limited. The Risk Map banner
uses the same three sentences from the existing flags and metric fields.

reasoning_source is null for an unknown district. reasoning_error is a short
code only (never a stack trace or secret) and is null when scoring succeeded.

This is rainfall-and-weather context plus LLM reasoning. It is not a
hydrological, glacier, or avalanche model.

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
