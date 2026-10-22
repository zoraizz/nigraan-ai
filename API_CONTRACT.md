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

HTTP 429 is not retried inside the user request and is not stored as zero
rainfall. The server records a process-local cooldown for the Open-Meteo URL
that returned it. Forecast, archive, and flood cooldowns are independent. A
valid `Retry-After` delay-seconds or HTTP-date sets that cooldown, capped at
the 3-hour weather-cache lifetime. A missing or invalid `Retry-After` uses
60 seconds. The request returns the existing nulls and availability flags
without sleeping for the cooldown. Fresh cache entries are still used. A
restart clears the cooldown. 5xx responses and timeouts still retry up to
two times. Concurrent requests for the same coordinate and weather window
share one in-flight fetch in that process.

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
      "confidence": 0.0,
      // --- flood signal (River Flood Tracker) ---
      // Optional hours until the modelled river-flood peak reaches this
      // district. Estimate, not a gauge reading. Number >= 0, or null.
      // Omit or null when the district has no ETA.
      "flood_eta_hours": 0.0,
      // Further optional signals use the same pattern: one key per
      // registered signal's request_field. Omit or null when absent.
      "<request_field>": "any"
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
      "damage_breakdown": { ... }, "overall_damage_level": "string", "confidence": 0.0,
      // Active signals only ({} when none are active). score is null when a
      // "skip" signal has no value for this district.
      "signals": { "<name>": { "value": "any", "score": 0.0 } }
    }
  ],
  "scoring": {
    "formula": "priority = (risk_weight * risk_score + damage_weight * damage_score) / (risk_weight + damage_weight)",  // extended when signals are active
    "risk_weight": 0.4, "damage_weight": 0.6,
    "risk_level_scores": { "low": 0.0, "medium": 0.5, "high": 1.0, "unknown": 0.0 },
    "damage_severity_scores": { "none": 0.0, "partial": 0.5, "destroyed": 1.0 },
    "tie_breaker": "equal scores ordered by district name (ascending)",
    "photo_count_note": "damage_score is a per-tile average, never a sum",
    "low_coverage_note": "transparency signal only; never a scoring input",
    // Every registered signal, active or not. "flood" is registered
    // (request_field flood_eta_hours).
    "signals": [
      { "name": "string", "request_field": "string", "weight": 0.0,
        "missing_policy": "zero|skip", "curve": "string", "note": "string",
        "active": true }
    ]
  }
}

Errors: unified structure { "error": { "code": "string", "message": "string" } }
with HTTP 422 for domain violations (duplicate district, conflicting damage
fields, `invalid_signal_value` when a signal rejects a value); schema-level
problems use FastAPI's standard 422 detail format.

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
- Optional signals (aid-priority/scoring.py OPTIONAL_SIGNALS) let features
  such as River Flood Tracker and Ground Photo Intake add a term without
  changing the formula's shape:
      priority = (risk_weight * risk_score + damage_weight * damage_score
                  + sum_k weight_k * score_k)
                 / (risk_weight + damage_weight + sum_k weight_k)
  Each signal maps its request_field value to a score in [0, 1] and takes
  its weight from its own env var (validated like PRIORITY_RISK_WEIGHT).
  A signal is ACTIVE for a request only when at least one district carries
  a non-null value for its field; a request without any signal fields is
  scored exactly as before. When a signal is active, a district without a
  value follows the signal's missing_policy: "zero" scores 0 and the weight
  still counts (e.g. no flood ETA = no water coming); "skip" removes the
  weight from both sums for that district, so it keeps exactly its
  no-signal score (e.g. no ground photos = no evidence, not zero damage).
  Unregistered extra keys on a district are accepted and ignored.
- --- flood signal (River Flood Tracker) --- `flood_eta_hours` (number >= 0
  or null) is hours until the river flood peak reaches the district, a
  River Flood Tracker estimate, not a gauge reading. Score is 1.0 when
  h <= 12, (120 - h) / 108 when 12 < h < 120, and 0.0 when h >= 120.
  Weight comes from PRIORITY_FLOOD_WEIGHT (default 0.3). missing_policy
  is "zero": when any district in the request sends an ETA, a district
  without one scores 0 for this signal and the weight still counts.
  A request that omits the field on every district does not activate the
  signal, so its priority scores stay on the risk-and-damage formula.
  The value is echoed under ranked_districts[].signals.flood when active,
  and scoring.signals lists the curve and note whether or not it is active.

