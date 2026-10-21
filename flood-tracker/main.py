r"""
FastAPI serving endpoint for the River Flood Tracker.

Endpoints:
    GET /flood-situation  -- where each Indus flood wave is, ETAs of its peak
                             at every barrage and village downstream, and
                             who is at risk (CONTRACT.md shape)
    GET /replay/2022      -- one /flood-situation per day at 06:00 for the
                             2022 floods, plus a predicted-vs-actual scorecard
    GET /health           -- service status, data files present, LLM config

Run:
    uvicorn main:app --host 0.0.0.0 --port 8003

All routing logic lives in routing.py (pure functions, no IO except its
loader). This module only loads the data files once at startup, validates
query parameters and shapes the HTTP responses.

Modes:
    replay -- as_of is a point inside the 2022 flows data. Every number is
              computed from readings at or before as_of only (no look-ahead).
    live   -- not enabled: there is no live FFC feed wired in yet, so the
              endpoint returns 501 rather than presenting replay data as live.

Environment variables (loaded from flood-tracker/.env, see .env.example):
    CORS_ORIGINS        -- comma-separated browser origins (default
                           http://localhost:5173)
    FLOOD_DATA_DIR      -- directory with flows_2022.csv, barrages.json,
                           reaches.json and optionally villages.json and
                           indus.geojson (default flood-tracker/data)
    ALERT_LLM_PROVIDER  -- gemini | qwen | template (default gemini). Only
                           reported by /health here; alert drafting lives in
                           alerts.py.
    GEMINI_API_KEY, GEMINI_MODEL, DASHSCOPE_API_KEY, QWEN_MODEL
                        -- LLM settings for alerts.py. /health reports only
                           whether a key is set, never the key.

Error responses use a unified structure:
    { "error": { "code": "<machine-readable>", "message": "<human-readable>" } }
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Load .env from the flood-tracker directory (same pattern as aid-priority).
load_dotenv(Path(__file__).parent / ".env")

import routing  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("flood_tracker")

app = FastAPI(
    title="Nigraan AI - River Flood Tracker",
    description="Indus flood-wave peaks, barrage and village ETAs, 2022 replay",
    version="0.1.0",
)

# CORS -- allow the dashboard frontend to call this API from the browser.
# An empty CORS_ORIGINS (as copied from .env.example) means the default.
_allowed_origins = [
    origin.strip()
    for origin in (os.environ.get("CORS_ORIGINS") or "http://localhost:5173").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Configuration (env-configurable; see .env.example)
# ---------------------------------------------------------------------------
LLM_PROVIDERS = {"gemini": "GEMINI_API_KEY", "qwen": "DASHSCOPE_API_KEY", "template": None}
DEFAULT_LLM_PROVIDER = "gemini"


def _load_provider() -> str:
    raw = os.environ.get("ALERT_LLM_PROVIDER")
    if not raw:
        return DEFAULT_LLM_PROVIDER
    value = raw.strip().lower()
    if value not in LLM_PROVIDERS:
        logger.warning(
            "Invalid ALERT_LLM_PROVIDER=%r (must be one of %s); using default %s",
            raw, sorted(LLM_PROVIDERS), DEFAULT_LLM_PROVIDER,
        )
        return DEFAULT_LLM_PROVIDER
    return value


def _load_data_dir() -> Path:
    default = Path(__file__).parent / "data"
    raw = os.environ.get("FLOOD_DATA_DIR")
    if not raw:
        return default
    path = Path(raw)
    if not path.is_dir():
        logger.warning("FLOOD_DATA_DIR=%r is not a directory; using default %s", raw, default)
        return default
    return path


LLM_PROVIDER = _load_provider()
DATA_DIR = _load_data_dir()

DATA_FILES = {
    "flows_2022.csv": DATA_DIR / "flows_2022.csv",
    "barrages.json": DATA_DIR / "barrages.json",
    "reaches.json": DATA_DIR / "reaches.json",
    "villages.json": DATA_DIR / "villages.json",
    "indus.geojson": DATA_DIR / "indus.geojson",
}
REQUIRED_FILES = ("flows_2022.csv", "barrages.json", "reaches.json")


def _load() -> tuple:
    missing = [n for n in REQUIRED_FILES if not DATA_FILES[n].exists()]
    if missing:
        return None, f"required data file(s) missing in {DATA_DIR}: {', '.join(missing)}"
    try:
        data = routing.load_data(
            DATA_FILES["barrages.json"],
            DATA_FILES["reaches.json"],
            DATA_FILES["flows_2022.csv"],
            DATA_FILES["villages.json"],
            DATA_FILES["indus.geojson"],
        )
        start, end = routing.data_range(data)
    except Exception as exc:  # noqa: BLE001 -- surfaced via /health and 503s
        logger.exception("Failed to load flood data from %s", DATA_DIR)
        return None, f"could not load flood data: {exc}"
    logger.info(
        "Loaded flood data from %s: %s to %s, villages=%s, geojson=%s",
        DATA_DIR, routing.fmt_time(start), routing.fmt_time(end),
        data.villages is not None, data.river_coords is not None,
    )
    return data, None


DATA, DATA_ERROR = _load()
_replay_cache: Optional[dict] = None


# ---------------------------------------------------------------------------
# Response models (CONTRACT.md)
# ---------------------------------------------------------------------------
class BarrageState(BaseModel):
    name: str
    order: int
    lat: float
    lon: float
    inflow_cusecs: float
    outflow_cusecs: float
    category: str
    trend: str


class ReachState(BaseModel):
    from_: str = Field(alias="from")
    to: str
    category: str
    coords: list[list[float]]


class Peak(BaseModel):
    barrage: str
    wave_id: str
    wave_label: Optional[str]
    status: str
    peak_time: str
    peak_outflow_cusecs: float


class Eta(BaseModel):
    wave_id: str
    wave_label: Optional[str]
    from_barrage: str
    barrage: str
    status: str
    eta: str
    eta_low: str
    eta_high: str
    hours_from_now: float
    observed_time: Optional[str] = None


class AtRiskVillage(BaseModel):
    id: str
    name: str
    district: str
    lat: float
    lon: float
    eta: str
    eta_low: str
    eta_high: str
    hours_to_arrival: float
    population: float
    population_source: str


class DataProvenance(BaseModel):
    flows: str
    etas: str
    villages: str
    population: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
    )


def _data_unavailable() -> JSONResponse:
    return _error(503, "data_unavailable", DATA_ERROR or "flood data not loaded")


def _validate_situation(body: dict) -> dict:
    """Validate against the contract models; returns the body unchanged."""
    for b in body["barrages"]:
        BarrageState(**b)
    for r in body["reaches"]:
        ReachState(**r)
    for p in body["peaks"]:
        Peak(**p)
    for e in body["etas"]:
        Eta(**e)
    for v in body["at_risk_villages"]:
        AtRiskVillage(**v)
    DataProvenance(**body["data_provenance"])
    return body


@app.get("/flood-situation")
def flood_situation(mode: str = "replay", as_of: Optional[str] = None):
    """Flood situation at as_of (CONTRACT.md).

    mode=replay (default): as_of is "YYYY-MM-DDTHH:MM" Asia/Karachi inside
    the flows data; defaults to the last reading. mode=live returns 501.
    """
    mode = (mode or "").strip().lower()
    if mode == "live":
        return _error(
            501, "live_not_enabled",
            "live mode is not enabled: no live FFC feed is wired in; use mode=replay",
        )
    if mode != "replay":
        return _error(422, "invalid_mode", f"mode must be 'replay' or 'live', got {mode!r}")
    if DATA is None:
        return _data_unavailable()

    if as_of is None or not as_of.strip():
        _, as_of_dt = routing.data_range(DATA)
    else:
        try:
            as_of_dt = routing.parse_time(as_of)
        except ValueError as exc:
            return _error(422, "invalid_as_of", str(exc))

    try:
        body = routing.situation(DATA, as_of_dt, mode="replay")
    except routing.AsOfOutOfRange as exc:
        return _error(422, "as_of_out_of_range", str(exc))

    logger.info(
        "Situation %s: %d peak(s), %d ETA(s), %d village(s) at risk",
        body["as_of"], len(body["peaks"]), len(body["etas"]), len(body["at_risk_villages"]),
    )
    return _validate_situation(body)


@app.get("/replay/2022")
def replay_2022():
    """Daily 06:00 situations for the 2022 floods plus the scorecard.

    Computed once on first request and cached for the life of the process.
    """
    global _replay_cache
    if DATA is None:
        return _data_unavailable()
    if _replay_cache is None:
        _replay_cache = routing.replay_2022(DATA)
        for step in _replay_cache["steps"]:
            _validate_situation(step)
        logger.info(
            "Replay 2022 computed: %d step(s), %d scorecard row(s)",
            len(_replay_cache["steps"]), len(_replay_cache["scorecard"]),
        )
    return _replay_cache


@app.get("/health")
def health():
    key_env = LLM_PROVIDERS[LLM_PROVIDER]
    data_range = None
    if DATA is not None:
        start, end = routing.data_range(DATA)
        data_range = {"start": routing.fmt_time(start), "end": routing.fmt_time(end)}
    return {
        "status": "ok" if DATA is not None else "degraded",
        "data_files": {name: path.exists() for name, path in DATA_FILES.items()},
        "data_range": data_range,
        "data_error": DATA_ERROR,
        "llm_provider": LLM_PROVIDER,
        "llm_configured": bool(key_env and os.environ.get(key_env, "").strip()),
    }
