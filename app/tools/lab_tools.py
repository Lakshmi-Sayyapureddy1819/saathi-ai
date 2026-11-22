"""Lab catalogue + schedule backend tools. All inputs/outputs are typed (Pydantic V2)."""
import json
import logging
import os
import random
import re
import time
from datetime import date as Date
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict

from app.observability.redact import redact
from app.observability.tracer import span, new_trace_id

FASTING_SLOTS = ["07:00 AM", "07:30 AM", "08:00 AM", "08:30 AM"]
REGULAR_SLOTS = ["09:00 AM", "09:30 AM", "10:00 AM", "10:30 AM", "11:00 AM"]
# Words that carry no package identity: request verbs, filler, and category nouns shared by many packages
# ("panel", "profile", "checkup"...). Matching on them is what made "fever panel" look like 5 packages.
STOPWORDS = {
    "book", "booking", "test", "tests", "need", "want", "please", "lab", "package", "packages", "with", "that",
    "this", "have", "the", "and", "for", "can", "you", "get", "schedule", "appointment", "slot", "slots", "karo",
    "karwana", "chahiye", "hai", "mujhe", "panel", "profile", "checkup", "check", "screening", "screen", "health",
    "assessment", "blood", "wellness", "package", "one", "pls", "today", "tomorrow", "kal", "aaj",
}
# Category nouns that mean "some lab test" without naming one. Used only to decide whether to ASK which test the
# member wants; they never produce catalogue matches (that is what STOPWORDS prevents).
GENERIC_REQUEST_WORDS = {"test", "tests", "checkup", "panel", "profile", "package", "packages", "blood", "lab",
                         "screening", "health", "report", "reports"}
_ORDINALS = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "fourth": 3, "4th": 3}


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2 and t not in STOPWORDS]


def _same_word(a: str, b: str) -> bool:
    """Equal, or same stem (>=5-char shared prefix: diabetes~diabetic). 'male' never matches 'female'."""
    return a == b or (len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5])


class LabPackage(BaseModel):
    model_config = ConfigDict(frozen=True)
    package_id: str
    name: str
    test_count: int = 0
    fasting_required: bool = False
    fasting_hours: int = 0
    price_inr: int = 0
    target_symptoms: List[str] = []


class PackageSelection(BaseModel):
    """Outcome of resolving a short reply against a list of candidate packages."""
    model_config = ConfigDict(frozen=True)
    status: Literal["selected", "ambiguous", "none"]
    package: Optional[LabPackage] = None
    matches: List[LabPackage] = []  # the tied candidates when ambiguous (lets the caller narrow the list)


class SlotAvailability(BaseModel):
    model_config = ConfigDict(frozen=True)
    package_id: str
    date: Date
    slots: List[str]


class BookingResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: Literal["booking_confirmed", "booking_failed", "booking_failed_needs_human_intervention"]
    booking_id: Optional[str] = None
    ticket_id: Optional[str] = None
    package_name: Optional[str] = None
    slot: Optional[str] = None
    date: Optional[Date] = None
    message: str = ""
    retry_latency_s: float = 0.0  # total time spent in backoff sleeps (surfaced, not hidden)


