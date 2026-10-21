"""Select a GloFAS v4 cell per barrage against FFC 2022 outflows.

Search 49 coordinates spaced 0.05 degrees around the published barrage.
Select the highest mean 2022 discharge to favour the Indus main stem; ties
use coordinates for determinism. Compute Pearson correlation after selection.
Scale by paired-period FFC maximum / GloFAS maximum in cusecs. This is an
in-sample bias adjustment, not independent validation or a hydraulic model.
Returned cell centres are saved, so runtime never repeats this search.
"""
import csv
import json
import math
from pathlib import Path
from statistics import correlation
import requests

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "flood-tracker" / "data"
URL = "https://flood-api.open-meteo.com/v1/flood"
FACTOR = 35.3147


def calibrate():
    barrages = json.loads((DATA / "barrages.json").read_text())
    with (DATA / "flows_2022.csv").open() as stream:
        flows = list(csv.DictReader(stream))
    result = {"_notes": {
        "source": URL, "model": "GloFAS v4 (API default seamless)", "period": "2022-08-10..2022-09-11",
        "method": "7x7 grid, 0.05 degree spacing; highest mean discharge over the 33-day 2022 interval; scale = paired FFC peak / paired GloFAS peak cusecs; calibrated only when scale in [0.25,4] and corr >= 0.3",
        "units": "m3/s x 35.3147 = cusecs", "cell_selection": "nearest",
        "limits": "In-sample peak bias scaling from 2022, not independently validated; cell may represent a tributary or reservoir; daily model dates assigned 06:00 PKT, not instantaneous readings."
    }}
    for barrage in barrages:
        name = barrage["name"]
        targets = [(barrage["lat"] + i * .05, barrage["lon"] + j * .05) for i in range(-3, 4) for j in range(-3, 4)]
        response = requests.get(URL, params={
            "latitude": ",".join(str(round(a, 6)) for a, _ in targets),
            "longitude": ",".join(str(round(b, 6)) for _, b in targets),
            "daily": "river_discharge",
            "start_date": "2022-08-10", "end_date": "2022-09-11", "cell_selection": "nearest", "timezone": "GMT",
        }, timeout=15)
        response.raise_for_status()
        cells = response.json()
        if not isinstance(cells, list) or len(cells) != 49:
            raise ValueError(f"{name}: expected 49 cell responses")
        observed = {r["date_time"][:10]: float(r["outflow_cusecs"]) for r in flows if r["barrage"] == name}
        candidates = []
        for cell in cells:
            daily = cell["daily"]
            pairs = [(observed[d], q * FACTOR) for d, q in zip(daily["time"], daily["river_discharge"]) if d in observed and q is not None and math.isfinite(q)]
            if len(pairs) != len(observed) or len(pairs) < 3:
                continue
            ffc, glofas = zip(*pairs)
            if max(glofas) <= 0 or len(set(glofas)) < 2:
                continue
            corr = correlation(ffc, glofas)
            entry = dict(lat=cell["latitude"], lon=cell["longitude"], scale=max(ffc)/max(glofas), corr=corr,
                         glofas_peak_cusecs=max(glofas), ffc_peak_cusecs=max(ffc))
            entry["mean_2022_cusecs"] = sum(q * FACTOR for q in daily["river_discharge"]) / len(daily["river_discharge"])
            entry["calibrated"] = .25 <= entry["scale"] <= 4 and corr >= .3
            candidates.append(entry)
        if not candidates:
            raise ValueError(f"{name}: no complete usable cell series")
        best = min(candidates, key=lambda r: (-r["mean_2022_cusecs"], r["lat"], r["lon"]))
        result[name] = best
        print(name, json.dumps(best), flush=True)
    (DATA / "glofas_calibration.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    calibrate()
