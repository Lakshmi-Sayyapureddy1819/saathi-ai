"""HTTP API: auth, session isolation, booking state, safety, coordinator security. Hermetic (no keys, no network)."""
import pytest
from fastapi.testclient import TestClient

from app import api
from app.tools.lab_tools import LabTools


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


def _new(c, member="MEM_1002"):
    r = c.post("/api/sessions", json={"member_id": member})
    assert r.status_code == 201, r.text
    body = r.json()
    return body["session"]["session_id"], {"Authorization": f"Bearer {body['session_token']}"}


def _say(c, sid, hdr, text):
    r = c.post(f"/api/sessions/{sid}/messages", json={"text": text}, headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()


def _last(view):
    return view["messages"][-1]


# ---------------- sessions & auth ----------------
def test_unknown_or_malformed_member_rejected(client):
    assert client.post("/api/sessions", json={"member_id": "MEM_9999"}).status_code == 404
    assert client.post("/api/sessions", json={"member_id": "../../etc"}).status_code == 422


def test_session_requires_its_own_token(client):
    sid, hdr = _new(client)
    assert client.get(f"/api/sessions/{sid}").status_code == 401
    assert client.get(f"/api/sessions/{sid}", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.post(f"/api/sessions/{sid}/messages", json={"text": "hi"}).status_code == 401
    assert client.get(f"/api/sessions/{sid}", headers=hdr).status_code == 200


def test_sessions_are_isolated(client):
    a, ha = _new(client, "MEM_1001")
    b, hb = _new(client, "MEM_1002")
    assert a != b
    assert client.get(f"/api/sessions/{a}", headers=hb).status_code == 401  # B's token cannot read A
    _say(client, a, ha, "book thyroid test")
    vb = client.get(f"/api/sessions/{b}", headers=hb).json()
    assert vb["messages"] == [] and vb["booking"]["stage"] == "idle"
    assert client.get(f"/api/sessions/{a}", headers=ha).json()["booking"]["stage"] == "choosing_slot"


def test_delete_session(client):
    sid, hdr = _new(client)
    assert client.delete(f"/api/sessions/{sid}", headers=hdr).json()["deleted"] is True
    assert client.get(f"/api/sessions/{sid}", headers=hdr).status_code == 404


def test_message_validation(client):
    sid, hdr = _new(client)
    for bad in ("", "   ", "x" * 501):
        assert client.post(f"/api/sessions/{sid}/messages", json={"text": bad}, headers=hdr).status_code == 422


def test_cors_only_allows_configured_origin(client):
    ok = client.options("/api/health", headers={"Origin": "http://localhost:5173",
                                                "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options("/api/health", headers={"Origin": "http://evil.example",
                                                 "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers


def test_config_never_leaks_keys(client):
    body = client.get("/api/config").json()
    assert set(body) == {"llm_configured", "coordinator_console_enabled", "max_message_chars"}


# ---------------- booking through the real workflow ----------------
def test_generic_request_then_package_then_slot_then_confirm(client):
    sid, hdr = _new(client)
    v = _say(client, sid, hdr, "Book a blood test")
    assert v["booking"]["stage"] == "choosing_package" and len(v["booking"]["options"]) == 12
    v = _say(client, sid, hdr, "LP_002")
    assert v["booking"]["stage"] == "choosing_slot" and v["booking"]["package"]["name"] == "Thyroid Screening Profile"
    assert "09:30 AM" in v["booking"]["slots"] and len(v["booking"]["dates"]) == 3
    v = _say(client, sid, hdr, "10:30 AM")  # short follow-up keeps context
    assert v["booking"]["stage"] == "confirming" and v["booking"]["slot"] == "10:30 AM"
    v = _say(client, sid, hdr, "yes confirm")
    last = _last(v)
    assert last["kind"] == "booking_confirmed" and last["confirmation"]["booking_id"].startswith("BOK_MEM_1002_")
    assert last["confirmation"]["slot"] == "10:30 AM" and v["booking"]["stage"] == "idle"
    assert last["confirmation"]["booking_id"] in last["text"]  # the id shown came from the tool, not the UI


def test_booked_slot_is_not_offered_again(client):
    s1, h1 = _new(client, "MEM_1001")
    for m in ("book thyroid test", "9:30 am", "yes"):
        v = _say(client, s1, h1, m)
    assert _last(v)["kind"] == "booking_confirmed"
    s2, h2 = _new(client, "MEM_1002")
    v = _say(client, s2, h2, "book thyroid test")
    assert "09:30 AM" not in v["booking"]["slots"]


def test_ambiguous_package_asks_again(client):
    sid, hdr = _new(client)
    _say(client, sid, hdr, "book vitality test")  # Senior Citizen Vitality (Male) / (Female)
    v = _say(client, sid, hdr, "senior")
    assert v["booking"]["stage"] == "choosing_package" and 2 <= len(v["booking"]["options"]) <= 5
    assert v["booking"]["package"] is None


def test_cancel_mid_booking(client):
    sid, hdr = _new(client)
    _say(client, sid, hdr, "book thyroid test")
    v = _say(client, sid, hdr, "cancel")
    assert v["booking"]["stage"] == "idle" and "cancelled" in _last(v)["text"].lower()


def test_change_time_at_confirmation(client):
    sid, hdr = _new(client)
    _say(client, sid, hdr, "book thyroid test")
    _say(client, sid, hdr, "9:30 am")
    v = _say(client, sid, hdr, "change time")
    assert v["booking"]["stage"] == "choosing_slot"


# ---------------- medical safety ----------------
def test_emergency_response_is_deterministic_and_structured(client):
    sid, hdr = _new(client)
    v = _say(client, sid, hdr, "I have severe chest pain")
    last = _last(v)
    assert v["triage_status"] == "RED_CRISIS" and last["kind"] == "emergency"
    assert last["emergency"]["helplines"] and "112" in last["text"]


def test_hinglish_emergency(client):
    sid, hdr = _new(client)
    assert _last(_say(client, sid, hdr, "Mere seene mein dard hai"))["kind"] == "emergency"


def test_emergency_clears_booking_draft(client):
    sid, hdr = _new(client)
    _say(client, sid, hdr, "book thyroid test")
    v = _say(client, sid, hdr, "I can't breathe")
    assert v["booking"]["stage"] == "idle"


def test_no_diagnosis_reply(client):
    sid, hdr = _new(client)
    last = _last(_say(client, sid, hdr, "do I have diabetes?"))
    assert last["kind"] == "safety_notice" and "can't provide a medical diagnosis" in last["text"]


# ---------------- human handoff + coordinator security ----------------
def _to_handoff(client, monkeypatch, member="MEM_1003"):
    monkeypatch.setattr("app.tools.lab_tools.time.sleep", lambda *_: None)
    api._GRAPH.lab_tools = LabTools(failure_rate=1.0)
    sid, hdr = _new(client, member)
    for m in ("book thyroid test", "9:30 am", "yes"):
        v = _say(client, sid, hdr, m)
    return sid, hdr, v


def test_handoff_pending_blocks_messages_and_is_not_self_approvable(client, monkeypatch):
    monkeypatch.setenv("COORDINATOR_TOKEN", "coord-secret-for-tests")
    sid, hdr, v = _to_handoff(client, monkeypatch)
    assert v["status"] == "awaiting_coordinator" and v["handoff"]["status"] == "pending"
    assert v["handoff"]["ticket_id"].startswith("CARE_") and _last(v)["kind"] == "handoff"
    r = client.post(f"/api/sessions/{sid}/messages", json={"text": "hello"}, headers=hdr)
    assert r.status_code == 409
    # The member's own session token must not approve; neither must a missing/wrong coordinator token.
    assert client.post(f"/api/coordinator/approvals/{sid}", json={"approved": True}, headers=hdr).status_code == 401
    assert client.post(f"/api/coordinator/approvals/{sid}", json={"approved": True},
                       headers={"X-Coordinator-Token": "wrong"}).status_code == 401
    assert client.get(f"/api/sessions/{sid}", headers=hdr).json()["handoff"]["status"] == "pending"


def test_coordinator_disabled_without_token(client, monkeypatch):
    sid, hdr, _ = _to_handoff(client, monkeypatch)
    assert client.get("/api/coordinator/approvals").status_code == 503
    assert client.post(f"/api/coordinator/approvals/{sid}", json={"approved": True}).status_code == 503


def test_coordinator_approves(client, monkeypatch):
    monkeypatch.setenv("COORDINATOR_TOKEN", "coord-secret-for-tests")
    ch = {"X-Coordinator-Token": "coord-secret-for-tests"}
    sid, hdr, _ = _to_handoff(client, monkeypatch)
    items = client.get("/api/coordinator/approvals", headers=ch).json()["items"]
    assert [i["session_id"] for i in items] == [sid] and items[0]["package_name"] == "Thyroid Screening Profile"
    assert "text" not in items[0] and "messages" not in items[0]  # no member message text exposed
    assert client.post(f"/api/coordinator/approvals/{sid}", json={"approved": True}, headers=ch).status_code == 200
    v = client.get(f"/api/sessions/{sid}", headers=hdr).json()
    assert v["status"] == "active" and v["handoff"]["status"] == "approved"
    assert _last(v)["kind"] == "handoff_resolved" and "approved" in _last(v)["text"]
    assert client.post(f"/api/coordinator/approvals/{sid}", json={"approved": True}, headers=ch).status_code == 404


def test_coordinator_rejects_then_member_can_rebook(client, monkeypatch):
    monkeypatch.setenv("COORDINATOR_TOKEN", "coord-secret-for-tests")
    ch = {"X-Coordinator-Token": "coord-secret-for-tests"}
    sid, hdr, _ = _to_handoff(client, monkeypatch)
    client.post(f"/api/coordinator/approvals/{sid}", json={"approved": False, "note": "Lab closed."}, headers=ch)
    v = client.get(f"/api/sessions/{sid}", headers=hdr).json()
    assert v["handoff"] == {"status": "rejected", "ticket_id": v["handoff"]["ticket_id"], "note": "Lab closed."}
    assert v["booking"]["stage"] == "choosing_slot"  # package kept, member picks another time
    api._GRAPH.lab_tools = LabTools(failure_rate=0.0)
    _say(client, sid, hdr, "10:00 AM")
    v = _say(client, sid, hdr, "yes")
    assert _last(v)["kind"] == "booking_confirmed"
