"""Typed session state. All models are Pydantic V2 (CLAUDE.md §2).

Models are frozen where the data is a value object; the session itself stays mutable
because the workflow updates it every turn (use `model_copy(update=...)` for value objects).
"""
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


class GroundingMode(BaseModel):
    """Grounding context mode."""
    model_config = ConfigDict(frozen=True)
    mode: Literal["mode_a_rag", "mode_b_facts"] = "mode_a_rag"


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
    reply_lang: Literal["en", "hinglish"] = "en"  # language of deterministic replies; follows what the member types
