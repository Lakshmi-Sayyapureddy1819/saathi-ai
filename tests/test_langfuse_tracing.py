"""Langfuse 4.x integration. The REAL SDK is exercised offline (in-memory OpenTelemetry exporter, no network, no
credentials). What this does NOT prove: that a live Langfuse project accepts and displays the data - see README."""
import inspect
import json
import logging
import uuid

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import app.observability.tracer as tr


@pytest.fixture(autouse=True)
def _restore_tracer():
    saved = (tr._langfuse, tr._lf_errors, tr._lf_last_error, tr._lf_init_note, tr._lf_auth_verified)
    yield
    tr._langfuse, tr._lf_errors, tr._lf_last_error, tr._lf_init_note, tr._lf_auth_verified = saved


def _local_records(trace_id):
    out = []
    with open(tr.TRACE_FILE, encoding="utf-8") as f:
        for line in f:
            if trace_id in line:
                out.append(json.loads(line))
    return out


def _real_client():
    from langfuse import Langfuse
    exp = InMemorySpanExporter()
    client = Langfuse(public_key=f"pk-lf-{uuid.uuid4().hex[:8]}", secret_key="sk-lf-test",
                      host="http://127.0.0.1:9", span_exporter=exp, flush_at=1, tracing_enabled=True)
    return client, exp


# ---------- SDK contract (guards against another silent API break on upgrade) ----------
def test_installed_sdk_has_the_methods_tracer_uses():
    from langfuse import Langfuse
    assert hasattr(Langfuse, "start_as_current_observation") and hasattr(Langfuse, "flush")
    params = inspect.signature(Langfuse.start_as_current_observation).parameters
    assert {"name", "as_type", "metadata", "trace_context"} <= set(params)
    assert not hasattr(Langfuse, "start_as_current_span")        # the 2.x/3.x name that silently failed on 4.x


def test_requirements_pin_a_compatible_langfuse_range():
    req = open("requirements.txt", encoding="utf-8").read()
    line = next(l for l in req.splitlines() if l.lower().startswith("langfuse"))
    assert "<5" in line and ">=4" in line, line


# ---------- success path with the real SDK ----------
def test_real_sdk_receives_nested_spans_on_our_trace_id():
    client, exp = _real_client()
    tr.init_langfuse(client)
    tid = tr.new_trace_id()
    with tr.span("turn", tid, kind="root", channel="chat"):
        with tr.span("node_x", tid, kind="node", member_id="M1"):
            with tr.span("llm:gemini-3.5-flash-lite", tid, kind="llm", model="gemini-3.5-flash-lite") as s:
                s.set(prompt_tokens=10, completion_tokens=5, cost_usd=0.001)
            with tr.span("tool:search_packages", tid, kind="tool"):
                pass
    tr.flush()
    spans = {s.name: s for s in exp.get_finished_spans()}
    assert set(spans) == {"turn", "node_x", "llm:gemini-3.5-flash-lite", "tool:search_packages"}
    assert {format(s.context.trace_id, "032x") for s in spans.values()} == {tid}          # our trace id propagated
    assert spans["node_x"].parent.span_id == spans["turn"].context.span_id                  # nesting preserved
    assert spans["llm:gemini-3.5-flash-lite"].parent.span_id == spans["node_x"].context.span_id
    gen = spans["llm:gemini-3.5-flash-lite"].attributes
    assert gen["langfuse.observation.type"] == "generation"
    assert gen["langfuse.observation.model.name"] == "gemini-3.5-flash-lite"
    assert json.loads(gen["langfuse.observation.usage_details"]) == {"input": 10, "output": 5}
    assert json.loads(gen["langfuse.observation.cost_details"]) == {"total": 0.001}
    assert spans["tool:search_packages"].attributes["langfuse.observation.type"] == "tool"
    st = tr.tracing_status()
    assert st.langfuse_enabled and st.langfuse_errors == 0
    assert all("langfuse_error" not in r for r in _local_records(tid))                       # local JSONL still written
    client.shutdown()


