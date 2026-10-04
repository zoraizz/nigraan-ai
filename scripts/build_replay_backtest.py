#!/usr/bin/env python3
"""Precomputed backtest of Risk Flag's rule-based scorer on the 2022 Pakistan floods.

Run from the repo root:

    python scripts/build_replay_backtest.py              # reuse cached raw responses
    python scripts/build_replay_backtest.py --refetch    # ignore the cache

Standard library only. Nothing from risk-flag is imported: the scorer
(`score_risk_fallback`), `DISTRICTS` and `HAZARD_CONTEXT` are extracted from
risk-flag/main.py with `ast` and executed unchanged, so no Gemini/FastAPI code
is loaded and no LLM is called.

Inputs:  risk-flag/main.py, data/replay/ground_truth_2022.json
Outputs: data/replay/raw/*.json (gitignored), data/replay/backtest_2022.json
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import statistics
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parent.parent
MAIN_PY = REPO / "risk-flag" / "main.py"
REPLAY_DIR = REPO / "data" / "replay"
RAW_DIR = REPLAY_DIR / "raw"
GROUND_TRUTH = REPLAY_DIR / "ground_truth_2022.json"
OUTPUT = REPLAY_DIR / "backtest_2022.json"

YEARS = (2022, 2021)
WINDOW_START = (6, 15)
WINDOW_END = (9, 10)
STEP_DAYS = 3
RUNUP_DAYS = 10            # reporting window before each impact reference date (chosen after viewing timelines)
FORECAST_DAYS = 3          # production: forecast_days=3 -> days D, D+1, D+2
DROUGHT_WINDOWS = (30, 90)  # production: archive past_days=30 / 90

PREVIOUS_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_MODEL = "jma_gsm"
FORECAST_VARS = ("precipitation", "precipitation_previous_day1", "precipitation_previous_day2")

THROTTLE_SECS = 1.5
MAX_ATTEMPTS = 6
BACKOFF_SECS = 5.0
HEADERS = {"User-Agent": "NigraanAI-ReplayBacktest/1.0 (github.com/zoraizz/nigraan-ai)"}

SOURCES = {
    "forecast": {
        "rainfall_source": "forecast (JMA GSM via Open-Meteo Previous Runs API, issued on the as-of date)",
        "flood_signal": (
            "Sum of three local (Asia/Karachi) days: day D from the stitched short-lead series "
            "(`precipitation`), day D+1 from the run issued ~1 day earlier "
            "(`precipitation_previous_day1`), day D+2 from the run issued ~2 days earlier "
            "(`precipitation_previous_day2`). All three come from model runs initialised on or "
            "around day D, i.e. what a 3-day forecast issued on D said."
        ),
    },
    "hindsight": {
        "rainfall_source": "observed (hindsight)",
        "flood_signal": (
            "Observed daily precipitation_sum (Open-Meteo Historical Weather API, default model, "
            "ECMWF IFS analysis at 9 km for these years) for days D, D+1 and D+2, treated as a "
            "perfect 3-day forecast. This uses data from after the as-of date and is an upper "
            "bound on what the scorer could achieve, not a predictive test."
        ),
    },
}

DROUGHT_SIGNAL = (
    "Both runs: sum of observed daily precipitation_sum from the Historical Weather API over "
    "D-30..D and D-90..D inclusive, mirroring production's archive call with past_days=30/90 "
    "(which returns today plus the previous N days). Missing days are skipped, as in production."
)


# ---------------------------------------------------------------------------
# Scorer extraction
# ---------------------------------------------------------------------------
def _extract_segments() -> tuple[dict[str, str], str]:
    src = MAIN_PY.read_text(encoding="utf-8")
    wanted = {"DISTRICTS", "HAZARD_CONTEXT", "score_risk_fallback"}
    segments: dict[str, str] = {}
    for node in ast.parse(src).body:
        name = None
        if isinstance(node, ast.FunctionDef):
            name = node.name
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        if name in wanted:
            segments[name] = ast.get_source_segment(src, node)
    missing = wanted - segments.keys()
    if missing:
        sys.exit(f"Could not find {sorted(missing)} in {MAIN_PY}")
    return segments, src


def load_scorer(neutral_context: bool = False) -> dict:
    segments, _ = _extract_segments()
    ns: dict = {}
    code = "\n\n".join(
        ["from __future__ import annotations", segments["DISTRICTS"], segments["HAZARD_CONTEXT"], segments["score_risk_fallback"]]
    )
    exec(compile(code, str(MAIN_PY), "exec"), ns)
    if neutral_context:
        ns["HAZARD_CONTEXT"] = {k: {} for k in ns["HAZARD_CONTEXT"]}
    return ns


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def probe_thresholds(score) -> dict:
    """Read the scorer's behaviour at the documented boundaries instead of trusting the docs."""

    def lvl(hazards, r3=None, r30=None, r90=None):
        return score("probe", hazards, r3, r30, r90)[0]

    probe = {
        "flood_3d_40.0mm": lvl(["flood"], 40.0),
        "flood_3d_40.1mm": lvl(["flood"], 40.1),
        "flood_3d_100.0mm": lvl(["flood"], 100.0),
        "flood_3d_100.1mm": lvl(["flood"], 100.1),
        "flood_3d_missing": lvl(["flood"], None),
        "glof": lvl(["glof", "avalanche"]),
        "landslide": lvl(["landslide"]),
        "drought_0mm": lvl(["drought"], None, 0.0, 0.0),
        "drought_1000mm": lvl(["drought"], None, 1000.0, 3000.0),
    }
    expected = {
        "flood_3d_40.0mm": "low", "flood_3d_40.1mm": "medium",
        "flood_3d_100.0mm": "medium", "flood_3d_100.1mm": "high",
        "flood_3d_missing": "low", "glof": "medium", "landslide": "medium",
        "drought_0mm": "low", "drought_1000mm": "low",
    }
    if probe != expected:
        sys.exit(f"Scorer behaviour changed; update the documented thresholds.\n got {probe}\n expected {expected}")
    return probe


