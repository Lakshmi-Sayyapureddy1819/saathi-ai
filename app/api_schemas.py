"""Wire models for the HTTP API (Pydantic V2, frozen). The UI renders these; it never parses chat text."""
from datetime import datetime
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_MESSAGE_CHARS = 500

BookingStage = Literal["idle", "choosing_package", "choosing_slot", "confirming"]
MessageRole = Literal["user", "assistant", "system"]
# answer = normal reply; safety_notice = deterministic no-diagnosis reply; emergency = red-flag escalation;
# booking_confirmed = tool-confirmed booking; handoff = coordinator needed; handoff_resolved = coordinator decided.
MessageKind = Literal["answer", "safety_notice", "emergency", "booking_confirmed", "handoff", "handoff_resolved"]
HandoffStatus = Literal["none", "pending", "approved", "rejected"]
SessionStatus = Literal["active", "awaiting_coordinator"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


# ---- requests ----
class CreateSessionRequest(_Frozen):
    member_id: Annotated[str, StringConstraints(pattern=r"^MEM_\d{4}$")]


class SendMessageRequest(_Frozen):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS)]


class CoordinatorDecisionRequest(_Frozen):
    approved: bool
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""


# ---- catalogue ----
class MemberPublic(_Frozen):
    member_id: str
    name: str
    age: int
    language_preference: str


class PackageOption(_Frozen):
    package_id: str
    name: str
    price_inr: int
    test_count: int
    fasting_required: bool
    fasting_hours: int


class ProgramSummary(_Frozen):
    doc_id: str
    title: str
    category: str


class DateOption(_Frozen):
    word: Literal["today", "tomorrow", "day after tomorrow"]  # the phrase sent to the backend (it parses these)
    label: str
    iso: str


class ConfigView(_Frozen):
    llm_configured: bool  # False -> coach replies are flagged [MOCK]; booking/safety are unaffected
    coordinator_console_enabled: bool
    max_message_chars: int


# ---- session state ----
class BookingView(_Frozen):
    stage: BookingStage = "idle"
    package: Optional[PackageOption] = None
    options: List[PackageOption] = Field(default_factory=list)  # candidate packages while choosing_package
    date_iso: Optional[str] = None
    date_label: Optional[str] = None
    slot: Optional[str] = None
    slots: List[str] = Field(default_factory=list)  # free slots while choosing_slot
    dates: List[DateOption] = Field(default_factory=list)


class BookingConfirmation(_Frozen):
    booking_id: str
    package_name: str
    date: str
    slot: str


class EmergencyView(_Frozen):
    message: str
    helplines: dict[str, str]


class HandoffView(_Frozen):
    status: HandoffStatus = "none"
    ticket_id: Optional[str] = None
    note: str = ""


class ChatMessage(_Frozen):
    id: int
    role: MessageRole
    kind: MessageKind = "answer"
    text: str
    at: datetime
    trace_id: Optional[str] = None
    emergency: Optional[EmergencyView] = None
    confirmation: Optional[BookingConfirmation] = None


class BookingItem(_Frozen):
    """A confirmed booking that can still be cancelled (cancel = send 'cancel <booking_id>' in the chat)."""
    booking_id: str
    package_name: str
    date: str
    slot: str


class SessionView(_Frozen):
    session_id: str
    member: MemberPublic
    status: SessionStatus
    triage_status: Literal["GREEN_NORMAL", "YELLOW_WARNING", "RED_CRISIS"]
    messages: List[ChatMessage]
    booking: BookingView
    handoff: HandoffView
    bookings: List[BookingItem] = Field(default_factory=list)


class SessionCreated(_Frozen):
    session_token: str  # bearer secret for this session; shown once, never logged
    session: SessionView


class DeleteResponse(_Frozen):
    session_id: str
    deleted: bool


# ---- coordinator ----
class ApprovalItem(_Frozen):
    session_id: str
    member_id: str
    member_name: str
    ticket_id: Optional[str]
    package_name: Optional[str]
    date: Optional[str]
    slot: Optional[str]
    requested_at: datetime


class ApprovalList(_Frozen):
    items: List[ApprovalItem]