def test_error_spans_are_marked_error_in_langfuse_and_locally():
    client, exp = _real_client()
    tr.init_langfuse(client)
    tid = tr.new_trace_id()
    with pytest.raises(ValueError):
        with tr.span("tool:boom", tid, kind="tool"):
            raise ValueError("kaput")
    tr.flush()
    (sp,) = exp.get_finished_spans()
    assert sp.attributes["langfuse.observation.level"] == "ERROR"
    assert _local_records(tid)[0]["status"] == "error"
    client.shutdown()


# ---------- graceful behaviour without credentials ----------
def test_no_credentials_means_local_only_with_a_clear_note(monkeypatch):
    for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.setenv(k, "")
    tr.init_langfuse()
    st = tr.tracing_status()
    assert not st.langfuse_enabled and "not set" in st.note and st.langfuse_errors == 0
    tid = tr.new_trace_id()
    with tr.span("node_y", tid):
        pass
    assert _local_records(tid)[0]["status"] == "ok"


# ---------- failures are survivable but never silent ----------
class _ExplodingClient:
    def __init__(self, where):
        self.where = where

    def start_as_current_observation(self, **kw):
        if self.where == "start":
            raise RuntimeError("langfuse start exploded")
        return _CM(self.where)

    def flush(self):
        raise RuntimeError("flush exploded")


class _CM:
    def __init__(self, where):
        self.where = where

    def __enter__(self):
        return self

    def update(self, **kw):
        if self.where == "update":
            raise RuntimeError("langfuse update exploded")

    def __exit__(self, *a):
        if self.where == "exit":
            raise RuntimeError("langfuse exit exploded")


@pytest.mark.parametrize("where", ["start", "update", "exit"])
def test_langfuse_failures_do_not_break_the_turn_and_are_recorded(where, caplog):
    tr.init_langfuse(_ExplodingClient(where))
    before = tr.tracing_status().langfuse_errors
    tid = tr.new_trace_id()
    ran = []
    with caplog.at_level(logging.WARNING):
        with tr.span("node_z", tid, kind="node"):
            ran.append(True)                                  # the business logic still runs
    assert ran == [True]
    st = tr.tracing_status()
    assert st.langfuse_errors == before + 1 and f"{where} exploded" in (st.last_langfuse_error or "")
    assert any(f"{where} exploded" in r.message for r in caplog.records)                     # logged, not swallowed
    rec = _local_records(tid)[0]
    assert rec["status"] == "ok" and f"{where} exploded" in rec["langfuse_error"]            # visible on the span


def test_flush_failure_is_recorded(caplog):
    tr.init_langfuse(_ExplodingClient("none"))
    with caplog.at_level(logging.WARNING):
        tr.flush()
    assert "flush exploded" in (tr.tracing_status().last_langfuse_error or "")


