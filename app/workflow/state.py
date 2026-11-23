"""Typed session state. All models are Pydantic V2 (CLAUDE.md §2).

Models are frozen where the data is a value object; the session itself stays mutable
because the workflow updates it every turn (use `model_copy(update=...)` for value objects).
"""
import os
import uuid
from datetime import datetime, date
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

NodeName = Literal[
    "start", "node_safety_gate", "node_emergency", "node_intent_router",
    "node_program_coach", "node_lab_booking", "node_human_handoff",
]
TriageLevel = Literal["GREEN_NORMAL", "YELLOW_WARNING", "RED_CRISIS"]


class PendingCheckup(BaseModel):
    """A lab checkup the member is due for but has not booked yet (drives the outbound reminder call)."""
    model_config = ConfigDict(frozen=True)
    package_id: str
    due_date: date
    reason: str = ""


class MemberProfile(BaseModel):
    """Static profile of a member."""
    member_id: str
    name: str
    age: int
    language_pref: str = "en-US"
    enrolled_programs: List[str] = Field(default_factory=list)
    past_bookings: List[str] = Field(default_factory=list)
    health_goals: List[str] = Field(default_factory=list)
    pending_checkups: List[PendingCheckup] = Field(default_factory=list)


class BookingDraft(BaseModel):
    """A booking in the process of being confirmed."""
    package_id: Optional[str] = None
    package_name: Optional[str] = None
    selected_date: Optional[date] = None
    selected_slot: Optional[str] = None
    verbal_confirmed: bool = False
    attempt_count: int = 0
    # Package disambiguation: ids we listed to the user, and a time they gave before choosing a package.
    candidate_package_ids: List[str] = Field(default_factory=list)
    pending_slot_text: Optional[str] = None


class TriageStatus(BaseModel):
    """Clinical safety triage status of the session."""
    model_config = ConfigDict(frozen=True)
    status: TriageLevel = "GREEN_NORMAL"


GroundingModeName = Literal["mode_a_rag", "mode_b_facts"]
_MODE_ALIASES: dict[str, GroundingModeName] = {
    "mode_a_rag": "mode_a_rag", "a": "mode_a_rag", "rag": "mode_a_rag", "agentic_rag": "mode_a_rag",
    "mode_b_facts": "mode_b_facts", "b": "mode_b_facts", "facts": "mode_b_facts", "no_rag": "mode_b_facts",
}


def default_grounding_mode() -> GroundingModeName:
    """Config switch for the Program Coach: env GROUNDING_MODE = mode_a_rag (agentic RAG, the default) or
    mode_b_facts (no retrieval; backend tools + fact-grounded prompt). An unknown value fails loudly at startup rather
    than silently running the wrong mode."""
    raw = os.getenv("GROUNDING_MODE", "").strip().lower()
    if not raw:
        return "mode_a_rag"
    if raw not in _MODE_ALIASES:
        raise ValueError(f"GROUNDING_MODE={raw!r} is invalid; use mode_a_rag or mode_b_facts.")
    return _MODE_ALIASES[raw]


class GroundingMode(BaseModel):
    """Grounding context mode (default comes from the GROUNDING_MODE config)."""
    model_config = ConfigDict(frozen=True)
    mode: GroundingModeName = Field(default_factory=default_grounding_mode)


class Citation(BaseModel):
    """A source shown to the member next to an answer. `cited` = the answer itself cited it; False = retrieved or
    fetched for the answer but not cited inline (shown as 'consulted')."""
    model_config = ConfigDict(frozen=True)
    source_id: str
    title: str
    kind: Literal["document", "backend_fact"]
    cited: bool = True


class GroundingTrace(BaseModel):
    """What the coach was actually given on its last turn: the evidence for audits and evals."""
    model_config = ConfigDict(frozen=True)
    mode: GroundingModeName
    text: str
    sources: List[str] = Field(default_factory=list)
    retrieval_query: Optional[str] = None   # Mode A: the last query the agent searched with
    search_queries: List[str] = Field(default_factory=list)  # Mode A: every query, in order
    agent_steps: int = 0                    # Mode A: agent decisions taken
    retriever: str = ""                     # Mode A: backend that served the search
    fabricated_citations: List[str] = Field(default_factory=list)  # ids the model cited that were not in its context
    uncited: bool = False                   # the answer used sources but cited none of them inline
    tools_called: List[str] = Field(default_factory=list)  # Mode B: the backend tools the agent called
    agent_decision: Literal["llm", "deterministic"] = "deterministic"
    skipped: bool = False


class EmergencyPayload(BaseModel):
    """What the emergency node needs to render a response."""
    model_config = ConfigDict(frozen=True)
    message: str = ""
    helplines: dict[str, str] = Field(default_factory=dict)


class Turn(BaseModel):
    """One user/assistant exchange."""
    model_config = ConfigDict(frozen=True)
    user_text: str
    response: str
    node: str
    trace_id: str
    at: datetime = Field(default_factory=datetime.now)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0


class UserSessionState(BaseModel):
    """Complete, serializable state of a user's session, passed through the workflow."""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    channel: str
    member: MemberProfile
    booking_draft: BookingDraft = Field(default_factory=BookingDraft)
    active_node: str  # last node that handled the turn
    next_node: Optional[str] = None
    triage_status: TriageStatus = Field(default_factory=TriageStatus)
    emergency_payload: Optional[EmergencyPayload] = None
    trace_id: Optional[str] = None
    handoff_ticket: Optional[str] = None
    yellow_reply: Optional[str] = None  # deterministic no-diagnosis reply for the current turn
    turn_history: List[Turn] = Field(default_factory=list)
    grounding_mode: GroundingMode = Field(default_factory=GroundingMode)
    last_citations: List[Citation] = Field(default_factory=list)  # verified sources for the latest coach answer
    last_grounding: Optional[GroundingTrace] = None  # evidence given to the coach on the latest coach turn
    reply_lang: Literal["en", "hinglish"] = "en"  # language of deterministic replies; follows what the member types
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_latency_ms: float = 0.0
