"""POST /api/sessions/{id}/reminder-call: the demo outbound call from the UI. Hermetic: the call itself is stubbed here
(the real flow is covered by tests/test_outbound_call.py)."""
import pytest
from fastapi.testclient import TestClient

from app import api
from app.channels.outbound import OutboundCallResult
from app.tools.lab_tools import LabTools


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.delenv("COORDINATOR_TOKEN", raising=False)
    api._GRAPH.lab_tools = LabTools(failure_rate=0.0)
    api._records.clear()
    api._create_log.clear()
    with TestClient(api.app) as c:
        yield c
    api._records.clear()
    api._create_log.clear()


def _new(c, member="MEM_1001"):
    r = c.post("/api/sessions", json={"member_id": member})
    assert r.status_code == 201, r.text
    body = r.json()
    return body["session"]["session_id"], {"Authorization": f"Bearer {body['session_token']}"}


def _stub_call(monkeypatch, booking_ids):
    seen = {}

    def fake(member, replies=None):
        seen["member_id"] = member.member_id
        return OutboundCallResult(outcome="booked" if booking_ids else "declined", trace_id="t-1",
                                  transcript=["AGENT: hello", "MEMBER: haan kar do"], booking_ids=list(booking_ids))

    monkeypatch.setattr(api, "run_scripted_call", fake)
    return seen


def test_booked_call_returns_transcript_and_adds_booking_to_the_member(client, monkeypatch):
    booking = "BOK_MEM_1001_9999 - Thyroid Screening Profile on 2026-11-28 09:00 AM"
    seen = _stub_call(monkeypatch, [booking])
    sid, hdr = _new(client)
    before = list(api._records[sid].session.member.past_bookings)
    r = client.post(f"/api/sessions/{sid}/reminder-call", headers=hdr)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["outcome"] == "booked"
    assert body["booking_ids"] == [booking]
    assert body["transcript"][0].startswith("AGENT:")
    assert body["simulated"] is True
    assert seen["member_id"] == "MEM_1001"
    assert booking in api._records[sid].session.member.past_bookings
    assert api._records[sid].session.member.past_bookings != before


def test_declined_call_leaves_bookings_unchanged(client, monkeypatch):
    _stub_call(monkeypatch, [])
    sid, hdr = _new(client)
    before = list(api._records[sid].session.member.past_bookings)
    body = client.post(f"/api/sessions/{sid}/reminder-call", headers=hdr).json()
    assert body["outcome"] == "declined"
    assert api._records[sid].session.member.past_bookings == before


def test_wrong_token_is_rejected(client, monkeypatch):
    _stub_call(monkeypatch, [])
    sid, _ = _new(client)
    r = client.post(f"/api/sessions/{sid}/reminder-call", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_unknown_session_is_404(client, monkeypatch):
    _stub_call(monkeypatch, [])
    r = client.post("/api/sessions/does-not-exist/reminder-call", headers={"Authorization": "Bearer x"})
    assert r.status_code == 404


def test_blocked_while_waiting_for_a_coordinator(client, monkeypatch):
    _stub_call(monkeypatch, [])
    sid, hdr = _new(client)
    api._records[sid].pending_interrupt_id = "int-1"
    r = client.post(f"/api/sessions/{sid}/reminder-call", headers=hdr)
    assert r.status_code == 409


def test_scripted_member_takes_the_first_offered_slot():
    from app.channels.outbound import first_offered_slot
    listing = "Available slots:\n- 09:30 AM\n- 10:00 AM\nAapko kaun sa samay theek rahega?"
    assert first_offered_slot(listing) == "09:30 AM"
    assert first_offered_slot("Kya main abhi aapke liye book kar doon?") is None
