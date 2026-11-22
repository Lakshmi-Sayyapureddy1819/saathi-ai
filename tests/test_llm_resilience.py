"""When providers fail: quick retry for transient errors, a circuit breaker so a dead provider is not waited on, and a
clear degraded reply (booking/safety keep working). Plus the contract the evaluation scripts rely on."""
import pytest
import requests

from app.workflow import model_client as mc
from app.workflow.graph import WorkflowGraph, execute_turn
from app.workflow.model_client import LLMResult, ModelClient
from app.workflow.replies import is_llm_down_reply, is_no_context_reply, say
from app.workflow.state import MemberProfile, UserSessionState


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    mc.reset_llm_status()
    monkeypatch.setattr(mc, "RETRY_DELAY_S", 0.0)
    yield
    mc.reset_llm_status()


def _install(monkeypatch, behaviour):
    calls = []

    def fake(self, model_id, prompt):
        calls.append(model_id)
        return behaviour(model_id, len(calls))

    monkeypatch.setattr(ModelClient, "_invoke", fake)
    return calls


def _ok(model_id):
    return LLMResult(text="fine", model=model_id, prompt_tokens=3, completion_tokens=1)


# ---------------- retry ----------------
def test_transient_error_is_retried_once_on_the_same_model(monkeypatch):
    def behaviour(model_id, n):
        if n == 1:
            raise RuntimeError("Gemini API returned 503")
        return _ok(model_id)

    calls = _install(monkeypatch, behaviour)
    res = ModelClient().generate("hi", "t-res-1")
    assert res.model == "gemini-3.5-flash-lite" and calls == ["gemini-3.5-flash-lite"] * 2
    assert mc.llm_status().fallback_calls == 0  # the primary recovered; no vendor switch


@pytest.mark.parametrize("exc", [
    RuntimeError("Gemini API returned 400"),       # rejected key / bad request: retrying cannot help
    RuntimeError("Gemini API returned 403"),
    requests.exceptions.ReadTimeout("slow"),        # a hang: retrying would double the member's wait
])
def test_non_transient_errors_go_straight_to_the_fallback(monkeypatch, exc):
    def behaviour(model_id, n):
        if "gemini" in model_id:
            raise exc
        return _ok(model_id)

    calls = _install(monkeypatch, behaviour)
    assert ModelClient().generate("hi", "t-res-2").model == "gpt-4o-mini"
    assert calls == ["gemini-3.5-flash-lite", "gpt-4o-mini"]


@pytest.mark.parametrize("exc", [ConnectionError("reset"), RuntimeError("OpenAI API returned 429")])
def test_connection_drops_and_rate_limits_count_as_transient(exc):
    assert mc._is_transient(exc)


# ---------------- circuit breaker ----------------
def test_breaker_opens_after_consecutive_failures_and_skips_the_dead_model(monkeypatch):
    def behaviour(model_id, n):
        if "gemini" in model_id:
            raise RuntimeError("Gemini API returned 400")
        return _ok(model_id)

    calls = _install(monkeypatch, behaviour)
    client = ModelClient()
    for i in range(mc.BREAKER_THRESHOLD):
        client.generate("hi", f"t-br-{i}")
    calls.clear()
    assert client.generate("hi", "t-br-after").model == "gpt-4o-mini"
    assert calls == ["gpt-4o-mini"]  # the dead primary was skipped, not waited on


def test_breaker_closes_after_cooldown_and_success_resets_it(monkeypatch):
    state = {"gemini_down": True}

    def behaviour(model_id, n):
        if "gemini" in model_id and state["gemini_down"]:
            raise RuntimeError("Gemini API returned 400")
        return _ok(model_id)

    _install(monkeypatch, behaviour)
    client = ModelClient()
    for i in range(mc.BREAKER_THRESHOLD):
        client.generate("hi", f"t-bc-{i}")
    assert mc._breaker_open("gemini-3.5-flash-lite")
    mc._OPEN_UNTIL["gemini-3.5-flash-lite"] = 0.0  # cooldown elapsed
    state["gemini_down"] = False
    assert client.generate("hi", "t-bc-probe").model == "gemini-3.5-flash-lite"
    assert not mc._breaker_open("gemini-3.5-flash-lite") and mc._CONSEC["gemini-3.5-flash-lite"] == 0


