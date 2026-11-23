"""Voice evaluation (brief section 3): 15 scripted multi-turn calls with simulated speech-recognition errors.

Drives the REAL workflow through `VoiceAgent` (same graph as chat; only the channel adapter differs) and measures:
  * read-back correctness - after the caller names a time, the spoken reply must contain the intended test, the date
    and the slot; for a garbled/unavailable time it must NOT read back a slot at all (re-ask instead);
  * wrong-booking rate (target 0) - any booking whose test/slot differs from the intended one, any booking without an
    explicit "yes", and any duplicate booking;
  * turn latency and time-to-first-audio (TTFA) against `TTFA_BUDGET_MS`.

What is simulated: audio. ASR errors are injected as the TEXT a recogniser would have produced ("nine fifty" for
"nine fifteen"), STT is a fixed 50 ms sleep and TTS "audio" is text. What is real: the workflow, the slot parser, the
read-back wording, barge-in cancellation and the measured workflow latency. Real STT/TTS latency is NOT in the numbers.

    python -m evaluations.voice_eval
"""
import statistics
import sys
import threading
from typing import List, Optional

sys.path.append(".")

from pydantic import BaseModel, ConfigDict

from app.channels.voice_agent import TTFA_BUDGET_MS, VoiceAgent
from app.workflow.graph import WorkflowGraph
from app.workflow.state import GroundingMode, MemberProfile, UserSessionState


class _EvalAgent(VoiceAgent):
    """VoiceAgent whose caller starts talking `interrupt_after_s` into the TTS (set only for the barge-in turn)."""
    interrupt_after_s: Optional[float] = None

    def speak(self, text: str) -> tuple[float, bool]:
        if self.interrupt_after_s is not None:
            threading.Timer(self.interrupt_after_s, self.barge_in).start()
        return super().speak(text)


class VoiceTurn(BaseModel):
    model_config = ConfigDict(frozen=True)
    heard: str                              # what the (simulated) ASR returned
    expect_slot: Optional[str] = None       # a read-back of this slot must be spoken on this turn
    expect_no_readback: bool = False        # no slot may be read back on this turn (garbled / unavailable time)
    barge_in: bool = False                  # the caller interrupts the TTS of this turn


class VoiceScenario(BaseModel):
    model_config = ConfigDict(frozen=True)
    case_id: str
    asr_error: str                          # what goes wrong in this call
    turns: List[VoiceTurn]
    expect_package: Optional[str] = None    # package_id that may be booked (None: nothing may be booked)
    expect_booked_slot: Optional[str] = None
    expect_pkg_name: str = "Thyroid Screening Profile"


