"""Tests for how llm.py copes with Gemini's behavior, using a fake instead of the real API."""
from types import SimpleNamespace

import pytest
from google.genai import errors

import llm


class Reply:
    text = '{"ok": true}'


@pytest.fixture(autouse=True)
def real_path(monkeypatch):
    """Switch off demo mode for these tests and skip real sleeping."""
    monkeypatch.setattr(llm, "MOCK", False)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)


def error(code, message="x"):
    cls = errors.ServerError if code >= 500 else errors.ClientError
    return cls(code, {"error": {"code": code, "message": message}})


def test_retries_a_503_then_succeeds(monkeypatch):
    calls = []

    def fake(system, user, use_system, use_json):
        calls.append(1)
        if len(calls) < 3:
            raise error(503, "overloaded")
        return Reply()

    monkeypatch.setattr(llm, "_generate", fake)
    assert llm.call_llm("s", "u") == '{"ok": true}'
    assert len(calls) == 3


def test_gives_up_after_max_attempts(monkeypatch):
    calls = []

    def fake(*a):
        calls.append(1)
        raise error(503)

    monkeypatch.setattr(llm, "_generate", fake)
    with pytest.raises(errors.ServerError):
        llm.call_llm("s", "u")
    assert len(calls) == llm.MAX_ATTEMPTS


def test_does_not_retry_a_rate_limit(monkeypatch):
    calls = []

    def fake(*a):
        calls.append(1)
        raise error(429, "quota")

    monkeypatch.setattr(llm, "_generate", fake)
    with pytest.raises(errors.ClientError):
        llm.call_llm("s", "u")
    assert len(calls) == 1  # retrying would burn more of the same per-minute quota


def test_drops_system_instruction_and_json_mode_for_models_that_reject_them(monkeypatch):
    seen = []

    def fake(system, user, use_system, use_json):
        seen.append((use_system, use_json))
        if use_system:
            raise error(400, "Developer instruction is not enabled for this model")
        if use_json:
            raise error(400, "JSON mode is not enabled for this model")
        return Reply()

    monkeypatch.setattr(llm, "_generate", fake)
    assert llm.call_llm("s", "u") == '{"ok": true}'
    assert seen == [(True, True), (False, True), (False, False)]


def test_other_400_errors_are_not_swallowed(monkeypatch):
    def fake(*a):
        raise error(400, "API key not valid")

    monkeypatch.setattr(llm, "_generate", fake)
    with pytest.raises(errors.ClientError):
        llm.call_llm("s", "u")


def test_reads_an_answer_the_sdk_labels_as_thoughts(monkeypatch):
    part = SimpleNamespace(text='{"answer": 1}', thought=True)
    reply = SimpleNamespace(
        text=None,
        prompt_feedback=None,
        usage_metadata=None,
        candidates=[SimpleNamespace(finish_reason="STOP", content=SimpleNamespace(parts=[part]))],
    )
    monkeypatch.setattr(llm, "_generate", lambda *a: reply)
    assert llm.call_llm("s", "u") == '{"answer": 1}'


def test_a_truly_empty_reply_raises_with_a_reason(monkeypatch):
    reply = SimpleNamespace(
        text=None,
        prompt_feedback=None,
        usage_metadata=None,
        candidates=[SimpleNamespace(finish_reason="MAX_TOKENS", content=SimpleNamespace(parts=[]))],
    )
    monkeypatch.setattr(llm, "_generate", lambda *a: reply)
    with pytest.raises(llm.EmptyReply) as info:
        llm.call_llm("s", "u")
    assert "MAX_TOKENS" in str(info.value)


def test_a_timeout_from_any_http_library_becomes_llm_timeout(monkeypatch):
    # Different SDK versions use different HTTP libraries, each with its own timeout class.
    class ReadTimeout(Exception):
        pass

    def fake(*a):
        raise ReadTimeout("took too long")

    monkeypatch.setattr(llm, "_generate", fake)
    with pytest.raises(llm.LLMTimeout):
        llm.call_llm("s", "u")


def test_unrelated_errors_are_not_mistaken_for_timeouts(monkeypatch):
    def fake(*a):
        raise ValueError("something else")

    monkeypatch.setattr(llm, "_generate", fake)
    with pytest.raises(ValueError):
        llm.call_llm("s", "u")
