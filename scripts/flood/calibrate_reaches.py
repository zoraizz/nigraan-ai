"""Estimate Indus reach lags from the two 2022 flood waves.

flows_2022.csv is one Annexure-I sample per day, almost always at 06:00.
2022 had two crests: an earlier one around 23-25 August and a later one
around 30 August to 8 September. Travel down the river moves those dates.

Taunsa shows both crests clearly (22 Aug and 30 Aug). Those two local
maxima, at least five days apart, are the anchors. Each other barrage
takes, for the same wave, its own local maximum in a short window upstream
or downstream of the neighbour already matched. Pairing the two biggest
days independently at every site mis-labels the waves, because Tarbela is
a regulated release and Kotri's hydrograph is a single long rise.

flood-tracker/routing.py finds crests on the live series with a 7% dip
rule (NEW_WAVE_DIP) and must agree with the crests found here; on the 2022
data it does at every barrage except Kotri, whose plateau is taken below.
flood-tracker/tests/test_routing.py checks that agreement.

Kotri's FFC outflow sat at 584,000 cusecs at 06:00 on 5, 6, 7 and 8 Sep.
A later Dawn reading of 600,018 on 10 Sep is about 2.7 percent higher and
the article attributes it to Manchhar Lake and an MNVD breach, not to the
Indus wave. The routed Kotri peak is therefore 8 Sep 06:00. The first wave
never forms a separate crest at Kotri; the 06:00 series is still rising.

lag hours = downstream peak time minus upstream peak time.
lag_min_h / lag_max_h are the two observed lags.
lag_median_h is their median (the mean of the two, when both exist).
attenuation_ratio is the median of downstream peak outflow / upstream peak
outflow. A value above 1 is tributary gain (Kabul above Kalabagh, Panjnad
above Guddu), not a routing loss.

Daily 06:00 sampling places each crest only to about +/-12 h, so a lag can
be off by about a day even when the match is right. That is stated on every
reach and is not folded into lag_min_h / lag_max_h, which stay the observed lags.

Leave-one-wave-out: lags are taken from wave 1 only. Wave 2's peak at a
barrage is predicted from the observed wave-2 peak at the barrage immediately
upstream, plus that wave-1 lag. The error is predicted time minus observed
wave-2 peak, in hours. Tarbela is the anchor and is not predicted.
"""

from __future__ import annotations

import csv
import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "flood-tracker" / "data"
CSV_PATH = DATA / "flows_2022.csv"
JSON_PATH = DATA / "reaches.json"

BARRAGES = ("Tarbela", "Kalabagh", "Chashma", "Taunsa", "Guddu", "Sukkur", "Kotri")
PAIRS = tuple(zip(BARRAGES, BARRAGES[1:]))

WINDOW_START = datetime(2022, 8, 10, 0, 0)
WINDOW_END = datetime(2022, 9, 14, 23, 59)
MIN_SEPARATION = timedelta(days=5)

SAMPLING_NOTE = (
    "Lags are outflow-peak time differences for the two 2022 Indus waves "
    "(earlier crest around 23-25 Aug, later crest around 30 Aug-8 Sep), "
    "matched separately at each end of the reach. Daily Annexure-I sampling "
    "is 06:00, so each peak time is coarse by about +/-12 h. "
    "attenuation_ratio is the median of downstream peak outflow divided by "
    "upstream peak outflow; above 1 means tributary gain."
)


def load_rows() -> dict[str, list[dict]]:
    by_barrage: dict[str, list[dict]] = {name: [] for name in BARRAGES}
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            by_barrage[row["barrage"]].append(
                {
                    "time": datetime.fromisoformat(row["date_time"]),
                    "outflow": int(row["outflow_cusecs"]),
                    "source_url": row["source_url"],
                }
            )
    for name in BARRAGES:
        by_barrage[name].sort(key=lambda item: item["time"])
    return by_barrage


def at_0600(obs: list[dict]) -> list[dict]:
    """Annexure-I samples. Off-hour news points are kept in the CSV but not used as crests."""
    return [item for item in obs if item["time"].hour == 6 and item["time"].minute == 0 and "ffc.gov.pk" in item["source_url"]]


