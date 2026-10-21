"""
Alert-draft tests. No network.

Usage (from flood-tracker/):
    python tests/test_alerts.py unit

Also pytest-compatible: pytest tests/test_alerts.py
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import alerts  # noqa: E402
from alerts import (  # noqa: E402
    GeminiProvider,
    QwenProvider,
    clear_alert_cache,
    draft_alerts,
    reply_acceptable,
    select_provider,
)

AS_OF = "2022-08-31T06:00"
LOW = "2022-09-01T06:00"
HIGH = "2022-09-01T18:00"
_ENV_KEYS = (
    "ALERT_LLM_PROVIDER",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "DASHSCOPE_API_KEY",
    "QWEN_MODEL",
)
_DRAFT_KEYS = {"village_id", "name", "district", "urdu", "sindhi", "source", "model"}


class _Env:
    """Save the provider env, then start each test with those keys unset."""

    def __enter__(self):
        self._saved = {key: os.environ.get(key) for key in _ENV_KEYS}
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
        clear_alert_cache()
        alerts._client = None
        alerts._client_key = None
        return self

    def __exit__(self, *_exc):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        clear_alert_cache()
        alerts._client = None
        alerts._client_key = None
        return False

    def set(self, **updates):
        for key, value in updates.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)


class _Scripted(alerts.AlertProvider):
    """Canned generate() for tests. Never opens a socket."""

    name = "gemini"
    model = "fake-model"

    def __init__(self, replies):
        self._replies = list(replies)
        self.prompts = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self._replies:
            return ""
        return self._replies.pop(0)


def _village(**extra):
    record = {
        "id": "rajanpur-rojhan",
        "name": "Rojhan",
        "district": "Rajanpur",
        "wave_id": "indus-2022-w1",
        "eta_low": LOW,
        "eta_high": HIGH,
        "hours_to_arrival": 30,
    }
    record.update(extra)
    return record


def _assert_template(draft):
    assert set(draft) == _DRAFT_KEYS, "draft keys must match the contract"
    assert draft["village_id"] == "rajanpur-rojhan"
    assert draft["name"] == "Rojhan"
    assert draft["district"] == "Rajanpur"
    assert draft["source"] == "template"
    assert draft["model"] == ""
    for language in ("urdu", "sindhi"):
        text = draft[language]
        assert "Rojhan" in text, language + " dropped the place"
        assert "Rajanpur" in text, language + " dropped the district"
        assert LOW in text and HIGH in text, language + " dropped the time window"
        assert len(text) <= 140, language + " template exceeds 140 characters"
    assert "اونچی زمین پر جائیں" in draft["urdu"], "urdu move instruction changed"
    assert "مٿانهين ڌرتي ڏانهن وڃو" in draft["sindhi"], "sindhi move instruction changed"
    assert "مسودہ" in draft["urdu"]
    assert "مسودو" in draft["sindhi"]
    assert draft["urdu"] != draft["sindhi"]


def test_template_fallback_without_a_key():
    """No Gemini key and no DashScope key: both providers stay on the template."""
    import requests

    calls = []
    original = requests.post

    def blocked(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("alert test attempted a network call")

    requests.post = blocked
    try:
        with _Env() as env:
            env.set(ALERT_LLM_PROVIDER="gemini")
            gemini = draft_alerts([_village()], AS_OF)
            _assert_template(gemini[0])
            assert alerts._client is None, "missing Gemini key must not build a client"

            env.set(ALERT_LLM_PROVIDER="qwen")
            qwen = draft_alerts([_village()], AS_OF)
            _assert_template(qwen[0])
            assert calls == [], "missing DashScope key must not call DashScope"
    finally:
        requests.post = original


def test_named_safe_place_and_hours_only_window():
    with _Env() as env:
        env.set(ALERT_LLM_PROVIDER="none")
        named = draft_alerts([_village(safe_place="Bund Road")], AS_OF)[0]
        assert named["source"] == "template"
        assert "Bund Road" in named["urdu"]
        assert "Bund Road" in named["sindhi"]
        assert "کی طرف جائیں" in named["urdu"]
        assert "ڏانهن وڃو" in named["sindhi"]
        assert "اونچی" not in named["urdu"]

        hours_only = _village()
        for key in ("eta", "eta_low", "eta_high"):
            hours_only.pop(key, None)
        hours = draft_alerts([hours_only], AS_OF)[0]
        assert "30h" in hours["urdu"] and "30h" in hours["sindhi"]
        assert hours["source"] == "template"

        untimed = _village()
        for key in ("eta", "eta_low", "eta_high", "hours_to_arrival"):
            untimed.pop(key, None)
        provider = _Scripted(["do not call"])
        missing = draft_alerts([untimed], AS_OF, provider=provider)[0]
        assert provider.prompts == [], "a village with no time must not call the model"
        assert missing["source"] == "template"
        assert "موجود نہیں" in missing["urdu"]
        assert "Rojhan" in missing["urdu"] and "Rojhan" in missing["sindhi"]


def test_validation_rejects_missing_place_name():
    bad = f"سیلابی لہر {LOW} to {HIGH}"
    assert not reply_acceptable(bad, "Rojhan", (LOW, HIGH))
    with _Env():
        provider = _Scripted([bad, bad])
        draft = draft_alerts([_village()], AS_OF, provider=provider)[0]
        assert draft["source"] == "template"
        assert draft["model"] == ""
        assert "Rojhan" in draft["urdu"]
        assert LOW in draft["urdu"] and HIGH in draft["urdu"]


def test_validation_rejects_reply_over_140_characters():
    prefix = f"Rojhan {LOW} {HIGH} "
    exact = prefix + ("ا" * (140 - len(prefix)))
    assert len(exact) == 140
    assert reply_acceptable(exact, "Rojhan", (LOW, HIGH))
    over = exact + "ا"
    assert len(over) == 141
    assert not reply_acceptable(over, "Rojhan", (LOW, HIGH))
    assert "Rojhan" in over and LOW in over and HIGH in over

    with _Env():
        provider = _Scripted([over, over])
        draft = draft_alerts([_village()], AS_OF, provider=provider)[0]
        assert draft["source"] == "template"
        assert len(draft["urdu"]) <= 140
        assert len(draft["sindhi"]) <= 140
        assert "Rojhan" in draft["urdu"] and LOW in draft["urdu"]


def test_validation_rejects_reply_missing_the_time():
    place_only = "Rojhan اونچی زمین پر جائیں"
    one_end = f"Rojhan {LOW} اونچی زمین پر جائیں"
    assert not reply_acceptable(place_only, "Rojhan", (LOW, HIGH))
    assert not reply_acceptable(one_end, "Rojhan", (LOW, HIGH))
    with _Env():
        provider = _Scripted([one_end, one_end])
        draft = draft_alerts([_village()], AS_OF, provider=provider)[0]
        assert draft["source"] == "template"
        assert LOW in draft["urdu"] and HIGH in draft["urdu"]


def test_provider_selection_from_env():
    with _Env() as env:
        assert isinstance(select_provider(), GeminiProvider)
        assert select_provider().model == "gemini-3.8-flash"

        env.set(ALERT_LLM_PROVIDER="Gemini", GEMINI_MODEL="gemini-test")
        selected = select_provider()
        assert isinstance(selected, GeminiProvider)
        assert selected.model == "gemini-test"

        env.set(ALERT_LLM_PROVIDER="qwen", QWEN_MODEL=None)
        assert isinstance(select_provider(), QwenProvider)
        assert select_provider().model == "qwen-plus"
        env.set(QWEN_MODEL="qwen-turbo")
        assert select_provider().model == "qwen-turbo"

        env.set(ALERT_LLM_PROVIDER=" None ")
        assert select_provider() is None
        draft = draft_alerts([_village()], AS_OF)[0]
        assert draft["source"] == "template"
        assert draft["model"] == ""


def test_unknown_provider_uses_gemini():
    with _Env() as env:
        env.set(ALERT_LLM_PROVIDER="not-a-provider")
        captured = []

        class _Handler(logging.Handler):
            def emit(self, record):
                captured.append(record)

        log = logging.getLogger("flood_tracker.alerts")
        previous = log.level
        handler = _Handler()
        log.setLevel(logging.INFO)
        log.addHandler(handler)
        try:
            selected = select_provider()
        finally:
            log.removeHandler(handler)
            log.setLevel(previous)
        assert isinstance(selected, GeminiProvider)
        warnings = [record.getMessage() for record in captured if record.levelno >= logging.WARNING]
        assert any("not-a-provider" in message for message in warnings), warnings


def test_accepted_reply_is_cached_per_language():
    urdu = f"Rojhan {LOW} {HIGH} اونچی زمین"
    sindhi = f"Rojhan {LOW} {HIGH} مٿانهين ڌرتي"
    assert len(urdu) <= 140 and len(sindhi) <= 140
    with _Env():
        provider = _Scripted([urdu, sindhi, "should-not-run", "should-not-run"])
        first = draft_alerts([_village()], AS_OF, provider=provider)[0]
        assert first["urdu"] == urdu
        assert first["sindhi"] == sindhi
        assert first["source"] == "gemini"
        assert first["model"] == "fake-model"
        assert len(provider.prompts) == 2
        assert "Urdu" in provider.prompts[0] and "Rojhan" in provider.prompts[0]
        assert LOW in provider.prompts[0] and HIGH in provider.prompts[0]
        assert "Sindhi" in provider.prompts[1]
        second = draft_alerts([_village()], AS_OF, provider=provider)[0]
        assert second["urdu"] == urdu and second["sindhi"] == sindhi
        assert len(provider.prompts) == 2, "cache must skip a second model call"


def test_empty_village_list():
    with _Env():
        assert draft_alerts([], AS_OF) == []


if __name__ == "__main__":
    # `unit` is the supported mode. There is no live /alert-drafts route here;
    # integration adds that in main.py, and these tests never open a socket.
    if len(sys.argv) > 1 and sys.argv[1].lower() != "unit":
        print("Use: python tests/test_alerts.py unit")
        sys.exit(2)
    tests = [
        test_template_fallback_without_a_key,
        test_named_safe_place_and_hours_only_window,
        test_validation_rejects_missing_place_name,
        test_validation_rejects_reply_over_140_characters,
        test_validation_rejects_reply_missing_the_time,
        test_provider_selection_from_env,
        test_unknown_provider_uses_gemini,
        test_accepted_reply_is_cached_per_language,
        test_empty_village_list,
    ]
    passed, failed = 0, 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
            passed += 1
        except AssertionError as exc:
            print(f"FAIL  {fn.__name__}: {exc}")
            failed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR {fn.__name__}: {type(exc).__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
