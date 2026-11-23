"""Production behaviour: no mock text to members, durable state, real-adapter contracts, safety alerts, startup guard."""
from datetime import date

import pytest
import requests
from fastapi.testclient import TestClient

from app import api
from app.config import get_settings, readiness
from app.persistence.store import Store
from app.safety import alerts
from app.safety.alerts import deliver, dispatch_emergency
from app.safety.triage_gate import dispatch_emergency_sms
from app.tools.lab_backend import HttpLabBackend, PartnerUnavailable, SlotTaken
from app.tools.lab_tools import LabTools
from app.workflow.graph import WorkflowGraph
from app.workflow.model_client import ModelClient
from app.workflow.state import MemberProfile, UserSessionState


# ------------------------------------------------------------------ no mock replies to members
def _session():
    return UserSessionState(channel="web", member=MemberProfile(member_id="MEM_X", name="A", age=30),
                            active_node="start", trace_id="t")


def test_without_a_key_and_mock_off_the_client_fails_closed(monkeypatch):
    monkeypatch.setenv("ALLOW_MOCK_LLM", "0")
    with pytest.raises(RuntimeError):
        ModelClient().generate("hello")


def test_coach_gives_an_honest_unavailable_reply_not_mock_text(monkeypatch):
    monkeypatch.setenv("ALLOW_MOCK_LLM", "0")
    g = WorkflowGraph()
    g.use_cache, g.planner = False, None
    out, _ = g.node_program_coach("Tell me about Kapalbhati", _session())
    assert "[MOCK" not in out and out.strip()


def test_mock_is_only_available_when_explicitly_allowed(monkeypatch):
    monkeypatch.setenv("ALLOW_MOCK_LLM", "1")
    assert ModelClient().generate("hello").mock is True


# ------------------------------------------------------------------ readiness / startup guard
def _prod_env(monkeypatch, **extra):
    base = {"APP_ENV": "production", "ALLOW_MOCK_LLM": "0", "ALLOW_SIMULATORS": "", "LAB_BACKEND": "",
            "LAB_API_URL": "", "LAB_API_KEY": "", "COORDINATOR_TOKEN": "", "FRONTEND_ORIGINS": "", "GEMINI_API_KEY": "",
            "OPENAI_API_KEY": "", "TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "", "SMTP_HOST": "",
            "TWILIO_ACCOUNT_SID": ""}
    base.update(extra)
    for k, v in base.items():
        monkeypatch.setenv(k, v)


def test_development_has_no_blocking_problems():
    r = readiness()
    assert r.environment == "development" and r.ready
    assert {c.name: c.mode for c in r.components}["lab_partner"] == "simulated"


def test_production_lists_every_simulated_or_missing_dependency(monkeypatch):
    _prod_env(monkeypatch)
    r = readiness()
    text = " ".join(r.problems)
    assert not r.ready
    for needle in ("LLM provider key", "LAB_BACKEND", "alert channel", "COORDINATOR_TOKEN", "FRONTEND_ORIGINS"):
        assert needle in text


def test_production_with_everything_real_is_ready(monkeypatch):
    _prod_env(monkeypatch, GEMINI_API_KEY="k", LAB_API_URL="https://lab.example/api", LAB_API_KEY="s",
              TELEGRAM_BOT_TOKEN="t", TELEGRAM_CHAT_ID="1", COORDINATOR_TOKEN="c",
              FRONTEND_ORIGINS="https://app.example")
    r = readiness()
    assert r.ready and r.problems == []
    assert {c.name: c.mode for c in r.components}["emergency_alerts"] == "real"


def test_app_refuses_to_start_in_production_with_simulators(monkeypatch):
    _prod_env(monkeypatch)
    with pytest.raises(RuntimeError, match="Refusing to start in production"):
        with TestClient(api.app):
            pass