def scan_context_for_leakage(hazard_context: dict) -> list[str]:
    findings = []
    for hazard, ctx in hazard_context.items():
        for key, value in ctx.items():
            text = json.dumps(value)
            for year in re.findall(r"\b(20\d\d)\b", text):
                if int(year) >= 2022:
                    findings.append(f"HAZARD_CONTEXT['{hazard}']['{key}'] mentions {year}: {value!r}")
    return findings


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------
def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def fetch(url: str, params: dict, cache_path: Path, refetch: bool) -> dict:
    if cache_path.exists() and not refetch:
        return json.loads(cache_path.read_text(encoding="utf-8"))["response"]

    full_url = f"{url}?{urlencode(params)}"
    body = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            with urlopen(Request(full_url, headers=HEADERS), timeout=90) as resp:
                body = json.load(resp)
            break
        except HTTPError as exc:
            if exc.code == 429 or 500 <= exc.code < 600:
                retry_after = exc.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else BACKOFF_SECS * 2 ** attempt
                print(f"  {exc.code} from {url}, retry {attempt + 1}/{MAX_ATTEMPTS} in {wait:.0f}s", flush=True)
                time.sleep(wait)
                continue
            raise RuntimeError(f"{exc.code} for {full_url}: {exc.read()[:300]!r}") from exc
        except URLError as exc:
            wait = BACKOFF_SECS * 2 ** attempt
            print(f"  network error {exc.reason}, retry {attempt + 1}/{MAX_ATTEMPTS} in {wait:.0f}s", flush=True)
            time.sleep(wait)
    if body is None:
        raise RuntimeError(f"Giving up on {full_url}")
    if body.get("error"):
        raise RuntimeError(f"Open-Meteo error for {full_url}: {body.get('reason')}")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"url": full_url, "fetched_at": datetime.now(timezone.utc).isoformat(), "response": body}),
        encoding="utf-8",
    )
    time.sleep(THROTTLE_SECS)
    return body


def window(year: int) -> tuple[date, date]:
    return date(year, *WINDOW_START), date(year, *WINDOW_END)


def as_of_dates(year: int) -> list[date]:
    start, end = window(year)
    out, d = [], start
    while d <= end:
        out.append(d)
        d += timedelta(days=STEP_DAYS)
    return out


def fetch_district_year(name: str, coords: tuple[float, float], year: int, refetch: bool) -> tuple[dict, dict]:
    lat, lon = coords
    start, end = window(year)
    fc = fetch(
        PREVIOUS_RUNS_URL,
        {
            "latitude": lat, "longitude": lon, "hourly": ",".join(FORECAST_VARS),
            "models": FORECAST_MODEL, "timezone": "auto",
            "start_date": start.isoformat(), "end_date": (end + timedelta(days=FORECAST_DAYS - 1)).isoformat(),
        },
        RAW_DIR / f"forecast_{slug(name)}_{year}.json",
        refetch,
    )
    arc = fetch(
        ARCHIVE_URL,
        {
            "latitude": lat, "longitude": lon, "daily": "precipitation_sum", "timezone": "auto",
            "start_date": (start - timedelta(days=max(DROUGHT_WINDOWS))).isoformat(),
            "end_date": (end + timedelta(days=FORECAST_DAYS - 1)).isoformat(),
        },
        RAW_DIR / f"archive_{slug(name)}_{year}.json",
        refetch,
    )
    return fc, arc


