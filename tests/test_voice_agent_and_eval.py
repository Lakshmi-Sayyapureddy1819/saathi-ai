"""Tests for voice calling agent and evaluation suite (requirement 3).

Verifies:
- VoiceAgent audio pipeline (STT normalization, graph execution, TTS streaming, barge-in)
- Read-back of test, date and slot with explicit confirmation before book_test
- Misheard numbers ('fifteen' vs 'fifty') and Hinglish parsing
- All 15 voice-style scenarios evaluated for readback correctness, wrong-booking rate (0), and TTFA budget
"""
import pytest

from app.channels.voice_agent import VoiceAgent, TTFA_BUDGET_MS
from app.workflow.graph import WorkflowGraph
from app.workflow.state import UserSessionState, MemberProfile
from evaluations.voice_eval import run_voice_eval, SCENARIOS


def test_voice_agent_hinglish_normalization():
    agent = VoiceAgent(verbose=False)
    assert agent.transcribe("kal subah thyroid test chahiye") == "tomorrow morning thyroid test chahiye"
    assert agent.transcribe("aaj shaam") == "today evening"
    assert agent.transcribe("parso") == "day after tomorrow"


def test_voice_agent_barge_in():
    import threading
    agent = VoiceAgent(tts_char_delay=0.01, verbose=False)
    # Trigger barge-in asynchronously during speech streaming
    threading.Timer(0.02, agent.barge_in).start()
    first_ms, barged = agent.speak("This is a long sentence that should be interrupted immediately.")
    assert barged is True


def test_voice_agent_readback_and_explicit_yes():
    graph = WorkflowGraph()
    agent = VoiceAgent(graph=graph, verbose=False, tts_char_delay=0.0)
    member = MemberProfile(member_id="VOICE_T1", name="Test Member", age=30)
    session = UserSessionState(channel="voice", member=member, active_node="start")

    # Turn 1: request thyroid test
    session = agent.process_voice_turn("book thyroid test", session)
    assert "Available slots" in agent.last_spoken or "Thyroid Screening Profile" in agent.last_spoken

    # Turn 2: select slot "09:30 AM"
    session = agent.process_voice_turn("nine thirty", session)
    # Must read back test, date, and slot
    assert "Thyroid Screening Profile" in agent.last_spoken
    assert "09:30 AM" in agent.last_spoken
    assert "20" in agent.last_spoken  # includes year/date
    assert session.booking_draft.verbal_confirmed is False
    assert len(session.member.past_bookings) == 0  # not booked yet!

    # Turn 3a: hesitant answer ("umm maybe") should NOT book
    session = agent.process_voice_turn("umm maybe", session)
    assert len(session.member.past_bookings) == 0  # still not booked!
    assert session.booking_draft.verbal_confirmed is False

    # Turn 3b: explicit "yes" confirms and calls book_test
    session = agent.process_voice_turn("yes confirm", session)
    assert len(session.member.past_bookings) == 1
    assert "Thyroid Screening Profile" in session.member.past_bookings[0]
    assert "09:30 AM" in session.member.past_bookings[0]


def test_voice_eval_15_scenarios_and_metrics():
    """Verify that all 15 voice-style test conversations execute and meet targets:
    - Exactly 15 scenarios
    - Readback correctness = 100%
    - Wrong-booking rate = 0%
    - 0 turns over the 1500 ms TTFA budget
    """
    assert len(SCENARIOS) == 15

    results = run_voice_eval(with_llm_turns=False)
    assert results.n_scenarios == 15
    assert results.wrong_bookings == 0, f"Expected 0 wrong bookings, got {results.wrong_bookings}"
    assert results.readback_ok == results.readback_checks, (
        f"Readback checks failed: {results.readback_ok}/{results.readback_checks} passed"
    )
    assert results.turns_over_budget == 0, (
        f"Turns over budget: {results.turns_over_budget} ({results.over_budget_turns})"
    )
    assert results.ttfa_budget_ms == TTFA_BUDGET_MS
