# GloFAS source verification

Phase 0, checked 2026-10-21: https://open-meteo.com/en/docs/flood-api

Sukkur (27.69, 68.85), nearest cell (27.675003, 68.875015): HTTP 200.
Today: 3395.25 m3/s = 119902.235175 cusecs (multiply by 35.3147).
30 past days and 30 forecast days including today returned 60 non-null days,
2026-09-21 through 2026-11-19. Historical 2022-08-10 through 2022-09-11
returned all 33 days.

The documentation allows forecast_days 0..210 (default 92); daily GloFAS
forecasts cover 30 days and seasonal forecasts extend further. We use 30.
The docs do not specify a past_days maximum; the deployed endpoint rejected
999999 with an allowed range of 0..15634 on the check date. We use 30.
cell_selection supports nearest (explicitly used), land and sea. The docs
warn that the nearest cell can miss the river, motivating the calibration grid.
Use timezone=GMT to preserve model dates: positive offsets can select the
previous UTC day. Assigning 06:00 PKT is a routing convention for daily
model values, not a claim that these are instantaneous gauge observations.

No API key is used. The free endpoint is for non-commercial use.