def test_init_failure_is_reported_not_hidden(monkeypatch, caplog):
    import langfuse
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-x")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-x")
    monkeypatch.setattr(langfuse, "Langfuse", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bad config")))
    with caplog.at_level(logging.WARNING):
        tr.init_langfuse()
    st = tr.tracing_status()
    assert not st.langfuse_enabled and "bad config" in st.note
    assert any("bad config" in r.message for r in caplog.records)


# ---------- credential check at initialisation ----------
class _AuthClient:
    def __init__(self, exc=None):
        self.exc, self.shutdown_called = exc, False

    def auth_check(self):
        if self.exc:
            raise self.exc
        return True

    def shutdown(self):
        self.shutdown_called = True


class _Http401(Exception):
    status_code = 401


def test_valid_credentials_are_verified_and_langfuse_stays_on():
    tr.init_langfuse(_AuthClient(), check_auth=True)
    st = tr.tracing_status()
    assert st.langfuse_enabled and st.auth_verified is True and st.langfuse_errors == 0


def test_rejected_credentials_turn_langfuse_off_with_a_clear_reason(caplog):
    c = _AuthClient(_Http401("Unauthorized"))
    with caplog.at_level(logging.WARNING):
        tr.init_langfuse(c, check_auth=True)
    st = tr.tracing_status()
    assert not st.langfuse_enabled and st.auth_verified is False and c.shutdown_called
    assert "REJECTED" in st.note and "pk-lf-" in st.note and "Unauthorized" in (st.last_langfuse_error or "")
    assert any("REJECTED" in r.message for r in caplog.records)
    tid = tr.new_trace_id()
    with tr.span("still_traced_locally", tid):                       # local tracing is unaffected
        pass
    assert _local_records(tid)[0]["status"] == "ok"


def test_real_sdk_unauthorized_error_is_recognised_as_rejected():
    from langfuse.api import UnauthorizedError
    assert tr._credentials_rejected(UnauthorizedError(body={}))


def test_unreachable_langfuse_is_unverified_not_rejected():
    tr.init_langfuse(_AuthClient(ConnectionError("network down")), check_auth=True)
    st = tr.tracing_status()
    assert st.langfuse_enabled and st.auth_verified is None and "could not be verified" in st.note


def test_injected_clients_are_not_checked_by_default():
    tr.init_langfuse(_AuthClient(_Http401("would fail")))           # tests inject fakes: no network, no check
    st = tr.tracing_status()
    assert st.langfuse_enabled and st.auth_verified is None


def test_auth_check_can_be_skipped_for_env_built_clients(monkeypatch):
    import langfuse
    built = []
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-x")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-x")
    monkeypatch.setenv("LANGFUSE_AUTH_CHECK", "0")
    monkeypatch.setattr(langfuse, "Langfuse", lambda *a, **k: built.append(1) or _AuthClient(_Http401("x")))
    tr.init_langfuse()
    st = tr.tracing_status()
    assert built and st.langfuse_enabled and st.auth_verified is None


def test_env_built_client_with_bad_keys_is_switched_off(monkeypatch):
    import langfuse
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-x")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-x")
    monkeypatch.delenv("LANGFUSE_AUTH_CHECK", raising=False)
    monkeypatch.setattr(langfuse, "Langfuse", lambda *a, **k: _AuthClient(_Http401("nope")))
    tr.init_langfuse()
    st = tr.tracing_status()
    assert not st.langfuse_enabled and st.auth_verified is False


# ---------- input/output, trace-level attributes, redaction ----------
def test_io_and_trace_attributes_reach_langfuse_and_text_is_redacted(monkeypatch):
    monkeypatch.delenv("LANGFUSE_CAPTURE_CONTENT", raising=False)
    client, exp = _real_client()
    tr.init_langfuse(client)
    tid = tr.new_trace_id()
    with tr.span("turn", tid, kind="root", member_id="M1", session_id="S1", channel="chat", prompt_version="v4",
                 input="I have chest pain") as root:
        with tr.span("tool:check_slots", tid, kind="tool", input={"package_id": "LP_1", "query": "secret"}) as t:
            t.set_output({"free_slots": ["09:30 AM"]})
        with tr.span("tool:other", tid, kind="tool"):   # sibling must still nest under the root
            pass
        root.set_output("Please call emergency services")
    tr.flush()
    spans = {s.name: s for s in exp.get_finished_spans()}
    a = spans["turn"].attributes
    assert a["user.id"] == "M1" and a["session.id"] == "S1" and a["langfuse.version"] == "v4"
    assert "saathi" in a["langfuse.trace.tags"] and "channel:chat" in a["langfuse.trace.tags"]
    assert "chest pain" not in json.dumps(dict(a)) and "<redacted" in a["langfuse.observation.input"]
    tool = spans["tool:check_slots"].attributes
    assert "LP_1" in tool["langfuse.observation.input"] and "secret" not in tool["langfuse.observation.input"]
    assert "09:30 AM" in tool["langfuse.observation.output"]
    root_id = spans["turn"].context.span_id
    assert spans["tool:other"].parent.span_id == root_id and spans["tool:check_slots"].parent.span_id == root_id
    client.shutdown()
