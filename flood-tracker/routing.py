r"""
Pure routing logic for the River Flood Tracker: categories, peak detection,
peak-to-peak ETAs down the Indus, village ETAs and the replay scorecard.

No IO except load_data(), which takes explicit file paths. Every other
function takes plain data and returns plain data, so the same code serves
the API (main.py), the replay and the tests.

Barrages, upstream to downstream (barrages.json `order` 1..7):
    Tarbela -> Kalabagh -> Chashma -> Taunsa -> Guddu -> Sukkur -> Kotri

Times
-----
All times are Asia/Karachi local wall-clock, "YYYY-MM-DDTHH:MM", no offset
(CONTRACT.md). They are handled as naive datetimes; the whole series is in
one zone with no DST, so arithmetic on naive values is exact.

Category (applied to OUTFLOW)
-----------------------------
    category = the highest of Low / Medium / High / Very High / Exceptionally
               High whose threshold <= outflow, else "Normal".
A reading exactly on a threshold is in the higher category. Thresholds come
from barrages.json (FFC classification table). Sukkur's exceptionally_high
(900000) is an assumed figure and barrages.json marks it as such.

Trend
-----
    stable   if |q - q_prev| <= 2% of q_prev
    rising   if q > q_prev (beyond 2%)
    falling  if q < q_prev (beyond 2%)
q_prev is the previous reading at the same barrage. The first reading is
"stable" (there is nothing to compare against). A previous reading of 0
(FFC "NIL") makes any positive reading "rising".

Peak detection (per barrage, NO LOOK-AHEAD)
-------------------------------------------
detect_events() walks a barrage's readings in time order and stops at
as_of, so nothing after as_of can influence a status. An "event" is one
wave's passage at one barrage:

    * An event starts at the first reading >= Low threshold.
    * It ends when outflow drops below Low. The next reading >= Low starts a
      new event.
    * It also ends when, after the event's max, outflow has dipped at least
      10% below that max (trough <= 0.9 * max) and then rises again (a
      "rising" trend reading). That rising reading starts the new event.
    * The event's peak is its max outflow. On ties the LATER reading wins,
      so a plateau's peak_time is the last day of the plateau seen so far
      (Kotri sat at 584000 for four 06:00 readings in 2022).

Status of an event:
    forming  outflow >= Low and the trend was "rising" on the latest two
             readings in a row. Sticky: stays forming while the flow holds
             near the max (a crest plateau) until it is confirmed passed.
    passed   the latest reading is at least 2% below the event max.
             peak_time is the time of that max. confirmed_time is the
             reading that first showed the drop. Sticky: stays passed
             unless a later reading exceeds the max (then the earlier "peak"
             was not the crest, and the event is forming again).
    none     neither yet (e.g. a single rise). Not reported.
A passed peak can therefore never be reported before its confirming
reading, and a forming peak never before two rising readings.

Linking events into waves (across barrages)
-------------------------------------------
Each barrage sees its own events; a "wave" is the same crest travelling
down the river. Event e at barrage j joins the wave of event f at an
upstream barrage i when e's peak time falls inside f's routed window:

    window = [f.peak + sum(lag_min_h) - 24h,  f.peak + sum(lag_max_h) + 24h]

The 24 h slack is the daily 06:00 sampling: each crest time is only known
to about +/-12 h at each end (reaches.json note). The nearest upstream
barrage is tried first, then the next one up (a wave can be merged into a
neighbouring wave at one barrage, e.g. Kalabagh and Sukkur in 2022, whose
dips between the two crests were under 10%). Among candidates, the one
closest to the median ETA wins. A wave joins at most one event per barrage.
An event with no upstream match starts a new wave (its "root").

Linking uses the peak times known at as_of only, so a forming event's wave
can change as its max moves; passed events are stable. Wave ids are
"indus-<year>-w<n>", numbered by the root event's peak time (ties by
barrage order).

ETAs (per wave)
---------------
L = the most downstream barrage where the wave's peak has passed (or, if it
has passed nowhere yet, the most downstream barrage where it is forming;
that ETA is provisional because the crest has not been seen yet).
For every barrage j downstream of L:

    eta      = peak_time(L) + sum(lag_median_h, L..j)
    eta_low  = peak_time(L) + sum(lag_min_h,    L..j)
    eta_high = peak_time(L) + sum(lag_max_h,    L..j)
    status   = "estimated", hours_from_now = eta - as_of

For every barrage j upstream of L (inclusive of L) where the wave has a
passed peak, except the first one in the chain, the row is "arrived": the
estimate is the one made from the previous passed barrage in the chain,
observed_time = j's own peak_time, hours_from_now = observed_time - as_of
(negative). So once a barrage records its own peak for a wave, "arrived"
replaces the estimate for that barrage, and estimates further down are
re-issued from it.

Live waves
----------
A wave is shown while it is forming somewhere, or while the window at the
next barrage below L is still open (as_of <= eta_high + 24 h), or for
72 h after its peak passed the last barrage (Kotri). A wave that does not
show up at the next barrage by then is treated as having dissipated (a
small blip at one barrage, a reservoir release) and is dropped.

Village ETAs
------------
Villages and barrages must sit on one kilometre scale. villages.json
river_km is measured along the indus.geojson centreline (1,468 km from
Tarbela to Kotri), while barrages.json river_km is the FFC travel-table
distance (Kotri 1,393). The two differ by up to ~140 km, enough to put a
Kashmore village (between Guddu and Sukkur) below Sukkur. So each barrage's
km here is its coordinate projected onto the same centreline
(barrage_positions); barrages.json river_km is used only when the
centreline (or its per-vertex river_km) is missing, and data_provenance
says so.

For each live wave, the arrival time at each barrage at or below L is known
(L: its observed peak_time, low = high = peak_time; below L: eta / eta_low /
eta_high). A village at river_km between barrages a and b (a.km <= km <
b.km) gets
    t(v) = t(a) + (km - a.km) / (b.km - a.km) * (t(b) - t(a))
for each of eta, eta_low and eta_high. Below the last barrage, the last
reach's hours-per-km rate (lag / reach length) is extended. A wave threatens
a village while it has not passed it:
    * the village's river_km is downstream of L (a barrage at or below the
      village that confirmed the crest means it has gone by), and
    * eta_high >= as_of. Once the whole window is behind us the wave is
      taken to have passed the village, even if no barrage below it has
      confirmed the crest yet (a stalled or attenuated crest, or a gap in
      the readings, must not keep a village "at risk" for days).
hours_to_arrival = eta - as_of. It is negative only inside the window
(eta < as_of <= eta_high): the crest is due now. If several waves threaten
a village, the earliest eta among those still threatening it is reported,
so a wave that has passed never masks the next one. Villages are sorted by
eta, then population descending. district_eta_hours = the minimum
hours_to_arrival per district over the villages on the list, so it never
carries an arrival from a wave that has already passed.

All ETAs are MODELLED (summed historical lags from reaches.json, not a
hydraulic model) and data_provenance says so in every response.

Replay scorecard
----------------
For each barrage j and each wave with a passed peak at j over the whole
series (actual_peak_time = T), the prediction is rebuilt from upstream
readings strictly before T only (j's own readings are not used): events are
re-detected on that truncated data, e's peak is matched to an upstream
reported (forming or passed) peak with the same window rule, and
    predicted_time = f.peak + sum(lag_median_h), low/high from min/max.
    error_hours    = actual_peak_time - predicted_time
Positive error = the crest came later than predicted. Barrages with no
upstream peak to predict from (Tarbela, or a wave first seen at j) have no
scorecard row.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

TIME_FMT = "%Y-%m-%dT%H:%M"

CATEGORIES = [
    "Normal",
    "Low Flood",
    "Medium Flood",
    "High Flood",
    "Very High Flood",
    "Exceptionally High Flood",
]
THRESHOLD_KEYS = ["low", "medium", "high", "very_high", "exceptionally_high"]

TREND_TOLERANCE = 0.02   # stable within 2% of the previous reading
PASSED_DROP = 0.02       # passed once the latest reading is >= 2% below max
NEW_WAVE_DIP = 0.10      # dip >= 10% below max then rise = new wave
MATCH_SLACK_H = 24       # +/-12 h sampling uncertainty at each end of a reach
LIVE_GRACE_H = 24        # keep a wave this long past the next barrage's eta_high
FINAL_DISPLAY_H = 72     # keep a wave this long after it passes the last barrage

REPLAY_STEP_HOUR = 6     # replay steps are daily at 06:00 (FFC Annexure-I time)


class AsOfOutOfRange(ValueError):
    """as_of is before the first or after the last reading in the data."""


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Reading:
    time: datetime
    inflow: float
    outflow: float
    source_url: str = ""


@dataclass
class Event:
    """One wave's passage at one barrage, as known at as_of."""

    barrage: str
    order: int
    start_time: datetime
    peak_time: datetime
    peak_outflow: float
    status: str = "none"                    # none | forming | passed
    confirmed_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    # Set by link_waves():
    root: Optional["Event"] = field(default=None, repr=False)
    upstream: Optional["Event"] = field(default=None, repr=False)


