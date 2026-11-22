"""Misspellings should still resolve to the intended package; an offered-nowhere time gets a clear message."""
import pytest

from app.tools.lab_tools import LabTools, _edit_distance, _same_word
from app.workflow.graph import WorkflowGraph, execute_turn
from app.workflow.state import MemberProfile, UserSessionState


def _setup():
    g = WorkflowGraph()
    g.lab_tools = LabTools(failure_rate=0.0)
    s = UserSessionState(channel="chat", member=MemberProfile(member_id="TY1", name="T", age=30), active_node="start")
    return g, s


def _say(g, s, *msgs):
    out = ""
    for m in msgs:
        out, s = execute_turn(m, s, graph=g)
    return out, s


def test_edit_distance_counts_swaps_as_one():
    assert _edit_distance("thyroid", "throid") == 1
    assert _edit_distance("thyroid", "thyriod") == 1
    assert _edit_distance("abc", "abc") == 0


def test_short_words_are_never_fuzzy_matched():
    assert not _same_word("male", "female")
    assert not _same_word("mens", "women")
    assert not _same_word("vitamin", "vitality")
    assert _same_word("throid", "thyroid") and _same_word("diabetic", "diabetes")


@pytest.mark.parametrize("typo", ["throid", "thyriod", "thyroyd", "thyroid tset", "book a throid test"])
def test_typo_reply_after_generic_request_selects_thyroid(typo):
    g, s = _setup()
    _, s = _say(g, s, "Book a blood test")
    out, s = _say(g, s, typo)
    assert s.booking_draft.package_name == "Thyroid Screening Profile", out


@pytest.mark.parametrize("typo", ["book a throid test", "book cardaic risk assessment", "book vitamn d test"])
def test_typo_in_first_request_finds_package(typo):
    g, s = _setup()
    out, s = _say(g, s, typo)
    assert s.booking_draft.package_id is not None, out


def test_typo_package_then_full_booking():
    g, s = _setup()
    out, s = _say(g, s, "Book a blood test", "throid", "9 am", "yes")
    assert "Booking confirmed" in out and "Thyroid" in s.member.past_bookings[-1]


def test_typo_does_not_break_male_female_disambiguation():
    g, s = _setup()
    _, s = _say(g, s, "book vitality test", "senior")
    out, s = _say(g, s, "femal")  # 5-letter typo of a 6-letter word -> still female
    assert s.booking_draft.package_name == "Senior Citizen Vitality (Female)", out


def test_gibberish_still_not_matched():
    g, s = _setup()
    out, s = _say(g, s, "Book a blood test", "qwzx plmk")
    assert s.booking_draft.package_id is None and "didn't recognise" in out


def test_unavailable_clock_time_is_called_out():
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test", "9pm")
    assert "isn't available" in out and "09:00 AM" in out
    assert s.booking_draft.selected_slot is None and s.member.past_bookings == []


def test_no_unavailable_message_when_no_time_was_given():
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test")
    assert "isn't available" not in out and "Available slots" in out