<!-- flood -->
## River Flood Tracker

Service: `flood-tracker/`. Endpoint shapes below follow
[flood-tracker/CONTRACT.md](flood-tracker/CONTRACT.md), with the current
main-wave scorecard filtering noted explicitly. ETAs are modelled estimates;
`data_provenance` distinguishes them from gauge readings.
[Fixtures](flood-tracker/data/fixtures/) are hand-made contract examples,
not gauge readings or model output.

## `GET /flood-situation?mode=replay&as_of=2022-08-31T06:00`

```json
{
  "as_of": "",
  "mode": "replay|live|what_if",
  "barrages": [{ "name": "", "order": 1, "lat": 0, "lon": 0, "inflow_cusecs": 0, "outflow_cusecs": 0, "category": "", "trend": "rising|falling|stable" }],
  "reaches": [{ "from": "", "to": "", "category": "", "coords": [[0, 0]] }],
  "peaks": [{ "barrage": "", "wave_id": "", "wave_label": "Wave 1|null", "status": "forming|passed", "peak_time": "", "peak_outflow_cusecs": 0 }],
  "etas": [{ "wave_id": "", "wave_label": "Wave 1|null", "from_barrage": "", "barrage": "", "status": "estimated|arrived", "eta": "", "eta_low": "", "eta_high": "", "hours_from_now": 0, "observed_time": null }],
  "at_risk_villages": [{ "id": "", "name": "", "district": "", "lat": 0, "lon": 0, "eta": "", "eta_low": "", "eta_high": "", "hours_to_arrival": 0, "population": 0, "population_source": "", "river_distance_km": 0.0 }],
  "district_eta_hours": { "<district>": 0.0 },
  "data_provenance": { "flows": "", "etas": "", "villages": "", "population": "" }
}
```

`reaches[].coords` are `[lat, lon]`. `at_risk_villages[].river_distance_km` (optional, all modes) is the village's distance in km to the indus.geojson centreline, rounded to 0.1. `mode` defaults to `replay`; omitted
`as_of` uses the last available reading. `mode=live` is described below. Invalid mode or
time returns HTTP 422 (`invalid_mode`, `invalid_as_of`,
`as_of_out_of_range`); missing required data returns HTTP 503
`data_unavailable`.

## `GET /flood-situation?mode=live`

Same situation object with `mode: "live"` and `as_of` = today 06:00 PKT, plus:

```json
{
  "forecast": [{ "name": "", "today_cusecs": 0, "today_category": "", "series": [{ "date": "YYYY-MM-DD", "cusecs": 0 }], "forecast_peak_cusecs": 0, "forecast_peak_date": "", "forecast_peak_category": "", "low_threshold_cusecs": 0, "first_crossing": { "category": "", "date": "" }, "calibrated": true, "confidence": "bias-scaled|low confidence" }],
  "outlook": ["<forecast rows whose forecast reaches Low Flood or higher, soonest first_crossing first>"],
  "forecast_days": 30,
  "calibration_warnings": [""]
}
```

- Flows are modelled: GloFAS v4 daily river discharge via the Open-Meteo Flood API (m3/s x 35.3147 = cusecs), multiplied by a per-barrage `scale` from `data/glofas_calibration.json` (FFC 2022 peak / GloFAS 2022 peak at the highest-mean-discharge cell of a 7x7, 0.05 degree grid). `data_provenance.flows` says so; these are not FFC gauge readings.
- Daily model dates are stamped 06:00 PKT. Readings up to today feed the routing engine; `series` holds today and the forecast days (up to 30).
- `first_crossing` is the first forecast day (today included) at or above Low Flood, with that day's category; `null` if none.
- Barrages with `calibrated: false` (scale outside 0.25..4 or correlation < 0.3) are shown with a "low confidence" badge.
- Fetches are cached in memory for 3 hours. Any fetch or calibration failure returns 503 `live_unavailable`.

## `POST /what-if`

Body: `{ "barrage": "Taunsa", "peak_cusecs": 650000, "peak_time"?: "YYYY-MM-DDTHH:MM" }` (`peak_time` defaults to today 06:00 PKT).

Returns a situation object with `mode: "what_if"`, `as_of` = `peak_time` + 24 h, plus:

