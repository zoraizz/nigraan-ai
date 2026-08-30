"""
Gemini-based risk reasoning for Nigraan AI's /predict-risk endpoint.

Uses Google's Gemini (via the google-genai SDK) to classify disaster risk
from rainfall data + static NDMA hazard context.  Falls back to rule-based
scoring when the API key is missing or the LLM call fails.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass

from google import genai
from google.genai import types
from pydantic import BaseModel

logger = logging.getLogger("risk_reasoning")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GEMINI_MODEL = "gemini-2.0-flash"
_GEMINI_TIMEOUT_SECS = 15


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------
class RiskAssessment(BaseModel):
    """Structured output schema requested from Gemini."""

    risk_level: str  # "low" | "medium" | "high"
    rationale: str


@dataclass
class ReasoningResult:
    """Return type for the reasoning layer."""

    risk_level: str
    rationale: str
    source: str  # "gemini" or "fallback"
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------
def _build_context_block(
    district: str,
    hazard_types: list[str],
    hazard_context: dict[str, dict],
    province: str,
) -> str:
    """Assemble the NDMA hazard context section of the prompt."""
    lines = [f"District: {district} ({province}, Pakistan)"]
    lines.append(f"Hazard types: {', '.join(hazard_types)}")
    lines.append("")

    for ht in hazard_types:
        ctx = hazard_context.get(ht, {})
        if ctx:
            lines.append(f"[{ht.upper()}]")
            lines.append(f"  {ctx.get('description', 'No description.')}")
            high_risk = ctx.get("high_risk_districts", [])
            lines.append(f"  High-risk districts: {', '.join(high_risk)}")
            lines.append(f"  Source: {ctx.get('source', 'NDMA reference')}")
            lines.append("")

    return "\n".join(lines)


def _build_rainfall_block(
    rainfall_3d: float | None,
    rainfall_30d: float | None,
    rainfall_90d: float | None,
) -> str:
    """Assemble the rainfall data section of the prompt."""
    parts: list[str] = []
    if rainfall_3d is not None:
        parts.append(f"3-day rainfall forecast: {rainfall_3d:.1f} mm")
    if rainfall_30d is not None:
        parts.append(f"30-day cumulative rainfall (historical): {rainfall_30d:.1f} mm")
    if rainfall_90d is not None:
        parts.append(f"90-day cumulative rainfall (historical): {rainfall_90d:.1f} mm")
    if not parts:
        return "No rainfall data available for this district."
    return "\n".join(parts)


def _build_prompt(
    district: str,
    hazard_types: list[str],
    hazard_context: dict[str, dict],
    province: str,
    rainfall_3d: float | None,
    rainfall_30d: float | None,
    rainfall_90d: float | None,
) -> str:
    """Build the full prompt sent to Gemini."""
    ctx = _build_context_block(district, hazard_types, hazard_context, province)
    rain = _build_rainfall_block(rainfall_3d, rainfall_30d, rainfall_90d)

    return (
        "You are a disaster risk analyst for Pakistan's National Disaster "
        "Management Authority (NDMA). Based on the information below, classify "
        "the current disaster risk level for this district.\n\n"
        "## District & Hazard Context\n"
        f"{ctx}\n"
        "## Rainfall Data\n"
        f"{rain}\n\n"
        "Respond with a JSON object containing exactly two fields:\n"
        '- "risk_level": one of "low", "medium", or "high"\n'
        '- "rationale": a single sentence explaining your assessment\n\n'
        "Consider the district's hazard history, current rainfall, and "
        "vulnerability profile. Do not include any text outside the JSON."
    )


# ---------------------------------------------------------------------------
# Gemini client (lazy singleton)
# ---------------------------------------------------------------------------
_client: genai.Client | None = None


def _get_client() -> genai.Client | None:
    """Return a cached Gemini client, or None if no API key is configured."""
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.info("GEMINI_API_KEY not set — LLM reasoning disabled")
        return None

    try:
        _client = genai.Client(api_key=api_key)
        logger.info("Gemini client initialised (model: %s)", GEMINI_MODEL)
        return _client
    except Exception:
        logger.exception("Failed to initialise Gemini client")
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def assess_risk_with_gemini(
    district: str,
    hazard_types: list[str],
    hazard_context: dict[str, dict],
    province: str,
    rainfall_3d: float | None = None,
    rainfall_30d: float | None = None,
    rainfall_90d: float | None = None,
) -> ReasoningResult | None:
    """Call Gemini for risk reasoning.

    Returns a ``ReasoningResult`` on success, or ``None`` if the call
    should fall back to rule-based scoring (no key, timeout, bad output).
    """
    client = _get_client()
    if client is None:
        return None

    prompt = _build_prompt(
        district, hazard_types, hazard_context, province,
        rainfall_3d, rainfall_30d, rainfall_90d,
    )

    t0 = time.monotonic()
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=RiskAssessment,
                temperature=0.2,
            ),
        )
        elapsed = time.monotonic() - t0
    except Exception as exc:
        elapsed = time.monotonic() - t0
        logger.warning(
            "Gemini call failed for %s (%.2fs): %s", district, elapsed, exc,
        )
        return None

    # ── Parse response ─────────────────────────────────────────────────
    try:
        assessment = RiskAssessment.model_validate_json(response.text)
    except Exception as exc:
        elapsed = time.monotonic() - t0
        logger.warning(
            "Gemini returned unparseable output for %s (%.2fs): %s — raw: %s",
            district, elapsed, exc, response.text[:200],
        )
        return None

    # Normalise risk level
    if assessment.risk_level not in ("low", "medium", "high"):
        logger.warning(
            "Gemini returned invalid risk_level '%s' for %s — defaulting to medium",
            assessment.risk_level, district,
        )
        assessment.risk_level = "medium"

    # ── Token usage ────────────────────────────────────────────────────
    usage = response.usage_metadata
    prompt_tokens = getattr(usage, "prompt_token_count", None)
    completion_tokens = getattr(usage, "candidates_token_count", None)
    total_tokens = getattr(usage, "total_token_count", None)

    logger.info(
        "Gemini [%s] %.2fs | risk=%s | tokens: prompt=%s completion=%s total=%s",
        district, elapsed, assessment.risk_level,
        prompt_tokens, completion_tokens, total_tokens,
    )

    return ReasoningResult(
        risk_level=assessment.risk_level,
        rationale=assessment.rationale,
        source="gemini",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