def hourly_to_daily(resp: dict, var: str) -> dict[date, float | None]:
    """Local-day totals; a day with any missing hour is None."""
    days: dict[date, list] = {}
    for t, v in zip(resp["hourly"]["time"], resp["hourly"][var]):
        days.setdefault(date.fromisoformat(t[:10]), []).append(v)
    return {d: (None if any(v is None for v in vals) else sum(vals)) for d, vals in days.items()}


def daily_series(resp: dict) -> dict[date, float | None]:
    return {date.fromisoformat(t): v for t, v in zip(resp["daily"]["time"], resp["daily"]["precipitation_sum"])}


# ---------------------------------------------------------------------------
# Features (same inputs production computes; see predict_risk in main.py)
# ---------------------------------------------------------------------------
def forecast_3d(fc_daily: dict[str, dict], d: date) -> float | None:
    parts = [
        fc_daily["precipitation"].get(d),
        fc_daily["precipitation_previous_day1"].get(d + timedelta(days=1)),
        fc_daily["precipitation_previous_day2"].get(d + timedelta(days=2)),
    ]
    return None if any(p is None for p in parts) else sum(parts)


def hindsight_3d(arc: dict[date, float | None], d: date) -> float | None:
    parts = [arc.get(d + timedelta(days=k)) for k in range(FORECAST_DAYS)]
    return None if any(p is None for p in parts) else sum(parts)


def past_sum(arc: dict[date, float | None], d: date, past_days: int) -> float:
    return sum(v for k in range(past_days + 1) if (v := arc.get(d - timedelta(days=k))) is not None)


def r1(x: float | None) -> float | None:
    return None if x is None else round(x, 1)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def share(levels: list[str], accepted: set[str]) -> float:
    return round(sum(lv in accepted for lv in levels) / len(levels), 3)


def first_date(dates: list[date], levels: list[str], accepted: set[str]) -> date | None:
    return next((d for d, lv in zip(dates, levels) if lv in accepted), None)


