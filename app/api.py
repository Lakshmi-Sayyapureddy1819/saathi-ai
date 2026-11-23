"""HTTP API for the Saathi web UI. It drives the ADK 2.x workflow (`AdkSaathi`), the same business logic as the
CLI, and adds the one thing the UI needs that the workflow does not: a typed, per-session view of booking state.

Run (local only):
    python -m uvicorn app.api:app --host 127.0.0.1 --port 8000

SECURITY MODEL (read before exposing this anywhere)
- Each session gets a random bearer token at creation; every session call needs it (constant-time compare). A
  session id alone grants nothing.
- Coordinator actions (approve/reject a handed-off booking) use a SEPARATE shared secret, COORDINATOR_TOKEN. A member's
  session token can never approve its own booking. If COORDINATOR_TOKEN is unset the endpoints are disabled.
  This is one shared secret, not per-coordinator identity: there is no audit trail of *who* approved.
- Only members in the members table (seeded from data/members.json) can be used; CORS is limited to FRONTEND_ORIGINS.
- Sessions (token hashes, transcripts with raw message text) are cached in memory and written through to the database
  (DATABASE_URL, SQLite by default), so a restart keeps them; they expire after SESSION_TTL_MINUTES idle and are capped.
  Not provided here: TLS termination and member login (use a TLS proxy and an identity provider). APP_ENV=production
  refuses to start while any simulator remains (see app/config.py and GET /api/readiness).
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hmac
import json
import os
import re
import hashlib
import logging
import secrets
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Deque, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api_schemas import (
    MAX_MESSAGE_CHARS, ApprovalItem, ApprovalList, BookingConfirmation, BookingItem, BookingView, ChatMessage, ConfigView,
    CoordinatorDecisionRequest, CreateSessionRequest, DateOption, DeleteResponse, EmergencyView, GroundingView, HandoffView,
    MemberPublic, MessageKind, PackageOption, ProgramSummary, SendMessageRequest, SessionCreated, SessionView,
    SetGroundingRequest, ConversationMetricsView, TurnMetricsView,
)
from app.config import Readiness, get_settings, readiness
from app.observability.tracer import flush, new_trace_id, span
from app.persistence.store import StoredSession, get_store
from app.tools.lab_tools import LabTools
from app.grounding.semantic_cache import CacheStats, wellness_cache
from app.workflow.model_client import LLMStatus, check_credentials, llm_status
from app.tools.lab_tools import LabPackage
from app.tools.slots import resolve_date
from app.workflow.adk_graph import _GRAPH, AdkSaathi, ApprovalDecision
from app.workflow.graph import active_bookings
from app.workflow.state import (BookingDraft, GroundingMode, MemberProfile, PendingCheckup, UserSessionState,
                                default_grounding_mode)

SESSION_TTL_S = int(os.getenv("SESSION_TTL_MINUTES", "120")) * 60
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "200"))
MSGS_PER_MINUTE = int(os.getenv("MESSAGES_PER_MINUTE", "30"))
CREATES_PER_MINUTE = int(os.getenv("SESSIONS_PER_MINUTE", "20"))
MAX_TRANSCRIPT = 400
_FRONTEND_ORIGINS = [o.strip() for o in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
                     .split(",") if o.strip()]
_BOOKING_RECORD = re.compile(r"^(?P<id>\S+) - (?P<pkg>.+) on (?P<date>\d{4}-\d{2}-\d{2}) (?P<slot>.+)$")


def _load_json(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


_MEMBERS: Dict[str, dict] = get_store().members()  # seeded from data/members.json on first start, then the database
_PROGRAMS: List[ProgramSummary] = [ProgramSummary(doc_id=p["doc_id"], title=p["title"], category=p["category"])
                                   for p in _load_json("data/programs.json")]


# ---------------------------------------------------------------- in-memory session store
@dataclass
class SessionRecord:
    session: UserSessionState
    token_hash: str
    messages: List[ChatMessage] = field(default_factory=list)
    pending_interrupt_id: Optional[str] = None
    handoff: HandoffView = field(default_factory=HandoffView)
    requested_at: Optional[datetime] = None
    last_seen: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    sent: Deque[float] = field(default_factory=deque)

    def add(self, role, text: str, kind: MessageKind = "answer", **extra) -> ChatMessage:
        msg = ChatMessage(id=(self.messages[-1].id + 1) if self.messages else 1, role=role, kind=kind, text=text,
                          at=datetime.now(), **extra)
        self.messages.append(msg)
        del self.messages[:-MAX_TRANSCRIPT]
        return msg


_engine = AdkSaathi()
_GRAPH.lab_tools = LabTools(store=get_store())      # confirmed bookings survive a restart
_GRAPH.engine.lab_tools = _GRAPH.lab_tools
_records: Dict[str, SessionRecord] = {}
_create_log: Deque[float] = deque()

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Refuse to start a production deployment that still depends on a simulator or lacks a real alert channel; otherwise
    fail loudly (in the log) if a configured provider key is rejected. Development never blocks on this."""
    r = readiness()
    if r.problems:
        for p in r.problems:
            logging.error("readiness: %s", p)
        if r.environment == "production":
            raise RuntimeError("Refusing to start in production: " + " ".join(r.problems))
    await asyncio.to_thread(check_credentials)
    yield
    # Graceful shutdown (SIGTERM from `docker stop`): sessions are persisted after every turn, so only buffered trace spans
    # remain. Flush them so a deploy or restart does not drop the last turns' telemetry.
    try:
        await asyncio.to_thread(flush)
    except Exception:  # shutdown must never hang or raise
        logging.exception("trace flush at shutdown failed")