@dataclass
class FloodData:
    barrages: list                          # barrages.json records, by order
    reaches: list                           # reaches.json records, by order
    readings: dict                          # barrage name -> [Reading] by time
    villages: Optional[list] = None         # villages.json, or None if absent
    river_coords: Optional[list] = None     # [[lat, lon], ...] or None
    sources: dict = field(default_factory=dict)  # file name -> present?
    river_km_line: Optional[list] = None    # km of each river_coords vertex, or None


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
def parse_time(value: str) -> datetime:
    """Parse "YYYY-MM-DDTHH:MM" (seconds tolerated and dropped)."""
    value = value.strip()
    try:
        return datetime.strptime(value[:16], TIME_FMT)
    except ValueError as exc:
        raise ValueError(
            f"time {value!r} is not in YYYY-MM-DDTHH:MM format"
        ) from exc


def fmt_time(dt: datetime) -> str:
    """Format to the minute, rounding half-minutes up."""
    if dt.second or dt.microsecond:
        dt = dt + timedelta(seconds=30)
    return dt.strftime(TIME_FMT)


def _hours(delta: timedelta) -> float:
    return round(delta.total_seconds() / 3600.0, 1)


# ---------------------------------------------------------------------------
# Category and trend
# ---------------------------------------------------------------------------
def category(barrage: dict, outflow: float) -> str:
    """Flood category of an outflow at a barrage (thresholds inclusive)."""
    thresholds = barrage["thresholds"]
    result = CATEGORIES[0]
    for key, name in zip(THRESHOLD_KEYS, CATEGORIES[1:]):
        if outflow >= thresholds[key]:
            result = name
    return result


