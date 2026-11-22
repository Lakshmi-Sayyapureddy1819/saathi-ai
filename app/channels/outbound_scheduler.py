"""Decides WHO to phone and WHEN for outbound checkup reminders. Deterministic code, no LLM.

Rules (all explicit and tested):
  * a member is eligible if they have a pending checkup (not already booked) due within LEAD_DAYS, or overdue;
  * never call a member on the do-not-call list;
  * only call inside the calling window (CALL_START_HOUR to CALL_END_HOUR local time); outside it the call is
    scheduled for the next window start;
  * at most MAX_ATTEMPTS attempts per member per checkup, at least MIN_RETRY_GAP apart;
  * members who already booked, or declined this checkup, are not called again.
Dialling itself sits behind the `Dialler` protocol. `SimulatedDialler` runs the call in-process (simulated STT/TTS);
a telephony provider would implement the same one method.
"""
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Literal, Optional, Protocol, Sequence

from pydantic import BaseModel, ConfigDict

from app.channels.outbound import OutboundCall, OutboundCallResult, pick_pending
from app.observability.tracer import new_trace_id, span
from app.tools.lab_tools import LabTools
from app.workflow.state import MemberProfile

LEAD_DAYS = 14
CALL_START_HOUR = 9
CALL_END_HOUR = 19
MAX_ATTEMPTS = 3
MIN_RETRY_GAP = timedelta(hours=4)

SkipReason = Literal["do_not_call", "nothing_pending", "not_due_yet", "max_attempts", "retry_too_soon",
                     "declined_before", "booked"]


class CallAttempt(BaseModel):
    """One earlier attempt for a member's checkup."""
    model_config = ConfigDict(frozen=True)
    member_id: str
    package_id: str
    at: datetime
    outcome: Literal["booked", "declined", "no_answer", "unfinished"]


class ScheduledCall(BaseModel):
    model_config = ConfigDict(frozen=True)
    member_id: str
    package_id: str
    due_date: date
    call_at: datetime
    attempt_number: int


class Skipped(BaseModel):
    model_config = ConfigDict(frozen=True)
    member_id: str
    reason: SkipReason


class SchedulePlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    trace_id: str
    calls: List[ScheduledCall]
    skipped: List[Skipped]


class Dialler(Protocol):
    """The one thing a telephony provider has to implement."""
    def place_call(self, member: MemberProfile, scheduled: ScheduledCall) -> OutboundCallResult: ...


def next_window_start(now: datetime) -> datetime:
    """`now` if it is inside the calling window, else the next 09:00."""
    start = now.replace(hour=CALL_START_HOUR, minute=0, second=0, microsecond=0)
    end = now.replace(hour=CALL_END_HOUR, minute=0, second=0, microsecond=0)
    if start <= now < end:
        return now
    return start if now < start else start + timedelta(days=1)


def plan_schedule(members: Sequence[MemberProfile], lab_tools: LabTools, now: datetime,
                  history: Sequence[CallAttempt] = (), do_not_call: Sequence[str] = (),
                  trace_id: Optional[str] = None) -> SchedulePlan:
    """Pure decision function: who should be called, and when. Earliest-due checkups first."""
    tid = trace_id or new_trace_id()
    calls: List[ScheduledCall] = []
    skipped: List[Skipped] = []
    with span("outbound_schedule", tid, kind="node", members=len(members), now=now.isoformat()) as s:
        for m in members:
            if m.member_id in do_not_call:
                skipped.append(Skipped(member_id=m.member_id, reason="do_not_call"))
                continue
            pending = pick_pending(m, lab_tools)
            if pending is None:
                already = any(c.package_id in m.past_bookings for c in m.pending_checkups)
                skipped.append(Skipped(member_id=m.member_id, reason="booked" if already else "nothing_pending"))
                continue
            if (pending.due_date - now.date()).days > LEAD_DAYS:
                skipped.append(Skipped(member_id=m.member_id, reason="not_due_yet"))
                continue
            tries = sorted((h for h in history if h.member_id == m.member_id and h.package_id == pending.package_id),
                           key=lambda h: h.at)
            if any(h.outcome in ("booked", "declined") for h in tries):
                skipped.append(Skipped(member_id=m.member_id,
                                       reason="booked" if any(h.outcome == "booked" for h in tries) else "declined_before"))
                continue
            if len(tries) >= MAX_ATTEMPTS:
                skipped.append(Skipped(member_id=m.member_id, reason="max_attempts"))
                continue
            earliest = now
            if tries and tries[-1].at + MIN_RETRY_GAP > now:
                earliest = tries[-1].at + MIN_RETRY_GAP
            calls.append(ScheduledCall(member_id=m.member_id, package_id=pending.package_id, due_date=pending.due_date,
                                       call_at=next_window_start(earliest), attempt_number=len(tries) + 1))
        calls.sort(key=lambda c: (c.due_date, c.call_at, c.member_id))
        s.set(scheduled=len(calls), skipped=len(skipped))
    return SchedulePlan(trace_id=tid, calls=calls, skipped=skipped)


class SimulatedDialler:
    """Runs the call in-process with scripted member replies (simulated STT/TTS). For demos and tests."""

    def __init__(self, replies: Callable[[MemberProfile], List[str]], verbose: bool = False):
        self.replies = replies
        self.verbose = verbose

    def place_call(self, member: MemberProfile, scheduled: ScheduledCall) -> OutboundCallResult:
        from app.channels.voice_agent import VoiceAgent
        call = OutboundCall(member, agent=VoiceAgent(verbose=self.verbose, tts_char_delay=0))
        before = list(member.past_bookings)
        call.start()
        for said in self.replies(member):
            if call.finished:
                break
            call.reply(said)
        return call.result(before)


def run_due_calls(plan: SchedulePlan, members: Dict[str, MemberProfile], dialler: Dialler,
                  now: datetime) -> List[CallAttempt]:
    """Place every call whose time has come. Returns the attempts to append to the history."""
    attempts: List[CallAttempt] = []
    for sc in plan.calls:
        if sc.call_at > now:
            continue  # outside the calling window: it stays scheduled for later
        result = dialler.place_call(members[sc.member_id], sc)
        outcome = result.outcome if result.outcome in ("booked", "declined", "unfinished") else "unfinished"
        attempts.append(CallAttempt(member_id=sc.member_id, package_id=sc.package_id, at=now, outcome=outcome))
    return attempts