```json
{
  "scenario": { "barrage": "", "peak_cusecs": 0, "peak_category": "", "peak_time": "", "assumption": "peak carried downstream unchanged; barrage gates and breaches not modelled; villages are those flooded in 2022" },
  "note": "Below Medium Flood: villages not listed (only when peak_category is below Medium Flood)"
}
```

- Synthetic hydrograph: every barrage at 60% of its Low threshold for the 6 days before `peak_time`; the chosen barrage rises over 3 days to `peak_cusecs` and falls 10% the next day. Routed with the same lag engine.
- Villages follow the exposure bands below. Below Medium Flood, `etas` are kept but `at_risk_villages` is `[]` and `note` is set.
- 422: `invalid_request` (`peak_cusecs` <= 0 or > 2,000,000, bad body), `invalid_scenario` (unknown barrage, bad `peak_time`).

### Exposure bands (live and what-if)

`at_risk_villages` in live and what-if are 2022-flooded villages within a radius of the river centreline that grows with the peak category (`river_distance_km` <= R):

| Peak category | Villages listed |
|---|---|
| Normal, Low Flood | none |
| Medium Flood | within 3 km |
| High Flood | within 6 km |
| Very High Flood | within 10 km |
| Exceptionally High Flood | all 2022-flooded villages |

- What-if uses `scenario.peak_category`; `scenario.exposure = { "radius_km": 10.0|null, "category": "", "rule": "villages flooded in 2022 within R km of the river centreline; larger floods reach further" }` (`radius_km` null = no limit, 0 = none listed). `district_eta_hours` is recomputed from the kept rows.
- Live uses, per village, the forecast peak category at the barrage just upstream of the village (by `river_km`); the response adds `exposure: { "rule": "", "bands_km": { "<category>": 0|3|6|10|null } }`.
- Replay is never filtered: those villages flooded in 2022.

## `GET /health` (flood fields)

`live_available`: `"ok"|"failed"|"never"` (last GloFAS fetch); `calibration_loaded`: bool.

## Time and category rules

- All times are Asia/Karachi local, format `YYYY-MM-DDTHH:MM`, with no offset.
- `hours_from_now` and `hours_to_arrival` are negative once the peak or the village arrival has passed.
- A reach's `category` is the higher of its two end barrages' categories. Order is Normal < Low Flood < Medium Flood < High Flood < Very High Flood < Exceptionally High Flood.

## Waves

- `wave_id` (`indus-<year>-w<n>`) is internal: every rise above Low Flood at any barrage gets one. Use it as a key, not as display text.
- `wave_label` is what the UI shows: `"Wave 1"`, `"Wave 2"`, ... in time order, only for waves that reached Medium Flood or higher at 2 or more barrages. It is `null` for a minor rise.
- `eta_low`/`eta_high` (and scorecard `predicted_low`/`predicted_high`) are at least 12 h either side of the estimate (daily 06:00 sampling).

## `GET /replay/2022`

```json
{
  "steps": ["<flood-situation objects, one per day at 06:00>"],
  "scorecard_note": "",
  "scorecard": [{ "barrage": "", "wave_id": "", "wave_label": "Wave 1|Wave 2", "in_sample": true, "note": "<string|null>", "actual_peak_time": "", "predicted_time": "", "predicted_low": "", "predicted_high": "", "error_hours": 0 }]
}
```

- The API scorecard excludes rows with null `wave_label` and sorts by
  `wave_label`, then barrage order: Tarbela, Kalabagh, Chashma, Taunsa,
  Guddu, Sukkur, Kotri.
- `error_hours = actual - predicted`: positive means the crest came later than predicted. A plateau crest (same outflow on consecutive readings, e.g. Kotri 584000 on 5-8 Sep) scores 0 when the prediction falls inside it, else the hours to the nearest edge; `note` says so.
- `in_sample` is true when reaches.json lags were calibrated on that crest. `scorecard_note` states this and gives the leave-one-wave-out errors.

## `POST /alert-drafts`