def category_rank(name: str) -> int:
    return CATEGORIES.index(name)


def trend(previous: Optional[float], current: float) -> str:
    """rising | falling | stable (stable within 2% of the previous reading)."""
    if previous is None:
        return "stable"
    if previous <= 0:
        return "rising" if current > 0 else "stable"
    if abs(current - previous) <= TREND_TOLERANCE * previous:
        return "stable"
    return "rising" if current > previous else "falling"


# ---------------------------------------------------------------------------
# Peak detection
# ---------------------------------------------------------------------------
def detect_events(
    readings: list,
    barrage: dict,
    as_of: Optional[datetime] = None,
) -> list:
    """Events at one barrage using only readings at or before as_of."""
    low = barrage["thresholds"]["low"]
    events: list = []
    cur: Optional[Event] = None
    trough: Optional[float] = None
    prev_q: Optional[float] = None
    prev_trend: Optional[str] = None

    for r in readings:
        if as_of is not None and r.time > as_of:
            break
        q = r.outflow
        tr = trend(prev_q, q)
        rising_twice = tr == "rising" and prev_trend == "rising"

        if q < low:
            if cur is not None:
                if q <= (1 - PASSED_DROP) * cur.peak_outflow and cur.status != "passed":
                    cur.status = "passed"
                    cur.confirmed_time = r.time
                cur.end_time = r.time
            cur, trough = None, None
        elif cur is None or (
            trough is not None
            and trough <= (1 - NEW_WAVE_DIP) * cur.peak_outflow
            and tr == "rising"
        ):
            if cur is not None:
                cur.end_time = r.time
            cur = Event(
                barrage=barrage["name"],
                order=barrage["order"],
                start_time=r.time,
                peak_time=r.time,
                peak_outflow=q,
                status="forming" if rising_twice else "none",
            )
            events.append(cur)
            trough = None
        elif q > cur.peak_outflow or (q == cur.peak_outflow and cur.status != "passed"):
            cur.peak_time = r.time
            cur.peak_outflow = q
            trough = None
            if rising_twice or cur.status in ("forming", "passed"):
                cur.status = "forming"
            cur.confirmed_time = None
        else:
            trough = q if trough is None else min(trough, q)
            if q <= (1 - PASSED_DROP) * cur.peak_outflow:
                if cur.status != "passed":
                    cur.status = "passed"
                    cur.confirmed_time = r.time
            elif rising_twice and cur.status != "passed":
                cur.status = "forming"

        prev_q, prev_trend = q, tr

    return events


