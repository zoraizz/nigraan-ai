"""
LLM risk reasoning for Nigraan AI's /predict-risk endpoint.

Tries Gemini first, then Grok (xAI) when a key is configured, then the caller
falls back to rule-based scoring.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

import requests
from google import genai
from google.genai import types
from pydantic import BaseModel

logger = logging.getLogger("risk_reasoning")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
_DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
_DEFAULT_GROK_MODEL = "grok-4.3"
_XAI_CHAT_URL = "https://api.x.ai/v1/chat/completions"
_ATTEMPT_TIMEOUT_SECS = 15
_ATTEMPT_TIMEOUT_MS = _ATTEMPT_TIMEOUT_SECS * 1000


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
    source: str  # "gemini" | "grok" | "fallback"
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    error: str | None = None  # "api_error" | "bad_json" when scoring must fall back


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


def _gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", "").strip() or _DEFAULT_GEMINI_MODEL


def _grok_model() -> str:
    return os.getenv("GROK_MODEL", "").strip() or _DEFAULT_GROK_MODEL


def _grok_api_key() -> str | None:
    """Grok runs only when XAI_API_KEY is set. A missing key skips the call."""
    value = os.getenv("XAI_API_KEY", "").strip()
    return value or None


def _failure(error: str) -> ReasoningResult:
    return ReasoningResult(
        risk_level="", rationale="", source="fallback", error=error,
    )


def _success(
    assessment: RiskAssessment,
    *,
    district: str,
    source: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> ReasoningResult:
    if assessment.risk_level not in ("low", "medium", "high"):
        logger.warning(
            "%s returned invalid risk_level %r for %s — defaulting to medium",
            source, assessment.risk_level, district,
        )
        assessment.risk_level = "medium"
    return ReasoningResult(
        risk_level=assessment.risk_level,
        rationale=assessment.rationale,
        source=source,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


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
        _client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=_ATTEMPT_TIMEOUT_MS,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        logger.info("Gemini client initialised (model: %s)", _gemini_model())
        return _client
    except Exception:
        logger.exception("Failed to initialise Gemini client")
        return None


def _call_gemini(district: str, prompt: str) -> ReasoningResult | None:
    """One Gemini attempt. None means no key (not an error)."""
    client = _get_client()
    if client is None:
        return None

    t0 = time.monotonic()
    try:
        response = client.models.generate_content(
            model=_gemini_model(),
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
            "Gemini call failed for %s (%.2fs): %s",
            district, elapsed, type(exc).__name__,
        )
        return _failure("api_error")

    try:
        assessment = RiskAssessment.model_validate_json(response.text)
    except Exception:
        logger.warning("Gemini returned unparseable output for %s", district)
        return _failure("bad_json")

    usage = response.usage_metadata
    prompt_tokens = getattr(usage, "prompt_token_count", None)
    completion_tokens = getattr(usage, "candidates_token_count", None)
    logger.info(
        "Gemini [%s] %.2fs | risk=%s | tokens: prompt=%s completion=%s",
        district, elapsed, assessment.risk_level, prompt_tokens, completion_tokens,
    )
    return _success(
        assessment,
        district=district,
        source="gemini",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def _call_grok(district: str, prompt: str) -> ReasoningResult | None:
    """One Grok attempt. None means no key (skip, not an error)."""
    api_key = _grok_api_key()
    if not api_key:
        return None

    model = _grok_model()
    t0 = time.monotonic()
    try:
        response = requests.post(
            _XAI_CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "temperature": 0.2,
                "reasoning_effort": "none",
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=_ATTEMPT_TIMEOUT_SECS,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        usage = payload.get("usage") or {}
    except Exception as exc:
        elapsed = time.monotonic() - t0
        logger.warning(
            "Grok call failed for %s (%.2fs): %s",
            district, elapsed, type(exc).__name__,
        )
        return _failure("api_error")

    try:
        if isinstance(content, str):
            assessment = RiskAssessment.model_validate_json(content)
        else:
            assessment = RiskAssessment.model_validate(content)
    except Exception:
        logger.warning("Grok returned unparseable output for %s", district)
        return _failure("bad_json")

    elapsed = time.monotonic() - t0
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    logger.info(
        "Grok [%s] %.2fs | model=%s | risk=%s",
        district, elapsed, model, assessment.risk_level,
    )
    return _success(
        assessment,
        district=district,
        source="grok",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def _usable(result: ReasoningResult | None) -> bool:
    return result is not None and result.error is None


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
    """Gemini, then Grok if a key is set. None or ``error`` means use rules.

    A missing Grok key skips that attempt. Each provider is one timed call.
    """
    prompt = _build_prompt(
        district, hazard_types, hazard_context, province,
        rainfall_3d, rainfall_30d, rainfall_90d,
    )

    gemini = _call_gemini(district, prompt)
    if _usable(gemini):
        return gemini

    grok = _call_grok(district, prompt)
    if grok is not None:
        return grok
    return gemini
