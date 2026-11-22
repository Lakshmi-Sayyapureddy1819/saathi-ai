import asyncio

from app.tools.lab_tools import LabTools
from app.workflow.adk_graph import AdkSaathi, ApprovalDecision, _GRAPH
from app.workflow.state import MemberProfile, UserSessionState


def _session(mid="ADK1"):
    return UserSessionState(channel="chat", member=MemberProfile(member_id=mid, name="T", age=30), active_node="start")


def _run(coro):
    return asyncio.run(coro)


def test_adk_emergency_route():
    r = _run(AdkSaathi().turn("I have severe chest pain", _session("ADK_E")))
    assert r.session.triage_status.status == "RED_CRISIS"
    assert "112" in r.response


def test_adk_yellow_warning_is_deterministic():
    r = _run(AdkSaathi().turn("do i have diabetes?", _session("ADK_Y")))
    assert "can't provide a medical diagnosis" in r.response


def test_adk_coach_route_and_fallback_routing():
    r = _run(AdkSaathi().turn("Tell me about Kapalbhati", _session("ADK_C")))
    assert r.session.active_node == "node_program_coach"
    r = _run(AdkSaathi().turn("hello there", _session("ADK_F")))  # no keyword, no LLM key -> coach fallback
    assert r.session.active_node == "node_program_coach"


def test_adk_multi_turn_booking_saves_history():
    _GRAPH.lab_tools = LabTools(failure_rate=0.0)
    app, s = AdkSaathi(), _session("ADK_B")
    for msg in ["book thyroid test", "9:30 am", "yes"]:
        r = _run(app.turn(msg, s))
        s = r.session
    assert "Booking confirmed" in r.response
    assert any("09:30 AM" in b for b in r.session.member.past_bookings)


def _outage_to_handoff(app, mid):
    _GRAPH.lab_tools = LabTools(failure_rate=1.0)
    import time
    orig, time.sleep = time.sleep, lambda *_: None
    try:
        s = _session(mid)
        for msg in ["book thyroid test", "9:30 am", "yes"]:
            r = _run(app.turn(msg, s))
            s = r.session
    finally:
        time.sleep = orig
        _GRAPH.lab_tools = LabTools(failure_rate=0.0)
    return r


def test_adk_handoff_pauses_then_approval_continues():
    app = AdkSaathi()
    r = _outage_to_handoff(app, "ADK_H1")
    assert r.pending_interrupt_id, "workflow should pause for coordinator approval"
    r2 = _run(app.resume(r.session, r.pending_interrupt_id, ApprovalDecision(approved=True)))
    assert "approved" in r2.response and r2.session.booking_draft.package_id is None


def test_adk_handoff_rejection_continues_booking_flow():
    app = AdkSaathi()
    r = _outage_to_handoff(app, "ADK_H2")
    r2 = _run(app.resume(r.session, r.pending_interrupt_id, ApprovalDecision(approved=False, note="Lab closed.")))
    assert "different time" in r2.response
    assert r2.session.booking_draft.package_id and not r2.session.booking_draft.selected_slot
    assert r2.session.active_node == "node_lab_booking"