# ---------------------------------------------------------------------------
# Lags
# ---------------------------------------------------------------------------
def _lag_sums(reaches: list, i_order: int, j_order: int) -> tuple:
    """(median, min, max) hours summed over reaches from order i to j (i < j).

    reaches[k] is the reach from barrage order k+1 to k+2.
    """
    seg = reaches[i_order - 1 : j_order - 1]
    return (
        sum(r["lag_median_h"] for r in seg),
        sum(r["lag_min_h"] for r in seg),
        sum(r["lag_max_h"] for r in seg),
    )


def _window(reaches: list, f: Event, j_order: int) -> tuple:
    med, lo, hi = _lag_sums(reaches, f.order, j_order)
    slack = timedelta(hours=MATCH_SLACK_H)
    return (
        f.peak_time + timedelta(hours=lo) - slack,
        f.peak_time + timedelta(hours=hi) + slack,
        f.peak_time + timedelta(hours=med),
    )


def _best_upstream(
    events_by_order: dict,
    reaches: list,
    j_order: int,
    peak_time: datetime,
    excluded_roots: set,
    reported_only: bool = False,
) -> Optional[Event]:
    """Closest-to-median upstream event whose window holds peak_time."""
    for i_order in range(j_order - 1, 0, -1):
        best = None
        for f in events_by_order.get(i_order, []):
            if reported_only and f.status not in ("forming", "passed"):
                continue
            root = f.root if f.root is not None else f
            if id(root) in excluded_roots:
                continue
            lo, hi, med = _window(reaches, f, j_order)
            if lo <= peak_time <= hi:
                dist = abs((peak_time - med).total_seconds())
                if best is None or dist < best[0]:
                    best = (dist, f)
        if best is not None:
            return best[1]
    return None


def link_waves(events_by_order: dict, reaches: list) -> dict:
    """Assign each event a root (wave) and return {id(root): wave_id}."""
    for j_order in sorted(events_by_order):
        claimed: set = set()
        for e in sorted(events_by_order[j_order], key=lambda ev: ev.start_time):
            f = _best_upstream(events_by_order, reaches, j_order, e.peak_time, claimed)
            e.upstream = f
            e.root = (f.root if f.root is not None else f) if f is not None else e
            claimed.add(id(e.root))

    roots = [e for evs in events_by_order.values() for e in evs if e.root is e]
    roots.sort(key=lambda r: (r.peak_time, r.order))
    return {
        id(r): f"indus-{r.start_time.year}-w{n}" for n, r in enumerate(roots, start=1)
    }


# ---------------------------------------------------------------------------
# Per-wave ETAs
# ---------------------------------------------------------------------------
def _eta_triplet(reaches: list, f: Event, j_order: int) -> tuple:
    med, lo, hi = _lag_sums(reaches, f.order, j_order)
    return (
        f.peak_time + timedelta(hours=med),
        f.peak_time + timedelta(hours=lo),
        f.peak_time + timedelta(hours=hi),
    )


@dataclass
class _Wave:
    wave_id: str
    events: dict            # order -> Event
    leading: Optional[Event]
    eta_rows: list          # internal rows with datetimes
    live: bool


def _build_wave(wave_id: str, events: dict, reaches: list, n_barrages: int,
                as_of: datetime) -> _Wave:
    passed = sorted(o for o, e in events.items() if e.status == "passed")
    forming = sorted(o for o, e in events.items() if e.status == "forming")
    if passed:
        leading = events[passed[-1]]
    elif forming:
        leading = events[forming[-1]]
    else:
        return _Wave(wave_id, events, None, [], False)

    rows = []
    for prev_o, j in zip(passed, passed[1:]):
        eta, lo, hi = _eta_triplet(reaches, events[prev_o], j)
        rows.append({
            "from": events[prev_o], "barrage_order": j, "status": "arrived",
            "eta": eta, "eta_low": lo, "eta_high": hi,
            "observed_time": events[j].peak_time,
        })
    for j in range(leading.order + 1, n_barrages + 1):
        eta, lo, hi = _eta_triplet(reaches, leading, j)
        rows.append({
            "from": leading, "barrage_order": j, "status": "estimated",
            "eta": eta, "eta_low": lo, "eta_high": hi, "observed_time": None,
        })

    if forming:
        live = True
    elif leading.order < n_barrages:
        nxt = next(r for r in rows if r["barrage_order"] == leading.order + 1)
        live = as_of <= nxt["eta_high"] + timedelta(hours=LIVE_GRACE_H)
    else:
        live = as_of <= leading.peak_time + timedelta(hours=FINAL_DISPLAY_H)
    return _Wave(wave_id, events, leading, rows, live)