T = VoiceTurn
SCENARIOS: List[VoiceScenario] = [
    VoiceScenario(case_id="VC-01", asr_error="none (clean baseline)", expect_package="LP_002", expect_booked_slot="09:30 AM",
                  turns=[T(heard="book thyroid test"), T(heard="nine thirty", expect_slot="09:30 AM"), T(heard="yes")]),
    VoiceScenario(case_id="VC-02", asr_error="'fifteen' / 'fifty' heard for the minutes", expect_package="LP_002",
                  expect_booked_slot="09:30 AM",
                  turns=[T(heard="book thyroid test"), T(heard="nine fifty", expect_no_readback=True),
                         T(heard="nine fifteen", expect_no_readback=True), T(heard="nine thirty", expect_slot="09:30 AM"),
                         T(heard="yes")]),
    VoiceScenario(case_id="VC-03", asr_error="colon dropped: '9 30'", expect_package="LP_002", expect_booked_slot="09:30 AM",
                  turns=[T(heard="book thyroid test"), T(heard="9 30", expect_slot="09:30 AM"), T(heard="yes")]),
    VoiceScenario(case_id="VC-04", asr_error="Hinglish time ('saadhe nau') and Hinglish yes", expect_package="LP_002",
                  expect_booked_slot="09:30 AM",
                  turns=[T(heard="thyroid test book karna hai"), T(heard="saadhe nau", expect_slot="09:30 AM"), T(heard="haan")]),
    VoiceScenario(case_id="VC-05", asr_error="Hinglish date + time ('kal subah', 'nau baje')", expect_package="LP_002",
                  expect_booked_slot="09:00 AM",
                  turns=[T(heard="kal subah thyroid test chahiye"), T(heard="nau baje", expect_slot="09:00 AM"),
                         T(heard="yes confirm")]),
    VoiceScenario(case_id="VC-06", asr_error="test name misheard ('tyroid')", expect_package="LP_002",
                  expect_booked_slot="10:00 AM",
                  turns=[T(heard="book a tyroid test"), T(heard="ten am", expect_slot="10:00 AM"), T(heard="yes")]),
    VoiceScenario(case_id="VC-07", asr_error="caller corrects the time after the read-back", expect_package="LP_002",
                  expect_booked_slot="10:30 AM",
                  turns=[T(heard="book thyroid test"), T(heard="nine am", expect_slot="09:00 AM"),
                         T(heard="no make it ten thirty", expect_slot="10:30 AM"), T(heard="yes")]),
    VoiceScenario(case_id="VC-08", asr_error="hesitant answer instead of a yes ('umm maybe')", expect_package=None,
                  turns=[T(heard="book thyroid test"), T(heard="nine thirty", expect_slot="09:30 AM"), T(heard="umm maybe")]),
    VoiceScenario(case_id="VC-09", asr_error="yes followed by a retraction ('yes no wait')", expect_package=None,
                  turns=[T(heard="book thyroid test"), T(heard="nine thirty", expect_slot="09:30 AM"),
                         T(heard="yes no wait")]),
    VoiceScenario(case_id="VC-10", asr_error="garbled time ('nine tirty')", expect_package=None,
                  turns=[T(heard="book thyroid test"), T(heard="uh nine tirty", expect_no_readback=True)]),
    VoiceScenario(case_id="VC-11", asr_error="time that does not exist for a fasting test ('seven fifty')",
                  expect_package="LP_004", expect_booked_slot="08:00 AM", expect_pkg_name="Cardiac Risk Assessment",
                  turns=[T(heard="book the cardiac risk assessment"), T(heard="seven fifty", expect_no_readback=True),
                         T(heard="eight am", expect_slot="08:00 AM"), T(heard="yes")]),
    VoiceScenario(case_id="VC-12", asr_error="'vitamin d' vs 'vitamin b'", expect_package="LP_005",
                  expect_booked_slot="11:00 AM", expect_pkg_name="Vitamin D & B12 Panel",
                  turns=[T(heard="i need a vitamin d test"), T(heard="eleven am", expect_slot="11:00 AM"), T(heard="yes")]),
    VoiceScenario(case_id="VC-13", asr_error="'fifteen past nine' (a minute that has no slot), then a valid time",
                  expect_package="LP_002", expect_booked_slot="09:30 AM",
                  turns=[T(heard="book thyroid test"), T(heard="fifteen past nine", expect_no_readback=True),
                         T(heard="half past nine", expect_slot="09:30 AM"), T(heard="yes")]),
    VoiceScenario(case_id="VC-14", asr_error="caller barges in during the read-back", expect_package="LP_002",
                  expect_booked_slot="09:30 AM",
                  turns=[T(heard="book thyroid test"), T(heard="nine thirty", expect_slot="09:30 AM", barge_in=True),
                         T(heard="yes")]),
    VoiceScenario(case_id="VC-15", asr_error="duplicate 'yes' after the booking (echo / double recognition)",
                  expect_package="LP_002", expect_booked_slot="09:30 AM",
                  turns=[T(heard="book thyroid test"), T(heard="nine thirty", expect_slot="09:30 AM"), T(heard="yes"),
                         T(heard="yes")]),
]


class ScenarioResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    case_id: str
    asr_error: str
    readback_checks: int
    readback_ok: int
    bookings: List[str]
    wrong_booking: bool
    barge_in_honoured: Optional[bool]
    failures: List[str]


class CoachTurn(BaseModel):
    model_config = ConfigDict(frozen=True)
    utterance: str
    ttfa_ms: float
    graph_ms: float
    llm_called: bool


class VoiceResults(BaseModel):
    model_config = ConfigDict(frozen=True)
    scenarios: List[ScenarioResult]
    readback_checks: int
    readback_ok: int
    wrong_bookings: int
    n_scenarios: int
    n_turns: int
    graph_ms_p50: float
    graph_ms_p95: float
    ttfa_ms_p50: float
    ttfa_ms_p95: float
    ttfa_budget_ms: float
    turns_over_budget: int
    over_budget_turns: List[str]
    coach_turns: List[CoachTurn]