Body: `{ "village_ids"?: [], "district"?: "", "as_of": "", "mode"?: "replay|live|what_if", "scenario"?: <what-if body> }` (for live/what_if, `as_of` must equal that situation's `as_of`; `scenario` is required for what_if)

```json
{
  "drafts": [{ "village_id": "", "name": "", "district": "", "urdu": "", "sindhi": "", "source": "gemini|qwen|template", "model": "" }]
}
```

- Villages are resolved against `at_risk_villages` of `/flood-situation` at `as_of`; `village_ids` wins when both are given. A district gives its at-risk villages in ETA order (`{"drafts": []}` when none is at risk), at most 25.
- Template fallback drafts use localized day, month and rough time of day
  in Urdu and Sindhi, retain the draft marker, and are at most 140 characters.
- 422 codes: `invalid_request` (body shape, e.g. no `as_of`), `missing_target`, `too_many_villages` (over 25 ids), `invalid_as_of`, `as_of_out_of_range`, `unknown_village_ids`, `village_not_at_risk`, `unknown_district`. 503 `data_unavailable` / `villages_unavailable`.

## Errors

```json
{ "error": { "code": "<machine>", "message": "<human>" } }
```

## Ground Photo Intake (damage-checker)

Turns ground-level disaster photos into structured, officer-reviewed reports.
Same base URL as `/classify-damage` (dashboard `ENDPOINTS.damageApi`).
`/classify-damage` and `/classify-scene` are unchanged. Errors use the
damage-checker shape:

```json
{ "error": "<human text>", "code": "<machine_code>" }
```

### Report object

The vision model fills the closed enums (`image_kind` through `confidence`).
Code adds the rest. `urgent`, `urgent_reasons` and every summary number come
from Python rules, never from the model.

```json
{
  "image_kind": "ground_disaster|aerial_or_satellite|irrelevant",
  "image_confidence": 0.93,
  "scene_type": "flooded_street|flooded_farmland|collapsed_house|damaged_building|damaged_road|broken_bridge|landslide|debris|relief_camp|other_disaster",
  "damage_level": "none|partial|destroyed",
  "water": { "present": true, "flowing": false, "depth": "none|ankle|knee|waist|chest|above_head" },
  "hazards": ["blocked_road|downed_power_lines|unstable_structure|fast_water|fire"],
  "people": { "visible": true, "count_estimate": 4, "stranded_or_trapped": false, "on_rooftop": true, "injured": false },
  "animals": { "livestock_visible": true, "livestock_at_risk": true },
  "needs": ["rescue|shelter|medical|food_water|road_clearance"],
  "summary": "1-2 sentences, damage and needs only",
  "confidence": 0.81,
  "id": "<uuid4 hex>",
  "created_at": "2026-10-22T09:14:03Z",
  "urgent": true,
  "urgent_reasons": ["people_trapped|people_on_rooftop|people_injured|rising_water_near_people"],
  "location": { "lat": 26.73, "lon": 67.78, "source": "exif|device|manual|unknown", "district": "Dadu", "village": "Johi" },
  "phash": "<64-bit dHash, hex>",
  "duplicate_of": null,
  "duplicate_count": 0,
  "status": "unverified|verified|corrected|rejected",
  "review": {
    "history": [{ "action": "verify|correct|reject", "officer": null, "note": null, "at": "2026-10-22T10:02:11Z" }],
    "ai_original": { "<the model's first observation: image_kind ... confidence>": "" }
  },
  "reporter_role": "field_worker|rescue_team|citizen",
  "vlm_source": "gemini|qwen",
  "vlm_model": "gemini-3.8-flash"
}
```

- `duplicate_of` is the id of the group's first report when the photo's
  perceptual hash is within `GROUND_DUPLICATE_MAX_HAMMING` bits (default 8)
  of a non-rejected report in the same district, or within 1 km when both
  have coordinates. Copies never count twice.
- `duplicate_count` is only filled in folded lists (`GET /ground-reports`
  without `include_duplicates`). It is 0 elsewhere.
- `rising_water_near_people` needs a visible person plus waist-deep or
  deeper, or flowing, water.

### `POST /intake`

Request: multipart/form-data, field `image`. Query, all optional:
`district`, `village`, `lat` (-90..90), `lon` (-180..180),
`reporter_role` (`field_worker|rescue_team|citizen`, default `citizen`).

The upload first goes through the same classifier and OOD guard as
`/classify-damage`. If the guard does not flag it, `route` is `satellite` and
the vision model is not called. If it does, the vision model looks at it,
and it becomes a ground report only when the model says `ground_disaster`
with `image_confidence` >= `GROUND_MIN_CONFIDENCE` (default 0.6). Every
other case is rejected the way `/classify-damage` rejects it, plus a
`reason`.

Satellite tile (`satellite` holds the same fields `/classify-damage` returns):

```json
{
  "route": "satellite",
  "satellite": {
    "damage_level": "partial", "confidence": 0.74, "area": "Dadu",
    "is_out_of_domain": false,
    "ood": { "cosine": 0.0312, "mahalanobis": 8.2041, "cosine_threshold": 0.15568, "mahalanobis_threshold": 19.044245,
             "photo_cosine": 0.14, "photo_mahalanobis": 21.3, "photo_score": 0.9932, "photo_score_threshold": 1.65,
             "signals": [] }
  }
}
```

Ground photo (`report` is the stored report object, `status` `unverified`):

```json
{
  "route": "ground",
  "report": {
    "id": "3f2a9c0e7b6d4e1f9a8b7c6d5e4f3a2b", "created_at": "2026-10-22T09:14:03Z",
    "image_kind": "ground_disaster", "image_confidence": 0.93,
    "scene_type": "flooded_street", "damage_level": "partial",
    "water": { "present": true, "flowing": true, "depth": "waist" },
    "hazards": ["fast_water"],
    "people": { "visible": true, "count_estimate": 4, "stranded_or_trapped": false, "on_rooftop": true, "injured": false },
    "animals": { "livestock_visible": false, "livestock_at_risk": false },
    "needs": ["rescue", "food_water"],
    "summary": "Waist-deep flowing water through a village street; a family is waiting on a rooftop.",
    "confidence": 0.81,
    "urgent": true, "urgent_reasons": ["people_on_rooftop", "rising_water_near_people"],
    "location": { "lat": 26.73, "lon": 67.78, "source": "exif", "district": "Dadu", "village": "Johi" },
    "phash": "c3e1f0f8781c0e07", "duplicate_of": null, "duplicate_count": 0,
    "status": "unverified",
    "review": { "history": [], "ai_original": { "image_kind": "ground_disaster", "...": "..." } },
    "reporter_role": "field_worker", "vlm_source": "gemini", "vlm_model": "gemini-3.8-flash"
  }
}
```

Irrelevant (same `message` and `ood` fields as a flagged `/classify-damage`):

```json
{
  "route": "irrelevant",
  "message": "This image doesn't resemble a satellite disaster-imagery tile -- the damage result may be unreliable.",
  "reason": "vlm_irrelevant|vlm_aerial|vlm_low_confidence|vlm_unavailable",
  "ood": { "cosine": 0.3104, "mahalanobis": 27.9, "cosine_threshold": 0.15568, "mahalanobis_threshold": 19.044245,
           "photo_cosine": 0.52, "photo_mahalanobis": 48.1, "photo_score": 2.8167, "photo_score_threshold": 1.65,
           "signals": ["texture", "photo_content"] }
}
```

- `vlm_unavailable` covers no provider configured, timeout, provider error
  and unparseable model output. Provider errors are never echoed.
- Location source: EXIF GPS (`exif`), else the `lat`/`lon` query
  (`device`), else a `district` query only (`manual`), else `unknown`. With
  coordinates, `district` becomes the nearest district centre within
  `GROUND_DISTRICT_MAX_KM` (default 60). Beyond that the sent district is
  kept.
- The stored photo is upright, EXIF-stripped, long side at most 1024 px.
- 400 `invalid_image`. 413 `image_too_large` (over `GROUND_MAX_UPLOAD_BYTES`,
  default 10485760, or too many pixels). `X-Model-Warning: untrained-weights`
  as on `/classify-damage`.

### `GET /ground-reports`

Query, all optional: `district`, `status`
(`unverified|verified|corrected|rejected`), `urgent` (`true|false`),
`include_duplicates` (default `false`).

Response: a JSON array of report objects. Order: urgent and unverified
first, then other unverified, then reviewed; newest first inside each group.
Without `include_duplicates`, copies are hidden and their first report
carries `duplicate_count`.

```json
[
  { "id": "3f2a9c0e7b6d4e1f9a8b7c6d5e4f3a2b", "status": "unverified", "urgent": true,
    "scene_type": "flooded_street", "damage_level": "partial", "duplicate_of": null, "duplicate_count": 1,
    "location": { "lat": 26.73, "lon": 67.78, "source": "exif", "district": "Dadu", "village": "Johi" },
    "...": "every other report field" }
]
```

422 `invalid_status` for an unknown `status`.

### `GET /ground-reports/{id}`

One report object, duplicates and rejected reports included. 404:

```json
{ "error": "Ground report not found.", "code": "not_found" }
```

### `GET /ground-reports/{id}/photo`

The stored JPEG (`Content-Type: image/jpeg`). 404 `not_found` as above.

### `PATCH /ground-reports/{id}/review`

Request: JSON body

```json
{
  "action": "verify|correct|reject",
  "corrections": {
    "damage_level": "destroyed",
    "scene_type": "collapsed_house",
    "needs": ["shelter", "medical"],
    "people": { "injured": true },
    "water": { "depth": "knee" },
    "district": "Dadu"
  },
  "note": "Checked with the Johi field team",
  "officer": "PDMA Sindh duty officer"
}
```

- `corrections` is applied only for `correct`. Every key is optional,
  `people` and `water` merge into the stored values, unknown keys fail.
- `correct` keeps the model's first output in `review.ai_original` (set
  once, never overwritten) and recomputes `urgent` / `urgent_reasons`.