# ---------------------------------------------------------------------------
# Village ETAs
# ---------------------------------------------------------------------------
def _lerp(t0: datetime, t1: datetime, frac: float) -> datetime:
    return t0 + (t1 - t0) * frac


def _project_km(coords: list, kms: list, lat: float, lon: float) -> float:
    """km of the closest point on the polyline to (lat, lon).

    Local equirectangular plane (lon scaled by cos(lat)); at these distances
    the error is far below the daily-sampling uncertainty.
    """
    scale = math.cos(math.radians(lat))
    px, py = lon * scale, lat
    best = None
    for i in range(len(coords) - 1):
        ax, ay = coords[i][1] * scale, coords[i][0]
        bx, by = coords[i + 1][1] * scale, coords[i + 1][0]
        dx, dy = bx - ax, by - ay
        seg = dx * dx + dy * dy
        t = 0.0 if seg == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg))
        d = (ax + t * dx - px) ** 2 + (ay + t * dy - py) ** 2
        if best is None or d < best[0]:
            best = (d, kms[i] + t * (kms[i + 1] - kms[i]))
    return best[1]


def barrage_positions(data: FloodData) -> tuple:
    """({order: km on the villages' scale}, on_centreline).

    Barrages projected onto the indus.geojson centreline, which is where
    villages.json river_km is measured. Falls back to barrages.json river_km
    (FFC travel-table km) when the centreline or its per-vertex km is
    missing, or the projection does not keep the barrages in river order.
    """
    ffc = {b["order"]: float(b["river_km"]) for b in data.barrages}
    coords, kms = data.river_coords, data.river_km_line
    if not coords or not kms or len(coords) != len(kms) or len(coords) < 2:
        return ffc, False
    line = {
        b["order"]: _project_km(coords, kms, float(b["lat"]), float(b["lon"]))
        for b in data.barrages
    }
    ordered = [line[o] for o in sorted(line)]
    if any(a >= b for a, b in zip(ordered, ordered[1:])):
        return ffc, False
    return line, True


def village_etas(
    villages: list,
    barrages: list,
    reaches: list,
    waves: list,
    as_of: datetime,
    positions: Optional[dict] = None,
) -> list:
    """At-risk villages (contract shape), sorted by eta then population desc.

    positions: {barrage order: km on the villages' river_km scale}; defaults
    to barrages.json river_km.
    """
    n = len(barrages)
    km = positions or {b["order"]: float(b["river_km"]) for b in barrages}
    last_reach = reaches[-1]
    last_len = km[n] - km[n - 1]

    best: dict = {}
    for w in waves:
        if not w.live or w.leading is None:
            continue
        L = w.leading
        times = {L.order: (L.peak_time, L.peak_time, L.peak_time)}
        for r in w.eta_rows:
            if r["status"] == "estimated":
                times[r["barrage_order"]] = (r["eta"], r["eta_low"], r["eta_high"])

        for v in villages:
            vkm = float(v["river_km"])
            if vkm <= km[L.order]:
                continue
            if vkm >= km[n]:
                base = times[n]
                extra = vkm - km[n]
                triplet = tuple(
                    t + timedelta(hours=extra * last_reach[key] / last_len)
                    for t, key in zip(base, ("lag_median_h", "lag_min_h", "lag_max_h"))
                )
            else:
                a = max(o for o in km if km[o] <= vkm)
                b = a + 1
                frac = (vkm - km[a]) / (km[b] - km[a])
                triplet = tuple(_lerp(times[a][k], times[b][k], frac) for k in range(3))
            if triplet[2] < as_of:
                continue
            eta = triplet[0]
            prior = best.get(v["id"])
            if prior is None or eta < prior[0][0]:
                best[v["id"]] = (triplet, v)

    rows = []
    for (eta, lo, hi), v in best.values():
        rows.append({
            "id": v["id"],
            "name": v["name"],
            "district": v["district"],
            "lat": v["lat"],
            "lon": v["lon"],
            "eta": fmt_time(eta),
            "eta_low": fmt_time(lo),
            "eta_high": fmt_time(hi),
            "hours_to_arrival": _hours(eta - as_of),
            "population": v.get("population", 0),
            "population_source": v.get("population_source", ""),
            "_eta": eta,
        })
    rows.sort(key=lambda r: (r["_eta"], -(r["population"] or 0), r["id"]))
    for r in rows:
        del r["_eta"]
    return rows


