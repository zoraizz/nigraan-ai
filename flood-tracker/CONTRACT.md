# River Flood Tracker contract

Parallel agents build against this file. Fixture responses in `flood-tracker/data/fixtures/` are hand-made examples of these shapes. They are not gauge readings and not model output.

## Data files (`flood-tracker/data/`)

- `flows_2022.csv`: `date_time` (ISO, Asia/Karachi, e.g. `2022-08-29T06:00`), `barrage`, `inflow_cusecs`, `outflow_cusecs`, `ffc_category`, `trend` (`R`|`F`|`S`|blank), `source_url`
- `barrages.json`: `[{name, order (1..7), lat, lon, river_km, thresholds: {low, medium, high, very_high, exceptionally_high}, threshold_source, notes}]`
- `reaches.json`: `[{from, to, lag_median_h, lag_min_h, lag_max_h, attenuation_ratio, events_used, note}]`
- `indus.geojson`: one LineString FeatureCollection, `properties.river_km_start = 0` at Tarbela; coordinates `[lon, lat]`
- `villages.json`: `[{id, name, district, lat, lon, river_km, bank (left|right), population, population_source, sources}]`

Indus barrages in order: Tarbela, Kalabagh, Chashma, Taunsa, Guddu, Sukkur, Kotri.

Flood categories (applied to outflow): Normal, Low Flood, Medium Flood, High Flood, Very High Flood, Exceptionally High Flood.

Thresholds in cusecs (Low/Medium/High/VeryHigh/ExceptionallyHigh), source FFD bulletin:

- Tarbela, Kalabagh, Chashma, Taunsa: 250000/375000/500000/650000/800000
- Guddu: 200000/350000/500000/700000/900000
- Sukkur: 200000/350000/500000/700000/900000 (Exceptionally High not published; 900000 assumed, mark it as assumed)
- Kotri: 200000/300000/450000/650000/800000

## `GET /flood-situation?mode=replay&as_of=2022-08-31T06:00`

```json
{
  "as_of": "",
  "mode": "replay|live|what_if",
  "barrages": [{ "name": "", "order": 1, "lat": 0, "lon": 0, "inflow_cusecs": 0, "outflow_cusecs": 0, "category": "", "trend": "rising|falling|stable" }],
  "reaches": [{ "from": "", "to": "", "category": "", "coords": [[0, 0]] }],
  "peaks": [{ "barrage": "", "wave_id": "", "wave_label": "Wave 1|null", "status": "forming|passed", "peak_time": "", "peak_outflow_cusecs": 0 }],
  "etas": [{ "wave_id": "", "wave_label": "Wave 1|null", "from_barrage": "", "barrage": "", "status": "estimated|arrived", "eta": "", "eta_low": "", "eta_high": "", "hours_from_now": 0, "observed_time": null }],
  "at_risk_villages": [{ "id": "", "name": "", "district": "", "lat": 0, "lon": 0, "eta": "", "eta_low": "", "eta_high": "", "hours_to_arrival": 0, "population": 0, "population_source": "" }],
  "district_eta_hours": { "<district>": 0.0 },
  "data_provenance": { "flows": "", "etas": "", "villages": "", "population": "" }
}
```

`reaches[].coords` are `[lat, lon]`.

## Time and category rules

- All times are Asia/Karachi local, format `YYYY-MM-DDTHH:MM`, with no offset.
- `hours_from_now` and `hours_to_arrival` are negative once the peak or the village arrival has passed.
- A reach's `category` is the higher of its two end barrages' categories. Order is Normal < Low Flood < Medium Flood < High Flood < Very High Flood < Exceptionally High Flood.

## Waves

- `wave_id` (`indus-<year>-w<n>`) is internal: every rise above Low Flood at any barrage gets one. Use it as a key, not as display text.
- `wave_label` is what the UI shows: `"Wave 1"`, `"Wave 2"`, ... in time order, only for waves that reached Medium Flood or higher at 2 or more barrages. It is `null` for a minor rise.
- `eta_low`/`eta_high` (and scorecard `predicted_low`/`predicted_high`) are at least 12 h either side of the estimate (daily 06:00 sampling).

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
- Below Medium Flood, `etas` are kept but `at_risk_villages` is `[]` and `note` is set.
- 422: `invalid_request` (`peak_cusecs` <= 0 or > 2,000,000, bad body), `invalid_scenario` (unknown barrage, bad `peak_time`).

## `GET /health` (flood fields)

`live_available`: `"ok"|"failed"|"never"` (last GloFAS fetch); `calibration_loaded`: bool.

## `GET /replay/2022`

```json
{
  "steps": ["<flood-situation objects, one per day at 06:00>"],
  "scorecard_note": "",
  "scorecard": [{ "barrage": "", "wave_id": "", "wave_label": "Wave 1|null", "in_sample": true, "note": "<string|null>", "actual_peak_time": "", "predicted_time": "", "predicted_low": "", "predicted_high": "", "error_hours": 0 }]
}
```

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
- 422 codes: `invalid_request` (body shape, e.g. no `as_of`), `missing_target`, `too_many_villages` (over 25 ids), `invalid_as_of`, `as_of_out_of_range`, `unknown_village_ids`, `village_not_at_risk`, `unknown_district`. 503 `data_unavailable` / `villages_unavailable`.

## Errors

```json
{ "error": { "code": "<machine>", "message": "<human>" } }
```