- Every action appends `{action, officer, note, at}` to `review.history`.
- `reject` drops the report from `/ground-summary` and from duplicate
  matching.

Response: the updated report object.

```json
{ "id": "3f2a9c0e7b6d4e1f9a8b7c6d5e4f3a2b", "status": "corrected", "damage_level": "destroyed",
  "urgent": true, "urgent_reasons": ["people_on_rooftop", "people_injured", "rising_water_near_people"],
  "review": { "history": [{ "action": "correct", "officer": "PDMA Sindh duty officer", "note": "Checked with the Johi field team", "at": "2026-10-22T10:02:11Z" }],
              "ai_original": { "damage_level": "partial", "...": "..." } },
  "...": "every other report field" }
```

404 `not_found`. 422 `invalid_action` or `invalid_corrections`.

### `GET /ground-summary`

Query, optional: `district`.

More photos != more damage: `share_destroyed`, `share_damaged` and
`ground_score` are shares over unique (non-duplicate), non-rejected reports.
`report_count`, `photo_count`, `verified_count`, `severity_mix`,
`top_scene_types` counts, `urgent_open` and `low_sample_warning` are display
only. Reports with no district are left out. Districts with no surviving
report are omitted.

```json
{
  "districts": {
    "Dadu": {
      "report_count": 4,
      "photo_count": 5,
      "verified_count": 2,
      "severity_mix": { "none": 1, "partial": 2, "destroyed": 1 },
      "share_destroyed": 0.25,
      "share_damaged": 0.75,
      "ground_score": 0.5,
      "top_scene_types": [{ "scene_type": "flooded_street", "count": 2 }, { "scene_type": "collapsed_house", "count": 1 }],
      "urgent_open": 1,
      "low_sample_warning": null
    }
  }
}
```