def evaluate(run: dict, districts: dict, gt: dict, dates: dict[int, list[date]]) -> dict:
    per_district = {}
    for name, info in districts.items():
        hz = info["hazard_types"]
        lv22 = run["2022"][name]["risk_level"]
        lv21 = run["2021"][name]["risk_level"]
        g = gt[name]
        row = {
            "hazard_types": hz,
            "affected_2022": g["affected"],
            "evidence": g["evidence"],
            "impact_reference_date": g["impact_reference_date"],
            "share_high": {"2022": share(lv22, {"high"}), "2021": share(lv21, {"high"})},
            "share_medium_or_high": {"2022": share(lv22, {"medium", "high"}), "2021": share(lv21, {"medium", "high"})},
            "high_dates_2021": [d.isoformat() for d, lv in zip(dates[2021], lv21) if lv == "high"],
        }
        if "flood" not in hz:
            constant = sorted(set(lv22) | set(lv21))
            row["outcome"] = f"uninformative (constant {'/'.join(constant)} in both years)"
            per_district[name] = row
            continue

        fh = first_date(dates[2022], lv22, {"high"})
        fm = first_date(dates[2022], lv22, {"medium", "high"})
        ref = date.fromisoformat(g["impact_reference_date"]) if g["impact_reference_date"] else None
        row["first_high_2022"] = fh.isoformat() if fh else None
        row["first_medium_or_high_2022"] = fm.isoformat() if fm else None
        row["days_first_high_before_reference"] = (ref - fh).days if (fh and ref) else None
        if fh is None:
            row["first_high_vs_reference"] = "never high"
        elif ref is None:
            row["first_high_vs_reference"] = "no reference date"
        else:
            row["first_high_vs_reference"] = "before or on reference" if fh <= ref else "after reference"

        runup = [
            (d, lv, r3)
            for d, lv, r3 in zip(dates[2022], lv22, run["2022"][name]["rainfall_3d_mm"])
            if ref and ref - timedelta(days=RUNUP_DAYS) <= d <= ref
        ]
        row["runup"] = [{"as_of": d.isoformat(), "risk_level": lv, "rainfall_3d_mm": r3} for d, lv, r3 in runup]
        if g["affected"] != "yes" or ref is None:
            row["outcome"] = "no ground truth"
        elif not runup:
            row["outcome"] = "reference date outside window"
        else:
            top = max((lv for _, lv, _ in runup), key=["low", "medium", "high"].index)
            row["outcome"] = {"high": "warned high", "medium": "medium only", "low": "no warning"}[top]
        per_district[name] = row

    flood = {n: r for n, r in per_district.items() if "flood" in r["hazard_types"]}
    by_outcome = lambda o: [n for n, r in flood.items() if r["outcome"] == o]  # noqa: E731
    summary = {
        "flood_districts": len(flood),
        "runup_days": RUNUP_DAYS,
        "warned_high_in_runup": by_outcome("warned high"),
        "medium_only_in_runup": by_outcome("medium only"),
        "no_warning_in_runup": by_outcome("no warning"),
        "first_high_after_reference": [n for n, r in flood.items() if r["first_high_vs_reference"] == "after reference"],
        "never_high_2022": [n for n, r in flood.items() if r["first_high_vs_reference"] == "never high"],
        "mean_share_high": {
            y: round(statistics.mean(r["share_high"][y] for r in flood.values()), 3) for y in ("2022", "2021")
        },
        "mean_share_medium_or_high": {
            y: round(statistics.mean(r["share_medium_or_high"][y] for r in flood.values()), 3) for y in ("2022", "2021")
        },
        "high_flags_2021_district_dates": sum(len(r["high_dates_2021"]) for r in flood.values()),
        "as_of_dates_per_year": len(dates[2022]),
        "static_districts": {n: r["outcome"] for n, r in per_district.items() if n not in flood},
        "false_alarm_note": (
            "Every flood district in scope was affected in 2022, so false alarms cannot be measured "
            "from 2022 alone. High flags in 2021 are reported as candidate false alarms, but 2021 "
            "impacts were not researched, so they are unverified."
        ),
    }
    return {"per_district": per_district, "summary": summary}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refetch", action="store_true", help="ignore cached raw responses")
    args = parser.parse_args()

    ns = load_scorer()
    neutral = load_scorer(neutral_context=True)
    score, districts, hazard_context = ns["score_risk_fallback"], ns["DISTRICTS"], ns["HAZARD_CONTEXT"]
    probe = probe_thresholds(score)
    segments, _ = _extract_segments()

    gt_doc = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    gt = {row["district"]: row for row in gt_doc["districts"]}
    if set(gt) != set(districts):
        sys.exit(f"Ground truth districts {sorted(set(gt) ^ set(districts))} do not match risk-flag DISTRICTS")

    dates = {y: as_of_dates(y) for y in YEARS}
    runs: dict[str, dict] = {s: {str(y): {} for y in YEARS} for s in SOURCES}
    unavailable = {s: 0 for s in SOURCES}
    grid_cells: dict[str, dict[str, list[float]]] = {"forecast": {}, "hindsight": {}}
    context_dependent = 0

    for year in YEARS:
        for name, info in districts.items():
            print(f"{year} {name}", flush=True)
            fc, arc = fetch_district_year(name, info["coords"], year, args.refetch)
            grid_cells["forecast"][name] = [fc["latitude"], fc["longitude"]]
            grid_cells["hindsight"][name] = [arc["latitude"], arc["longitude"]]
            fc_daily = {v: hourly_to_daily(fc, v) for v in FORECAST_VARS}
            arc_daily = daily_series(arc)
            hz = info["hazard_types"]

            for source in SOURCES:
                rows = {"rainfall_3d_mm": [], "rainfall_30d_mm": [], "rainfall_90d_mm": [], "risk_level": []}
                for d in dates[year]:
                    r3 = None
                    if "flood" in hz:
                        r3 = forecast_3d(fc_daily, d) if source == "forecast" else hindsight_3d(arc_daily, d)
                        if r3 is None:
                            unavailable[source] += 1
                    r30 = r90 = None
                    if "drought" in hz:
                        r30, r90 = (past_sum(arc_daily, d, n) for n in DROUGHT_WINDOWS)
                    level, _ = score(name, hz, r3, r30, r90)
                    if neutral["score_risk_fallback"](name, hz, r3, r30, r90)[0] != level:
                        context_dependent += 1
                    rows["rainfall_3d_mm"].append(r1(r3))
                    rows["rainfall_30d_mm"].append(r1(r30))
                    rows["rainfall_90d_mm"].append(r1(r90))
                    rows["risk_level"].append(level)
                runs[source][str(year)][name] = {k: v for k, v in rows.items() if any(x is not None for x in v)}

    if context_dependent:
        sys.exit(f"{context_dependent} risk levels changed when HAZARD_CONTEXT was neutralised; check for leakage")

    output = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "generator": "scripts/build_replay_backtest.py",
            "primary_run": "forecast",
            "rainfall_source": SOURCES["forecast"]["rainfall_source"],
            "runs": {
                s: {
                    **meta,
                    "drought_signal": DROUGHT_SIGNAL,
                    "rainfall_unavailable_count": unavailable[s],
                    "grid_cells": grid_cells[s],
                    "distinct_grid_cells_flood_districts": len(
                        {tuple(c) for n, c in grid_cells[s].items() if "flood" in districts[n]["hazard_types"]}
                    ),
                }
                for s, meta in SOURCES.items()
            },
            "forecast_model_note": (
                "Production calls api.open-meteo.com/v1/forecast with the default best_match model. "
                "That blend's lead-time archive does not cover 2021-2022 (Previous Runs API returns "
                "nulls), so the forecast run uses JMA GSM (~55 km), the only model found with "
                "lead-time data for both years. Expect it to be coarser than production."
            ),
            "scorer": {
                "file": "risk-flag/main.py",
                "function": "score_risk_fallback",
                "commit": git("log", "-1", "--format=%H", "--", "risk-flag/main.py"),
                "working_tree_clean": git("status", "--porcelain", "--", "risk-flag/main.py") == "",
                "function_sha256": hashlib.sha256(segments["score_risk_fallback"].encode()).hexdigest(),
                "note": (
                    "Production tries Gemini first and only uses this rule-based scorer as a fallback. "
                    "This backtest evaluates the rule-based path only; Gemini was not called."
                ),
            },
            "thresholds": {
                "flood": "high if 3-day rainfall > 100 mm, medium if > 40 mm, else low; low if rainfall missing",
                "glof_avalanche_landslide": "always medium (no rainfall input)",
                "drought": "always low (30/90-day rainfall is reported in the reason text but not used for the level)",
                "verified_by_probe": probe,
                "tuned_on_2022": False,
            },
            "leakage_checks": {
                "hazard_context_mentions_2022_or_later": scan_context_for_leakage(hazard_context),
                "levels_changed_with_neutral_hazard_context": context_dependent,
                "conclusion": (
                    "HAZARD_CONTEXT only feeds the reason text of the rule-based scorer; replacing it "
                    "with empty entries changes no risk level, so nothing in it can leak 2022 outcomes "
                    "into this backtest. It would reach Gemini's prompt, which is not exercised here."
                ),
                "district_selection_caveat": (
                    "The 16 districts and their hazard labels were chosen in 2026 from NDMA material "
                    "that postdates 2022, and the flood list overlaps the 2022 footprint. That choice "
                    "cannot be undone here, so this backtest measures timing and the 2022-vs-2021 "
                    "contrast, not whether the product picks the right districts."
                ),
            },
            "window": {str(y): [window(y)[0].isoformat(), window(y)[1].isoformat()] for y in YEARS},
            "as_of_step_days": STEP_DAYS,
            "evaluation_notes": [
                "impact_reference_date is a documented-by upper bound; true onset may be earlier.",
                "first_high_2022 is the first as-of date flagged high anywhere in the window. For several "
                "districts it falls on an earlier rain spell (early July), so days_first_high_before_reference "
                "is not a lead time for the documented impact.",
                f"outcome looks only at as-of dates from reference-{RUNUP_DAYS} days to the reference date. "
                f"The {RUNUP_DAYS}-day window was chosen after viewing the timelines; the full per-date "
                "series is included so other windows can be checked.",
                "Districts whose hazard is not flood get a constant level from the scorer, so they carry "
                "no timing or year-contrast signal.",
            ],
        },
        "as_of_dates": {str(y): [d.isoformat() for d in dates[y]] for y in YEARS},
        "districts": [
            {"name": n, "province": i["province"], "hazard_types": i["hazard_types"], "coords": list(i["coords"])}
            for n, i in districts.items()
        ],
        "ground_truth": gt_doc["districts"],
        "runs": runs,
        "evaluation": {s: evaluate(runs[s], districts, gt, dates) for s in SOURCES},
    }

    OUTPUT.write_text(json.dumps(output, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nWrote {OUTPUT.relative_to(REPO)} ({OUTPUT.stat().st_size / 1024:.0f} KB)")
    for s in SOURCES:
        print(f"\n[{s}]")
        print(json.dumps(output["evaluation"][s]["summary"], indent=1))


if __name__ == "__main__":
    main()