def test_invalid_env_values_are_rejected(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    with pytest.raises(ValueError):
        get_settings()


def test_readiness_endpoint_is_public_and_leaks_no_secrets(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "SECRET-BOT-TOKEN")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    with TestClient(api.app) as c:
        body = c.get("/api/readiness").text
    assert "SECRET-BOT-TOKEN" not in body and "telegram" in body


# ------------------------------------------------------------------ durable bookings + sessions
def test_confirmed_bookings_survive_a_restart():
    store = Store("sqlite:///:memory:")
    t1 = LabTools(failure_rate=0.0, store=store)
    pkg = t1.lab_packages[0]
    r = t1.book_test(pkg.package_id, "MEM_1", "09:00 AM", date(2030, 1, 5))
    assert r.status == "booking_confirmed"
    t2 = LabTools(failure_rate=0.0, store=store)  # "restart": a new process, same database
    assert t2.get_booking(r.booking_id, "MEM_1") is not None
    assert "09:00 AM" not in t2.check_slots(pkg.package_id, date(2030, 1, 5)).slots  # the slot is still taken
    assert t2.cancel_booking(r.booking_id, "MEM_1").status == "cancelled"
    assert LabTools(failure_rate=0.0, store=store).get_booking(r.booking_id, "MEM_1") is None


def test_session_survives_a_restart_and_keeps_token_security():
    with TestClient(api.app) as c:
        b = c.post("/api/sessions", json={"member_id": "MEM_1002"}).json()
        sid, hdr = b["session"]["session_id"], {"Authorization": f"Bearer {b['session_token']}"}
        c.post(f"/api/sessions/{sid}/messages", json={"text": "hello"}, headers=hdr)
        n = len(c.get(f"/api/sessions/{sid}", headers=hdr).json()["messages"])
        api._records.clear()
        api._engine._seeded.clear()  # simulate a process restart
        again = c.get(f"/api/sessions/{sid}", headers=hdr)
        assert again.status_code == 200 and len(again.json()["messages"]) == n
        assert c.get(f"/api/sessions/{sid}", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert c.post(f"/api/sessions/{sid}/messages", json={"text": "still here?"}, headers=hdr).status_code == 200
        assert c.delete(f"/api/sessions/{sid}", headers=hdr).status_code == 200
        api._records.clear()
        assert c.get(f"/api/sessions/{sid}", headers=hdr).status_code == 404


def test_session_tokens_are_stored_only_as_hashes():
    with TestClient(api.app) as c:
        b = c.post("/api/sessions", json={"member_id": "MEM_1002"}).json()
    row = api.get_store().load_session(b["session"]["session_id"])
    assert row is not None and b["session_token"] not in row.payload and b["session_token"] != row.token_hash


# ------------------------------------------------------------------ real lab partner adapter
class _Resp:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body or {}

    def json(self):
        return self._body


class _Http:
    """Scripted stand-in for requests.Session: returns queued responses/exceptions and records every request."""

    def __init__(self, *script):
        self.script, self.calls = list(script), []

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _backend(*script):
    h = _Http(*script)
    return HttpLabBackend("https://lab.example/api", "KEY", 2.0, session=h), h


def _reserve(backend):
    return backend.reserve(package_id="LP_001", member_id="M", day=date(2030, 1, 5), slot="09:00 AM",
                           idempotency_key="k1")


def test_http_backend_maps_partner_responses_to_typed_outcomes():
    b, h = _backend(_Resp(201, {"booking_ref": "P-1"}))
    assert _reserve(b).booking_ref == "P-1"
    _, url, kw = h.calls[0]
    assert url == "https://lab.example/api/bookings" and kw["headers"]["Idempotency-Key"] == "k1"
    assert kw["headers"]["Authorization"] == "Bearer KEY" and kw["timeout"] == 2.0
    with pytest.raises(SlotTaken):
        _reserve(_backend(_Resp(409))[0])
    for bad in (_Resp(503), _Resp(429), requests.Timeout("slow"), requests.ConnectionError("down")):
        with pytest.raises(PartnerUnavailable):
            _reserve(_backend(bad)[0])


def test_booking_retries_transient_partner_errors_with_the_same_idempotency_key(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    b, h = _backend(_Resp(503), requests.Timeout("slow"), _Resp(201, {"booking_ref": "P-9"}))
    t = LabTools(backend=b)
    r = t.book_test(t.lab_packages[0].package_id, "MEM_1", "09:00 AM", date(2030, 1, 6))
    assert r.status == "booking_confirmed" and t.get_booking(r.booking_id, "MEM_1").partner_ref == "P-9"
    keys = {c[2]["headers"]["Idempotency-Key"] for c in h.calls}
    assert len(h.calls) == 3 and len(keys) == 1  # a retry can never create a second booking


def test_partner_outage_ends_in_human_handoff_not_a_fake_confirmation(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    b, _ = _backend(_Resp(500), _Resp(500), _Resp(500))
    t = LabTools(backend=b)
    r = t.book_test(t.lab_packages[0].package_id, "MEM_1", "09:00 AM", date(2030, 1, 6))
    assert r.status == "booking_failed_needs_human_intervention" and r.ticket_id
    assert t._bookings == {}


def test_partner_slot_conflict_is_reported_as_taken():
    b, _ = _backend(_Resp(409))
    t = LabTools(backend=b)
    r = t.book_test(t.lab_packages[0].package_id, "MEM_1", "09:00 AM", date(2030, 1, 6))
    assert r.status == "booking_failed" and "taken" in r.message


def test_cancel_is_not_reported_when_the_partner_could_not_cancel():
    b, _ = _backend(_Resp(201, {"booking_ref": "P-1"}), requests.Timeout("slow"))
    t = LabTools(backend=b)
    r = t.book_test(t.lab_packages[0].package_id, "MEM_1", "09:00 AM", date(2030, 1, 7))
    res = t.cancel_booking(r.booking_id, "MEM_1")
    assert res.status == "partner_unavailable" and t.get_booking(r.booking_id, "MEM_1") is not None


def test_partner_slot_list_is_authoritative_when_reported():
    b, _ = _backend(_Resp(200, {"slots": ["10:00 AM", "11:00 AM"]}))
    t = LabTools(backend=b)
    assert t.check_slots(t.lab_packages[1].package_id, date(2030, 1, 8)).slots == ["10:00 AM", "11:00 AM"]


def test_simulator_is_refused_in_production_without_explicit_override(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    for k in ("ALLOW_SIMULATORS", "LAB_API_URL", "LAB_BACKEND"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError):
        LabTools()


# ------------------------------------------------------------------ emergency alerts
class _Ch:
    def __init__(self, name, fail_times=0):
        self.name, self.fail_times, self.sent = name, fail_times, []

    def send(self, text):
        if self.fail_times:
            self.fail_times -= 1
            raise RuntimeError("provider down")
        self.sent.append(text)


def test_alert_goes_to_every_channel_and_is_audited():
    store = Store("sqlite:///:memory:")
    a, b = _Ch("telegram"), _Ch("email")
    rep = deliver("MEM_1", "CARDIAC_EMERGENCY", "msg", [a, b], store, sleep=lambda s: None)
    assert rep.delivered and a.sent == ["msg"] and b.sent == ["msg"]
    assert {r.channel: r.status for r in store.alerts()} == {"telegram": "sent", "email": "sent"}


def test_alert_retries_once_and_one_failing_channel_does_not_block_the_other():
    store = Store("sqlite:///:memory:")
    flaky, down = _Ch("telegram", fail_times=1), _Ch("email", fail_times=9)
    rep = deliver("MEM_1", "SELF_HARM_EMERGENCY", "msg", [flaky, down], store, sleep=lambda s: None)
    assert rep.delivered and flaky.sent == ["msg"]
    assert {r.channel: r.status for r in store.alerts()} == {"telegram": "sent", "email": "failed"}


def test_undelivered_alert_is_loud_and_recorded(caplog):
    store = Store("sqlite:///:memory:")
    with caplog.at_level("CRITICAL"):
        rep = deliver("MEM_1", "CARDIAC_EMERGENCY", "msg", [_Ch("telegram", 9)], store, sleep=lambda s: None)
    assert not rep.delivered and "NOT DELIVERED" in caplog.text
    assert store.alerts()[0].status == "failed"


def test_no_channel_configured_is_recorded_not_silent(caplog):
    store = Store("sqlite:///:memory:")
    with caplog.at_level("CRITICAL"):
        rep = deliver("MEM_1", "CARDIAC_EMERGENCY", "msg", [], store)
    assert not rep.delivered and store.alerts()[0].status == "no_channel" and "no delivery channel" in caplog.text


def test_alert_text_has_member_id_and_category_but_never_the_members_words():
    ch, store = _Ch("telegram"), Store("sqlite:///:memory:")
    dispatch_emergency("MEM_1", "CARDIAC_EMERGENCY", "message <redacted len=20 tag=ab12>", wait=True,
                       channels=[ch], store=store)
    assert "MEM_1" in ch.sent[0] and "CARDIAC_EMERGENCY" in ch.sent[0] and "chest pain" not in ch.sent[0]


def test_telegram_token_never_appears_in_audit_details(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:SECRET")
    store = Store("sqlite:///:memory:")

    class Leaky(_Ch):
        def send(self, text):
            raise RuntimeError("HTTPSConnectionPool: /bot123:SECRET/sendMessage failed")
    deliver("MEM_1", "X", "msg", [Leaky("telegram")], store, sleep=lambda s: None)
    assert "123:SECRET" not in store.alerts()[0].detail


def test_configured_channels_come_from_environment(monkeypatch):
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SMTP_HOST", "TWILIO_ACCOUNT_SID", "ALERT_EMAIL_TO",
              "ALERT_EMAIL_FROM"):
        monkeypatch.delenv(k, raising=False)
    assert alerts.configured_channel_names() == []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    monkeypatch.setenv("SMTP_HOST", "smtp.example")
    monkeypatch.setenv("ALERT_EMAIL_TO", "a@b.c")
    monkeypatch.setenv("ALERT_EMAIL_FROM", "x@y.z")
    assert alerts.configured_channel_names() == ["telegram", "email"]


def test_the_gate_never_raises_even_if_the_alert_pipeline_explodes(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("pool exploded")
    monkeypatch.setattr("app.safety.triage_gate.dispatch_emergency", boom)
    out = dispatch_emergency_sms("MEM_1", "CARDIAC_EMERGENCY; message <redacted len=5 tag=x>")
    assert out["status"] == "alert_queued"
