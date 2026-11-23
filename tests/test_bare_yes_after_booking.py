"""A bare 'yes' after a booking is confirmed must get a clear 'nothing pending' reply, not 'I didn't quite catch that'."""
from app.workflow.graph import WorkflowGraph, execute_turn
from app.workflow.replies import say
from app.workflow.state import MemberProfile, UserSessionState


def _session() -> UserSessionState:
    return UserSessionState(channel="web", member=MemberProfile(member_id="MEM_T", name="T", age=30),
                            active_node="start", trace_id="t")


def test_bare_yes_after_confirmed_booking_says_nothing_pending(monkeypatch):
    monkeypatch.setenv("ALLOW_MOCK_LLM", "1")
    g = WorkflowGraph()
    g.lab_tools.failure_rate = 0.0
    s = _session()
    reply, s = execute_turn("book a Cardiac Risk Assessment tomorrow at 7:00 AM", s, graph=g)
    assert "yes" in reply.lower()                      # read-back asking for confirmation
    reply, s = execute_turn("yes", s, graph=g)
    assert "BOK_" in reply                             # booked
    reply, s = execute_turn("yes", s, graph=g)         # the member says yes again
    assert reply == say(s.reply_lang, "nothing_to_confirm")
    assert len(s.member.past_bookings) == 1            # and no second booking was created


def test_bare_yes_outside_booking_is_not_hijacked(monkeypatch):
    """'yes' in a wellness conversation must keep going to the coach, not the booking handler."""
    monkeypatch.setenv("ALLOW_MOCK_LLM", "1")
    g = WorkflowGraph()
    g.lab_tools.failure_rate = 0.0
    s = _session()
    reply, s = execute_turn("yes", s, graph=g)
    assert reply != say(s.reply_lang, "nothing_to_confirm")