def district_eta_hours(at_risk: list) -> dict:
    out: dict = {}
    for v in at_risk:
        h = v["hours_to_arrival"]
        if v["district"] not in out or h < out[v["district"]]:
            out[v["district"]] = h
    return out


# ---------------------------------------------------------------------------
# Reach geometry
# ---------------------------------------------------------------------------
def _nearest_index(coords: list, lat: float, lon: float) -> int:
    return min(
        range(len(coords)),
        key=lambda k: (coords[k][0] - lat) ** 2 + (coords[k][1] - lon) ** 2,
    )


def reach_coords(river_coords: Optional[list], up: dict, down: dict) -> list:
    """[lat, lon] polyline for a reach: the river line between the two
    barrages' nearest vertices, or a straight segment without the line."""
    a = [up["lat"], up["lon"]]
    b = [down["lat"], down["lon"]]
    if not river_coords:
        return [a, b]
    i = _nearest_index(river_coords, *a)
    j = _nearest_index(river_coords, *b)
    if i <= j:
        seg = river_coords[i : j + 1]
    else:
        seg = list(reversed(river_coords[j : i + 1]))
    return [a] + [list(p) for p in seg[1:-1]] + [b]


# ---------------------------------------------------------------------------
# Situation
# ---------------------------------------------------------------------------
def data_range(data: FloodData) -> tuple:
    """(earliest as_of where every barrage has a reading, last reading)."""
    firsts = [rs[0].time for rs in data.readings.values() if rs]
    lasts = [rs[-1].time for rs in data.readings.values() if rs]
    if not firsts or len(firsts) < len(data.barrages):
        raise AsOfOutOfRange("flows data has no readings for some barrages")
    return max(firsts), max(lasts)


def _check_as_of(data: FloodData, as_of: datetime) -> None:
    start, end = data_range(data)
    if as_of < start or as_of > end:
        raise AsOfOutOfRange(
            f"as_of {fmt_time(as_of)} is outside the flows data "
            f"({fmt_time(start)} to {fmt_time(end)})"
        )


def _latest_two(readings: list, as_of: datetime) -> tuple:
    prev = latest = None
    for r in readings:
        if r.time > as_of:
            break
        prev, latest = latest, r
    return prev, latest


def _waves_at(data: FloodData, as_of: datetime) -> tuple:
    events_by_order = {
        b["order"]: detect_events(data.readings.get(b["name"], []), b, as_of)
        for b in data.barrages
    }
    ids = link_waves(events_by_order, data.reaches)
    grouped: dict = {}
    for evs in events_by_order.values():
        for e in evs:
            grouped.setdefault(id(e.root), {})[e.order] = e
    waves = [
        _build_wave(ids[rid], evs, data.reaches, len(data.barrages), as_of)
        for rid, evs in grouped.items()
    ]
    waves.sort(key=lambda w: int(w.wave_id.rsplit("w", 1)[1]))
    return events_by_order, waves


