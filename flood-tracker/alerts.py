"""
Urdu and Sindhi flood-alert drafts for one village at a time.

``draft_alerts(villages, as_of)`` returns the list inside ``POST /alert-drafts``
(see flood-tracker/CONTRACT.md). Each item is:

    village_id, name, district, urdu, sindhi, source, model

``source`` is ``gemini``, ``qwen``, or ``template``. ``model`` is the model id
when a model phrased the draft, and ``""`` when the hand-written template was
used.

FACTS AND PHRASING
==================
The village record supplies every fact. The model is only allowed to phrase
them.

- Place is ``name``. It is copied into the sentence so a reply that drops the
  village can be rejected.
- District is ``district``.
- The time window is ``eta_low`` and ``eta_high`` when both are present,
  otherwise ``eta``, otherwise ``hours_to_arrival`` rendered as ``30h`` or
  ``-4h``. Hours are not added beside a clock window: a second time figure
  would give the model two facts and the 140-character cap cannot carry both.
- The instruction is "move to higher ground", or "go to {safe_place}" when
  the record names ``safe_place`` or ``shelter``.

Times stay as given. This module does not convert time zones. Callers pass
Asia/Karachi local strings (``YYYY-MM-DDTHH:MM``), matching the contract.

REJECTION
=========
A model reply is kept only when, after whitespace is collapsed:

- it contains the place name exactly,
- it contains every time-window string exactly,
- and it is at most 140 characters.

Otherwise that reply is discarded. The contract has one ``source`` for the
whole draft, so both languages stay on the template unless both replies pass.
A draft never labels a template sentence as model text, or the reverse.

The 140-character cap is the whole sentence. Templates are hand-written Urdu
and Sindhi frames with the facts filled in. They are what ``ALERT_LLM_PROVIDER=none``
returns, and what a missing key, a transport error, or a rejected reply
returns. A one-word draft marker (مسودہ / مسودو) is included when it fits, so
the sentence is not dressed up as an official warning. The cap comes first:
place, time, and the move instruction are kept ahead of the marker and, if
needed, ahead of the district.

PROVIDER SWITCH
===============
``ALERT_LLM_PROVIDER`` chooses the phrasing engine. ``gemini`` (the default),
``qwen``, and ``none`` are the only values. Anything else logs a warning and
uses Gemini. Changing provider is an environment change; callers do not pass
a vendor flag.

- Gemini uses the google-genai SDK the same way risk-flag does: a lazy
  client, ``GEMINI_API_KEY``, ``GEMINI_MODEL`` (default ``gemini-3.8-flash``),
  a 10 second timeout, and a single attempt.
- Qwen is built and left off unless the env selects it. It calls DashScope's
  OpenAI-compatible chat completions endpoint with ``requests``,
  ``DASHSCOPE_API_KEY``, and ``QWEN_MODEL`` (default ``qwen-plus``), with the
  same 10 second timeout and one attempt. There is no retry loop.
- A missing key does not raise and does not call the network. The template
  is the draft.

CACHE
=====
Accepted model sentences are stored in memory under
``(village id, wave id, language, provider name)``. A hit is used only when
it still contains the current place and time window, so a changed ETA is not
served from an old sentence. Rejected replies and templates are not cached.
``wave_id`` (or ``wave``) should be set by the caller; without it the wave
part of the key is empty.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Once, and not inside generate(). A later load with override=False would
# put a key back into the environment after a caller had cleared it.
load_dotenv(Path(__file__).parent / ".env")

logger = logging.getLogger("flood_tracker.alerts")

MAX_ALERT_CHARS = 140
_TIMEOUT_SECS = 10
_TIMEOUT_MS = _TIMEOUT_SECS * 1000
_DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
_DEFAULT_QWEN_MODEL = "qwen-plus"
_QWEN_CHAT_URL = (
    "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
)
_KNOWN_PROVIDERS = ("gemini", "qwen", "none")

# Hand-written frames. Proper nouns and clock times are filled from the record.
_MOVE_URDU_HIGH = "اونچی زمین پر جائیں"
_MOVE_SINDHI_HIGH = "مٿانهين ڌرتي ڏانهن وڃو"
_UNKNOWN_URDU = "آمد کا وقت موجود نہیں"
_UNKNOWN_SINDHI = "اچڻ جو وقت موجود نه آهي"
_DRAFT_URDU = "مسودہ"
_DRAFT_SINDHI = "مسودو"

_CACHE: dict[tuple[str, str, str, str], str] = {}
_cache_lock = threading.Lock()
_client = None
_client_key: str | None = None
_client_lock = threading.Lock()
_logged_defaults: set[str] = set()


class AlertProvider:
    """``generate(prompt) -> text``. Empty text means the template is used.

    ``name`` is the draft ``source`` when the reply is kept (``gemini`` or
    ``qwen``). ``model`` is the model id reported on that draft. One call is
    one attempt; implementations do not retry.
    """

    name = ""
    model = ""

    def generate(self, prompt: str) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class _Facts:
    village_id: str
    place: str
    district: str
    wave_id: str
    time_parts: tuple[str, ...]
    move_urdu: str
    move_sindhi: str
    as_of: str

    @property
    def time_marker(self) -> str:
        return " to ".join(self.time_parts)


def clear_alert_cache() -> None:
    """Drop cached sentences. Tests use this; the process cache otherwise lives
    until restart."""
    with _cache_lock:
        _CACHE.clear()


def reply_acceptable(text: str, place: str, time_parts: tuple[str, ...] | list[str]) -> bool:
    """True when ``text`` is a usable alert sentence for this place and window.

    Whitespace is collapsed first. The place and each time string must occur
    exactly. The collapsed sentence must be 1..140 characters. A missing
    place, a missing time part, or an empty time window fails the check.
    """
    cleaned = _collapse(text)
    if not cleaned or len(cleaned) > MAX_ALERT_CHARS:
        return False
    if not place or place not in cleaned:
        return False
    parts = tuple(time_parts)
    if not parts or any(not part or part not in cleaned for part in parts):
        return False
    return True


def select_provider() -> AlertProvider | None:
    """Build the provider named by ``ALERT_LLM_PROVIDER``.

    Unset or blank uses Gemini and logs that fallback once. ``none`` returns
    None so the caller stays on the template. An unknown value logs a warning
    and uses Gemini. The key is not required to select a provider; a missing
    key is handled inside ``generate``.
    """
    raw = os.getenv("ALERT_LLM_PROVIDER")
    if raw is None or not raw.strip():
        _note_default("ALERT_LLM_PROVIDER", "gemini")
        return GeminiProvider()
    choice = raw.strip().lower()
    if choice == "none":
        return None
    if choice == "qwen":
        return QwenProvider()
    if choice == "gemini":
        return GeminiProvider()
    logger.warning(
        "ALERT_LLM_PROVIDER=%r is unknown; using gemini",
        raw.strip(),
    )
    return GeminiProvider()


class GeminiProvider(AlertProvider):
    """google-genai client, created on the first keyed call and reused."""

    name = "gemini"

    @property
    def model(self) -> str:
        return _env_or_default("GEMINI_MODEL", _DEFAULT_GEMINI_MODEL)

    def generate(self, prompt: str) -> str:
        client = _get_gemini_client()
        if client is None:
            return ""
        try:
            from google.genai import types

            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2),
            )
            text = getattr(response, "text", None) or ""
        except Exception as exc:
            logger.warning("Gemini alert call failed: %s", type(exc).__name__)
            return ""
        return str(text).strip()


class QwenProvider(AlertProvider):
    """DashScope OpenAI-compatible chat completions. Off unless selected."""

    name = "qwen"

    @property
    def model(self) -> str:
        return _env_or_default("QWEN_MODEL", _DEFAULT_QWEN_MODEL)

    def generate(self, prompt: str) -> str:
        api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
        if not api_key:
            _note_missing_key("DASHSCOPE_API_KEY")
            return ""
        try:
            import requests

            response = requests.post(
                _QWEN_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "temperature": 0.2,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=_TIMEOUT_SECS,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            logger.warning("Qwen alert call failed: %s", type(exc).__name__)
            return ""
        return _message_text(content)


def draft_alerts(villages, as_of, *, provider: AlertProvider | None = None) -> list[dict]:
    """Draft one Urdu sentence and one Sindhi sentence per village.

    ``villages`` are at-risk records (``id`` or ``village_id``, ``name``,
    ``district``, and the time fields). ``as_of`` is the situation clock and
    is given to the model as context; it is not copied into the sentence.
    Omit ``provider`` in production; it is chosen from ``ALERT_LLM_PROVIDER``.
    ``provider=None`` has the same meaning. Tests pass a provider whose
    ``generate`` returns canned text and does not touch the network.
    """
    chosen = select_provider() if provider is None else provider
    as_of_text = _clock(as_of)
    drafts: list[dict] = []
    try:
        records = list(villages or [])
    except TypeError:
        logger.warning("draft_alerts expected a list of villages")
        return []

    for record in records:
        facts = _facts_from(record, as_of_text)
        if facts is None:
            continue
        drafts.append(_draft_one(facts, chosen))
    return drafts


def _draft_one(facts: _Facts, provider: AlertProvider | None) -> dict:
    urdu_template = _render_template(facts, "urdu")
    sindhi_template = _render_template(facts, "sindhi")
    if provider is None or not facts.time_parts:
        return _row(facts, urdu_template, sindhi_template, "template", "")

    urdu_hit = _lookup(provider, facts, "urdu")
    sindhi_hit = _lookup(provider, facts, "sindhi")
    urdu_text, urdu_ok = (
        (urdu_hit, True) if urdu_hit is not None else _generate(provider, facts, "urdu")
    )
    sindhi_text, sindhi_ok = (
        (sindhi_hit, True)
        if sindhi_hit is not None
        else _generate(provider, facts, "sindhi")
    )
    if urdu_ok and sindhi_ok:
        if urdu_hit is None:
            _remember(provider, facts, "urdu", urdu_text)
        if sindhi_hit is None:
            _remember(provider, facts, "sindhi", sindhi_text)
        return _row(facts, urdu_text, sindhi_text, provider.name, provider.model)
    return _row(facts, urdu_template, sindhi_template, "template", "")


def _row(facts: _Facts, urdu: str, sindhi: str, source: str, model: str) -> dict:
    reported_model = model if source in ("gemini", "qwen") else ""
    return {
        "village_id": facts.village_id,
        "name": facts.place,
        "district": facts.district,
        "urdu": urdu,
        "sindhi": sindhi,
        "source": source,
        "model": reported_model,
    }


def _generate(provider: AlertProvider, facts: _Facts, language: str) -> tuple[str, bool]:
    prompt = _build_prompt(facts, language)
    try:
        raw = provider.generate(prompt)
    except Exception as exc:
        logger.warning(
            "Alert provider %s failed for %s/%s: %s",
            provider.name,
            facts.village_id,
            language,
            type(exc).__name__,
        )
        return "", False
    cleaned = _collapse("" if raw is None else str(raw))
    if reply_acceptable(cleaned, facts.place, facts.time_parts):
        return cleaned, True
    logger.info(
        "Rejected %s reply for %s (%s): %s",
        provider.name,
        facts.village_id,
        language,
        _reject_reason(cleaned, facts.place, facts.time_parts),
    )
    return "", False


def _lookup(provider: AlertProvider, facts: _Facts, language: str) -> str | None:
    key = _cache_key(facts, language, provider.name)
    with _cache_lock:
        cached = _CACHE.get(key)
    if cached and reply_acceptable(cached, facts.place, facts.time_parts):
        return cached
    return None


def _remember(provider: AlertProvider, facts: _Facts, language: str, text: str) -> None:
    key = _cache_key(facts, language, provider.name)
    with _cache_lock:
        _CACHE[key] = text


def _cache_key(facts: _Facts, language: str, provider_name: str) -> tuple[str, str, str, str]:
    return (facts.village_id, facts.wave_id, language, provider_name)


def _build_prompt(facts: _Facts, language: str) -> str:
    language_name = "Urdu" if language == "urdu" else "Sindhi"
    move = facts.move_urdu if language == "urdu" else facts.move_sindhi
    return (
        "You phrase one flood-alert sentence for people in a village beside the Indus in Pakistan.\n"
        f"Write in {language_name}.\n"
        "Use only the facts below. Do not add a place, a district, a time, a number, or a measurement.\n"
        "Do not call this an official NDMA or PDMA warning.\n"
        "The sentence must contain the place name and every time string exactly as written here.\n"
        f"Place name: {facts.place}\n"
        f"District: {facts.district}\n"
        f"Time window: {facts.time_marker}\n"
        f"Instruction: {move}\n"
        f"Reference time (Asia/Karachi): {facts.as_of}\n"
        f"Maximum {MAX_ALERT_CHARS} characters.\n"
        "Reply with the sentence only."
    )


def _render_template(facts: _Facts, language: str) -> str:
    """Fill the hand-written frame. Shorten only to stay within 140 characters.

    Order of what we give up: the draft marker, then the district, then a
    named safe place (the higher-ground instruction replaces it). The place
    and the time window stay, because those are the facts a reader must see.
    """
    move = facts.move_urdu if language == "urdu" else facts.move_sindhi
    short_move = _MOVE_URDU_HIGH if language == "urdu" else _MOVE_SINDHI_HIGH
    unknown = _UNKNOWN_URDU if language == "urdu" else _UNKNOWN_SINDHI
    marker = _DRAFT_URDU if language == "urdu" else _DRAFT_SINDHI
    moves = [move] if move == short_move else [move, short_move]
    heads = [f"{facts.place} ({facts.district})"] if facts.district else []
    heads.append(facts.place)

    candidates: list[str] = []
    for head in heads:
        clock = facts.time_marker if facts.time_parts else unknown
        for instruction in moves:
            sentence = f"{head}: {clock}۔ {instruction}"
            candidates.append(f"{sentence}۔ {marker}")
            candidates.append(sentence)
    for text in candidates:
        if _template_fits(text, facts):
            return text
    core = f"{facts.place}: {facts.time_marker}".strip()
    if len(core) > MAX_ALERT_CHARS:
        logger.warning(
            "Place and time for %s exceed %s characters",
            facts.place,
            MAX_ALERT_CHARS,
        )
    return core


def _template_fits(text: str, facts: _Facts) -> bool:
    if len(text) > MAX_ALERT_CHARS or facts.place not in text:
        return False
    return all(part in text for part in facts.time_parts)


def _facts_from(record, as_of: str) -> _Facts | None:
    if isinstance(record, (str, bytes)) or record is None:
        logger.warning("Skipping a village record that is not an object")
        return None
    if not isinstance(record, dict) and not hasattr(record, "name"):
        logger.warning("Skipping a village record that is not an object")
        return None
    place = _text(_field(record, "name"))
    if not place:
        logger.warning("Skipping a village with no name")
        return None
    village_id = _text(_field(record, "village_id", "id")) or place
    safe = _text(_field(record, "safe_place", "shelter"))
    if safe:
        move_urdu = f"{safe} کی طرف جائیں"
        move_sindhi = f"{safe} ڏانهن وڃو"
    else:
        move_urdu = _MOVE_URDU_HIGH
        move_sindhi = _MOVE_SINDHI_HIGH
    return _Facts(
        village_id=village_id,
        place=place,
        district=_text(_field(record, "district")),
        wave_id=_text(_field(record, "wave_id", "wave")),
        time_parts=_time_parts(record),
        move_urdu=move_urdu,
        move_sindhi=move_sindhi,
        as_of=as_of,
    )


def _time_parts(record) -> tuple[str, ...]:
    low = _clock(_field(record, "eta_low"))
    high = _clock(_field(record, "eta_high"))
    if low and high:
        return (low, high)
    eta = _clock(_field(record, "eta"))
    if eta:
        return (eta,)
    token = _hours_token(_field(record, "hours_to_arrival"))
    if token:
        return (token,)
    return ()


def _hours_token(value) -> str:
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        try:
            number = float(text)
        except ValueError:
            return text
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return ""
    if number.is_integer():
        return f"{int(number)}h"
    return f"{number:.1f}h"


def _field(record, *names):
    for name in names:
        if isinstance(record, dict):
            if name not in record:
                continue
            value = record[name]
        elif hasattr(record, name):
            value = getattr(record, name)
        else:
            continue
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clock(value) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%dT%H:%M")
    return str(value).strip()


def _collapse(text: str) -> str:
    return " ".join(str(text).split())


def _reject_reason(text: str, place: str, time_parts: tuple[str, ...]) -> str:
    if not text:
        return "empty"
    if len(text) > MAX_ALERT_CHARS:
        return f"length {len(text)} exceeds {MAX_ALERT_CHARS}"
    if not place or place not in text:
        return "missing place"
    missing = [part for part in time_parts if part not in text]
    if not time_parts or missing:
        return "missing time"
    return "rejected"


def _message_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        pieces: list[str] = []
        for part in content:
            if isinstance(part, str):
                pieces.append(part)
            elif isinstance(part, dict):
                pieces.append(str(part.get("text") or ""))
        return "".join(pieces).strip()
    return ""


def _env_or_default(name: str, default: str) -> str:
    raw = os.getenv(name, "").strip()
    if raw:
        return raw
    _note_default(name, default)
    return default


def _note_default(name: str, default: str) -> None:
    if name in _logged_defaults:
        return
    logger.info("%s unset; using %s", name, default)
    _logged_defaults.add(name)


def _note_missing_key(name: str) -> None:
    if name in _logged_defaults:
        return
    logger.info("%s not set; alert drafts will use the template", name)
    _logged_defaults.add(name)


def _get_gemini_client():
    """Lazy Gemini client. None when the key is missing or the SDK cannot start.

    The client is rebuilt when the key changes. Timeout is 10 seconds and
    ``attempts=1`` matches risk-flag: a single try, no extra retry.
    """
    global _client, _client_key
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        _note_missing_key("GEMINI_API_KEY")
        return None
    with _client_lock:
        if _client is not None and _client_key == api_key:
            return _client
        try:
            from google import genai
            from google.genai import types
        except Exception:
            logger.exception("google-genai is not installed; using the alert template")
            return None
        try:
            _client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    timeout=_TIMEOUT_MS,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
            _client_key = api_key
            logger.info(
                "Gemini client initialised (model: %s)",
                _env_or_default("GEMINI_MODEL", _DEFAULT_GEMINI_MODEL),
            )
            return _client
        except Exception:
            logger.exception("Failed to initialise Gemini client")
            _client = None
            _client_key = None
            return None