- `ground_score = (0.5 * partial + 1.0 * destroyed) / report_count`.
- `photo_count` includes duplicates. `verified_count` counts `verified` and
  `corrected`. `urgent_open` counts unique reports that are urgent.
- `low_sample_warning` is `"low sample — based on N report(s)"` below 3
  unique reports, else `null`.

### `GET /health` (ground fields)

`ground_vlm_providers` (names, e.g. `["gemini"]`), `ground_vlm_configured`
(bool), `ground_report_count`. Never a key or an env value.

### `POST /rank-priority`: optional `ground_evidence` (aid-priority)

Registered as the `ground` optional signal: `missing_policy` `skip`, weight
`PRIORITY_GROUND_WEIGHT` (default 0.2). Per district, optional:

```json
{
  "district": "Dadu", "hazard_type": "flood", "risk_level": "high",
  "overall_damage_level": "partial", "confidence": 0.74,
  "ground_evidence": { "none": 1, "partial": 2, "destroyed": 1, "verified_count": 2, "urgent_open": 1 }
}
```

- `none`, `partial`, `destroyed` are required integers >= 0 with a sum >= 1
  (the district's `severity_mix` from `/ground-summary`). `verified_count`
  and `urgent_open` are optional integers >= 0, validated but not scored.
- Score: `(0.5 * partial + 1.0 * destroyed) / (none + partial + destroyed)`.
  The same shares score the same however many reports they hold.
- Omit the field (or send `null`) for a district with no ground reports: it
  is skipped, not scored as zero.
- Echoed per district:
  `"signals": { "ground": { "value": { "none": 1, "partial": 2, "destroyed": 1, "verified_count": 2, "urgent_open": 1 }, "score": 0.5 } }`.
  `score` is `null` for a skipped district.
- A bad value is 422 `invalid_signal_value` in the aid-priority error shape
  (`{"error": {"code", "message"}}`).