app = FastAPI(title="Saathi Care AI API", version="1.0", lifespan=_lifespan)
app.add_middleware(CORSMiddleware, allow_origins=_FRONTEND_ORIGINS, allow_methods=["GET", "POST", "DELETE"],
                   allow_headers=["Authorization", "Content-Type", "X-Coordinator-Token"])


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _payload(rec: "SessionRecord") -> str:
    return json.dumps({
        "session": rec.session.model_dump(mode="json"),
        "messages": [m.model_dump(mode="json") for m in rec.messages],
        "handoff": rec.handoff.model_dump(mode="json"),
        "pending_interrupt_id": rec.pending_interrupt_id,
        "requested_at": rec.requested_at.isoformat() if rec.requested_at else None})


def _persist(rec: "SessionRecord") -> None:
    """Write the session through to the database. A storage fault is logged, never shown to the member."""
    try:
        get_store().save_session(StoredSession(session_id=rec.session.session_id, token_hash=rec.token_hash,
                                               member_id=rec.session.member.member_id, payload=_payload(rec),
                                               updated_at=time.time()))
    except Exception:  # noqa: BLE001
        logging.exception("could not persist session %s", rec.session.session_id)


def _restore(session_id: str) -> Optional["SessionRecord"]:
    """Rebuild a session after a restart (or cache eviction) from the database."""
    try:
        row = get_store().load_session(session_id)
    except Exception:  # noqa: BLE001
        logging.exception("could not load session %s", session_id)
        return None
    if row is None or time.time() - row.updated_at > SESSION_TTL_S:
        return None
    data = json.loads(row.payload)
    rec = SessionRecord(session=UserSessionState.model_validate(data["session"]), token_hash=row.token_hash,
                        messages=[ChatMessage.model_validate(m) for m in data["messages"]],
                        handoff=HandoffView.model_validate(data["handoff"]))
    if data.get("pending_interrupt_id"):
        # The paused coordinator approval lived in process memory and cannot be resumed after a restart. Say so honestly.
        rec.add("system", "The server restarted while your booking request was waiting for the care team. The ticket "
                          f"{rec.session.handoff_ticket or ''} is still open with them; you can keep chatting here.".replace("  ", " "),
                kind="answer")
        rec.handoff = HandoffView(status="none", ticket_id=rec.session.handoff_ticket)
    return rec


def _purge_expired() -> None:
    try:
        get_store().purge_sessions(SESSION_TTL_S)
    except Exception:  # noqa: BLE001
        logging.exception("could not purge stored sessions")
    now = time.monotonic()
    for sid in [k for k, r in _records.items() if now - r.last_seen > SESSION_TTL_S]:
        _drop(sid)


def _drop(session_id: str) -> bool:
    try:
        get_store().delete_session(session_id)
    except Exception:  # noqa: BLE001
        logging.exception("could not delete stored session %s", session_id)
    rec = _records.pop(session_id, None)
    if rec is None:
        return False
    try:  # best effort: free the ADK-side copy too
        asyncio.get_running_loop().create_task(_engine.service.delete_session(
            app_name="SaathiWorkflow", user_id=rec.session.member.member_id, session_id=session_id))
    except Exception:  # noqa: BLE001 - cleanup must never fail a request
        pass
    _engine._seeded.discard(session_id)
    return True


