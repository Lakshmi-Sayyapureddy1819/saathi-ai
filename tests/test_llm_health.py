"""Model failures must be visible and explained: reason on the span, counts, fallback usage, startup key check."""
import json
import logging

import pytest
from fastapi.testclient import TestClient

from app import api
from app.observability import tracer as tr
from app.workflow import model_client as mc
from app.workflow.model_client import LLMResult, ModelClient


@pytest.fixture(autouse=True)
def _clean():
    mc.reset_llm_status()
    yield
    mc.reset_llm_status()


def _client(monkeypatch, behaviour):
    """ModelClient whose provider call is replaced by `behaviour(model_id) -> LLMResult | raises`."""
    monkeypatch.setattr(ModelClient, "_invoke", lambda self, model_id, prompt: behaviour(model_id))
    return ModelClient()  # cost_optimized: gemini-3.5-flash-lite -> gpt-4o-mini


def _ok(model_id):
    return LLMResult(text="fine", model=model_id, prompt_tokens=5, completion_tokens=2)


def _spans(trace_id):
    out = []
    for line in open(tr.TRACE_FILE, encoding="utf-8", errors="ignore"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("trace_id") == trace_id and r.get("kind") == "llm":
            out.append(r)
    return out


def test_primary_failure_is_recorded_with_a_reason_and_fallback_is_counted(monkeypatch):
    def behaviour(model_id):
        if "gemini" in model_id:
            raise RuntimeError("Gemini API returned 400")
        return _ok(model_id)

    res = _client(monkeypatch, behaviour).generate("hello", trace_id="t-health-1")
    assert res.model == "gpt-4o-mini"
    st = mc.llm_status()
    by = {h.model: h for h in st.models}
    assert by["gemini-3.5-flash-lite"].failed == 1 and "returned 400" in by["gemini-3.5-flash-lite"].last_error
    assert by["gpt-4o-mini"].ok == 1 and st.fallback_calls == 1
    failed = [s for s in _spans("t-health-1") if s["metadata"].get("failed")]
    assert failed and "returned 400" in failed[0]["metadata"]["error"]  # the reason is on the span itself


def test_healthy_primary_means_no_fallback(monkeypatch):
    _client(monkeypatch, _ok).generate("hello", trace_id="t-health-2")
    st = mc.llm_status()
    assert st.fallback_calls == 0 and [(h.model, h.ok, h.failed) for h in st.models] == [("gemini-3.5-flash-lite", 1, 0)]


def test_both_providers_failing_raises_and_counts_both(monkeypatch):
    def behaviour(model_id):
        raise ConnectionError("network down")

    with pytest.raises(RuntimeError, match="All models failed"):
        _client(monkeypatch, behaviour).generate("hello", trace_id="t-health-3")
    st = mc.llm_status()
    assert {h.model: h.failed for h in st.models} == {"gemini-3.5-flash-lite": 1, "gpt-4o-mini": 1}
    assert st.fallback_calls == 0


def test_mock_replies_are_not_counted_as_model_successes(monkeypatch):
    monkeypatch.setattr(ModelClient, "_invoke", lambda self, m, p: LLMResult(text="[MOCK] x", model=m, mock=True))
    ModelClient().generate("hello", trace_id="t-health-4")
    assert mc.llm_status().models == []


def test_failure_reason_never_contains_the_api_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSECRET-KEY-VALUE-123")

    def behaviour(model_id):
        if "gemini" in model_id:
            raise RuntimeError("bad request for key AIzaSECRET-KEY-VALUE-123")
        return _ok(model_id)

    _client(monkeypatch, behaviour).generate("hello", trace_id="t-health-5")
    blob = json.dumps(mc.llm_status().model_dump(mode="json")) + json.dumps(_spans("t-health-5"))
    assert "AIzaSECRET-KEY-VALUE-123" not in blob and "<key>" in blob


# ---------------- startup credential check ----------------
class _Resp:
    def __init__(self, code):
        self.status_code = code


def test_credential_check_reports_each_provider(monkeypatch, caplog):
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    monkeypatch.setenv("OPENAI_API_KEY", "o-key")
    codes = {"generativelanguage": 400, "openai": 200}
    monkeypatch.setattr(mc.requests, "get", lambda url, **kw: _Resp(next(v for k, v in codes.items() if k in url)))
    with caplog.at_level(logging.ERROR):
        out = mc.check_credentials()
    assert out == {"gemini": "rejected (HTTP 400)", "openai": "ok"}
    assert "GEMINI key is rejected (HTTP 400)" in caplog.text and "g-key" not in caplog.text
    assert mc.llm_status().credentials == out


def test_credential_check_handles_missing_keys_and_network_errors(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "o-key")

    def boom(url, **kw):
        raise ConnectionError("no route")

    monkeypatch.setattr(mc.requests, "get", boom)
    assert mc.check_credentials() == {"gemini": "not set", "openai": "unreachable (ConnectionError)"}


def test_credential_check_is_skipped_without_keys_so_tests_never_hit_the_network():
    assert mc.check_credentials() == {"gemini": "not set", "openai": "not set"}


# ---------------- API endpoint ----------------
def test_llm_status_endpoint_has_no_secrets_or_message_text(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-ENDPOINT-SECRET")
    mc._record("gemini-3.5-flash-lite", ok=False, error="Gemini API returned 429")
    with TestClient(api.app) as c:
        r = c.get("/api/llm-status")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"models", "fallback_calls", "credentials"}
    assert body["models"][0]["last_error"] == "Gemini API returned 429"
    assert "AIza-ENDPOINT-SECRET" not in r.text
