"""Regression: 'book a blood test' must ASK which test (keeping booking context), not return nothing and let the
next turns ('9:00 AM', 'yes confirm') fall through to the wellness coach. Generic words must still not match."""
from app.channels.voice_agent import VoiceAgent
from app.tools.lab_tools import LabTools
from app.workflow.graph import WorkflowGraph, execute_turn
from app.workflow.state import MemberProfile, UserSessionState


def _g():
    g = WorkflowGraph()
    g.lab_tools = LabTools(failure_rate=0.0)
    return g


def _s(mid="GEN1", channel="chat"):
    return UserSessionState(channel=channel, member=MemberProfile(member_id=mid, name="T", age=30), active_node="start")


def _say(g, s, *msgs):
    out = ""
    for m in msgs:
        out, s = execute_turn(m, s, graph=g)
    return out, s


def test_generic_request_asks_which_test_and_keeps_context():
    g, s = _g(), _s()
    out, s = _say(g, s, "I want to book a blood test")
    assert "Which test" in out and s.active_node == "node_lab_booking"
    assert len(s.booking_draft.candidate_package_ids) == len(g.lab_tools.lab_packages)  # whole catalogue pending
    assert not s.booking_draft.package_id


def test_no_broad_matching_is_reintroduced():
    t = LabTools()
    for q in ["book a blood test", "I need a checkup", "lab test please", "I need to schedule a lipid profile"]:
        assert t.search_packages(q) == [], q        # still no catalogue matches from generic words
    assert t.is_generic_request("book a blood test") and not t.is_generic_request("book karo")


def test_time_and_yes_before_choosing_stay_in_booking():
    g, s = _g(), _s()
    _, s = _say(g, s, "I want to book a blood test")
    out, s = _say(g, s, "09:00 AM")
    assert s.active_node == "node_lab_booking" and "which package" in out.lower()      # not the coach
    assert s.booking_draft.pending_slot_text == "09:00 AM"
    out, s = _say(g, s, "yes confirm")
    assert s.active_node == "node_lab_booking" and s.member.past_bookings == []        # nothing booked blind


def test_choosing_after_time_applies_the_remembered_time_then_books():
    g, s = _g(), _s()
    _, s = _say(g, s, "I want to book a blood test", "09:00 AM")
    out, s = _say(g, s, "the thyroid one")
    assert s.booking_draft.package_id == "LP_002" and s.booking_draft.selected_slot == "09:00 AM"
    out, s = _say(g, s, "yes confirm")
    assert "Booking confirmed" in out and "09:00 AM" in s.member.past_bookings[0]


def test_symptom_reply_narrows_the_options():
    g, s = _g(), _s()
    _, s = _say(g, s, "I want to book a blood test")
    out, s = _say(g, s, "I have constant fatigue")          # ties several packages -> narrowed, still in flow
    assert s.active_node == "node_lab_booking"
    assert 1 < len(s.booking_draft.candidate_package_ids) < len(g.lab_tools.lab_packages) or s.booking_draft.package_id


def test_long_lists_are_capped():
    g, s = _g(), _s()
    out, s = _say(g, s, "book a blood test")
    assert out.count("\n- ") <= 6 and "more" in out


def test_voice_demo_flow_end_to_end(monkeypatch):
    import app.workflow.graph as graph_mod
    real = graph_mod.WorkflowGraph
    monkeypatch.setattr(graph_mod, "WorkflowGraph", lambda *a, **k: real(*a, **k))
    agent = VoiceAgent(tts_char_delay=0.0)
    s = _s("VOICE1", "voice")
    for u in ["I want to book a blood test for kal subah.", "the thyroid one", "09:00 AM", "yes confirm"]:
        s = agent.process_voice_turn(u, s)
    assert len(s.member.past_bookings) == 1 and "Thyroid" in s.member.past_bookings[0]
    assert len(agent.metrics) == 4 and all(m.total_ms > 0 for m in agent.metrics)
