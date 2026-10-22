"""Throwaway probe for Gemini's ground-photo JSON and latency.

Step 1 only. The prompt and the Pydantic model stay in this file so we can
see what gemini-3.8-flash actually returns, and how long it takes, before
the intake package exists. Step 3 moves both into damage-checker/ground_intake/.

The model fills observation fields only (image_kind through confidence).
Urgent, scores, ids, locations, and review state are decided later in code
and are intentionally absent from this schema.

Usage (from the repo root, with damage-checker/.env holding GEMINI_API_KEY):

    damage-checker\\.venv\\Scripts\\python.exe damage-checker\\scripts\\try_vlm.py path\\to\\photo.jpg

GEMINI_VL_MODEL overrides the model name. The default is gemini-3.8-flash.

Thinking budget
---------------
Gemini 3.5 and newer reject thinking_budget and want thinking_level. This
script sets thinking_level to LOW for those models (including the default
gemini-3.8-flash) and a small token budget for older names. If the installed
SDK has neither knob, the call goes out without one.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image
from pydantic import BaseModel, Field, ValidationError

# ---- config ----

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
_DEFAULT_MODEL = "gemini-3.8-flash"
_LONG_SIDE_PX = 1024
_JPEG_QUALITY = 85
# Older Gemini models still take a token budget. 256 is a low cap, not "off"
# (0 disables thinking). Gemini 3.5+ uses thinking_level instead.
_LOW_THINKING_BUDGET = 256
_THINKING_LEVEL_MIN = (3, 5)

# ---- schema (fields the model fills) ----

ImageKind = Literal["ground_disaster", "aerial_or_satellite", "irrelevant"]
SceneType = Literal[
    "flooded_street",
    "flooded_farmland",
    "collapsed_house",
    "damaged_building",
    "damaged_road",
    "broken_bridge",
    "landslide",
    "debris",
    "relief_camp",
    "other_disaster",
]
DamageLevel = Literal["none", "partial", "destroyed"]
WaterDepth = Literal["none", "ankle", "knee", "waist", "chest", "above_head"]
Hazard = Literal[
    "blocked_road",
    "downed_power_lines",
    "unstable_structure",
    "fast_water",
    "fire",
]
Need = Literal["rescue", "shelter", "medical", "food_water", "road_clearance"]


class WaterObservation(BaseModel):
    present: bool
    flowing: bool
    depth: WaterDepth


class PeopleObservation(BaseModel):
    visible: bool
    count_estimate: int | None = Field(
        ge=0,
        description="Integer headcount, or null when nobody is visible or the count is unclear.",
    )
    stranded_or_trapped: bool
    on_rooftop: bool
    injured: bool


class AnimalsObservation(BaseModel):
    livestock_visible: bool
    livestock_at_risk: bool


class GroundObservation(BaseModel):
    """Closed observation the vision model is allowed to fill."""

    image_kind: ImageKind
    image_confidence: float = Field(ge=0.0, le=1.0)
    scene_type: SceneType
    damage_level: DamageLevel
    water: WaterObservation
    hazards: list[Hazard]
    people: PeopleObservation
    animals: AnimalsObservation
    needs: list[Need]
    summary: str = Field(
        description="One or two sentences on damage and needs only.",
    )
    confidence: float = Field(ge=0.0, le=1.0)


PROMPT = """Return JSON only, matching the response schema. No markdown and no extra keys.

Decide image_kind:
- ground_disaster: a ground-level photograph of a disaster (flood, collapse, debris, landslide, damaged road or bridge, relief camp).
- aerial_or_satellite: an overhead, drone, aerial, or satellite view.
- irrelevant: anything else.

Describe damage, hazards, and needs only. Never identify, name, or describe the faces of individuals. If people are visible, record only a count and whether anyone appears stranded, on a rooftop, or injured. Do not describe appearance, clothing, or identity.

