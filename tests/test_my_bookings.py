"""'My bookings' and cancelling a CONFIRMED booking: deterministic, owner-only, frees the slot."""
import pytest
from fastapi.testclient import TestClient

from app import api
from app.tools.lab_tools import LabTools
from app.workflow.graph import WorkflowGraph, execute_turn
from app.workflow.state import MemberProfile, UserSessionState


# ---------------- tool + graph level ----------------
def _setup(member="BK1"):
    g = WorkflowGraph()
    g.lab_tools = LabTools(failure_rate=0.0)
    s = UserSessionState(channel="chat", member=MemberProfile(member_id=member, name="T", age=30), active_node="start")
    return g, s


def _say(g, s, *msgs):
    out = ""
    for m in msgs:
        out, s = execute_turn(m, s, graph=g)
    return out, s


def _book(g, s, slot="9:30 am"):
    out, s = _say(g, s, "book thyroid test", slot, "yes")
    assert "Booking confirmed" in out or "Booking confirm ho gayi" in out
    return s, s.member.past_bookings[-1].split(" - ")[0]


def test_cancel_by_id_frees_the_slot_and_removes_it_from_history():
    g, s = _setup()
    s, bid = _book(g, s)
    out, s = _say(g, s, f"cancel {bid}")
    assert "cancelled your booking" in out and bid in out and "free again" in out
    assert not any(r.startswith(bid) for r in s.member.past_bookings)
    assert g.lab_tools.get_booking(bid, "BK1") is None
    _, s2 = _setup("BK2")
    g2 = g  # same schedule backend: the slot is bookable by someone else again
    out2, _ = _say(g2, s2, "book thyroid test", "9:30 am")
    assert "Just to confirm" in out2


def test_cancel_without_id_asks_which_and_never_cancels_by_itself():
    g, s = _setup()
    s, bid = _book(g, s)
    out, s = _say(g, s, "cancel")
    assert bid in out and "reply 'cancel" in out
    assert g.lab_tools.get_booking(bid, "BK1") is not None  # still booked
    out, s = _say(g, s, f"cancel {bid}")
    assert "cancelled your booking" in out


def test_cancel_with_two_bookings_lists_both():
    g, s = _setup()
    s, b1 = _book(g, s, "9:30 am")
    s, b2 = _book(g, s, "10:30 am")
    out, s = _say(g, s, "cancel my booking")
    assert b1 in out and b2 in out and "Which one" in out


def test_a_member_cannot_cancel_someone_elses_booking():
    g, a = _setup("OWNER")
    a, bid = _book(g, a)
    _, b = _setup("OTHER")
    out, b = _say(g, b, f"cancel {bid}")
    assert "couldn't find an active booking" in out
    assert g.lab_tools.get_booking(bid, "OWNER") is not None


def test_unknown_or_already_cancelled_id():
    g, s = _setup()
    out, s = _say(g, s, "cancel BOK_BK1_0000")
    assert "couldn't find an active booking" in out
    s, bid = _book(g, s)
    _say(g, s, f"cancel {bid}")
    out, s = _say(g, s, f"cancel {bid}")
    assert "couldn't find an active booking" in out


def test_cancel_during_a_pending_draft_still_cancels_the_draft_not_the_booking():
    g, s = _setup()
    s, bid = _book(g, s)
    out, s = _say(g, s, "book thyroid test", "cancel")
    assert "cancelled that booking" in out
    assert g.lab_tools.get_booking(bid, "BK1") is not None  # the confirmed booking is untouched


def test_hinglish_cancel_reply():
    g, s = _setup()
    s, bid = _book(g, s)
    out, s = _say(g, s, f"mujhe cancel karna hai {bid}")
    assert s.reply_lang == "hinglish" and "cancel kar di gayi hai" in out


def test_seed_history_is_never_listed_or_cancellable():
    g, s = _setup()
    s.member = s.member.model_copy(update={"past_bookings": ["LP_001", "LP_005"]})
    out, s = _say(g, s, "cancel")  # nothing real to cancel: falls through to normal handling, cancels nothing
    assert s.member.past_bookings == ["LP_001", "LP_005"]


# ---------------- API level ----------------
@pytest.fixture()
def client(monkeypatch):
    monkeypatch.delenv("COORDINATOR_TOKEN", raising=False)
    api._GRAPH.lab_tools = LabTools(failure_rate=0.0)
    api._records.clear()
    api._create_log.clear()  # the per-minute session limiter is process-global; each test starts fresh
    with TestClient(api.app) as c:
        yield c
    api._records.clear()
    api._create_log.clear()  # the per-minute session limiter is process-global; each test starts fresh
    api._GRAPH.lab_tools = LabTools(failure_rate=0.0)


def _new(c, member):
    r = c.post("/api/sessions", json={"member_id": member}).json()
    return r["session"]["session_id"], {"Authorization": f"Bearer {r['session_token']}"}


def _say_api(c, sid, hdr, text):
    r = c.post(f"/api/sessions/{sid}/messages", json={"text": text}, headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()


def test_api_lists_and_cancels_bookings_through_the_adk_workflow(client):
    sid, hdr = _new(client, "MEM_1001")
    assert client.get(f"/api/sessions/{sid}", headers=hdr).json()["bookings"] == []
    for m in ("book thyroid test", "10:30 am", "yes"):
        v = _say_api(client, sid, hdr, m)
    assert [b["slot"] for b in v["bookings"]] == ["10:30 AM"]
    bid = v["bookings"][0]["booking_id"]
    v = _say_api(client, sid, hdr, f"cancel {bid}")
    assert v["bookings"] == [] and "cancelled your booking" in v["messages"][-1]["text"]
    # a later turn must not resurrect it (ADK session state carries the cancellation)
    v = _say_api(client, sid, hdr, "what yoga helps with stress")
    assert v["bookings"] == []
    # and the slot is free for another member
    s2, h2 = _new(client, "MEM_1002")
    v2 = _say_api(client, s2, h2, "book thyroid test")
    assert "10:30 AM" in v2["booking"]["slots"]


def test_api_bookings_are_per_session(client):
    s1, h1 = _new(client, "MEM_1001")
    for m in ("book thyroid test", "9:30 am", "yes"):
        v1 = _say_api(client, s1, h1, m)
    s2, h2 = _new(client, "MEM_1001")  # same member, new session
    assert client.get(f"/api/sessions/{s2}", headers=h2).json()["bookings"] == []
    bid = v1["bookings"][0]["booking_id"]
    v = _say_api(client, s2, h2, f"cancel {bid}")
    assert "couldn't find an active booking" in v["messages"][-1]["text"]
    assert len(client.get(f"/api/sessions/{s1}", headers=h1).json()["bookings"]) == 1
