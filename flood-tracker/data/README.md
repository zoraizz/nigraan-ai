# Flood-tracker data

Provenance for the files built for the 2022 Indus replay. Times are Asia/Karachi, `YYYY-MM-DDTHH:MM`, with no offset.

## flows_2022.csv

**Real gauge table, transcribed from FFC.** Each row is one Indus structure in Annexure-I of that day's Daily Flood Situation Report, read at 06:00. Columns are today's inflow, today's outflow, the flood category (applied to outflow), and the trend in parentheses: R rising, F falling, S stable. `NIL` in the table is stored as 0.

Source PDFs: `https://ffc.gov.pk/wp-content/uploads/2022/MM/DFSR-DD-MM-2022.pdf`, cached under `scripts/flood/raw/` (not committed). The script also tries the WordPress upload-month folder `/2022/10/` and unpadded names such as `DFSR-9-9-2022.pdf`.

| Days | What was found |
| --- | --- |
| 10 Aug–8 Sep, and 11 Sep | PDF parsed. 31 days, 7 barrages, 217 rows. |
| 9 Sep | No PDF on any tried URL. One news row: Kotri 18:00, inflow 604087, outflow 583882, High Flood, trend S. |
| 10 Sep | No PDF. One news row: Kotri 06:00, inflow 626053, outflow 600018, High Flood, trend blank. |
| 12–20 Sep | No PDF. Left as gaps. No news article stated a full Annexure-I table. |

The 9 and 10 Sep Kotri rows are from Dawn, Mohammad Hussain Khan, "New peak of high flood hits Kotri Barrage", 11 Sep 2022: <https://www.dawn.com/news/1709397>. The article quotes the FFD 06:00 report for 10 Sep and calls the 9 Sep 18:00 reading steady. The same piece gives Saturday Guddu (inflow 165161, outflow 158537) and Sukkur (185010 upstream and downstream) as normal, but with no clock time, so those two were not written.

`python scripts/flood/build_flows_2022.py --verify` checks nine outflows and prints `9/9 checkpoints within 2%`:

- 29 Aug 06:00: Kalabagh 407000, Chashma 519000, Taunsa 567000, Guddu 501000, Sukkur 531000, Kotri 337000
- 8 Sep 06:00: Kotri 584000, Guddu 186000, Sukkur 273000

News figures printed beside the parse, not as pass/fail: Taunsa 30 Aug 06:00 is 622000 in the FFC table against 622095 in the news (FFC rounds to the thousand). Sukkur 25 Aug 06:00 is 580000 against 579753. Guddu at 23 Aug 18:00 (576075) and 2 Sep 12:00 (558218) are not in this file; Annexure-I is 06:00 only. The 06:00 samples those days are Guddu 550000 and 558000.

Limits: one sample a day, so a crest between samples is invisible. FFC discharges are rounded. This is not a rating-curve archive.

## barrages.json

**Coordinates are published positions. River kilometres are derived. Thresholds are the FFC classification table.**