def _rate_ok(log: Deque[float], limit: int) -> bool:
    now = time.monotonic()
    while log and now - log[0] > 60:
        log.popleft()
    if len(log) >= limit:
        return False
    log.append(now)
    return True


def _bearer(authorization: Optional[str]) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def _get_record(session_id: str, authorization: Optional[str]) -> SessionRecord:
    """401 for a missing/wrong token, 404 only when the id is unknown. Same 401 for both bad cases would hide
    expiry from the UI, so unknown ids get 404 (the UI then offers a fresh session)."""
    rec = _records.get(session_id)
    if rec is None:
        rec = _restore(session_id)
        if rec is None:
            raise HTTPException(404, "Session not found or expired. Start a new session.")
        _records[session_id] = rec
    if not hmac.compare_digest(rec.token_hash, _hash(_bearer(authorization))):
        raise HTTPException(401, "Invalid session token.")
    rec.last_seen = time.monotonic()
    return rec


def require_coordinator(x_coordinator_token: Optional[str] = Header(default=None)) -> None:
    expected = os.getenv("COORDINATOR_TOKEN", "")
    if not expected:
        raise HTTPException(503, "Coordinator console is disabled: set COORDINATOR_TOKEN on the server.")
    if not hmac.compare_digest(expected, x_coordinator_token or ""):
        raise HTTPException(401, "Invalid coordinator token.")


# ---------------------------------------------------------------- view building (read-only on session state)
def _pkg_option(p: LabPackage) -> PackageOption:
    return PackageOption(package_id=p.package_id, name=p.name, price_inr=p.price_inr, test_count=p.test_count,
                         fasting_required=p.fasting_required, fasting_hours=p.fasting_hours)


def _date_label(d: date) -> str:
    return f"{d:%a} {d.day} {d:%b}"


def _dates() -> List[DateOption]:
    today = date.today()
    out = []
    for word, delta, prefix in (("today", 0, "Today"), ("tomorrow", 1, "Tomorrow"),
                                ("day after tomorrow", 2, "Day after")):
        d = today + timedelta(days=delta)
        out.append(DateOption(word=word, label=f"{prefix}, {_date_label(d)}", iso=d.isoformat()))
    return out


def _booking_view(session: UserSessionState) -> BookingView:
    d: BookingDraft = session.booking_draft
    tools = _GRAPH.lab_tools
    if d.package_id:
        pkg = tools.get_package(d.package_id)
        day = d.selected_date or resolve_date("")
        base = dict(package=_pkg_option(pkg) if pkg else None, date_iso=day.isoformat(), date_label=_date_label(day),
                    slot=d.selected_slot)
        if d.selected_slot:
            return BookingView(stage="confirming", **base)
        return BookingView(stage="choosing_slot", slots=tools.check_slots(d.package_id, day).slots,
                           dates=_dates(), **base)
    if d.candidate_package_ids:
        pkgs = [p for pid in d.candidate_package_ids if (p := tools.get_package(pid))]
        return BookingView(stage="choosing_package", options=[_pkg_option(p) for p in pkgs])
    return BookingView()


def _triage(session: UserSessionState):
    return session.triage_status.status


def _status(rec: SessionRecord):
    return "awaiting_coordinator" if rec.pending_interrupt_id else "active"


def _grounding_fields(session) -> dict:
    """Citations + grounding panel for a coach answer. Empty for every other node (booking, safety, greetings)."""
    g = session.last_grounding
    if session.active_node != "node_program_coach" or not session.last_citations:
        return {}
    # A cache hit has citations (verified against the library) but no grounding panel: nothing was retrieved this turn.
    panel = None if g is None else GroundingView(
        mode=g.mode, retriever=g.retriever, search_queries=g.search_queries, tools_called=g.tools_called,
        agent_steps=g.agent_steps, decided_by=g.agent_decision)
    return {"citations": list(session.last_citations), "grounding": panel}


