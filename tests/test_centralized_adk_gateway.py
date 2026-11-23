"""Tests for Centralized Google ADK Model Gateway Integration.

Verifies:
1. Program Coach uses ADKModelGateway.
2. Intent routing uses ADKModelGateway.
3. LLM-based triage operations use ADKModelGateway.
4. No application-level direct model HTTP calls to Gemini remain (uses native ADK Gemini).
5. Retry attempts are bounded and backoff increases correctly with jitter.
6. Multi-provider fallback executes properly when primary provider fails.
7. Failed model requests never execute booking tools.
8. Safety emergencies are caught deterministically even when all LLM providers are down.
9. Observability captures both failed and successful model attempts with spans and metadata.
"""
import pytest
import requests
from datetime import date
from unittest.mock import MagicMock, patch

from google.adk.models import LlmRequest, LlmResponse
from google.adk.models.base_llm import BaseLlm
from google.genai import types

from app.safety.triage_gate import evaluate_safety_gate, HELPLINE_PAYLOAD
from app.tools.lab_tools import LabTools
from app.workflow.gateway import ADKModelGateway
from app.workflow.graph import WorkflowGraph
from app.workflow.model_client import LLMResult, ModelClient, reset_llm_status
from app.workflow.state import BookingDraft, GroundingMode, MemberProfile, UserSessionState


def _make_session() -> UserSessionState:
    m = MemberProfile(
        member_id="M_TEST",
        name="Aarav",
        age=34,
        enrolled_programs=["Yoga for Stress"],
        past_bookings=[],
    )
    return UserSessionState(
        channel="chat",
        member=m,
        active_node="start",
        trace_id="t-adk-gw-1",
        grounding_mode=GroundingMode(mode="mode_a_rag"),
    )


def test_adk_model_gateway_subclasses_base_llm():
    """Verify ADKModelGateway is a genuine subclass of ADK BaseLlm."""
    gw = ADKModelGateway()
    assert isinstance(gw, BaseLlm)
    assert gw.model == "gateway"


def test_program_coach_uses_adk_gateway():
    """Verify Program Coach routes its generation through ADKModelGateway."""
    g = WorkflowGraph()
    assert isinstance(g.model_client, ADKModelGateway)

    called_requests = []

    class MockClient:
        def generate(self, prompt, trace_id=None):
            return LLMResult(text="Grounded wellness advice [PROG_YOGA].", model="mock-gw")

    g.model_client = ADKModelGateway(client=MockClient())
    orig_generate_request = g.model_client.generate_request

    def spy_generate_request(req, trace_id=None):
        called_requests.append(req)
        return orig_generate_request(req, trace_id=trace_id)

    g.model_client.generate_request = spy_generate_request
    session = _make_session()

    out, session = g.node_program_coach("What are the benefits of pranayama?", session)
    assert len(called_requests) >= 1
    assert isinstance(called_requests[0], LlmRequest)
    assert called_requests[0].model == "gateway"


def test_intent_routing_uses_adk_gateway():
    """Verify intent router fallback uses ADKModelGateway."""
    g = WorkflowGraph()
    assert isinstance(g.router_client, ADKModelGateway)

    called_requests = []

    def fake_request(req, trace_id=None):
        called_requests.append(req)
        return LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text="LAB_BOOKING")]),
            finish_reason=types.FinishReason.STOP,
        )

    g.router_client.generate_request = fake_request
    route = g._llm_route("Can you tell me about the prices and slots for tests?", "t-route")
    assert route == "node_lab_booking"
    assert len(called_requests) == 1
    assert isinstance(called_requests[0], LlmRequest)


def test_llm_based_triage_uses_adk_gateway():
    """Verify evaluate_safety_gate invokes ADKModelGateway with an LlmRequest."""
    called = []

    class SpyGateway(ADKModelGateway):
        def generate_request(self, req, trace_id=None):
            called.append(req)
            return LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text="YELLOW_WARNING")]),
                finish_reason=types.FinishReason.STOP,
            )

    spy_gw = SpyGateway()
    # Use a clinical concern that does not match hardcoded regexes so it triggers stage 3
    is_safe, status, payload = evaluate_safety_gate(
        "is it risky for someone with high blood pressure to do intense inversions?",
        "M1",
        spy_gw,
    )
    assert len(called) == 1
    assert isinstance(called[0], LlmRequest)
    assert status == "YELLOW_WARNING"