def local_crests(obs: list[dict]) -> list[dict]:
    """Centres of strict local maxima. A flat run counts once. Endpoints do not."""
    series = [item for item in at_0600(obs) if WINDOW_START <= item["time"] <= WINDOW_END]
    crests = []
    index = 0
    while index < len(series):
        end = index
        while end + 1 < len(series):
            gap = series[end + 1]["time"] - series[end]["time"]
            if series[end + 1]["outflow"] != series[index]["outflow"] or gap > timedelta(hours=30):
                break
            end += 1
        before = index > 0 and series[index - 1]["outflow"] < series[index]["outflow"]
        after = end + 1 < len(series) and series[end + 1]["outflow"] < series[index]["outflow"]
        if before and after:
            crests.append(series[(index + end) // 2])
        index = end + 1
    return crests


def two_anchor_waves(crests: list[dict]) -> dict[int, dict]:
    """Earlier and later of the two highest crests at least five days apart."""
    if not crests:
        return {}
    primary = max(crests, key=lambda item: (item["outflow"], item["time"]))
    others = [item for item in crests if abs(item["time"] - primary["time"]) >= MIN_SEPARATION]
    chosen = [primary]
    if others:
        chosen.append(max(others, key=lambda item: (item["outflow"], item["time"])))
    chosen.sort(key=lambda item: item["time"])
    return {wave: peak for wave, peak in enumerate(chosen, start=1)}


def best_crest(crests: list[dict], start: datetime, end: datetime) -> dict | None:
    inside = [item for item in crests if start <= item["time"] <= end]
    if not inside:
        return None
    return max(inside, key=lambda item: (item["outflow"], item["time"]))


def kotri_plateau(series: list[dict]) -> dict | None:
    """Last 06:00 of the flat 584,000 crest on 5-8 Sep, if that plateau is present."""
    wanted = {datetime(2022, 9, day, 6, 0) for day in (5, 6, 7, 8)}
    rows = [item for item in series if item["time"] in wanted and "ffc.gov.pk" in item["source_url"]]
    if len(rows) != 4 or len({item["outflow"] for item in rows}) != 1:
        return None
    rows.sort(key=lambda item: item["time"])
    return rows[-1]


def match_waves(series: dict[str, list[dict]]) -> dict[str, dict[int, dict]]:
    crests = {name: local_crests(series[name]) for name in BARRAGES}
    peaks: dict[str, dict[int, dict]] = {name: {} for name in BARRAGES}
    peaks["Taunsa"] = two_anchor_waves(crests["Taunsa"])
    for upstream, downstream in (("Taunsa", "Guddu"), ("Guddu", "Sukkur"), ("Sukkur", "Kotri")):
        for wave, up_peak in peaks[upstream].items():
            # Do not cross into the next wave's upstream peak.
            horizon = up_peak["time"] + timedelta(days=10)
            later = peaks[upstream].get(wave + 1)
            if later and later["time"] < horizon:
                horizon = later["time"]
            chosen = best_crest(crests[downstream], up_peak["time"] + timedelta(hours=1), horizon)
            if chosen:
                peaks[downstream][wave] = chosen
    for downstream, upstream in (("Taunsa", "Chashma"), ("Chashma", "Kalabagh"), ("Kalabagh", "Tarbela")):
        for wave, down_peak in peaks[downstream].items():
            chosen = best_crest(
                crests[upstream],
                down_peak["time"] - timedelta(days=5),
                down_peak["time"],
            )
            if chosen:
                peaks[upstream][wave] = chosen
    plateau = kotri_plateau(series["Kotri"])
    if plateau is not None:
        # Wave 2 is the Indus crest. The 10 Sep news point is a side inflow.
        peaks["Kotri"][2] = plateau
        if peaks["Kotri"].get(1) and peaks["Kotri"][1]["time"] >= plateau["time"]:
            peaks["Kotri"].pop(1, None)
    return peaks


def hours_between(upstream: datetime, downstream: datetime) -> float:
    return (downstream - upstream).total_seconds() / 3600.0


def as_hours(value: float) -> int | float:
    if abs(value - round(value)) < 1e-9:
        return int(round(value))
    return round(value, 2)


def stamp(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M")


def build_reaches(series: dict[str, list[dict]], peaks: dict[str, dict[int, dict]]) -> list[dict]:
    reaches = []
    for upstream, downstream in PAIRS:
        events = []
        lags = []
        ratios = []
        for wave in (1, 2):
            up = peaks[upstream].get(wave)
            down = peaks[downstream].get(wave)
            if not up or not down:
                continue
            lag = hours_between(up["time"], down["time"])
            lags.append(lag)
            if up["outflow"] > 0:
                ratios.append(down["outflow"] / up["outflow"])
            events.append(
                {
                    "wave": wave,
                    "upstream_peak": stamp(up["time"]),
                    "downstream_peak": stamp(down["time"]),
                    "lag_h": as_hours(lag),
                    "upstream_outflow_cusecs": up["outflow"],
                    "downstream_outflow_cusecs": down["outflow"],
                    "upstream_source": up["source_url"],
                    "downstream_source": down["source_url"],
                }
            )
        note = SAMPLING_NOTE
        outside = [
            event["downstream_source"]
            for event in events
            if "ffc.gov.pk" not in event["downstream_source"]
        ]
        outside += [
            event["upstream_source"]
            for event in events
            if "ffc.gov.pk" not in event["upstream_source"]
        ]
        if outside:
            note += " A peak in this reach is not from an FFC PDF: " + "; ".join(dict.fromkeys(outside)) + "."
        if downstream == "Kotri":
            note += (
                " Kotri's FFC 06:00 outflow was 584,000 on 5, 6, 7 and 8 Sep, so the "
                "crest time is only known to about +/-36 h, wider than the usual +/-12 h. "
                "8 Sep is the last day of that plateau. Dawn's 10 Sep 06:00 figure of "
                "600,018 (https://www.dawn.com/news/1709397) is about 2.7% higher and the "
                "article attributes it to Manchhar Lake and an MNVD breach, so it is not "
                "used as the routed Indus peak. The earlier wave did not form a separate "
                "crest at Kotri; the 06:00 series was still rising."
            )
        elif len(lags) < 2:
            note += " Only one of the two waves produced a separated crest at both ends of this reach."
        reaches.append(
            {
                "from": upstream,
                "to": downstream,
                "lag_median_h": as_hours(statistics.median(lags)) if lags else None,
                "lag_min_h": as_hours(min(lags)) if lags else None,
                "lag_max_h": as_hours(max(lags)) if lags else None,
                "attenuation_ratio": round(statistics.median(ratios), 3) if ratios else None,
                "events_used": events,
                "note": note,
            }
        )
    return reaches


def leave_one_wave_out(peaks: dict[str, dict[int, dict]]) -> list[str]:
    """One-step: predict each barrage from its upstream neighbour using the wave-1 lag."""
    lines = [
        "Leave-one-wave-out: lags from wave 1 only. "
        "Wave 2 peak at each barrage is predicted from the observed wave-2 peak "
        "at the barrage immediately upstream. Error = predicted minus observed, hours.",
        "Tarbela: anchor, not predicted",
    ]
    for upstream, downstream in PAIRS:
        up1 = peaks[upstream].get(1)
        down1 = peaks[downstream].get(1)
        up2 = peaks[upstream].get(2)
        down2 = peaks[downstream].get(2)
        if not (up1 and down1 and up2 and down2):
            lines.append(
                f"{downstream}: error not computed "
                f"(wave1 up={'yes' if up1 else 'no'}, wave1 down={'yes' if down1 else 'no'}, "
                f"wave2 up={'yes' if up2 else 'no'}, wave2 down={'yes' if down2 else 'no'})"
            )
            continue
        lag = hours_between(up1["time"], down1["time"])
        predicted = up2["time"] + timedelta(hours=lag)
        error = hours_between(down2["time"], predicted)
        lines.append(
            f"{downstream}: predicted {stamp(predicted)} "
            f"observed {stamp(down2['time'])} "
            f"error {as_hours(error):+} h "
            f"(wave-1 lag {as_hours(lag)} h)"
        )
    return lines


def print_peaks(peaks: dict[str, dict[int, dict]]) -> None:
    print("Peaks (outflow):")
    for name in BARRAGES:
        for wave in (1, 2):
            peak = peaks[name].get(wave)
            if not peak:
                print(f"  {name} wave {wave}: none")
                continue
            origin = "ffc" if "ffc.gov.pk" in peak["source_url"] else peak["source_url"]
            print(f"  {name} wave {wave}: {stamp(peak['time'])} {peak['outflow']} cusecs ({origin})")


def main() -> None:
    series = load_rows()
    peaks = match_waves(series)
    print_peaks(peaks)
    reaches = build_reaches(series, peaks)
    JSON_PATH.write_text(json.dumps(reaches, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {JSON_PATH.relative_to(ROOT).as_posix()}")
    for line in leave_one_wave_out(peaks):
        print(line)


if __name__ == "__main__":
    main()
