"""Regression: an explicit date used to be silently replaced by 'tomorrow' (e.g. '25 November' -> 24 November)."""
from datetime import date

import pytest

from app.tools.slots import DATE_WORD, explicit_date, resolve_date

TODAY = date(2026, 11, 23)  # a Monday


@pytest.mark.parametrize("text,expected", [
    ("book a cardiac test on 25 November at 8:00 AM", date(2026, 11, 25)),
    ("25th nov please", date(2026, 11, 25)),
    ("on 3rd of December", date(2026, 12, 3)),
    ("november 30", date(2026, 11, 30)),
    ("Nov 26th morning", date(2026, 11, 26)),
    ("5 January", date(2027, 1, 5)),                 # already passed this year -> next year
    ("on friday", date(2026, 11, 27)),
    ("next monday", date(2026, 11, 30)),              # today is Monday: next occurrence, not today
    ("tuesday 7 am", date(2026, 11, 24)),
])
def test_explicit_dates_resolve(text, expected):
    assert resolve_date(text, TODAY) == expected


@pytest.mark.parametrize("text,expected", [
    ("tomorrow", date(2026, 11, 24)), ("kal subah", date(2026, 11, 24)), ("today", TODAY), ("aaj", TODAY),
    ("parso", date(2026, 11, 25)), ("day after tomorrow", date(2026, 11, 25)),
    ("book a sugar test", date(2026, 11, 24)),        # nothing stated: legacy default is tomorrow
])
def test_existing_relative_words_unchanged(text, expected):
    assert resolve_date(text, TODAY) == expected


def test_impossible_date_is_not_guessed():
    assert explicit_date("31 November", TODAY) is None


@pytest.mark.parametrize("text", ["may I book a test", "I march forward", "the sat", "9 am", "7:30", "Test 1", "package 2"])
def test_ordinary_words_and_numbers_are_not_dates(text):
    assert not DATE_WORD.search(text)
    assert explicit_date(text, TODAY) is None


def test_booking_flow_keeps_the_requested_date(monkeypatch):
    from app.workflow.graph import WorkflowGraph, execute_turn
    from app.workflow.state import MemberProfile, UserSessionState
    monkeypatch.setenv("ALLOW_MOCK_LLM", "1")
    g = WorkflowGraph(); g.lab_tools.failure_rate = 0.0
    s = UserSessionState(channel="web", member=MemberProfile(member_id="MEM_D", name="D", age=30), active_node="start", trace_id="t")
    target = resolve_date("25 November")
    reply, s = execute_turn("I want to book a Cardiac Risk Assessment on 25 November at 8:00 AM", s, graph=g)
    assert target.strftime("%d %B %Y").lstrip("0") in reply or target.strftime("%-d %B %Y") in reply or str(target.day) in reply
    assert s.booking_draft.selected_date == target