Use false, "none", an empty list, or null when you are unsure. Do not guess. image_confidence and confidence are numbers from 0 to 1. summary is one or two sentences about damage and needs only.
"""


# ---- image prep ----

def encode_jpeg(path: Path) -> bytes:
    """Open an image, convert to RGB, cap the long side at 1024 px, JPEG q=85."""
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        rgb.thumbnail((_LONG_SIDE_PX, _LONG_SIDE_PX), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        rgb.save(buffer, format="JPEG", quality=_JPEG_QUALITY)
        return buffer.getvalue()


# ---- model call ----

def _model_version(model: str) -> tuple[int, int] | None:
    match = re.search(r"gemini-(\d+)(?:\.(\d+))?", model.lower())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2) or 0)


def _thinking_config(model: str) -> types.ThinkingConfig | None:
    """Low thinking when the SDK exposes a knob this model accepts."""
    if not hasattr(types, "ThinkingConfig"):
        return None
    version = _model_version(model)
    if version is not None and version >= _THINKING_LEVEL_MIN:
        level_enum = getattr(types, "ThinkingLevel", None)
        low = getattr(level_enum, "LOW", None) if level_enum is not None else None
        if low is None:
            return None
        return types.ThinkingConfig(thinking_level=low, include_thoughts=False)
    return types.ThinkingConfig(
        thinking_budget=_LOW_THINKING_BUDGET,
        include_thoughts=False,
    )


def _public_error(exc: BaseException, api_key: str) -> str:
    text = f"{type(exc).__name__}: {exc}"
    if api_key:
        text = text.replace(api_key, "[redacted]")
    return text


def _generate(client: genai.Client, model: str, jpeg: bytes, api_key: str) -> tuple[float, str]:
    config_kwargs: dict = {
        "response_mime_type": "application/json",
        "response_schema": GroundObservation,
        "temperature": 0.2,
    }
    thinking = _thinking_config(model)
    if thinking is not None:
        config_kwargs["thinking_config"] = thinking

    started = time.perf_counter()
    try:
        response = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"),
                PROMPT,
            ],
            config=types.GenerateContentConfig(**config_kwargs),
        )
    except Exception as exc:
        elapsed = time.perf_counter() - started
        raise RuntimeError(f"{elapsed:.2f}s {_public_error(exc, api_key)}") from exc
    elapsed = time.perf_counter() - started
    return elapsed, response.text or ""


def _print_result(label: str, elapsed: float, raw: str) -> bool:
    print(f"{label}  {elapsed:.2f}s")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        print(raw)
        print("error: response was not JSON", file=sys.stderr)
        return False
    try:
        GroundObservation.model_validate(payload)
    except ValidationError as exc:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"error: schema mismatch: {exc}", file=sys.stderr)
        return False
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return True


def main(argv: list[str] | None = None) -> int:
    load_dotenv(_ENV_PATH)
    parser = argparse.ArgumentParser(
        description="Send local images to Gemini and print schema JSON plus latency.",
    )
    parser.add_argument("images", nargs="+", type=Path, help="One or more image paths.")
    args = parser.parse_args(argv)

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print(
            "GEMINI_API_KEY is not set. Put it in damage-checker/.env.",
            file=sys.stderr,
        )
        return 1
    model = os.getenv("GEMINI_VL_MODEL", "").strip() or _DEFAULT_MODEL
    client = genai.Client(api_key=api_key)

    failed = False
    for index, path in enumerate(args.images):
        if index:
            print()
        if not path.is_file():
            print(f"{path}  error: file not found", file=sys.stderr)
            failed = True
            continue
        try:
            jpeg = encode_jpeg(path)
            elapsed, raw = _generate(client, model, jpeg, api_key)
        except Exception as exc:
            print(f"{path}  {_public_error(exc, api_key)}", file=sys.stderr)
            failed = True
            continue
        if not _print_result(str(path), elapsed, raw):
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