def situation(data: FloodData, as_of: datetime, mode: str = "replay") -> dict:
    """The /flood-situation response (CONTRACT.md) at as_of."""
    _check_as_of(data, as_of)
    by_order = {b["order"]: b for b in data.barrages}

    barrage_rows = []
    categories = {}
    flow_notes = []
    for b in data.barrages:
        prev, latest = _latest_two(data.readings[b["name"]], as_of)
        cat = category(b, latest.outflow)
        categories[b["order"]] = cat
        barrage_rows.append({
            "name": b["name"],
            "order": b["order"],
            "lat": b["lat"],
            "lon": b["lon"],
            "inflow_cusecs": latest.inflow,
            "outflow_cusecs": latest.outflow,
            "category": cat,
            "trend": trend(prev.outflow if prev else None, latest.outflow),
        })
        if latest.time != as_of:
            flow_notes.append(f"{b['name']} last read {fmt_time(latest.time)}")
        if latest.source_url and "ffc.gov.pk" not in latest.source_url:
            flow_notes.append(
                f"{b['name']} reading is news-reported ({latest.source_url}), "
                "not an FFC table"
            )

    reach_rows = []
    for r in data.reaches:
        up = next(b for b in data.barrages if b["name"] == r["from"])
        down = next(b for b in data.barrages if b["name"] == r["to"])
        cat = max(categories[up["order"]], categories[down["order"]], key=category_rank)
        reach_rows.append({
            "from": r["from"],
            "to": r["to"],
            "category": cat,
            "coords": reach_coords(data.river_coords, up, down),
        })

    _, waves = _waves_at(data, as_of)
    live = [w for w in waves if w.live]

    peaks = []
    etas = []
    for w in live:
        for o in sorted(w.events):
            e = w.events[o]
            if e.status in ("forming", "passed"):
                peaks.append({
                    "barrage": e.barrage,
                    "wave_id": w.wave_id,
                    "status": e.status,
                    "peak_time": fmt_time(e.peak_time),
                    "peak_outflow_cusecs": e.peak_outflow,
                })
        for r in sorted(w.eta_rows, key=lambda x: x["barrage_order"]):
            ref = r["observed_time"] if r["status"] == "arrived" else r["eta"]
            etas.append({
                "wave_id": w.wave_id,
                "from_barrage": r["from"].barrage,
                "barrage": by_order[r["barrage_order"]]["name"],
                "status": r["status"],
                "eta": fmt_time(r["eta"]),
                "eta_low": fmt_time(r["eta_low"]),
                "eta_high": fmt_time(r["eta_high"]),
                "hours_from_now": _hours(ref - as_of),
                "observed_time": (
                    fmt_time(r["observed_time"]) if r["observed_time"] else None
                ),
            })

    if data.villages is None:
        at_risk = []
        villages_note = (
            "villages.json not found: at_risk_villages is empty, no village "
            "ETAs computed"
        )
        population_note = "no villages file, so no population figures"
    else:
        positions, on_line = barrage_positions(data)
        at_risk = village_etas(data.villages, data.barrages, data.reaches, live, as_of,
                               positions)
        villages_note = (
            f"villages.json ({len(data.villages)} villages). Village ETAs are "
            "modelled: barrage ETAs interpolated by river_km between the two "
            "barrages around each village"
        )
        if on_line:
            villages_note += (
                "; barrages placed on the indus.geojson centreline that "
                "village river_km is measured on"
            )
        else:
            villages_note += (
                "; indus.geojson river_km not available, so barrages use the "
                "FFC travel-table river_km, which can differ from the village "
                "centreline km by up to ~140 km"
            )
        pop_sources = sorted({
            str(v.get("population_source", "")) for v in data.villages
            if v.get("population_source")
        })
        population_note = (
            "from villages.json population_source: " + "; ".join(pop_sources)
            if pop_sources else "villages.json gives no population_source"
        )

    flows_note = (
        "gauge: FFC Daily Flood Situation Report Annexure-I readings "
        "(flows_2022.csv), latest reading at or before as_of per barrage; "
        "category and trend computed from outflow"
    )
    if flow_notes:
        flows_note += ". " + "; ".join(flow_notes)

    etas_note = (
        "modelled: upstream peak_time + summed lag_median_h from reaches.json "
        "(2022 peak-to-peak lags, not a hydraulic model); range from summed "
        "lag_min_h/lag_max_h. Peaks use only readings at or before as_of"
    )
    if any(w.leading is not None and w.leading.status == "forming" for w in live):
        etas_note += (
            ". ETAs from a forming peak are provisional: the crest has not "
            "been seen yet, so they are an earliest-arrival estimate"
        )
    if not data.river_coords:
        etas_note += ". indus.geojson not found: reach coords are straight lines"

    return {
        "as_of": fmt_time(as_of),
        "mode": mode,
        "barrages": barrage_rows,
        "reaches": reach_rows,
        "peaks": peaks,
        "etas": etas,
        "at_risk_villages": at_risk,
        "district_eta_hours": district_eta_hours(at_risk),
        "data_provenance": {
            "flows": flows_note,
            "etas": etas_note,
            "villages": villages_note,
            "population": population_note,
        },
    }


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------
def replay_steps(data: FloodData) -> list:
    """Daily 06:00 as_of values inside the data range."""
    start, end = data_range(data)
    day: date = start.date()
    steps = []
    while True:
        t = datetime(day.year, day.month, day.day, REPLAY_STEP_HOUR)
        if t > end:
            break
        if t >= start:
            steps.append(t)
        day += timedelta(days=1)
    return steps


