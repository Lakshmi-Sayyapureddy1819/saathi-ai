"""Outbound reminder call: the agent phones a member about a pending checkup and books it.

What is deterministic code (CLAUDE.md: safety is never left to the LLM):
  * picking the pending checkup, the opening line, and the decline / voicemail handling;
  * every reply that is not a plain decline goes through `execute_turn`, so the safety gate, red-flag escalation,
    slot read-back and the booking confirmation all behave exactly as on an inbound call.
The booking itself reuses the normal booking flow: the call only pre-fills the draft with the pending package.
Telephony (dialling, STT, TTS) is simulated by `VoiceAgent`; plug a real provider in there.
"""
import re
from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict

from app.channels.voice_agent import VoiceAgent
from app.observability.tracer import new_trace_id, span
from app.tools.lab_tools import LabTools
from app.workflow.graph import WorkflowGraph
from app.workflow.state import BookingDraft, MemberProfile, PendingCheckup, UserSessionState

CallOutcome = Literal["booked", "declined", "no_pending_checkup", "unfinished"]

# Only a whole-utterance decline ends the call. Anything longer (e.g. "no, I have chest pain") goes to the
# safety gate through execute_turn, so a red flag can never be swallowed by the decline shortcut.
_DECLINE = re.compile(
    r"^\s*(no|nahi|nahin|nope|not now|no thanks|no thank you|later|baad mein|baad me|abhi nahi|abhi nahin|mat karo)"
    r"[\s.!,]*(thanks|thank you|dhanyavad|shukriya)?[\s.!]*$", re.I)

_OPENING = {
    "en": ("Hello {name}, this is Saathi Care calling from your wellness programme. You are due for your "
           "{package} (by {due}). Would you like me to book it for you now?"),
    "hinglish": ("Namaste {name}, hum Saathi Care se call kar rahe hain. Aapka {package} {due} tak due hai. "
                 "Kya main abhi aapke liye book kar doon?"),
}
_DECLINED = {
    "en": "No problem, {name}. I will not book anything now. You can call us any time to book. Take care.",
    "hinglish": "Theek hai {name}, abhi kuch book nahi karenge. Jab chahein humein call kar sakte hain. Dhanyavad.",
}


class OutboundCallPlan(BaseModel):
    """What the agent will say first, and which package the call is about."""
    model_config = ConfigDict(frozen=True)
    member_id: str
    package_id: str
    package_name: str
    due_date: date
    language: Literal["en", "hinglish"]
    opening_line: str


class OutboundCallResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    outcome: CallOutcome
    trace_id: str
    transcript: List[str]
    booking_ids: List[str]


def _language(member: MemberProfile) -> Literal["en", "hinglish"]:
    return "hinglish" if member.language_pref.lower().startswith(("hindi", "hinglish", "hi")) else "en"


def pick_pending(member: MemberProfile, lab_tools: LabTools) -> Optional[PendingCheckup]:
    """Earliest-due pending checkup that exists in the catalogue and is not already booked."""
    candidates = [c for c in member.pending_checkups
                  if lab_tools.get_package(c.package_id) and c.package_id not in member.past_bookings]
    return min(candidates, key=lambda c: c.due_date) if candidates else None


def plan_call(member: MemberProfile, lab_tools: LabTools, trace_id: str) -> Optional[OutboundCallPlan]:
    with span("outbound_plan_call", trace_id, kind="node", member_id=member.member_id) as s:
        pending = pick_pending(member, lab_tools)
        s.set(has_pending=pending is not None)
        if pending is None:
            return None
        package = lab_tools.get_package(pending.package_id)
        lang = _language(member)
        line = _OPENING[lang].format(name=member.name.split()[0], package=package.name,
                                     due=f"{pending.due_date:%d %B}")
        return OutboundCallPlan(member_id=member.member_id, package_id=package.package_id,
                                package_name=package.name, due_date=pending.due_date, language=lang,
                                opening_line=line)


