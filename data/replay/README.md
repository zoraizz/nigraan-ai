# 2022 flood replay: Risk Flag backtest

`backtest_2022.json` replays Risk Flag's rule-based scorer over the 2022 monsoon, with 2021 as a control year, and compares the flags with documented 2022 impacts. It is precomputed static data for the replay screen. Regenerate it with:

```
python scripts/build_replay_backtest.py            # reuses data/replay/raw/ if present
python scripts/build_replay_backtest.py --refetch  # re-downloads (64 Open-Meteo requests, throttled)
```

The script uses the Python standard library only. It does not import risk-flag and never calls Gemini.

## Short answer to "is this predictive, or tuned to 2022?"

- **Nothing was tuned.** The scorer is `score_risk_fallback` from `risk-flag/main.py` at commit `839f21c`, extracted with `ast` and run unchanged. The script probes its thresholds at the boundaries (40 mm and 100 mm over 3 days) and refuses to run if they have changed. No 2022 data was used to set anything.
- **The main run is a real forecast test.** For each as-of date it uses the 3-day rainfall forecast issued on that date (JMA GSM via Open-Meteo's Previous Runs API), not the rain that actually fell.
- **The result is weak.** The scorer separates 2022 from 2021 clearly. But in the 10 days before each documented impact it raised `high` for only 2 of 9 flood districts; the rest were at `medium`. Seven of the 16 districts always get the same level from this scorer, so they can't be evaluated at all.
- **One leak can't be undone here.** The 16 districts and their hazard labels were chosen in 2026, with knowledge of 2022. The flood list overlaps the 2022 footprint, so this backtest says nothing about whether the product picks the right districts.

## Method

### Scorer (unchanged)

| Hazard in `DISTRICTS` | Rule | Rainfall input used for the level |
|---|---|---|
| flood | `high` if 3-day rainfall > 100 mm, `medium` if > 40 mm, else `low` (also `low` if rainfall missing) | 3-day sum |
| glof / avalanche / landslide | always `medium` | none |
| drought | always `low` | none (30/90-day totals only appear in the reason text) |

In production, Gemini is tried first and this scorer is only the fallback. This backtest evaluates the fallback only.

### As-of dates and features

- Window: 15 Jun to 10 Sep, in both 2022 and 2021. As-of dates fall every 3 days (30 per year). Because each 3-day signal covers days D, D+1 and D+2, consecutive as-of dates tile the window with no gaps or overlap.
- Flood districts get one 3-day signal per as-of date D, in local (Asia/Karachi) days, matching production's `forecast_days=3` (today plus two days).
- Drought districts get the 30- and 90-day totals, D-30..D and D-90..D, from the Historical Weather API. This mirrors production's archive call with `past_days=30/90`, which returns today plus the previous N days. Missing days are skipped, as production does. Production's "today" is a partial day; here it's a complete day. That doesn't matter, because these totals never change the level.

### Rainfall sources (two runs, both reported)

The source choice was made on coverage and method before any result was computed.

| Run | `rainfall_source` | 3-day signal for as-of date D |
|---|---|---|
| `forecast` (primary) | forecast (JMA GSM via Open-Meteo Previous Runs API, issued on the as-of date) | Day D from the stitched short-lead series (`precipitation`); D+1 from `precipitation_previous_day1`; D+2 from `precipitation_previous_day2`. All three come from model runs initialised on or around D. |
| `hindsight` | observed (hindsight) | Observed daily totals for D, D+1 and D+2 from the Historical Weather API (default model; for these years it returned the same values as `ecmwf_ifs`, the 9 km ECMWF IFS analysis). This is a perfect-forecast upper bound and uses data from after D. |

Why not production's exact forecast?

- Production calls `api.open-meteo.com/v1/forecast` with the default `best_match` blend. The Previous Runs API returns nulls for `best_match` (and for GFS, ECMWF and ICON) in 2022.
- The Historical Forecast API covers 2022, but it stitches together only the first few hours of each run, so it isn't a 3-day forecast. For 2022 its default model returns exactly the ECMWF IFS archive values.
- JMA GSM was the only model found with real lead-time archives for both years.

JMA GSM has a ~55 km grid, so the 9 flood districts fall into only 7 distinct grid cells: Khairpur and Sukkur share one, and Jacobabad and Jaffarabad share another. The hindsight data puts them in 9 distinct cells.

### Ground truth

`ground_truth_2022.json` holds one entry per district, with source URLs. Each entry gives:

- whether the district was affected;
- the strength of the evidence;
- `impact_reference_date`, the earliest date by which a source documents impact. This is an upper bound on onset, not the onset itself;
- the calamity-hit notification date, where one was confirmed;
- the hazard actually observed.

Sources include provincial calamity notifications reported by Dawn, Geo, The News and Express Tribune; OCHA situation reports and the 13 Sep 2022 response snapshot; NDMA SitRep 085; and UNDP's GLOF-II flood report (dated GLOF events by district). Each source records how it was checked: page read directly, search-engine excerpt, or Wikipedia citation. "Unknown" is used wherever a named source couldn't be found.

### Leakage check on the static hazard context

`HAZARD_CONTEXT` contains no reference to 2022 or any outcome. The only post-2021 strings are two source titles ("NDMA GLOF/Avalanche Guidelines 2026"). The rule-based scorer uses `HAZARD_CONTEXT` only in its reason text. The script re-runs every case with `HAZARD_CONTEXT` replaced by empty entries and confirms that no risk level changes, so nothing was excluded. (`HAZARD_CONTEXT` would reach Gemini's prompt, but Gemini isn't part of this test.)

## Results

The **run-up** column shows the highest level the scorer gave on as-of dates in the 10 days up to and including the impact reference date. I chose the 10-day window after looking at the timelines; the JSON has every as-of date, so you can check other windows. The **first high** column is the first `high` anywhere in the 2022 window. For the Sindh districts in the forecast run, that first high falls on the early-July rain spell, so it isn't a lead time for the August impact.

Share columns give the proportion of the 30 as-of dates flagged medium or high, 2022 / 2021.

### Flood districts (the only ones the scorer can discriminate)

| District | Impact documented by | Forecast: first high | Forecast: run-up max (3-day mm) | Forecast: share medium/high, 2022 / 2021 | Hindsight: first high | Hindsight: run-up max (3-day mm) | Hindsight: share medium/high, 2022 / 2021 |
|---|---|---|---|---|---|---|---|
| Dadu | 2022-08-21 | 07-06 | high (116 on 08-11; 115 on 08-17; 113 on 08-20) | 43% / 7% | 08-17 | high (350 on 08-17) | 27% / 0% |
| Khairpur | 2022-08-21 | 07-06 | medium (86) | 50% / 7% | 08-17 | high (132 on 08-17) | 23% / 0% |
| Sukkur | 2022-08-21 | 07-06 | medium (86) | 50% / 7% | never | medium (76) | 23% / 0% |
| Larkana | 2022-08-21 | 07-06 | high (114 on 08-11; 103 on 08-17; 222 on 08-20) | 50% / 7% | 08-17 | high (159 on 08-17) | 30% / 0% |
| Jacobabad | 2022-08-21 | 07-06 | medium (98) | 50% / 10% | 08-17 | high (155 on 08-17) | 27% / 0% |
| Jaffarabad | 2022-08-16 | 07-06 | medium (98) | 50% / 10% | 08-17 (after impact) | medium (53) | 30% / 0% |
| D.I. Khan | 2022-08-22 | 08-23 (after impact) | medium (60) | 23% / **30%** | 08-17 | high (142 on 08-17) | 13% / 0% |
| D.G. Khan | 2022-07-25 | never | medium (66) | 20% / 7% | never | medium (89) | 20% / 0% |
| Rajanpur | 2022-07-18 | 07-24 (after impact) | medium (74) | 43% / 0% | never | medium (61) | 20% / 0% |

Summary across the 9 flood districts:

| | Forecast (primary) | Hindsight (upper bound) |
|---|---|---|
| High in the 10-day run-up | 2 of 9 (Dadu, Larkana) | 5 of 9 (Dadu, Khairpur, Larkana, Jacobabad, D.I. Khan) |
| Medium only in the run-up | 7 of 9 | 4 of 9 |
| Never high in 2022 | D.G. Khan | Sukkur, D.G. Khan, Rajanpur |
| First high after the documented impact | D.I. Khan, Rajanpur | Jaffarabad |
| Mean share flagged high, 2022 / 2021 | 7.4% / 0.4% | 3.3% / 0% |
| Mean share flagged medium or high, 2022 / 2021 | 42% / 9% | 24% / 0% |
| High flags in 2021 (candidate false alarms) | 1 (D.I. Khan, as-of 2021-07-18, 103 mm) | 0 |

### Districts the scorer cannot discriminate

| District | Product hazard | Scorer output, both years | What happened in 2022 |
|---|---|---|---|
| Chitral | GLOF/avalanche | always medium | GLOFs from 18 Jun; calamity-hit 22 Aug |
| Hunza | GLOF/avalanche | always medium | Hassanabad GLOF with damage 30 Jun (plus 7 May, before the window) |
| Skardu | GLOF/avalanche | always medium | GLOFs from 5 Jul; 162 houses damaged in Bashoo |
| Mansehra | landslide | always medium | flash floods 30 Jul; 8 killed near Balakot (reported 26 Aug) |
| Battagram | landslide | always medium | flash flooding 30 Jul (single weak report) |
| Chagai | drought | always low | flood-response food aid by 26 Aug (weak evidence) |
| Tharparkar | drought | always low | flooded; calamity-hit on OCHA's 13 Sep snapshot |

Chagai and Tharparkar are structural misses: they flooded in 2022, and a drought-labelled district can never be raised above low. The static-medium districts did suffer GLOFs and flash floods, but the scorer can't express anything other than medium for them, so those events count as neither hits nor misses.

## Reading the results honestly

1. **Clear year contrast, weak event timing.** In the forecast run, flood districts were flagged medium or high on 42% of 2022 dates against 9% in 2021. Even so, in the worst flood year on record, the 100 mm `high` gate fired before the documented impact in only 2 of 9 districts. Most of 2022 sat at `medium`. On these numbers, `medium` means "wetter than usual", not "flood imminent".
2. **The hindsight run's "warnings" are mostly concurrent.** Its five run-up highs all come from the 17–19 Aug window, which is inside the 16–21 Aug Sindh rain spell. So the result shows the threshold can catch the peak when the rainfall is known, not that it gives warning in advance.
3. **The outcome depends on the dataset.** The coarse JMA forecast flagged more highs than the 9 km ECMWF analysis (7.4% vs 3.3% of dates). For example, Sukkur is never high in hindsight but has a high in the forecast run (its grid cell is shared with Khairpur). A threshold sitting this close to the top of the gridded rainfall distribution makes per-district results fragile.
4. **Hill-torrent and riverine flooding is out of reach.** D.G. Khan, Rajanpur and D.I. Khan flood from rain on the Koh-e-Suleman range west of the district headquarters, and Sindh's riverine inundation comes from rain far upstream. A 3-day point total at the district HQ can't see either. D.G. Khan was never high in either run, and D.I. Khan was flagged more often in 2021 than in 2022 in the forecast run.
5. **False alarms are barely measurable.** Every flood district in scope was affected in 2022, so false alarms can't be counted from 2022 alone. 2021 shows one high flag and a 9% medium-or-high rate in the forecast run. 2021 impacts were not researched, so these are candidate false alarms, not confirmed ones.
6. **The sample is small.** 9 informative districts × 30 dates, in two grid-cell pairs that share forecasts. No confidence intervals are given because they would be very wide.

## Limitations

- Only the rule-based fallback is tested. The production path (Gemini with the hazard context) is not.
- The forecast model is JMA GSM at about 55 km, not production's `best_match`. Run timing is approximate: "previous day N" means the run issued roughly N days earlier, to within the 6-hour run cycle. Day D itself uses the latest short-lead runs during D, so it peeks a few hours ahead.
- The hindsight run treats a model analysis as observed rainfall. It is not rain-gauge data, and analyses tend to smooth convective extremes.
- Rainfall is taken at a single district-HQ coordinate. Several districts collapse into one JMA grid cell.
- Impact reference dates are documented-by upper bounds drawn from a mix of news and humanitarian reports, several read from search-engine excerpts. Gilgit-Baltistan's and KP's named calamity lists were not found, so `calamity_declared` is `unknown` for Hunza, Skardu, Mansehra, Battagram, Chagai and Tharparkar. The Battagram and Chagai impacts rest on weak evidence.
- The 2021 control has no ground truth of its own.
- District and hazard selection happened after 2022 (see the short answer above).

## File layout (`backtest_2022.json`)

- `metadata`: rainfall sources and exact signal definitions; scorer file, commit, function hash and probe-verified thresholds; leakage-check results; grid cells per run; `generated_at`; evaluation notes.
- `as_of_dates["2022" | "2021"]`: the 30 as-of dates per year.
- `districts`: name, province, hazard types and coordinates, as in risk-flag.
- `ground_truth`: a copy of `ground_truth_2022.json` entries.
- `runs["forecast" | "hindsight"][year][district]`: arrays aligned with `as_of_dates`, holding `risk_level` plus `rainfall_3d_mm` (flood districts) or `rainfall_30d_mm`/`rainfall_90d_mm` (drought districts). Static districts carry only `risk_level`.
- `evaluation["forecast" | "hindsight"]`: `per_district` (first high, run-up dates and levels, shares by year, 2021 high dates, outcome) and `summary`.

Raw Open-Meteo responses are cached in `data/replay/raw/`, which is gitignored.
