"""Outbound reminder call: opener, booking, decline, and that safety still wins mid-call."""
from datetime import date

import pytest

from app.channels.outbound import OutboundCall, pick_pending
from app.channels.voice_agent import VoiceAgent
from app.tools.lab_tools import LabTools
from app.workflow.graph import WorkflowGraph
from app.workflow.state import MemberProfile, PendingCheckup


@pytest.fixture(autouse=True)
def _no_lab_outage(monkeypatch):
    monkeypatch.setenv("LAB_FAILURE_RATE", "0")


def _member(lang="english", pending=None, booked=None) -> MemberProfile:
    return MemberProfile(
        member_id="MEM_T", name="Test Member", age=40, language_pref=lang, past_bookings=booked or [],
        pending_checkups=pending if pending is not None else [
            PendingCheckup(package_id="LP_004", due_date=date(2026, 12, 20)),
            PendingCheckup(package_id="LP_002", due_date=date(2026, 12, 5))])


def _call(member: MemberProfile) -> OutboundCall:
    graph = WorkflowGraph(model_node="voice")
    return OutboundCall(member, agent=VoiceAgent(graph=graph, verbose=False, tts_char_delay=0), graph=graph)


def test_picks_earliest_due_and_skips_already_booked():
    tools = LabTools()
    assert pick_pending(_member(), tools).package_id == "LP_002"
    assert pick_pending(_member(booked=["LP_002"]), tools).package_id == "LP_004"
    assert pick_pending(_member(pending=[PendingCheckup(package_id="LP_999", due_date=date(2026, 12, 1))]),
                        tools) is None


def test_opening_names_the_package_and_follows_member_language():
    en = _call(_member("english"))
    assert "Thyroid Screening Profile" in en.start() and "Hello Test" in en.plan.opening_line
    hi = _call(_member("hinglish"))
    assert "Namaste Test" in hi.start() and hi.plan.language == "hinglish"


def test_member_with_nothing_pending_gets_no_call():
    call = _call(_member(pending=[]))
    assert call.start() is None and call.finished
    assert call.result([]).outcome == "no_pending_checkup"


def test_call_books_the_pending_package():
    member = _member()
    call = _call(member)
    call.start()
    for said in ["yes please", "tomorrow", "09:00 AM", "yes confirm"]:
        call.reply(said)
    res = call.result([])
    assert res.outcome == "booked" and len(res.booking_ids) == 1
    assert "Thyroid Screening Profile" in res.booking_ids[0]
    assert res.transcript[0].startswith("AGENT: Hello Test")


@pytest.mark.parametrize("said", ["no", "not now", "nahi", "No thanks."])
def test_plain_decline_ends_call_without_booking(said):
    call = _call(_member())
    call.start()
    call.reply(said)
    assert call.finished and call.result([]).outcome == "declined"
    assert call.session.booking_draft.package_id is None


def test_red_flag_mid_call_escalates_and_never_books():
    call = _call(_member())
    call.start()
    call.reply("I have severe chest pain and I am breathless")
    assert call.session.triage_status.status == "RED_CRISIS"
    assert call.finished
    res = call.result([])
    assert res.outcome == "unfinished" and res.booking_ids == []


def test_decline_that_mentions_a_symptom_is_not_swallowed():
    call = _call(_member())
    call.start()
    call.reply("no, I have severe chest pain")
    assert call.session.triage_status.status == "RED_CRISIS"
    assert not call.declined


def test_trace_id_is_set_and_propagated():
    call = _call(_member())
    call.start()
    call.reply("yes")
    call.reply("tomorrow")
    assert len(call.trace_id) == 32
    assert call.session.trace_id == call.trace_id          # same trace for the plan and every turn
    assert {t.trace_id for t in call.session.turn_history} == {call.trace_id}
