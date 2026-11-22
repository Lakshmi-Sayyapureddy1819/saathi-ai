"""Who gets called, and when: eligibility, calling window, retries, do-not-call, and a full scheduled run."""
from datetime import date, datetime, timedelta

import pytest

from app.channels import outbound_scheduler as sch
from app.tools.lab_tools import LabTools
from app.workflow.state import MemberProfile, PendingCheckup

NOON = datetime(2026, 11, 25, 12, 0)


@pytest.fixture(autouse=True)
def _no_lab_outage(monkeypatch):
    monkeypatch.setenv("LAB_FAILURE_RATE", "0")


def _m(mid="M1", due=date(2026, 12, 1), pkg="LP_002", booked=None, lang="english") -> MemberProfile:
    return MemberProfile(member_id=mid, name=f"Member {mid}", age=40, language_pref=lang, past_bookings=booked or [],
                         pending_checkups=[PendingCheckup(package_id=pkg, due_date=due)])


def _plan(members, now=NOON, history=(), dnc=()):
    return sch.plan_schedule(members, LabTools(), now, history=history, do_not_call=dnc)


def _reasons(plan):
    return {s.member_id: s.reason for s in plan.skipped}


def test_due_soon_and_overdue_members_are_scheduled_earliest_due_first():
    plan = _plan([_m("A", due=date(2026, 12, 5)), _m("B", due=date(2026, 11, 20)), _m("C", due=date(2026, 12, 1))])
    assert [c.member_id for c in plan.calls] == ["B", "C", "A"]      # overdue first
    assert all(c.attempt_number == 1 for c in plan.calls)


def test_not_due_yet_nothing_pending_booked_and_do_not_call_are_skipped():
    plan = _plan([_m("FAR", due=date(2027, 3, 1)), _m("NONE").model_copy(update={"pending_checkups": []}),
                  _m("DONE", booked=["LP_002"]), _m("DNC")], dnc=["DNC"])
    assert plan.calls == []
    assert _reasons(plan) == {"FAR": "not_due_yet", "NONE": "nothing_pending", "DONE": "booked", "DNC": "do_not_call"}


@pytest.mark.parametrize("now,expected", [
    (datetime(2026, 11, 25, 7, 30), datetime(2026, 11, 25, 9, 0)),     # too early: wait for 09:00 today
    (datetime(2026, 11, 25, 9, 0), datetime(2026, 11, 25, 9, 0)),      # window opens: call now
    (datetime(2026, 11, 25, 18, 59), datetime(2026, 11, 25, 18, 59)),
    (datetime(2026, 11, 25, 19, 0), datetime(2026, 11, 26, 9, 0)),     # window closed: tomorrow 09:00
    (datetime(2026, 11, 25, 23, 0), datetime(2026, 11, 26, 9, 0))])
def test_calls_only_inside_the_calling_window(now, expected):
    assert _plan([_m()], now=now).calls[0].call_at == expected


def test_retry_waits_the_minimum_gap_and_stops_after_max_attempts():
    first = sch.CallAttempt(member_id="M1", package_id="LP_002", at=NOON, outcome="no_answer")
    soon = _plan([_m()], now=NOON + timedelta(hours=1), history=[first]).calls[0]
    assert soon.call_at == NOON + sch.MIN_RETRY_GAP and soon.attempt_number == 2
    tries = [first.model_copy(update={"at": NOON - timedelta(days=i)}) for i in range(3)]
    plan = _plan([_m()], history=tries)
    assert plan.calls == [] and _reasons(plan) == {"M1": "max_attempts"}


@pytest.mark.parametrize("outcome,reason", [("declined", "declined_before"), ("booked", "booked")])
def test_members_who_declined_or_booked_are_not_called_again(outcome, reason):
    h = sch.CallAttempt(member_id="M1", package_id="LP_002", at=NOON - timedelta(days=1), outcome=outcome)
    plan = _plan([_m()], history=[h])
    assert plan.calls == [] and _reasons(plan) == {"M1": reason}


def test_scheduled_run_places_due_calls_books_and_defers_the_rest():
    members = {"A": _m("A"), "B": _m("B", due=date(2026, 12, 3))}
    plan = _plan(list(members.values()), now=datetime(2026, 11, 25, 8, 0))     # before the window opens
    assert all(c.call_at == datetime(2026, 11, 25, 9, 0) for c in plan.calls)
    dialler = sch.SimulatedDialler(lambda m: ["yes please", "tomorrow", "09:00 AM", "yes confirm"]
                                   if m.member_id == "A" else ["no thanks"])
    assert sch.run_due_calls(plan, members, dialler, datetime(2026, 11, 25, 8, 0)) == []   # window not open yet
    attempts = sch.run_due_calls(plan, members, dialler, datetime(2026, 11, 25, 9, 5))
    assert {a.member_id: a.outcome for a in attempts} == {"A": "booked", "B": "declined"}
    after = _plan(list(members.values()), now=datetime(2026, 11, 25, 9, 10), history=attempts)
    assert after.calls == []                                                   # nobody is called twice
