"""GloFAS acquisition and adapters for the unchanged 2022 routing engine.

Daily model dates are fetched in GMT to avoid Open-Meteo shifting to the
previous UTC day's discharge for a positive timezone. The same model date
is assigned 06:00 PKT for compatibility with routing, not as an instantaneous
observation. Units are converted to cusecs then multiplied by the committed
2022 peak bias factor. Inflow equals outflow: GloFAS has no gate observations.
Only history through today's model date enters peak detection; forecasts
are kept in a separate block. A locked, three-hour cache is keyed by day and
calibration; failures never serve expired data as a fresh forecast.

What-if constructs a single rise/fall at the selected barrage and otherwise
sub-Low baselines. The existing lag and village interpolation engine routes
that event. No downstream gauge observations are invented. Peak magnitude
is assumed unchanged downstream; gates, breaches and new flood footprints
are outside the model. The 2022 village inventory is an exposure proxy.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import math
import threading
import time

import requests
import routing

URL = "https://flood-api.open-meteo.com/v1/flood"
CUSECS = 35.3147
CACHE_SECONDS = 3 * 60 * 60
PKT = timezone(timedelta(hours=5))
PROVENANCE = "modelled: GloFAS v4 river discharge via Open-Meteo, bias-scaled per barrage against FFC 2022 gauges (glofas_calibration.json); not FFC gauge readings"
ASSUMPTION = "peak carried downstream unchanged; barrage gates and breaches not modelled; villages are those flooded in 2022"
_lock = threading.Lock()
_cache = None
last_fetch = "never"


class LiveUnavailable(RuntimeError):
    """No complete, current, calibrated live data is available."""


def today_clock():
    return datetime.now(PKT).replace(hour=6, minute=0, second=0, microsecond=0, tzinfo=None)


def load_calibration(path, barrages):
    try:
        calibration = json.loads(path.read_text(encoding="utf-8"))
        for b in barrages:
            row = calibration[b["name"]]
            for key in ("lat", "lon", "scale", "corr", "glofas_peak_cusecs", "ffc_peak_cusecs"):
                if isinstance(row[key], bool) or not isinstance(row[key], (int, float)) or not math.isfinite(row[key]):
                    raise ValueError(f"invalid {key}")
            if not (-90 <= row["lat"] <= 90 and -180 <= row["lon"] <= 180 and -1 <= row["corr"] <= 1):
                raise ValueError("invalid cell/correlation")
            if not isinstance(row.get("calibrated"), bool):
                raise ValueError("missing calibrated flag")
            if min(row["scale"], row["glofas_peak_cusecs"], row["ffc_peak_cusecs"]) <= 0:
                raise ValueError("non-positive calibration")
        return calibration
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise LiveUnavailable(f"Calibration unavailable: {exc}") from exc


def calibration_warnings(calibration):
    return [f"{name}: weak cell calibration (scale {row['scale']:.2f}, correlation {row['corr']:.3f}); interpret forecast cautiously"
            for name, row in calibration.items() if not name.startswith("_") and not row["calibrated"]]


def fetch_live(calibration):
    global _cache, last_fetch
    with _lock:
        try:
            if not calibration:
                raise LiveUnavailable("Calibration not loaded")
            today = today_clock().date()
            key = (today.isoformat(), json.dumps(calibration, sort_keys=True))
            if _cache and _cache[0] == key and time.monotonic() - _cache[1] < CACHE_SECONDS:
                return deepcopy(_cache[2])
            names = [name for name in calibration if not name.startswith("_")]
            response = requests.get(URL, params={
                "latitude": ",".join(str(calibration[n]["lat"]) for n in names),
                "longitude": ",".join(str(calibration[n]["lon"]) for n in names),
                "daily": "river_discharge", "past_days": 30, "forecast_days": 30,
                "cell_selection": "nearest", "timezone": "GMT",
            }, timeout=15)
            response.raise_for_status()
            bodies = response.json()
            if not isinstance(bodies, list) or len(bodies) != len(names):
                raise ValueError("expected one discharge series per barrage")
            expected = [(today + timedelta(days=i)).isoformat() for i in range(-30, 30)]
            series = {}
            for name, body in zip(names, bodies):
                daily = body["daily"]
                if daily["time"] != expected or len(daily["river_discharge"]) != len(expected):
                    raise ValueError(f"{name}: incomplete or stale daily series")
                rows = []
                for day, value in zip(expected, daily["river_discharge"]):
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                        raise ValueError(f"{name}: invalid/missing discharge on {day}")
                    q = value * CUSECS * calibration[name]["scale"]
                    if not math.isfinite(q):
                        raise ValueError(f"{name}: scaled discharge is not finite")
                    rows.append({"date": day, "cusecs": round(q, 2)})
                series[name] = rows
            _cache = (key, time.monotonic(), series)
            last_fetch = "ok"
            return deepcopy(series)
        except Exception as exc:
            last_fetch = "failed"
            if isinstance(exc, LiveUnavailable):
                raise
            raise LiveUnavailable(f"GloFAS forecast unavailable: {exc}") from exc


def forecast_rows(barrages, series, today):
    """First crossing = first forecast day at/above Low, with that day's category.

    Today is included. A barrage already above Low crosses on today. Outlook
    sorts on this date, then barrage order; peak date is separate information.
    """
    rows = []
    for b in barrages:
        days = [r for r in series[b["name"]] if r["date"] >= today]
        if not days or days[0]["date"] != today:
            raise LiveUnavailable(f"{b['name']}: today's discharge missing")
        peak = max(days, key=lambda r: r["cusecs"])
        crossing = next((r for r in days if r["cusecs"] >= b["thresholds"]["low"]), None)
        rows.append({"name": b["name"], "today_cusecs": days[0]["cusecs"],
                     "today_category": routing.category(b, days[0]["cusecs"]), "series": days,
                     "forecast_peak_cusecs": peak["cusecs"], "forecast_peak_date": peak["date"],
                     "forecast_peak_category": routing.category(b, peak["cusecs"]),
                     "low_threshold_cusecs": b["thresholds"]["low"],
                     "first_crossing": {"category": routing.category(b, crossing["cusecs"]), "date": crossing["date"]} if crossing else None})
    outlook = sorted((r for r in rows if r["first_crossing"]), key=lambda r: r["first_crossing"]["date"])
    return rows, outlook


def live_situation(data, calibration):
    series = fetch_live(calibration)
    clock = today_clock()
    readings = {name: [routing.Reading(routing.parse_time(r["date"] + "T06:00"), r["cusecs"], r["cusecs"])
                       for r in rows if r["date"] <= clock.date().isoformat()] for name, rows in series.items()}
    body = routing.situation(replace(data, readings=readings), clock, mode="live")
    body["data_provenance"]["flows"] = PROVENANCE
    body["data_provenance"]["villages"] += "; exposure proxy: villages flooded in 2022, not a current inundation map"
    body["forecast"], body["outlook"] = forecast_rows(data.barrages, series, clock.date().isoformat())
    for row in body["forecast"]:
        row["calibrated"] = calibration[row["name"]]["calibrated"]
        row["confidence"] = "bias-scaled" if row["calibrated"] else "low confidence"
    body["forecast_days"] = len(body["forecast"][0]["series"])
    body["calibration_warnings"] = calibration_warnings(calibration)
    return body


def what_if(data, barrage, peak_cusecs, peak_time=None):
    chosen = next((b for b in data.barrages if b["name"] == barrage), None)
    if chosen is None:
        raise ValueError("unknown barrage")
    if not math.isfinite(peak_cusecs) or not 0 < peak_cusecs <= 2000000:
        raise ValueError("peak_cusecs must be > 0 and <= 2000000")
    peak = routing.parse_time(peak_time) if peak_time else today_clock()
    readings = {}
    for b in data.barrages:
        base = .6 * b["thresholds"]["low"]
        # A sub-baseline hypothetical peak still must be the selected maximum.
        if b == chosen:
            base = min(base, .6 * peak_cusecs)
        rows = []
        for day in range(-6, 2):
            q = base
            if b == chosen and -2 <= day <= 0:
                q = base + (peak_cusecs - base) * (day + 3) / 3
            elif b == chosen and day == 1:
                q = .9 * peak_cusecs
            rows.append(routing.Reading(peak + timedelta(days=day), q, q))
        readings[b["name"]] = rows
    body = routing.situation(replace(data, readings=readings), peak + timedelta(days=1), mode="what_if")
    cat = routing.category(chosen, peak_cusecs)
    body["scenario"] = dict(barrage=barrage, peak_cusecs=peak_cusecs, peak_category=cat,
                            peak_time=routing.fmt_time(peak), assumption=ASSUMPTION)
    body["data_provenance"]["flows"] = "synthetic what-if hydrograph; not gauge readings or a forecast"
    body["data_provenance"]["etas"] += "; " + ASSUMPTION
    if routing.category_rank(cat) < routing.category_rank("Medium Flood"):
        body["at_risk_villages"] = []
        body["district_eta_hours"] = {}
        body["note"] = "Below Medium Flood: villages not listed"
    return body
