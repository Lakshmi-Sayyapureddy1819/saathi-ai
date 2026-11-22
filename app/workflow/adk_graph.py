"""ADK 2.x Workflow wrapper around the single set of business-logic nodes in graph.py.

No logic is duplicated here: every ADK node calls `WorkflowGraph(chain=False).run_node(...)` for exactly one
step, persists the typed `UserSessionState` into ADK session state (JSON), and routes on `session.next_node`.
The only ADK-specific piece is human-in-the-loop: when booking fails after retries, the workflow pauses with a
`RequestInput` for a care coordinator, and resumes with an approve / reject decision.

    START -> safety_gate -> emergency | intent_router -> program_coach | lab_booking -> handoff_request
                                                                                      -> (pause) -> handoff_resolution
"""
import asyncio
from typing import Optional

from google.adk.agents.context import Context
from google.adk.events import Event, RequestInput
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import Workflow, node, START
from google.adk.workflow.utils._workflow_hitl_utils import (
    create_request_input_response, get_request_input_interrupt_ids, has_request_input_function_call,
)
from google.genai import types as genai_types
from pydantic import BaseModel, ConfigDict

from app.observability.tracer import new_trace_id, span, flush
from app.workflow.graph import WorkflowGraph
from app.workflow.state import UserSessionState

APP_NAME = "SaathiWorkflow"
_GRAPH = WorkflowGraph(chain=False)


class ApprovalDecision(BaseModel):
    """Care coordinator's answer to a handoff request."""
    approved: bool
    note: str = ""


class AdkTurnResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    response: str
    session: UserSessionState
    pending_interrupt_id: Optional[str] = None  # set when the workflow is paused awaiting approval


# ---------- state helpers (typed state <-> ADK session state) ----------
def _load(ctx: Context) -> UserSessionState:
    return UserSessionState.model_validate(ctx.state["session"])


def _save(ctx: Context, session: UserSessionState) -> None:
    ctx.state["session"] = session.model_dump(mode="json")


async def _step(ctx: Context, node_name: str):
    """Run one business-logic node off-thread (it does blocking I/O) and persist the result."""
    session = _load(ctx)
    response, session = await asyncio.to_thread(_GRAPH.run_node, node_name, ctx.state["user_text"], session)
    _save(ctx, session)
    if response is not None:
        ctx.state["response"] = response
    return session, ctx.state.get("response", "")


# ---------- nodes ----------
@node
async def safety_gate(ctx: Context):
    session, response = await _step(ctx, "node_safety_gate")
    if session.next_node:
        yield Event(route=session.next_node)
    else:
        yield Event(output=response)


@node
async def emergency(ctx: Context):
    _, response = await _step(ctx, "node_emergency")
    yield Event(output=response)


@node
async def intent_router(ctx: Context):
    session, _ = await _step(ctx, "node_intent_router")
    yield Event(route=session.next_node or "node_program_coach")  # fallback routing preserved


@node
async def program_coach(ctx: Context):
    _, response = await _step(ctx, "node_program_coach")
    yield Event(output=response)


@node
async def lab_booking(ctx: Context):
    session, response = await _step(ctx, "node_lab_booking")
    if session.next_node == "node_human_handoff":
        yield Event(route="node_human_handoff", output=response)
    else:
        yield Event(output=response)


@node
async def handoff_request(ctx: Context):
    """Pause for a coordinator decision. The decision becomes this node's output on resume."""
    session = _load(ctx)
    session.active_node = "node_human_handoff"
    _save(ctx, session)
    yield RequestInput(
        message=(f"Booking for {session.member.member_id} failed after retries "
                 f"(ticket {session.handoff_ticket}). Approve callback?"),
        payload={"ticket_id": session.handoff_ticket, "member_id": session.member.member_id,
                 "package_id": session.booking_draft.package_id, "slot": session.booking_draft.selected_slot},
        response_schema=ApprovalDecision,
    )


@node
async def handoff_resolution(ctx: Context, node_input: ApprovalDecision):
    session = _load(ctx)
    response, session = _GRAPH.resolve_handoff(session, node_input.approved, node_input.note)
    _save(ctx, session)
    ctx.state["response"] = response
    yield Event(output=response)


saathi_workflow = Workflow(
    name=APP_NAME,
    edges=[
        (START, safety_gate),
        (safety_gate, {"node_emergency": emergency, "node_intent_router": intent_router}),
        (intent_router, {"node_program_coach": program_coach, "node_lab_booking": lab_booking}),
        (lab_booking, {"node_human_handoff": handoff_request}),
        (handoff_request, handoff_resolution),
    ],
)


# ---------- driver ----------
class AdkSaathi:
    """Runs the workflow turn by turn; the typed session lives in ADK session state between turns."""

    def __init__(self):
        self.service = InMemorySessionService()
        self.runner = Runner(app_name=APP_NAME, session_service=self.service, node=saathi_workflow,
                             auto_create_session=True)
        self._seeded: set[str] = set()

    async def _drive(self, session: UserSessionState, new_message: genai_types.Content,
                     state_delta: Optional[dict] = None) -> AdkTurnResult:
        interrupt_id: Optional[str] = None
        async for ev in self.runner.run_async(user_id=session.member.member_id, session_id=session.session_id,
                                              new_message=new_message, state_delta=state_delta):
            if has_request_input_function_call(ev):
                interrupt_id = get_request_input_interrupt_ids(ev)[0]
        stored = await self.service.get_session(app_name=APP_NAME, user_id=session.member.member_id,
                                                session_id=session.session_id)
        final = UserSessionState.model_validate(stored.state["session"])
        return AdkTurnResult(response=str(stored.state.get("response", "")), session=final,
                             pending_interrupt_id=interrupt_id)

    async def turn(self, user_text: str, session: UserSessionState) -> AdkTurnResult:
        session.trace_id = new_trace_id()
        delta: dict = {"user_text": user_text, "response": ""}
        if session.session_id not in self._seeded:  # first turn seeds the typed session
            self._seeded.add(session.session_id)
            delta["session"] = session.model_dump(mode="json")
        else:  # later turns: keep stored session but refresh the trace id
            stored = await self.service.get_session(app_name=APP_NAME, user_id=session.member.member_id,
                                                    session_id=session.session_id)
            cur = dict(stored.state["session"])
            cur["trace_id"] = session.trace_id
            delta["session"] = cur
        with span("turn", session.trace_id, kind="root", engine="adk", session_id=session.session_id,
                  member_id=session.member.member_id, channel=session.channel, input=user_text) as s:
            msg = genai_types.Content(role="user", parts=[genai_types.Part(text=user_text)])
            res = await self._drive(session, msg, delta)
            s.set_output(res.response)
        flush()
        return res

    async def resume(self, session: UserSessionState, interrupt_id: str, decision: ApprovalDecision) -> AdkTurnResult:
        part = create_request_input_response(interrupt_id, decision.model_dump())
        msg = genai_types.Content(role="user", parts=[part])
        return await self._drive(session, msg)