def _p(xs: List[float], q: int) -> float:
    return round(statistics.quantiles(xs, n=100, method="inclusive")[q - 1], 1) if len(xs) >= 2 else (xs[0] if xs else 0.0)


def _new_session(case_id: str) -> UserSessionState:
    m = MemberProfile(member_id=f"VOICE_{case_id}", name="Voice Eval", age=30)
    return UserSessionState(channel="voice", member=m, active_node="start", grounding_mode=GroundingMode(mode="mode_a_rag"))


def _readback_ok(spoken: str, turn: VoiceTurn, pkg_name: str) -> bool:
    if turn.expect_no_readback:
        return "Just to confirm" not in spoken and "Bas ek baar confirm" not in spoken
    return (turn.expect_slot or "") in spoken and pkg_name in spoken and "20" in spoken  # slot + test + a dated read-back


def run_scenario(sc: VoiceScenario, graph: WorkflowGraph, agent: "_EvalAgent") -> ScenarioResult:
    session = _new_session(sc.case_id)
    graph.lab_tools._booked.clear()      # every call starts against an empty schedule (no slot taken by an earlier call)
    graph.lab_tools._bookings.clear()
    checks = ok = 0
    failures: List[str] = []
    barge_honoured: Optional[bool] = None
    for i, turn in enumerate(sc.turns, 1):
        n_before = len(agent.metrics)
        if turn.barge_in:
            agent.tts_char_delay = 0.01                               # slow "audio" so there is something to interrupt
            agent.interrupt_after_s = 0.05                            # caller starts talking 50 ms into the TTS
        session = agent.process_voice_turn(turn.heard, session)
        agent.tts_char_delay = 0.0
        agent.interrupt_after_s = None
        m = agent.metrics[n_before]
        if turn.barge_in:
            barge_honoured = m.barged_in
            if not m.barged_in:
                failures.append(f"turn {i}: barge-in was not honoured")
        if turn.expect_slot or turn.expect_no_readback:
            checks += 1
            good = _readback_ok(agent.last_spoken, turn, sc.expect_pkg_name)
            ok += good
            if not good:
                failures.append(f"turn {i} ({turn.heard!r}): read-back wrong -> {agent.last_spoken[:140]!r}")
    bookings = list(session.member.past_bookings)
    wrong = False
    if sc.expect_package is None:
        wrong = bool(bookings)
    else:
        wrong = len(bookings) != 1 or not (sc.expect_pkg_name in bookings[0] and (sc.expect_booked_slot or "") in bookings[0])
    if wrong:
        failures.append(f"booking wrong: expected {sc.expect_package} {sc.expect_booked_slot}, got {bookings}")
    return ScenarioResult(case_id=sc.case_id, asr_error=sc.asr_error, readback_checks=checks, readback_ok=ok,
                          bookings=bookings, wrong_booking=wrong, barge_in_honoured=barge_honoured, failures=failures)


COACH_UTTERANCES = ["what yoga helps with stress", "kapalbhati ke fayde kya hain", "what should I eat for better sleep"]


def run_voice_eval(graph: Optional[WorkflowGraph] = None, with_llm_turns: bool = True) -> VoiceResults:
    graph = graph or WorkflowGraph(model_node="voice")
    graph.lab_tools.failure_rate = 0.0
    prev_cache, graph.use_cache = graph.use_cache, False
    agent = _EvalAgent(tts_char_delay=0.0, graph=graph, verbose=False)
    results = [run_scenario(sc, graph, agent) for sc in SCENARIOS]
    booking_turns = list(agent.metrics)                               # all workflow turns above are booking turns
    coach: List[CoachTurn] = []
    if with_llm_turns:
        for u in COACH_UTTERANCES:
            before = len(agent.metrics)
            agent.process_voice_turn(u, _new_session("COACH"))
            m = agent.metrics[before]
            coach.append(CoachTurn(utterance=u, ttfa_ms=m.ttfa_ms, graph_ms=m.graph_ms, llm_called=True))
    graph.use_cache = prev_cache
    labels = [f"{sc.case_id} {t.heard!r}" for sc in SCENARIOS for t in sc.turns]   # same order as agent.metrics
    over = [f"{lab} {m.ttfa_ms:.0f} ms" for lab, m in zip(labels, booking_turns) if m.ttfa_ms > TTFA_BUDGET_MS]
    g = [m.graph_ms for m in booking_turns]
    t = [m.ttfa_ms for m in booking_turns]
    return VoiceResults(
        scenarios=results, readback_checks=sum(r.readback_checks for r in results),
        readback_ok=sum(r.readback_ok for r in results), wrong_bookings=sum(r.wrong_booking for r in results),
        n_scenarios=len(results), n_turns=len(booking_turns), graph_ms_p50=_p(g, 50), graph_ms_p95=_p(g, 95),
        ttfa_ms_p50=_p(t, 50), ttfa_ms_p95=_p(t, 95), ttfa_budget_ms=TTFA_BUDGET_MS,
        turns_over_budget=len(over), over_budget_turns=over, coach_turns=coach)