def scorecard(data: FloodData) -> list:
    """Predicted vs actual crest time per barrage and wave (see docstring)."""
    _, end = data_range(data)
    _, final_waves = _waves_at(data, end)
    rows = []
    for w in final_waves:
        for o in sorted(w.events):
            e = w.events[o]
            if e.status != "passed" or o == 1:
                continue
            before = e.peak_time - timedelta(minutes=1)
            upstream = {
                b["order"]: detect_events(data.readings.get(b["name"], []), b, before)
                for b in data.barrages if b["order"] < o
            }
            f = _best_upstream(upstream, data.reaches, o, e.peak_time, set(),
                               reported_only=True)
            if f is None:
                continue
            eta, lo, hi = _eta_triplet(data.reaches, f, o)
            rows.append({
                "barrage": e.barrage,
                "wave_id": w.wave_id,
                "actual_peak_time": fmt_time(e.peak_time),
                "predicted_time": fmt_time(eta),
                "predicted_low": fmt_time(lo),
                "predicted_high": fmt_time(hi),
                "error_hours": _hours(e.peak_time - eta),
            })
    rows.sort(key=lambda r: (r["actual_peak_time"], r["barrage"]))
    return rows


def replay_2022(data: FloodData) -> dict:
    """The /replay/2022 response: one situation per day at 06:00 + scorecard."""
    return {
        "steps": [situation(data, t, mode="replay") for t in replay_steps(data)],
        "scorecard": scorecard(data),
    }


# ---------------------------------------------------------------------------
# Loader (the only IO in this module)
# ---------------------------------------------------------------------------
def _num(value: str) -> float:
    value = (value or "").strip()
    if not value:
        return 0
    f = float(value)
    return int(f) if f.is_integer() else f


def _river_coords(geojson: dict) -> list:
    coords: list = []
    feats = geojson.get("features", [geojson]) if isinstance(geojson, dict) else []
    for feat in feats:
        geom = feat.get("geometry", feat)
        if geom.get("type") == "LineString":
            coords.extend(geom["coordinates"])
        elif geom.get("type") == "MultiLineString":
            for line in geom["coordinates"]:
                coords.extend(line)
    return [[c[1], c[0]] for c in coords]   # GeoJSON [lon, lat] -> [lat, lon]


def _river_km_line(geojson: dict, n_coords: int) -> Optional[list]:
    """properties.river_km per vertex of a single-LineString centreline."""
    feats = geojson.get("features", [geojson]) if isinstance(geojson, dict) else []
    if len(feats) != 1:
        return None
    kms = (feats[0].get("properties") or {}).get("river_km")
    if not isinstance(kms, list) or len(kms) != n_coords:
        return None
    return [float(k) for k in kms]


def load_data(
    barrages_path: Path,
    reaches_path: Path,
    flows_path: Path,
    villages_path: Optional[Path] = None,
    geojson_path: Optional[Path] = None,
) -> FloodData:
    """Read the data files. villages and geojson are optional."""
    barrages = sorted(
        json.loads(Path(barrages_path).read_text(encoding="utf-8")),
        key=lambda b: b["order"],
    )
    names = [b["name"] for b in barrages]

    reaches_raw = json.loads(Path(reaches_path).read_text(encoding="utf-8"))
    by_pair = {(r["from"], r["to"]): r for r in reaches_raw}
    reaches = []
    for up, down in zip(names, names[1:]):
        if (up, down) not in by_pair:
            raise ValueError(f"reaches.json has no reach {up} -> {down}")
        reaches.append(by_pair[(up, down)])

    readings: dict = {n: [] for n in names}
    with open(flows_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name = row["barrage"].strip()
            if name not in readings:
                continue
            readings[name].append(Reading(
                time=parse_time(row["date_time"]),
                inflow=_num(row.get("inflow_cusecs", "")),
                outflow=_num(row.get("outflow_cusecs", "")),
                source_url=(row.get("source_url") or "").strip(),
            ))
    for rs in readings.values():
        rs.sort(key=lambda r: r.time)

    villages = None
    if villages_path is not None and Path(villages_path).exists():
        villages = json.loads(Path(villages_path).read_text(encoding="utf-8"))

    river = river_km_line = None
    if geojson_path is not None and Path(geojson_path).exists():
        geo = json.loads(Path(geojson_path).read_text(encoding="utf-8"))
        river = _river_coords(geo)
        river_km_line = _river_km_line(geo, len(river))

    return FloodData(
        barrages=barrages,
        reaches=reaches,
        readings=readings,
        villages=villages,
        river_coords=river,
        river_km_line=river_km_line,
        sources={
            "barrages.json": True,
            "reaches.json": True,
            "flows_2022.csv": True,
            "villages.json": villages is not None,
            "indus.geojson": river is not None,
        },
    )
