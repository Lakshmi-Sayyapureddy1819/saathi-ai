"""Booking-adjacent questions that need no package: answered by code, never by the 'no package found' fallback."""
import pytest

from app.workflow.graph import WorkflowGraph, execute_turn
from app.workflow.replies import MSG
from app.workflow.state import MemberProfile, UserSessionState


def _session(past=()):
    m = MemberProfile(member_id="M_BQ", name="Asha", age=30, past_bookings=list(past))
    return UserSessionState(channel="eval", member=m, active_node="start")


def _run(text, past=()):
    g = WorkflowGraph()
    g.lab_tools.failure_rate = 0.0
    reply, session = execute_turn(text, _session(past), graph=g)
    return reply, session


NONE_FOUND = (MSG["none_found"][0][:40], MSG["none_found"][1][:40])


@pytest.mark.parametrize("text", ["What are my past bookings?", "show my bookings", "which tests have I booked"])
def test_listing_bookings_without_any_says_so(text):
    reply, _ = _run(text)
    assert reply == MSG["no_bookings"][0]


def test_listing_bookings_shows_the_members_records():
    rec = "BOK_M_BQ_1234 - Thyroid Screening Profile on 2026-12-01 08:00 AM"
    reply, _ = _run("What are my past bookings?", past=[rec])
    assert rec in reply and "couldn't find a lab package" not in reply


@pytest.mark.parametrize("text", ["Confirm my appointment", "confirm"])
def test_confirm_with_nothing_pending_is_explained(text):
    reply, session = _run(text)
    assert reply == MSG["nothing_to_confirm"][0]
    assert session.booking_draft.package_id is None