class LabTools:
    def __init__(self, packages_path: str = "data/lab_packages.json", failure_rate: Optional[float] = None):
        try:
            with open(packages_path, "r", encoding="utf-8") as f:
                self.lab_packages: List[LabPackage] = [LabPackage(**p) for p in json.load(f)]
        except FileNotFoundError:
            logging.error(f"Lab packages data file not found at {packages_path}")
            self.lab_packages = []
        self.failure_rate = float(os.getenv("LAB_FAILURE_RATE", "0.15")) if failure_rate is None else failure_rate
        # Schedule backend state: (package_id, date, slot) already taken.
        self._booked: set[tuple[str, Date, str]] = set()

    def get_package(self, package_id: str) -> Optional[LabPackage]:
        return next((p for p in self.lab_packages if p.package_id == package_id), None)

    @staticmethod
    def is_generic_request(text: str) -> bool:
        """'book a blood test' style: asks for a lab test but names none we can match."""
        return any(w in GENERIC_REQUEST_WORDS for w in re.findall(r"[a-z0-9]+", text.lower()))

    @staticmethod
    def _score(pkg: LabPackage, text: str, qtokens: List[str]) -> int:
        q = text.lower()
        score = 0
        if pkg.package_id.lower() in q.replace(" ", "_") or pkg.package_id.lower() in q:
            score += 10
        if pkg.name.lower() in q:
            score += 10
        name_tokens = _tokens(pkg.name)
        score += 3 * sum(any(_same_word(t, n) for n in name_tokens) for t in set(qtokens))
        symptom_tokens = {w for sym in pkg.target_symptoms for w in _tokens(sym)}
        score += 2 * sum(1 for sym in pkg.target_symptoms if sym.lower() in q)
        score += sum(any(_same_word(t, w) for w in symptom_tokens) for t in set(qtokens))
        return score

    def _rank(self, text: str, pool: List[LabPackage]) -> List[LabPackage]:
        """Best-scoring packages only (ties kept). Empty when nothing distinctive matches."""
        qtokens = _tokens(text)
        scored = [(self._score(p, text, qtokens), p) for p in pool]
        top = max((sc for sc, _ in scored), default=0)
        if top <= 0:
            return []
        return [p for sc, p in sorted(scored, key=lambda x: (-x[0], x[1].package_id)) if sc == top]

    def search_packages(self, query: str, target_symptom: Optional[str] = None,
                        trace_id: Optional[str] = None) -> List[LabPackage]:
        """Ranked catalogue search. One result = unambiguous; several = a genuine tie the caller must resolve."""
        with span("tool:search_packages", trace_id or new_trace_id(), kind="tool", query=redact(query)) as s:
            text = f"{query} {target_symptom}" if target_symptom else query
            results = self._rank(text, self.lab_packages)
            s.set(n_results=len(results))
            return results

    def select_package(self, reply: str, candidates: List[LabPackage],
                       trace_id: Optional[str] = None) -> PackageSelection:
        """Resolve a short follow-up ('LP_007', 'the second one', 'female') against the packages we listed."""
        with span("tool:select_package", trace_id or new_trace_id(), kind="tool", reply=redact(reply),
                  n_candidates=len(candidates)) as s:
            r = reply.lower()
            by_id = [p for p in candidates if p.package_id.lower() in r]
            if len(by_id) == 1:
                s.set(status="selected", via="id")
                return PackageSelection(status="selected", package=by_id[0])
            idx: Optional[int] = None
            m = re.fullmatch(r"\s*(?:option|number|no\.?|#)?\s*([1-9])\s*[.)]?\s*", r)
            if m:
                idx = int(m.group(1)) - 1
            else:
                word = next((w for w in re.findall(r"[a-z0-9]+", r) if w in _ORDINALS), None)
                if word:
                    idx = _ORDINALS[word]
                elif re.search(r"\blast\b", r):
                    idx = len(candidates) - 1
            if idx is not None:
                if 0 <= idx < len(candidates):
                    s.set(status="selected", via="ordinal")
                    return PackageSelection(status="selected", package=candidates[idx])
                s.set(status="none")
                return PackageSelection(status="none")
            ranked = self._rank(reply, candidates)
            status = "selected" if len(ranked) == 1 else ("ambiguous" if ranked else "none")
            s.set(status=status, via="text")
            return PackageSelection(status=status, package=ranked[0] if len(ranked) == 1 else None,
                                    matches=ranked if status == "ambiguous" else [])

    def check_slots(self, package_id: str, preferred_date: Date, trace_id: Optional[str] = None) -> SlotAvailability:
        with span("tool:check_slots", trace_id or new_trace_id(), kind="tool",
                  package_id=package_id, date=str(preferred_date)) as s:
            pkg = self.get_package(package_id)
            if pkg is None:
                return SlotAvailability(package_id=package_id, date=preferred_date, slots=[])
            base = FASTING_SLOTS if pkg.fasting_required else REGULAR_SLOTS
            free = [x for x in base if (package_id, preferred_date, x) not in self._booked]
            s.set(n_slots=len(free))
            return SlotAvailability(package_id=package_id, date=preferred_date, slots=free)

    def book_test(self, package_id: str, member_id: str, slot: str, date: Date,
                  trace_id: Optional[str] = None, retries: int = 3, initial_delay: float = 0.5) -> BookingResult:
        """Book with exponential-backoff retry; on exhaustion return a human-handoff ticket."""
        trace_id = trace_id or new_trace_id()
        delay, slept = initial_delay, 0.0
        for attempt in range(1, retries + 1):
            with span("tool:book_test", trace_id, kind="tool", package_id=package_id, slot=slot,
                      date=str(date), attempt=attempt) as s:
                try:
                    if random.random() < self.failure_rate:  # simulated partner-API outage
                        raise RuntimeError("PartnerLabAPIConnectionRefused 500")
                    pkg = self.get_package(package_id)
                    if pkg is None:
                        return BookingResult(status="booking_failed", message="Invalid package_id.")
                    if (package_id, date, slot) in self._booked:
                        return BookingResult(status="booking_failed", message="That slot was just taken. Please pick another.")
                    self._booked.add((package_id, date, slot))
                    return BookingResult(status="booking_confirmed",
                                         booking_id=f"BOK_{member_id}_{random.randint(1000, 9999)}",
                                         package_name=pkg.name, slot=slot, date=date, retry_latency_s=slept)
                except RuntimeError as e:
                    s.set(error=str(e))
                    logging.warning(f"book_test attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(delay)
                slept += delay
                delay *= 2
        return BookingResult(
            status="booking_failed_needs_human_intervention",
            ticket_id=f"CARE_{random.randint(10000, 99999)}",
            message="We couldn't complete the booking right now. A care coordinator will call you back within 15 minutes.",
            retry_latency_s=slept)
