"""Cancel / change handling inside the booking flow (needed by the web UI's Cancel and Change-time buttons)."""
from datetime import date, timedelta

from app.tools.lab_tools import LabTools
from app.workflow.graph import WorkflowGraph, execute_turn
from app.workflow.state import MemberProfile, UserSessionState


def _setup():
    g = WorkflowGraph()
    g.lab_tools = LabTools(failure_rate=0.0)
    s = UserSessionState(channel="chat", member=MemberProfile(member_id="CC1", name="T", age=30), active_node="start")
    return g, s


def _say(g, s, *msgs):
    out = ""
    for m in msgs:
        out, s = execute_turn(m, s, graph=g)
    return out, s


def test_cancel_while_choosing_slot_resets_draft():
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test", "cancel")
    assert "cancelled" in out.lower()
    assert s.booking_draft.package_id is None
    assert s.active_node == "node_lab_booking"  # stayed in booking: not bounced to the wellness coach


def test_cancel_at_confirmation_still_works():
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test", "9:30 am", "cancel")
    assert "cancelled" in out.lower() and s.booking_draft.package_id is None


def test_change_time_at_confirmation_rereads_new_slot():
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test", "9:30 am", "make it 10:30 am instead")
    assert "10:30 AM" in out and "09:30" not in out
    assert s.booking_draft.selected_slot == "10:30 AM" and not s.booking_draft.verbal_confirmed
    out, s = _say(g, s, "yes confirm")
    assert "Booking confirmed" in out
    assert any("10:30 AM" in b for b in s.member.past_bookings)


def test_change_request_without_time_relists_slots():
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test", "9:30 am", "change time")
    assert "Available slots" in out and s.booking_draft.selected_slot is None
    assert s.booking_draft.package_name == "Thyroid Screening Profile"  # package is kept


def test_bare_no_at_confirmation_still_cancels_and_yes_still_confirms():
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test", "9:30 am", "no")
    assert "cancelled" in out.lower()
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test", "9:30 am", "yes")
    assert "Booking confirmed" in out


def test_explicit_day_word_overrides_stored_date():
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test")  # defaults to tomorrow
    assert s.booking_draft.selected_date == date.today() + timedelta(days=1)
    out, s = _say(g, s, "today")
    assert s.booking_draft.selected_date == date.today() and "Available slots" in out


# ---- confirmation that carries a DIFFERENT time is a change, never a booking of the old slot ----
import pytest


@pytest.mark.parametrize("reply,new_slot", [
    ("yes, make it 11 am", "11:00 AM"),
    ("yes but 11 am instead", "11:00 AM"),
    ("yes please, can we do 10 am", "10:00 AM"),
])
def test_confirmation_with_different_time_is_a_change_not_a_booking(reply, new_slot):
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test", "9:30 am", reply)
    assert "Booking confirmed" not in out and s.member.past_bookings == []        # nothing booked
    assert s.booking_draft.selected_slot == new_slot and not s.booking_draft.verbal_confirmed
    assert new_slot in out and "09:30" not in out and "confirm" in out.lower()     # revised details re-read
    out, s = _say(g, s, "yes")                                                     # only now does it book
    assert "Booking confirmed" in out and new_slot in s.member.past_bookings[-1] and "09:30" not in s.member.past_bookings[-1]


def test_yes_restating_the_same_time_still_confirms():
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test", "9:30 am", "yes, 9:30 am")
    assert "Booking confirmed" in out and "09:30 AM" in s.member.past_bookings[-1]


def test_yes_with_unavailable_time_does_not_book_old_slot():
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test", "9:30 am", "yes, make it 3 pm")
    assert s.member.past_bookings == [] and "Booking confirmed" not in out
    assert s.booking_draft.selected_slot is None and "Available slots" in out


def test_yes_with_change_word_but_no_time_relists_instead_of_booking():
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test", "9:30 am", "yes, but change the time")
    assert s.member.past_bookings == [] and "Available slots" in out


def test_plain_yes_and_plain_change_unchanged():
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test", "9:30 am", "yes")
    assert "Booking confirmed" in out
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test", "9:30 am", "make it 11 am")
    assert s.booking_draft.selected_slot == "11:00 AM" and s.member.past_bookings == []


@pytest.mark.parametrize("word", ["no", "cancel"])
def test_no_and_cancel_keep_cancelling(word):
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test", "9:30 am", word)
    assert "cancelled" in out.lower() and s.booking_draft.package_id is None and s.member.past_bookings == []


def test_cancel_with_a_time_cancels_and_does_not_change_or_book():
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test", "9:30 am", "cancel, I'll do 11 am later")
    assert "cancelled" in out.lower() and s.member.past_bookings == [] and s.booking_draft.package_id is None


def test_changing_time_after_a_change_keeps_working_and_clears_stale_confirmation():
    g, s = _setup()
    _, s = _say(g, s, "book thyroid test", "9:30 am", "yes, make it 11 am")
    out, s = _say(g, s, "actually 10 am")
    assert s.booking_draft.selected_slot == "10:00 AM" and not s.booking_draft.verbal_confirmed
    out, s = _say(g, s, "yes")
    assert "10:00 AM" in s.member.past_bookings[-1] and len(s.member.past_bookings) == 1


def test_day_change_at_confirmation_is_not_booked_on_old_date():
    g, s = _setup()
    _, s = _say(g, s, "book thyroid test", "9:30 am")
    old = s.booking_draft.selected_date
    out, s = _say(g, s, "yes, today at 9:30 am")
    assert s.member.past_bookings == [] and s.booking_draft.selected_date != old


def test_not_yet_at_confirmation_keeps_the_pending_booking_and_books_nothing():
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test", "9:30 am", "not yet")
    assert s.active_node == "node_lab_booking" and s.member.past_bookings == []
    assert s.booking_draft.selected_slot == "09:30 AM" and "yes" in out.lower()
    out, s = _say(g, s, "yes")
    assert "Booking confirmed" in out


def test_unparseable_split_time_fails_safe_without_booking_the_old_slot():
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test", "9:30 am", "yes 10 30")   # parsed as 10:00 today: a change, never the old slot
    assert s.member.past_bookings == [] and "Booking confirmed" not in out
