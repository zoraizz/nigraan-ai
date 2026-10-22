"""Swappable, bounded vision calls for ground-photo observations.

Providers return validated observations, never routing decisions or scores. The
chain retries malformed output once per provider and moves on immediately for
transport failures. It returns the first valid observation even if it says
irrelevant: the caller must apply the OOD gate and confidence policy.

Clients are lazy and reused, so importing this module needs neither credentials
nor a network. Provider errors are deliberately not logged or exposed because
SDK exceptions may contain request headers or credentials.
"""

from __future__ import annotations

import base64
import io
import json
import math
import os
import re
from threading import Lock
from typing import Protocol

import requests
from PIL import Image

from .prompts import PROMPT
from .schema import VlmObservation

# ---- preparation and validation ----


def prepare_image(pil: Image.Image) -> bytes:
    """Return an RGB JPEG, at most 1024 px on its long side, without EXIF."""
    rgb = pil.convert("RGB")
    rgb.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    rgb.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


class InvalidObservation(ValueError):
    """Malformed JSON or a response that does not match the observation schema."""


class VlmUnavailable(RuntimeError):
    """No configured provider produced a valid observation."""


def parse_observation(text: str) -> VlmObservation:
    """Decode the first JSON object, accepting fences and surrounding prose."""
    try:
        text = re.sub(r"^\s*```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        start = text.index("{")
        payload, _ = json.JSONDecoder().raw_decode(text[start:])
        return VlmObservation.model_validate(payload)
    except (ValueError, TypeError, AttributeError):
        raise InvalidObservation("Invalid vision observation") from None


def _timeout_seconds() -> float:
    try:
        value = float(os.getenv("GROUND_VLM_TIMEOUT_SECONDS", "20"))
        return value if math.isfinite(value) and value >= 0.001 else 20.0
    except ValueError:
        return 20.0


class VisionProvider(Protocol):
    name: str
    model: str

    @property
    def configured(self) -> bool: ...

    def describe(self, jpeg_bytes: bytes) -> VlmObservation: ...


# ---- Gemini (lazy client, timeout in milliseconds) ----


class GeminiProvider:
    name = "gemini"

    def __init__(self) -> None:
        self.model = os.getenv("GEMINI_VL_MODEL", "").strip() or "gemini-3.8-flash"
        self._client = None
        self._lock = Lock()

    @property
    def configured(self) -> bool:
        return bool(os.getenv("GEMINI_API_KEY", "").strip())

    def describe(self, jpeg_bytes: bytes) -> VlmObservation:
        from google import genai
        from google.genai import types

        if not self.configured:
            raise VlmUnavailable("Gemini is not configured")
        with self._lock:
            if self._client is None:
                options = {"timeout": int(_timeout_seconds() * 1000)}
                if hasattr(types, "HttpRetryOptions"):
                    options["retry_options"] = types.HttpRetryOptions(attempts=1)
                self._client = genai.Client(
                    api_key=os.environ["GEMINI_API_KEY"].strip(),
                    http_options=types.HttpOptions(**options),
                )
        config = {
            "response_mime_type": "application/json",
            "response_schema": VlmObservation,
            "temperature": 0.2,
        }
        thinking = getattr(types, "ThinkingConfig", None)
        if thinking is not None:
            fields = thinking.model_fields
            if self.model.startswith("gemini-3"):
                if "thinking_level" in fields:
                    config["thinking_config"] = thinking(thinking_level="LOW")
            elif "thinking_budget" in fields:
                config["thinking_config"] = thinking(thinking_budget=256)
        response = self._client.models.generate_content(
            model=self.model,
            contents=[types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"), PROMPT],
            config=types.GenerateContentConfig(**config),
        )
        return parse_observation(response.text)


# ---- DashScope OpenAI-compatible endpoint ----


class QwenDashScopeProvider:
    name = "qwen"

    def __init__(self) -> None:
        self.model = os.getenv("DASHSCOPE_VL_MODEL", "").strip() or "qwen3-vl-plus"

    @property
    def configured(self) -> bool:
        return bool(os.getenv("DASHSCOPE_API_KEY", "").strip())

    def describe(self, jpeg_bytes: bytes) -> VlmObservation:
        if not self.configured:
            raise VlmUnavailable("DashScope is not configured")
        base = os.getenv("DASHSCOPE_BASE_URL", "").strip() or (
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        )
        encoded = base64.b64encode(jpeg_bytes).decode("ascii")
        response = requests.post(
            f"{base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['DASHSCOPE_API_KEY'].strip()}"},
            json={
                "model": self.model,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}},
                ]}],
            },
            timeout=_timeout_seconds(),
        )
        response.raise_for_status()
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise InvalidObservation("Invalid DashScope response") from None
        return parse_observation(content)


# ---- ordered fallback; test overrides never construct real providers ----

_test_providers: list[VisionProvider] | None = None
_providers: dict[str, VisionProvider] = {}
_providers_lock = Lock()


def set_providers_for_tests(providers: list[VisionProvider] | None) -> None:
    """Inject an ordered list; None restores environment-selected providers."""
    global _test_providers
    _test_providers = None if providers is None else list(providers)


def _configured_chain() -> list[VisionProvider]:
    if _test_providers is not None:
        return _test_providers
    chain = []
    factories = {"gemini": GeminiProvider, "qwen": QwenDashScopeProvider}
    with _providers_lock:
        for name in os.getenv("GROUND_VLM_PROVIDERS", "gemini").split(","):
            name = name.strip().lower()
            if name == "dashscope":
                name = "qwen"
            if name not in factories:
                continue
            if name not in _providers:
                _providers[name] = factories[name]()
            if _providers[name] not in chain:
                chain.append(_providers[name])
    return chain


def describe_with_chain(jpeg: bytes) -> tuple[VlmObservation, str, str]:
    for provider in _configured_chain():
        if not provider.configured:
            continue
        for _ in range(2):
            try:
                observation = provider.describe(jpeg)
                if not isinstance(observation, VlmObservation):
                    raise InvalidObservation("Provider did not return an observation")
                return observation, provider.name, provider.model
            except InvalidObservation:
                continue
            except Exception:
                break
    raise VlmUnavailable("No vision provider produced a valid observation") from None
