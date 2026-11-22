"""Voice channel (simulated audio I/O).

STT/TTS are still simulated: plug real providers into `transcribe` / `speak`.
What is real here: Hinglish normalisation, number-safe slot read-back, barge-in cancellation of TTS,
and per-turn latency measurement.
"""
import threading
import time
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.tools.slots import match_slot
from app.workflow.graph import execute_turn
from app.workflow.state import UserSessionState

HINGLISH = {"kal": "tomorrow", "aaj": "today", "subah": "morning", "shaam": "evening", "parso": "day after tomorrow"}
# Number words are NOT rewritten here: slots.py parses them to integers so "fifteen" != "fifty".


class VoiceTurnMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)
    stt_ms: float
    graph_ms: float
    tts_first_chunk_ms: float
    total_ms: float
    barged_in: bool = False


class VoiceAgent:
    def __init__(self, tts_char_delay: float = 0.02):
        self.tts_char_delay = tts_char_delay
        self._barge_in = threading.Event()
        self.metrics: List[VoiceTurnMetrics] = []

    def barge_in(self) -> None:
        """Call when the caller starts speaking: stops the in-flight TTS."""
        self._barge_in.set()

    @staticmethod
    def normalize(text: str) -> str:
        return " ".join(HINGLISH.get(w, w) for w in text.lower().split())

    def transcribe(self, audio_or_text: str) -> str:
        time.sleep(0.05)  # placeholder for real STT latency
        return self.normalize(audio_or_text)

    def speak(self, text: str) -> tuple[float, bool]:
        """Stream text as 'audio'. Returns (first_chunk_ms, barged_in)."""
        self._barge_in.clear()
        t0 = time.perf_counter()
        first: Optional[float] = None
        print("TTS: ", end="", flush=True)
        for ch in text:
            if self._barge_in.is_set():
                print(" [interrupted]")
                return first or 0.0, True
            if first is None:
                first = (time.perf_counter() - t0) * 1000
            print(ch, end="", flush=True)
            time.sleep(self.tts_char_delay)
        print()
        return first or 0.0, False

    def readback(self, transcript: str, session: UserSessionState) -> Optional[str]:
        """If a slot is pending, echo the understood time so the caller can catch ASR errors."""
        d = session.booking_draft
        if d.package_id and not d.selected_slot:
            from app.workflow.graph import WorkflowGraph  # local import: avoid cycle at module load
            avail = WorkflowGraph().lab_tools.check_slots(d.package_id, d.selected_date or __import__("datetime").date.today())
            m = match_slot(transcript, avail.slots)
            if m.status == "matched":
                return f"I heard {m.slot}."
            if m.status == "none":
                return "Sorry, I didn't catch a valid time."
        return None

    def process_voice_turn(self, user_audio_transcript: str, session: UserSessionState) -> UserSessionState:
        t0 = time.perf_counter()
        transcript = self.transcribe(user_audio_transcript)
        t1 = time.perf_counter()
        print(f"[ASR]: {transcript}")
        response, session = execute_turn(transcript, session)
        t2 = time.perf_counter()
        first_ms, barged = self.speak(response)
        t3 = time.perf_counter()
        self.metrics.append(VoiceTurnMetrics(stt_ms=round((t1 - t0) * 1000, 1), graph_ms=round((t2 - t1) * 1000, 1),
                                             tts_first_chunk_ms=round(first_ms, 1),
                                             total_ms=round((t3 - t0) * 1000, 1), barged_in=barged))
        return session