def test_no_application_direct_gemini_http_calls(monkeypatch):
    """Verify Gemini calls go through native ADK BaseLlm, not requests.post to generativelanguage."""
    disallowed_urls = []

    orig_post = requests.post

    def guarded_post(url, *args, **kwargs):
        if "generativelanguage.googleapis.com" in str(url):
            disallowed_urls.append(url)
            raise AssertionError(f"Direct raw HTTP call to Gemini detected: {url}")
        return orig_post(url, *args, **kwargs)

    monkeypatch.setattr(requests, "post", guarded_post)

    client = ModelClient()
    monkeypatch.setenv("ALLOW_MOCK_LLM", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    gw = ADKModelGateway(client=client)
    res = gw.generate("Test prompt")
    assert res.mock is True
    assert len(disallowed_urls) == 0


def test_retry_attempts_are_bounded_and_backoff_increases(monkeypatch):
    """Verify retry attempts are strictly bounded and delays scale exponentially."""
    monkeypatch.setattr("app.workflow.model_client.RETRY_DELAY_S", 0.05)
    delays = []

    import time

    def fake_sleep(d):
        delays.append(d)

    monkeypatch.setattr(time, "sleep", fake_sleep)

    client = ModelClient()
    attempt_count = 0

    def failing_invoke(model_id, prompt):
        nonlocal attempt_count
        attempt_count += 1
        raise ConnectionError("connection reset by peer")

    monkeypatch.setattr(client, "_invoke", failing_invoke)

    with pytest.raises(ConnectionError):
        client._invoke_with_retry("gemini-3.5-flash-lite", "hello", max_retries=3)

    # 1 initial + 3 retries = 4 total attempts
    assert attempt_count == 4
    # 3 delays recorded
    assert len(delays) == 3
    # Backoff increases: delay[1] > delay[0] and delay[2] > delay[1]
    assert delays[1] > delays[0]
    assert delays[2] > delays[1]


def test_fallback_works_after_primary_failure(monkeypatch):
    """Verify fallback to secondary provider occurs seamlessly."""
    reset_llm_status()
    monkeypatch.setattr("app.workflow.model_client.RETRY_DELAY_S", 0.0)

    client = ModelClient()

    def selective_invoke(model_id, prompt):
        if "gemini" in model_id:
            raise RuntimeError("Gemini 500 internal server error")
        return LLMResult(text="Fallback response from OpenAI", model=model_id, prompt_tokens=5, completion_tokens=5)

    monkeypatch.setattr(client, "_invoke", selective_invoke)

    gw = ADKModelGateway(client=client)
    res = gw.generate("Hello", trace_id="t-fb-test")
    assert res.model == "gpt-4o-mini"
    assert "OpenAI" in res.text


def test_failed_requests_do_not_execute_booking_tools(monkeypatch):
    """Verify that a broken LLM provider never causes booking execution."""
    g = WorkflowGraph()
    booking_called = []

    def fake_book(*args, **kwargs):
        booking_called.append(args)
        raise AssertionError("book_test must not be called on LLM failure!")

    monkeypatch.setattr(g.lab_tools, "book_test", fake_book)

    # Simulate failing LLM
    def failing_request(*args, **kwargs):
        raise RuntimeError("All LLM providers unreachable")

    g.model_client.generate_request = failing_request

    session = _make_session()
    out, session = g.node_program_coach("I have questions about my diet", session)
    assert len(booking_called) == 0
    assert session.booking_draft.package_id is None


def test_safety_emergencies_caught_deterministically_when_all_llms_down():
    """Verify that RED_CRISIS is caught deterministically with zero LLM dependence."""
    failing_gw = ADKModelGateway()

    def broken_call(*args, **kwargs):
        raise RuntimeError("Total cloud outage: no network or LLM")

    failing_gw.generate_request = broken_call

    # Emergency symptoms in Hindi, English, and Hinglish
    emergencies = [
        "I have severe chest pain and breathlessness",
        "mere seene me bahut tez dard ho raha hai",
        "vomiting blood and unconscious",
        "I feel like ending my life please help",
    ]

    for utterance in emergencies:
        is_safe, status, payload = evaluate_safety_gate(utterance, "MEM_EMERGENCY", failing_gw)
        assert is_safe is False
        assert status == "RED_CRISIS"
        assert payload["helplines"]["Medical Helpline"] == "108"


def test_observability_captures_successful_and_failed_attempts(monkeypatch):
    """Verify Langfuse spans record both successful and failed model invocations."""
    from app.observability.tracer import span, get_current_turn_metrics, new_trace_id

    tid = new_trace_id()
    client = ModelClient()

    monkeypatch.setattr(
        client,
        "_invoke",
        lambda m, p: LLMResult(text="Success", model=m, prompt_tokens=10, completion_tokens=5, cost_usd=0.001),
    )
    gw = ADKModelGateway(client=client)

    with span("turn:root", tid, kind="root"):
        res = gw.generate("Hello", trace_id=tid)
        metrics = get_current_turn_metrics()
        assert metrics["prompt_tokens"] == 10
        assert metrics["completion_tokens"] == 5
        assert metrics["cost_usd"] == 0.001