def test_both_models_down_fails_fast_once_both_breakers_are_open(monkeypatch):
    calls = _install(monkeypatch, lambda m, n: (_ for _ in ()).throw(RuntimeError("returned 400")))
    client = ModelClient()
    for i in range(mc.BREAKER_THRESHOLD):
        with pytest.raises(RuntimeError, match="All models failed"):
            client.generate("hi", f"t-both-{i}")
    calls.clear()
    with pytest.raises(RuntimeError, match="All models failed"):
        client.generate("hi", "t-both-fast")
    assert calls == []  # no provider was contacted at all


def test_routes_without_a_fallback_never_use_the_breaker(monkeypatch):
    """Eval-only 'mix' routes must see every failure (counted, not hidden)."""
    calls = _install(monkeypatch, lambda m, n: (_ for _ in ()).throw(RuntimeError("returned 400")))
    client = ModelClient(node="mix_openai_4o")
    for i in range(mc.BREAKER_THRESHOLD + 3):
        with pytest.raises(RuntimeError):
            client.generate("hi", f"t-mix-{i}")
    assert len(calls) == mc.BREAKER_THRESHOLD + 3


# ---------------- what the member sees ----------------
def _graph_session(monkeypatch):
    _install(monkeypatch, lambda m, n: (_ for _ in ()).throw(ConnectionError("network down")))
    g = WorkflowGraph()
    g.use_cache = False
    s = UserSessionState(channel="chat", member=MemberProfile(member_id="RS1", name="T", age=30), active_node="start")
    return g, s


def test_degraded_reply_is_polite_grounded_and_clear_in_english(monkeypatch):
    g, s = _graph_session(monkeypatch)
    out, s = execute_turn("What yoga helps with exhaustion?", s, graph=g)
    assert "isn't responding right now" in out and "Viparita Karani" in out and "book a lab test" in out
    assert is_llm_down_reply(out)


def test_degraded_reply_in_hinglish(monkeypatch):
    g, s = _graph_session(monkeypatch)
    out, s = execute_turn("Mujhe bahut thakan rehti hai, kya yoga karun?", s, graph=g)
    assert "jawab nahi de pa raha" in out and is_llm_down_reply(out)


def test_degraded_reply_is_trimmed(monkeypatch):
    from app.workflow.graph import _brief
    assert len(_brief("word " * 500)) <= 610 and _brief("short") == "short"


def test_booking_and_safety_keep_working_when_every_model_is_down(monkeypatch):
    g, s = _graph_session(monkeypatch)
    from app.tools.lab_tools import LabTools
    g.lab_tools = LabTools(failure_rate=0.0)
    out, s = execute_turn("I have severe chest pain", s, graph=g)
    assert s.triage_status.status == "RED_CRISIS" and "112" in out
    for m in ("book thyroid test", "9:30 am", "yes"):
        out, s = execute_turn(m, s, graph=g)
    assert "Booking confirmed" in out


# ---------------- contract with the evaluation scripts ----------------
@pytest.mark.parametrize("lang", ["en", "hinglish"])
def test_eval_detectors_recognise_the_real_replies(lang):
    assert is_llm_down_reply(say(lang, "llm_down", context="Some library text"))
    assert is_no_context_reply(say(lang, "coach_empty"))
    assert not is_llm_down_reply(say(lang, "coach_empty")) and not is_no_context_reply(say(lang, "llm_down", context="x"))


def test_detectors_ignore_normal_answers_and_keep_legacy_wording():
    assert not is_llm_down_reply("Viparita Karani is a restorative pose [PROG_Y_006].")
    assert not is_no_context_reply("Viparita Karani is a restorative pose [PROG_Y_006].")
    assert is_llm_down_reply("Here is what our library says:\nstuff")      # pre-rewording text
    assert is_no_context_reply("I don't have that in our program library.")  # pre-rewording text