def _view(rec: SessionRecord) -> SessionView:
    m = rec.session.member
    src = _MEMBERS.get(m.member_id, {})
    s = rec.session
    turns_view = [
        TurnMetricsView(
            trace_id=t.trace_id,
            prompt_tokens=t.prompt_tokens,
            completion_tokens=t.completion_tokens,
            total_tokens=t.total_tokens,
            cost_usd=t.cost_usd,
            latency_ms=t.latency_ms,
        )
        for t in s.turn_history
    ]
    conv_metrics = ConversationMetricsView(
        session_id=s.session_id,
        total_prompt_tokens=s.total_prompt_tokens,
        total_completion_tokens=s.total_completion_tokens,
        total_tokens=s.total_tokens,
        total_cost_usd=round(s.total_cost_usd, 6),
        total_latency_ms=round(s.total_latency_ms, 2),
        turn_count=len(s.turn_history),
        turns=turns_view,
    )
    return SessionView(
        session_id=rec.session.session_id,
        member=MemberPublic(member_id=m.member_id, name=m.name, age=m.age,
                            language_preference=src.get("language_preference", "english")),
        status=_status(rec), triage_status=_triage(rec.session), messages=list(rec.messages),
        booking=_booking_view(rec.session), handoff=rec.handoff,
        bookings=[BookingItem(booking_id=b.booking_id, package_name=b.package_name, date=b.date.isoformat(), slot=b.slot)
                  for b in active_bookings(rec.session, _GRAPH.lab_tools)],
        grounding_mode=rec.session.grounding_mode.mode,
        metrics=conv_metrics)


# ---------------------------------------------------------------- public / catalogue endpoints
@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/cache-status", response_model=CacheStats)
def cache_status() -> CacheStats:
    """Semantic-cache TTL, store (memory/redis), entries, hits, expirations and Redis errors. Never includes the Redis
    URL (it can contain a password) or any cached text."""
    return wellness_cache.stats()


@app.get("/api/llm-status", response_model=LLMStatus)
def llm_health() -> LLMStatus:
    """Per-model ok/failed counts, last error, fallback usage and provider key status. Contains no secrets and no
    message text."""
    return llm_status()


@app.get("/api/readiness", response_model=Readiness)
def get_readiness() -> Readiness:
    """What is real and what is simulated in this deployment, and what blocks a production start. No secrets."""
    return readiness()