class OutboundCall:
    """One reminder call. `start()` speaks the opener; `reply()` handles each thing the member says."""

    def __init__(self, member: MemberProfile, agent: Optional[VoiceAgent] = None,
                 graph: Optional[WorkflowGraph] = None):
        self.graph = graph or WorkflowGraph(model_node="voice")
        self.agent = agent or VoiceAgent(graph=self.graph)
        self.trace_id = new_trace_id()
        self.plan = plan_call(member, self.graph.lab_tools, self.trace_id)
        self.transcript: List[str] = []
        self.finished = False
        self.declined = False
        self.session = UserSessionState(channel="voice", member=member, active_node="start",
                                        reply_lang=self.plan.language if self.plan else "en")

    def start(self) -> Optional[str]:
        """Speak the opening line and seed the booking draft with the pending package."""
        if self.plan is None:
            self.finished = True
            return None
        self.session.booking_draft = BookingDraft(package_id=self.plan.package_id,
                                                  package_name=self.plan.package_name)
        self.session.active_node = "node_lab_booking"
        self.transcript.append(f"AGENT: {self.plan.opening_line}")
        self.agent.speak(self.plan.opening_line)
        return self.plan.opening_line

    def reply(self, member_said: str) -> str:
        """Handle one member utterance. A plain decline ends the call; everything else uses the normal workflow."""
        self.transcript.append(f"MEMBER: {member_said}")
        if _DECLINE.match(member_said):
            with span("outbound_decline", self.trace_id, kind="node", member_id=self.session.member.member_id):
                self.session.booking_draft = BookingDraft()
                self.declined, self.finished = True, True
                text = _DECLINED[self.plan.language if self.plan else "en"].format(
                    name=self.session.member.name.split()[0])
            self.agent.speak(text)
            self.transcript.append(f"AGENT: {text}")
            return text
        self.session = self.agent.process_voice_turn(member_said, self.session, trace_id=self.trace_id)
        text = self.agent.last_spoken
        self.transcript.append(f"AGENT: {text}")
        if self.session.turn_history and self.session.turn_history[-1].node != "node_lab_booking":
            self.finished = True  # escalated to emergency/handoff, or moved to another topic: stop the reminder script
        return text

    def result(self, before_bookings: List[str]) -> OutboundCallResult:
        new = [b for b in self.session.member.past_bookings if b not in before_bookings]
        if self.plan is None:
            outcome: CallOutcome = "no_pending_checkup"
        elif new:
            outcome = "booked"
        elif self.declined:
            outcome = "declined"
        else:
            outcome = "unfinished"
        return OutboundCallResult(outcome=outcome, trace_id=self.trace_id, transcript=self.transcript,
                                  booking_ids=new)


# The member side of the demo call. It is scripted: the simulated dialler has no real speech input. The member takes
# the first slot the agent actually offers, so a slot taken by an earlier booking does not break the demo.
_OFFERED_SLOT = re.compile(r"^- (\d{1,2}:\d{2} [AP]M)\s*$", re.M)


def first_offered_slot(agent_text: str) -> Optional[str]:
    """The first '- HH:MM AM/PM' line of an agent message that lists slots, or None."""
    m = _OFFERED_SLOT.search(agent_text)
    return m.group(1) if m else None


def run_scripted_call(member: MemberProfile) -> OutboundCallResult:
    """One reminder call on the simulated telephony with scripted member replies. Silent (no TTS printing)."""
    working = member.model_copy(deep=True)
    before = list(working.past_bookings)
    call = OutboundCall(working, agent=VoiceAgent(verbose=False, tts_char_delay=0))
    call.start()
    call.reply("haan kar do")
    call.reply("kal subah")
    if not call.finished:
        slot = first_offered_slot(call.transcript[-1]) or "09:00 AM"
        call.reply(slot)
    if not call.finished:
        call.reply("yes confirm")
    return call.result(before)