def voice_section_md(v: VoiceResults) -> str:
    rb = round(100 * v.readback_ok / v.readback_checks, 1) if v.readback_checks else 0.0
    lines = [
        "## Voice (15 scripted calls with simulated ASR errors)", "",
        "Same workflow as chat, driven through `VoiceAgent` (`python -m evaluations.voice_eval`). **Audio is simulated:** "
        "ASR errors are injected as the text a recogniser would return, STT is a fixed 50 ms sleep and TTS is text. "
        "Real STT/TTS latency is **not** in these numbers.", "",
        "| Metric | Result | Target | Sample |", "|---|---|---|---|",
        f"| Read-back correctness (right test + date + slot, or no read-back for a garbled time) | {rb}% | 100% | "
        f"{v.readback_ok}/{v.readback_checks} checks |",
        f"| Wrong-booking rate (wrong test/slot, no explicit yes, or duplicate) | "
        f"{round(100 * v.wrong_bookings / v.n_scenarios, 1)}% | 0% | {v.wrong_bookings}/{v.n_scenarios} calls |",
        f"| Workflow latency per booking turn, p50 / p95 (no LLM call) | {v.graph_ms_p50} / {v.graph_ms_p95} ms | - | n={v.n_turns} turns |",
        f"| Time to first audio, simulated STT+workflow+TTS, p50 / p95 | {v.ttfa_ms_p50} / {v.ttfa_ms_p95} ms | "
        f"<= {int(v.ttfa_budget_ms)} ms | {v.turns_over_budget} of {v.n_turns} turns over budget |", ""]
    if v.over_budget_turns:
        lines += ["Over-budget booking turn(s): " + "; ".join(v.over_budget_turns) + ". A bare 'yes' with no booking in "
                  "progress matches no keyword rule, so the router falls back to an LLM call (known gap: not fixed).", ""]
    if v.coach_turns:
        c = [x.ttfa_ms for x in v.coach_turns]
        lines += [f"Turns that call an LLM (wellness questions by voice, n={len(c)}): TTFA {min(c):.0f}-{max(c):.0f} ms "
                  f"({'within' if max(c) <= v.ttfa_budget_ms else 'OVER'} the {int(v.ttfa_budget_ms)} ms budget, before real STT/TTS). "
                  "Met by a deterministic spoken filler ('One moment, let me check') that the voice adapter plays when the "
                  "workflow has not answered after 600 ms; fast turns (booking, emergency) never get one. "
                  "This is time to *first audio*: the full LLM answer still arrives ~1.3-1.6 s later. Streaming tokens into "
                  "TTS (to shorten that) is **not implemented**.", ""]
    lines += ["**Budget allocation (ms):** STT final ~400 (assumed) + workflow <= 600 (measured above) + TTS first byte ~300 "
              "(assumed) = 1300, leaving 200 ms slack. The two assumed parts are vendor-typical figures, not measurements.", "",
              "**Calls that failed a check:** " + (", ".join(f"{r.case_id} ({'; '.join(r.failures)[:160]})"
                                                           for r in v.scenarios if r.failures) or "none"), "",
              "Per-call ASR error injected: " + "; ".join(f"{r.case_id} {r.asr_error}" for r in v.scenarios) + ".", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    res = run_voice_eval()
    print(voice_section_md(res))
    for r in res.scenarios:
        print(r.case_id, "OK" if not r.failures else r.failures)