@app.get("/api/config", response_model=ConfigView)
def config() -> ConfigView:
    return ConfigView(llm_configured=bool(os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")),
                      coordinator_console_enabled=bool(os.getenv("COORDINATOR_TOKEN")),
                      max_message_chars=MAX_MESSAGE_CHARS, grounding_mode=default_grounding_mode(),
                      retriever=_GRAPH.engine.retriever.name)


@app.get("/api/members", response_model=List[MemberPublic])
def members() -> List[MemberPublic]:
    return [MemberPublic(member_id=m["member_id"], name=m["name"], age=m["age"],
                         language_preference=m.get("language_preference", "english")) for m in _MEMBERS.values()]


@app.get("/api/packages", response_model=List[PackageOption])
def packages(q: str = "") -> List[PackageOption]:
    tools = _GRAPH.lab_tools
    q = q.strip()[:100]
    if not q:
        return [_pkg_option(p) for p in tools.lab_packages]
    needle = q.lower()
    hits = {p.package_id: p for p in tools.search_packages(q)}
    for p in tools.lab_packages:  # also plain substring matches on name/id (search_packages ignores generic words)
        if needle in p.name.lower() or needle in p.package_id.lower():
            hits.setdefault(p.package_id, p)
    return [_pkg_option(p) for p in hits.values()]


@app.get("/api/programs", response_model=List[ProgramSummary])
def programs() -> List[ProgramSummary]:
    return _PROGRAMS


# ---------------------------------------------------------------- session endpoints
@app.post("/api/sessions", response_model=SessionCreated, status_code=201)
async def create_session(req: CreateSessionRequest) -> SessionCreated:
    src = _MEMBERS.get(req.member_id)
    if src is None:
        raise HTTPException(404, "Unknown member.")
    if not _rate_ok(_create_log, CREATES_PER_MINUTE):
        raise HTTPException(429, "Too many sessions created. Wait a minute.")
    _purge_expired()
    if len(_records) >= MAX_SESSIONS:
        raise HTTPException(503, "Server is at its session limit. Try again later.")
    member = MemberProfile(
        member_id=src["member_id"], name=src["name"], age=src["age"], language_pref=src.get("language_preference", "en-US"),
        enrolled_programs=list(src.get("enrolled_programs", [])), past_bookings=list(src.get("past_bookings", [])),
        health_goals=list(src.get("health_goals", [])),
        pending_checkups=[PendingCheckup(**c) for c in src.get("pending_checkups", [])])
    session = UserSessionState(channel="web", member=member, active_node="start", booking_draft=BookingDraft())
    if req.grounding_mode:
        session.grounding_mode = GroundingMode(mode=req.grounding_mode)
    token = secrets.token_urlsafe(32)
    rec = SessionRecord(session=session, token_hash=_hash(token))
    _records[session.session_id] = rec
    _persist(rec)
    return SessionCreated(session_token=token, session=_view(rec))


_MODE_NOTE = {
    "mode_a_rag": "Answer mode: Library search (Mode A, agentic RAG). Mimi now decides what to look up in the wellness library and cites the documents she used.",
    "mode_b_facts": "Answer mode: My records only (Mode B, no retrieval). Mimi now answers only from your profile, bookings, schedule and the lab catalogue, and says \"I don't have that information\" otherwise.",
}


@app.post("/api/sessions/{session_id}/grounding", response_model=SessionView)
async def set_grounding(session_id: str, req: SetGroundingRequest,
                        authorization: Optional[str] = Header(default=None)) -> SessionView:
    """Switch the Program Coach between Mode A (agentic RAG) and Mode B (fact-grounded, no retrieval) for this session."""
    rec = _get_record(session_id, authorization)
    async with rec.lock:
        if rec.session.grounding_mode.mode != req.mode:
            rec.session.grounding_mode = GroundingMode(mode=req.mode)
            rec.add("system", _MODE_NOTE[req.mode], kind="answer")
            _persist(rec)
    return _view(rec)


@app.get("/api/sessions/{session_id}", response_model=SessionView)
def get_session(session_id: str, authorization: Optional[str] = Header(default=None)) -> SessionView:
    return _view(_get_record(session_id, authorization))


@app.get("/api/sessions/{session_id}/metrics", response_model=ConversationMetricsView)
def get_session_metrics(session_id: str, authorization: Optional[str] = Header(default=None)) -> ConversationMetricsView:
    """Return tokens, cost and latency per conversation for the specified session."""
    rec = _get_record(session_id, authorization)
    s = rec.session
    turns_view = [
        TurnMetricsView(
            trace_id=t.trace_id,
            prompt_tokens=t.prompt_tokens,
            completion_tokens=t.completion_tokens,
            total_tokens=t.total_tokens,
            cost_usd=t.cost_usd,
            latency_ms=t.latency_ms,
        )
        for t in s.turn_history
    ]
    return ConversationMetricsView(
        session_id=s.session_id,
        total_prompt_tokens=s.total_prompt_tokens,
        total_completion_tokens=s.total_completion_tokens,
        total_tokens=s.total_tokens,
        total_cost_usd=round(s.total_cost_usd, 6),
        total_latency_ms=round(s.total_latency_ms, 2),
        turn_count=len(s.turn_history),
        turns=turns_view,
    )


@app.delete("/api/sessions/{session_id}", response_model=DeleteResponse)
async def delete_session(session_id: str, authorization: Optional[str] = Header(default=None)) -> DeleteResponse:
    _get_record(session_id, authorization)
    return DeleteResponse(session_id=session_id, deleted=_drop(session_id))


def _kind_for(triage: str, node: str, confirmed: bool, pending: bool) -> MessageKind:
    if triage == "RED_CRISIS":
        return "emergency"
    if triage == "YELLOW_WARNING":
        return "safety_notice"
    if confirmed:
        return "booking_confirmed"
    if pending:
        return "handoff"
    return "answer"


@app.post("/api/sessions/{session_id}/messages", response_model=SessionView)
async def send_message(session_id: str, req: SendMessageRequest,
                       authorization: Optional[str] = Header(default=None)) -> SessionView:
    rec = _get_record(session_id, authorization)
    if rec.pending_interrupt_id:
        raise HTTPException(409, "This session is waiting for a care coordinator to decide on your booking.")
    if not _rate_ok(rec.sent, MSGS_PER_MINUTE):
        raise HTTPException(429, "You are sending messages too quickly.")
    async with rec.lock:  # one turn at a time per session
        if req.channel:
            rec.session.channel = req.channel
        rec.handoff = HandoffView()  # a previous decision banner is history once the member moves on
        before = len(rec.session.member.past_bookings)
        rec.add("user", req.text)
        try:
            res = await _engine.turn(req.text, rec.session)
        except Exception as e:  # noqa: BLE001 - report, don't leak internals or details of the member's text
            rec.add("system", "Something went wrong on our side. Please try again.", kind="answer")
            raise HTTPException(500, f"Turn failed ({type(e).__name__}).") from e
        rec.session = res.session
        triage = _triage(res.session)
        new_bookings = res.session.member.past_bookings[before:]
        confirmation: Optional[BookingConfirmation] = None
        if new_bookings and (m := _BOOKING_RECORD.match(new_bookings[-1])):
            confirmation = BookingConfirmation(booking_id=m["id"], package_name=m["pkg"], date=m["date"], slot=m["slot"])
        emergency = None
        if triage == "RED_CRISIS" and res.session.emergency_payload:
            p = res.session.emergency_payload
            emergency = EmergencyView(message=p.message, helplines=dict(p.helplines))
        if res.pending_interrupt_id:
            rec.pending_interrupt_id = res.pending_interrupt_id
            rec.requested_at = datetime.now()
            rec.handoff = HandoffView(status="pending", ticket_id=res.session.handoff_ticket)
        rec.add("assistant", res.response or "(no response)",
                kind=_kind_for(triage, res.session.active_node, confirmation is not None,
                               bool(res.pending_interrupt_id)),
                trace_id=res.session.trace_id, emergency=emergency, confirmation=confirmation,
                **_grounding_fields(res.session))
        _persist(rec)
    return _view(rec)


# ---------------------------------------------------------------- coordinator endpoints (separate secret)
@app.get("/api/coordinator/approvals", response_model=ApprovalList, dependencies=[Depends(require_coordinator)])
def list_approvals() -> ApprovalList:
    items = []
    for rec in _records.values():
        if not rec.pending_interrupt_id:
            continue
        d, s = rec.session.booking_draft, rec.session
        pkg = _GRAPH.lab_tools.get_package(d.package_id) if d.package_id else None
        items.append(ApprovalItem(
            session_id=s.session_id, member_id=s.member.member_id, member_name=s.member.name,
            ticket_id=s.handoff_ticket, package_name=pkg.name if pkg else None,
            date=d.selected_date.isoformat() if d.selected_date else None, slot=d.selected_slot,
            requested_at=rec.requested_at or datetime.now()))
    return ApprovalList(items=items)


@app.post("/api/coordinator/approvals/{session_id}", response_model=ApprovalItem,
          dependencies=[Depends(require_coordinator)])
async def decide_approval(session_id: str, req: CoordinatorDecisionRequest) -> ApprovalItem:
    rec = _records.get(session_id)
    if rec is None or not rec.pending_interrupt_id:
        raise HTTPException(404, "No pending approval for that session.")
    async with rec.lock:
        if not rec.pending_interrupt_id:
            raise HTTPException(409, "That approval was already decided.")
        d, s = rec.session.booking_draft, rec.session
        pkg = _GRAPH.lab_tools.get_package(d.package_id) if d.package_id else None
        item = ApprovalItem(session_id=session_id, member_id=s.member.member_id, member_name=s.member.name,
                            ticket_id=s.handoff_ticket, package_name=pkg.name if pkg else None,
                            date=d.selected_date.isoformat() if d.selected_date else None, slot=d.selected_slot,
                            requested_at=rec.requested_at or datetime.now())
        ticket = s.handoff_ticket
        trace_id = new_trace_id()
        with span("coordinator_decision", trace_id, kind="root", engine="adk", session_id=session_id,
                  approved=req.approved):
            res = await _engine.resume(rec.session, rec.pending_interrupt_id, ApprovalDecision(
                approved=req.approved, note=req.note))
        flush()
        rec.session = res.session
        rec.pending_interrupt_id = None
        rec.handoff = HandoffView(status="approved" if req.approved else "rejected", ticket_id=ticket, note=req.note)
        rec.add("system", res.response, kind="handoff_resolved", trace_id=trace_id)
        _persist(rec)
    return item
