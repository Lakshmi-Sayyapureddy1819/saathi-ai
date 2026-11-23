"""Voice channel (simulated audio I/O).

STT/TTS are still simulated: plug real providers into `transcribe` / `speak`.
What is real here: Hinglish normalisation, number-safe slot read-back, barge-in cancellation of TTS,
and per-turn latency measurement.
"""
import re
import threading
import time
from typing import List, Optional, TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from app.observability.tracer import new_trace_id, span
from app.tools.slots import match_slot
from app.workflow.graph import execute_turn
from app.workflow.state import UserSessionState

if TYPE_CHECKING:  # avoid a runtime import cycle; the graph is only passed through
    from app.workflow.graph import WorkflowGraph

# Time-to-first-audio budget: caller stops speaking -> first audible syllable. Allocation (ms):
#   real STT final result ~400 (assumed, NOT measured here) + workflow <= 600 (measured) + TTS first byte ~300 (assumed)
#   = 1300, leaving 200 ms slack. Turns that call an LLM cannot meet it without streaming (see EVALS.md voice section).
TTFA_BUDGET_MS = 1500.0

# If the workflow has not answered after this long (it is waiting on an LLM), speak a fixed filler.
# Deterministic code, not LLM output; contains no clinical content. Budget: STT ~400 + 600 + TTS ~300 = 1300 ms.
FILLER_AFTER_MS = 600.0
FILLERS = {"en": "One moment, let me check that for you.", "hinglish": "Ek second, main check karti hoon."}

HINGLISH = {"kal": "tomorrow", "aaj": "today", "subah": "morning", "shaam": "evening", "parso": "day after tomorrow"}
# Number words are NOT rewritten here: slots.py parses them to integers so "fifteen" != "fifty".


class VoiceTurnMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)
    stt_ms: float
    graph_ms: float
    tts_first_chunk_ms: float
    total_ms: float
    barged_in: bool = False
    ttfa_ms: float = 0.0  # what the caller waits before hearing anything (filler if spoken, else the reply)
    filler_spoken: bool = False


class VoiceAgent:
    def __init__(self, tts_char_delay: float = 0.002, graph: Optional["WorkflowGraph"] = None, verbose: bool = True,
                 filler_after_ms: float = FILLER_AFTER_MS):
        self.tts_char_delay = tts_char_delay
        self.filler_after_ms = filler_after_ms
        if graph is None:
            from app.workflow.graph import WorkflowGraph
            graph = WorkflowGraph(model_node="voice")
        self.graph = graph          # reuse one workflow across turns (defaults to model_node='voice')
        self.verbose = verbose
        self.last_spoken: str = ""  # exactly what the caller heard on the last turn (for read-back checks)
        self._barge_in = threading.Event()
        self.metrics: List[VoiceTurnMetrics] = []

    def barge_in(self) -> None:
        """Call when the caller starts speaking: stops the in-flight TTS."""
        self._barge_in.set()

    @staticmethod
    def normalize(text: str) -> str:
        import re
        def _rep(m):
            w = m.group(0).lower()
            return HINGLISH.get(w, m.group(0))
        return re.sub(r"\b[A-Za-z]+\b", _rep, text)

    def transcribe(self, audio_or_text: str) -> str:
        time.sleep(0.05)  # placeholder for real STT latency
        return self.normalize(audio_or_text)

    def speak(self, text: str) -> tuple[float, bool]:
        """Stream text as 'audio'. Returns (first_chunk_ms, barged_in)."""
        text = re.sub(r"\s?\[[A-Za-z][A-Za-z0-9_]{2,40}\]", "", text)  # citation markers are shown on screen, never spoken
        self._barge_in.clear()
        t0 = time.perf_counter()
        first: Optional[float] = None
        self.last_spoken = text
        if self.verbose:
            print("TTS: ", end="", flush=True)
        for ch in text:
            if self._barge_in.is_set():
                if self.verbose:
                    print(" [interrupted]")
                return first or 0.0, True
            if first is None:
                first = (time.perf_counter() - t0) * 1000
            if self.verbose:
                print(ch, end="", flush=True)
            time.sleep(self.tts_char_delay)
        if self.verbose:
            print()
        return first or 0.0, False

    def readback(self, transcript: str, session: UserSessionState) -> Optional[str]:
        """If a slot is pending, echo the understood time so the caller can catch ASR errors."""
        d = session.booking_draft
        if d.package_id and not d.selected_slot:
            from app.workflow.graph import WorkflowGraph  # local import: avoid cycle at module load
            lab_tools = self.graph.lab_tools if self.graph else WorkflowGraph(model_node="voice").lab_tools
            avail = lab_tools.check_slots(d.package_id, d.selected_date or __import__("datetime").date.today())
            m = match_slot(transcript, avail.slots)
            if m.status == "matched":
                return f"I heard {m.slot}."
            if m.status == "none":
                return "Sorry, I didn't catch a valid time."
        return None

    def process_voice_turn(self, user_audio_transcript: str, session: UserSessionState,
                           trace_id: Optional[str] = None) -> UserSessionState:
        trace_id = trace_id or session.trace_id or new_trace_id()
        t0 = time.perf_counter()
        with span("voice:stt", trace_id, kind="tool", input=user_audio_transcript) as s_stt:
            transcript = self.transcribe(user_audio_transcript)
            s_stt.set_output(transcript)
        t1 = time.perf_counter()
        if self.verbose:
            print(f"[ASR]: {transcript}")
        # Run the workflow in a worker. If it is still busy after FILLER_AFTER_MS (an LLM turn), speak a
        # fixed filler so the caller hears audio inside the budget. Fast turns (booking, emergency) finish
        # first and never get a filler, so a safety reply is never preceded by "let me check".
        box: dict = {}

        def _run() -> None:
            try:
                box["out"] = execute_turn(transcript, session, trace_id=trace_id, graph=self.graph)
            except BaseException as exc:  # re-raised on the caller's thread below
                box["err"] = exc

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        worker.join(timeout=self.filler_after_ms / 1000)
        filler_first_ms = 0.0
        filler_spoken = False
        if worker.is_alive():
            with span("voice:filler", trace_id, kind="tool") as s_fill:
                filler_first_ms, filler_barged = self.speak(FILLERS[session.reply_lang])
                s_fill.set(first_chunk_ms=filler_first_ms, barged_in=filler_barged)
            filler_spoken = True
            if filler_barged:
                worker.join()
                if "err" in box:
                    raise box["err"]
                return box["out"][1]  # caller interrupted the filler: stay silent, keep state
        worker.join()
        if "err" in box:
            raise box["err"]
        response, session = box["out"]
        t2 = time.perf_counter()
        with span("voice:tts", trace_id, kind="tool", input=response) as s_tts:
            first_ms, barged = self.speak(response)
            s_tts.set(first_chunk_ms=first_ms, barged_in=barged)
        t3 = time.perf_counter()
        # TTFA is when the caller first hears anything: the filler if one was spoken, else the reply.
        if filler_spoken:
            ttfa = (t1 - t0) * 1000 + self.filler_after_ms + filler_first_ms
        else:
            ttfa = (t2 - t0) * 1000 + first_ms
        self.metrics.append(VoiceTurnMetrics(stt_ms=round((t1 - t0) * 1000, 1), graph_ms=round((t2 - t1) * 1000, 1),
                                             tts_first_chunk_ms=round(first_ms, 1),
                                             total_ms=round((t3 - t0) * 1000, 1), barged_in=barged,
                                             ttfa_ms=round(ttfa, 1), filler_spoken=filler_spoken))
        return session