| Barrage | lat, lon | Source | river_km |
| --- | --- | --- | --- |
| Tarbela | 34.089722, 72.698333 | Wikipedia, Tarbela Dam, 34°05′23″N 72°41′54″E | 0 |
| Kalabagh | 32.918531, 71.521922 | Wikipedia, Jinnah Barrage (FFC's Kalabagh), 32°55′06.71″N 71°31′18.92″E | 201 |
| Chashma | 32.433889, 71.378889 | Wikipedia, Chashma Barrage, 32°26′02″N 71°22′44″E | 259 |
| Taunsa | 30.512778, 70.849167 | Wikipedia, Taunsa Barrage, 30°30′46″N 70°50′57″E | 496 |
| Guddu | 28.418611, 69.713333 | Wikipedia, Guddu Barrage, 28°25′07″N 69°42′48″E | 704 |
| Sukkur | 27.680556, 68.845278 | Wikipedia, Sukkur Barrage, 27°40′50″N 68°50′43″E | 913 |
| Kotri | 25.442222, 68.316667 | Wikipedia, Kotri Barrage, 25°26′32″N 68°19′00″E | 1393 |

`river_km` is the sum of segment lengths on the FFC flood-season travel table (<https://ffc.gov.pk/time-of-travel/>), not a centerline measurement: Tarbela to Khairabad/Attock 40 km, on to Kalabagh 161, Chashma 58, Taunsa 237, Guddu 208, Sukkur 209, Kotri 480. Mithankot–Guddu (95 km) is a gauge inside Taunsa–Guddu and is not added again.

Thresholds (low / medium / high / very high / exceptionally high, cusecs, applied to outflow) are from FFC, Flood Classification of Major Rivers (<https://ffc.gov.pk/flood-classification-of-major-rivers/>), whose unit is 100,000 cusecs. Sukkur exceptionally high is printed there as 9.0 (900000). The tracker contract says that limit was not in the older FFD bulletin and that 900000 is assumed; it is marked assumed on the Sukkur record.

## reaches.json

**Derived.** Lags are peak-outflow time differences between neighbours, matched wave by wave. Not a hydraulic model.

Taunsa is the anchor because both crests are obvious there: 22 Aug (551000) and 30 Aug (622000). Other sites take the local maximum of the same wave within five days upstream or ten days downstream. Wave 1 is the earlier crest (about 23–25 Aug once it reaches Guddu and Sukkur). Wave 2 is the later one (30 Aug–8 Sep).

| Reach | lag median (h) | min–max | attenuation | Peaks used |
| --- | --- | --- | --- | --- |
| Tarbela → Kalabagh | 24 | 24–24 | 1.125 | 18 Aug→19 Aug; 27 Aug→28 Aug |
| Kalabagh → Chashma | 12 | 0–24 | 1.287 | 19 Aug→19 Aug; 28 Aug→29 Aug |
| Chashma → Taunsa | 48 | 24–72 | 1.338 | 19 Aug→22 Aug; 29 Aug→30 Aug |
| Taunsa → Guddu | 48 | 24–72 | 0.948 | 22 Aug→23 Aug; 30 Aug→2 Sep |
| Guddu → Sukkur | 36 | 24–48 | 1.029 | 23 Aug→25 Aug; 2 Sep→3 Sep |
| Sukkur → Kotri | 120 | 120–120 | 1.043 | wave 2 only: 3 Sep→8 Sep |

Attenuation is the median of downstream peak outflow / upstream peak outflow. Above 1 means tributary gain (Kabul above Kalabagh, hill torrents and Panjnad above Taunsa and Guddu), not a pure loss.

Daily 06:00 sampling puts each crest only to about +/−12 h, so a lag can be off by about a day. That uncertainty is not folded into `lag_min_h` / `lag_max_h`; those are the two observed lags.

Kotri did not show a separate crest for wave 1; outflow was still rising. Wave 2 is 8 Sep 06:00, outflow 584000. The same 584000 was reported at 06:00 on 5, 6, 7 and 8 Sep, so that crest is only known to about +/−36 h. Dawn's 10 Sep 06:00 outflow of 600018 is about 2.7% higher and is attributed to Manchhar Lake and an MNVD breach, so it is not the routed Indus peak. Tarbela's peaks are reservoir releases, not a free-river crest.

### Leave-one-wave-out

Lags from wave 1 only. Wave 2's peak at each barrage is predicted from the **observed** wave-2 peak at the barrage immediately upstream, plus the wave-1 lag. Error is observed minus predicted (`error_hours = actual - predicted`, as in the `/replay/2022` scorecard): positive means the crest came later than predicted.

| Barrage | Predicted wave-2 peak | Observed | Error |
| --- | --- | --- | --- |
| Tarbela | anchor, not predicted | 27 Aug 06:00 | — |
| Kalabagh | 28 Aug 06:00 | 28 Aug 06:00 | 0 h |
| Chashma | 28 Aug 06:00 | 29 Aug 06:00 | +24 h |
| Taunsa | 1 Sep 06:00 | 30 Aug 06:00 | −48 h |
| Guddu | 31 Aug 06:00 | 2 Sep 06:00 | +48 h |
| Sukkur | 4 Sep 06:00 | 3 Sep 06:00 | −24 h |
| Kotri | not predicted | 8 Sep 06:00 | no wave-1 lag |

The errors are multiples of the daily sample. Wave 1 was slower than wave 2 from Chashma to Taunsa (72 h vs 24 h) and faster from Taunsa to Guddu (24 h vs 72 h). A single lag does not carry both waves inside a day.

### Replay scorecard (`GET /replay/2022`)

`error_hours = actual - predicted`; positive means the crest came later than predicted. Rows whose crest is one of the `events_used` above carry `"in_sample": true`: the lags were calibrated on those same two waves, so those errors flatter the model. The leave-one-wave-out table above is the out-of-sample check, and `scorecard_note` repeats it. Kotri's wave-2 crest is the 584000 plateau (5–8 Sep 06:00): it scores 0 h when the prediction falls inside the plateau and otherwise the hours to the nearest edge.
