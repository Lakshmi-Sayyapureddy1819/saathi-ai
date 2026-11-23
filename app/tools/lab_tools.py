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
from app.persistence.store import Store, StoredBooking
from app.tools.lab_backend import LabBackend, PartnerUnavailable, SimulatedLabBackend, SlotTaken, make_backend

FASTING_SLOTS = ["07:00 AM", "07:30 AM", "08:00 AM", "08:30 AM"]
REGULAR_SLOTS = ["09:00 AM", "09:30 AM", "10:00 AM", "10:30 AM", "11:00 AM"]
# Words that carry no package identity: request verbs, filler, and category nouns shared by many packages
# ("panel", "profile", "checkup"...). Matching on them is what made "fever panel" look like 5 packages.
STOPWORDS = {
    "book", "booking", "test", "tests", "need", "want", "please", "lab", "package", "packages", "with", "that",
    "this", "have", "the", "and", "for", "can", "you", "get", "schedule", "appointment", "slot", "slots", "karo",
    "karwana", "chahiye", "hai", "mujhe", "panel", "profile", "checkup", "check", "screening", "screen", "health",
    "assessment", "blood", "wellness", "package", "one", "pls", "today", "tomorrow", "kal", "aaj",
    "khoon", "jaanch", "janch", "karwani", "karvana", "karvani", "subah", "baje",
}
# Category nouns that mean "some lab test" without naming one. Used only to decide whether to ASK which test the
# member wants; they never produce catalogue matches (that is what STOPWORDS prevents).
GENERIC_REQUEST_WORDS = {"test", "tests", "checkup", "panel", "profile", "package", "packages", "blood", "lab",
                         "screening", "health", "report", "reports", "khoon", "jaanch", "janch"}
# Everyday / Hinglish words people use for a test instead of its catalogue name ("sugar test", "bp check", "shaadi
# ke liye"). Matched as whole words with typo tolerance (see _same_word), so "shugar" still finds the diabetic profile.
_ALIAS_WORDS: dict[str, tuple[str, ...]] = {
    "LP_002": ("thyroid", "tsh", "goiter"),
    "LP_003": ("sugar", "diabetes", "diabetic", "glucose", "hba1c", "madhumeh"),
    "LP_004": ("heart", "cardiac", "bp", "cholesterol", "dil"),
    "LP_005": ("vitamin", "b12", "d3", "vit"),
    "LP_006": ("senior", "elderly", "budhape"),
    "LP_007": ("senior", "elderly", "budhape"),
    "LP_008": ("liver", "kidney", "kidneys", "jaundice", "urine", "peshab"),
    "LP_009": ("ladies", "women", "womens", "woman", "mahila"),
    "LP_010": ("gents", "mens"),
    "LP_011": ("fever", "bukhar", "malaria", "dengue", "typhoid", "infection"),
    "LP_012": ("wedding", "marriage", "shaadi", "shadi", "prewedding"),
}
_ALIAS_PHRASES: dict[str, tuple[str, ...]] = {
    "LP_001": ("full body", "whole body", "master health", "complete body", "sab kuch", "poore body", "poora body"),
    "LP_004": ("blood pressure",),
    "LP_005": ("vitamin d", "vitamin b"),
    "LP_012": ("pre wedding", "pre-wedding", "shaadi ke liye"),
}
# Words specific enough that, on their own, they mean "I want this lab test" (so no booking verb is needed to route).
_STRONG_WORDS = frozenset({
    "thyroid", "tsh", "diabetes", "diabetic", "sugar", "glucose", "hba1c", "cholesterol", "cardiac", "vitamin", "b12",
    "liver", "kidney", "jaundice", "dengue", "malaria", "typhoid", "wedding", "shaadi", "shadi", "bp",
})
_ORDINALS = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "fourth": 3, "4th": 3}


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2 and t not in STOPWORDS]


def _edit_distance(a: str, b: str) -> int:
    """Optimal-string-alignment distance: insert/delete/substitute/adjacent-swap each cost 1."""
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len(a)][len(b)]


def _same_word(a: str, b: str) -> bool:
    """Equal, same stem (>=5-char shared prefix: diabetes~diabetic), or a likely typo ('throid'~'thyroid').

    Typo tolerance: 1 edit for words of 5+ letters, 2 edits for 8+. Short words (male/female, <5 letters) are never
    fuzzy-matched, so 'male' still cannot match 'female'."""
    if a == b:
        return True
    if len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5]:
        return True
    shortest = min(len(a), len(b))
    if shortest < 5 or abs(len(a) - len(b)) > 2:
        return False
    return _edit_distance(a, b) <= (2 if shortest >= 8 else 1)


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


class BookingRecord(BaseModel):
    """A confirmed booking held by the schedule backend (what 'my bookings' and cancel operate on)."""
    model_config = ConfigDict(frozen=True)
    booking_id: str
    package_id: str
    package_name: str
    member_id: str
    date: Date
    slot: str
    partner_ref: Optional[str] = None  # the partner's own reference (needed to cancel there)


class CancelResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: Literal["cancelled", "not_found", "partner_unavailable"]
    booking: Optional[BookingRecord] = None


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
    def __init__(self, packages_path: str = "data/lab_packages.json", failure_rate: Optional[float] = None,
                 backend: Optional[LabBackend] = None, store: Optional[Store] = None):
        try:
            with open(packages_path, "r", encoding="utf-8") as f:
                self.lab_packages: List[LabPackage] = [LabPackage(**p) for p in json.load(f)]
        except FileNotFoundError:
            logging.error(f"Lab packages data file not found at {packages_path}")
            self.lab_packages = []
        rate = float(os.getenv("LAB_FAILURE_RATE", "0")) if failure_rate is None else failure_rate
        self.backend: LabBackend = backend or make_backend(rate)
        self.store = store  # optional durable copy of confirmed bookings; None = in-memory only (unit tests)
        # Schedule state: (package_id, date, slot) already taken, and confirmed bookings (hydrated from the store).
        self._booked: set[tuple[str, Date, str]] = set()
        self._bookings: dict[str, BookingRecord] = {}  # booking_id -> confirmed booking
        if self.store is not None:
            for b in self.store.bookings():
                rec = BookingRecord(booking_id=b.booking_id, package_id=b.package_id, package_name=b.package_name,
                                    member_id=b.member_id, date=Date.fromisoformat(b.date), slot=b.slot,
                                    partner_ref=b.partner_ref)
                self._bookings[rec.booking_id] = rec
                self._booked.add((rec.package_id, rec.date, rec.slot))

    @property
    def failure_rate(self) -> float:
        """Injected outage rate of the SIMULATED backend (chaos tests). Always 0.0 for a real backend."""
        return self.backend.failure_rate if isinstance(self.backend, SimulatedLabBackend) else 0.0

    @failure_rate.setter
    def failure_rate(self, value: float) -> None:
        if isinstance(self.backend, SimulatedLabBackend):
            self.backend.failure_rate = value

    def get_package(self, package_id: str) -> Optional[LabPackage]:
        return next((p for p in self.lab_packages if p.package_id == package_id), None)

    @staticmethod
    def is_generic_request(text: str) -> bool:
        """'book a blood test' style: asks for a lab test but names none we can match."""
        return any(w in GENERIC_REQUEST_WORDS or any(_same_word(w, g) for g in GENERIC_REQUEST_WORDS)
                   for w in re.findall(r"[a-z0-9]+", text.lower()))

    @staticmethod
    def mentions_test(text: str) -> bool:
        """True if the message names a specific test in everyday words ('thyroid', 'sugar', 'dengue', 'bp'), even
        misspelled and with no booking verb. Used by the router so a bare 'throid' still means lab booking."""
        words = re.findall(r"[a-z0-9]+", text.lower())
        return any(_same_word(w, s) for w in words for s in _STRONG_WORDS)

    @staticmethod
    def _score(pkg: LabPackage, text: str, qtokens: List[str]) -> int:
        q = text.lower()
        score = 0
        words = re.findall(r"[a-z0-9]+", q)
        score += 6 * sum(any(_same_word(w, a) for w in words) for a in _ALIAS_WORDS.get(pkg.package_id, ()))
        score += 8 * sum(1 for ph in _ALIAS_PHRASES.get(pkg.package_id, ()) if ph in q)
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
        with span("tool:search_packages", trace_id or new_trace_id(), kind="tool", query=redact(query),
                  input={"query": query, "target_symptom": target_symptom}) as s:
            text = f"{query} {target_symptom}" if target_symptom else query
            results = self._rank(text, self.lab_packages)
            s.set(n_results=len(results))
            s.set_output([{"package_id": r.package_id, "name": r.name} for r in results])
            return results

    def select_package(self, reply: str, candidates: List[LabPackage],
                       trace_id: Optional[str] = None) -> PackageSelection:
        """Resolve a short follow-up ('LP_007', 'the second one', 'female') against the packages we listed."""
        with span("tool:select_package", trace_id or new_trace_id(), kind="tool", reply=redact(reply),
                  n_candidates=len(candidates),
                  input={"reply": reply, "candidates": [c.package_id for c in candidates]}) as s:
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
                  package_id=package_id, date=str(preferred_date),
                  input={"package_id": package_id, "date": str(preferred_date)}) as s:
            pkg = self.get_package(package_id)
            if pkg is None:
                return SlotAvailability(package_id=package_id, date=preferred_date, slots=[])
            base = FASTING_SLOTS if pkg.fasting_required else REGULAR_SLOTS
            partner: Optional[List[str]] = None
            try:
                partner = self.backend.free_slots(package_id, preferred_date, base)
            except PartnerUnavailable as e:  # degrade to our own view; the booking call re-checks at the partner
                logging.warning("Partner slot lookup failed (%s); using local availability.", e)
                s.set(partner_error=str(e))
            pool = base if partner is None else partner  # the partner's list is authoritative when it reports one
            free = [x for x in pool if (package_id, preferred_date, x) not in self._booked]
            s.set(n_slots=len(free))
            s.set_output({"free_slots": free})
            return SlotAvailability(package_id=package_id, date=preferred_date, slots=free)

    def get_booking(self, booking_id: str, member_id: str) -> Optional[BookingRecord]:
        """The booking, only if it exists AND belongs to this member (other members' ids look like 'not found')."""
        rec = self._bookings.get(booking_id)
        return rec if rec is not None and rec.member_id == member_id else None

    def cancel_booking(self, booking_id: str, member_id: str, trace_id: Optional[str] = None) -> CancelResult:
        """Cancel a confirmed booking and free its slot. Deterministic; a member can only cancel their own."""
        with span("tool:cancel_booking", trace_id or new_trace_id(), kind="tool", booking_id=booking_id,
                  member_id=member_id) as s:
            rec = self.get_booking(booking_id, member_id)
            if rec is None:
                s.set(status="not_found")
                return CancelResult(status="not_found")
            if rec.partner_ref:
                try:
                    self.backend.release(rec.partner_ref)
                except PartnerUnavailable as e:  # never claim a cancellation the partner did not make
                    s.set(status="partner_unavailable", error=str(e))
                    return CancelResult(status="partner_unavailable", booking=rec)
            del self._bookings[booking_id]
            self._booked.discard((rec.package_id, rec.date, rec.slot))
            if self.store is not None:
                self.store.delete_booking(booking_id)
            s.set(status="cancelled")
            return CancelResult(status="cancelled", booking=rec)

    def book_test(self, package_id: str, member_id: str, slot: str, date: Date,
                  trace_id: Optional[str] = None, retries: int = 3, initial_delay: float = 0.5) -> BookingResult:
        """Book with exponential-backoff retry; on exhaustion return a human-handoff ticket."""
        trace_id = trace_id or new_trace_id()
        delay, slept = initial_delay, 0.0
        for attempt in range(1, retries + 1):
            with span("tool:book_test", trace_id, kind="tool", package_id=package_id, slot=slot,
                      date=str(date), attempt=attempt,
                      input={"package_id": package_id, "member_id": member_id, "slot": slot, "date": str(date)}) as s:
                try:
                    pkg = self.get_package(package_id)
                    if pkg is None:
                        return BookingResult(status="booking_failed", message="Invalid package_id.")
                    taken_msg = "I'm sorry, that slot was just taken. Could you please pick another time?"
                    if (package_id, date, slot) in self._booked:
                        s.set(error="SlotAlreadyBooked: slot is no longer available (stale record / conflict)")
                        return BookingResult(status="booking_failed", message=taken_msg)
                    # Stable across retries, so a retry after a timeout cannot create a second partner booking.
                    try:
                        partner = self.backend.reserve(package_id=package_id, member_id=member_id, day=date, slot=slot,
                                                       idempotency_key=f"{member_id}:{package_id}:{date}:{slot}")
                    except SlotTaken:
                        s.set(error="SlotAlreadyBooked: partner reports the slot is taken")
                        return BookingResult(status="booking_failed", message=taken_msg)
                    self._booked.add((package_id, date, slot))
                    booking_id = f"BOK_{member_id}_{random.randint(1000, 9999)}"
                    while booking_id in self._bookings:  # ids stay unique even if the random suffix repeats
                        booking_id = f"BOK_{member_id}_{random.randint(1000, 9999)}"
                    self._bookings[booking_id] = BookingRecord(booking_id=booking_id, package_id=package_id,
                                                               package_name=pkg.name, member_id=member_id,
                                                               date=date, slot=slot, partner_ref=partner.booking_ref)
                    if self.store is not None:
                        self.store.put_booking(StoredBooking(booking_id=booking_id, member_id=member_id,
                                                             package_id=package_id, package_name=pkg.name,
                                                             date=date.isoformat(), slot=slot,
                                                             partner_ref=partner.booking_ref))
                    return BookingResult(status="booking_confirmed", booking_id=booking_id,
                                         package_name=pkg.name, slot=slot, date=date, retry_latency_s=slept)
                except (RuntimeError, PartnerUnavailable) as e:
                    s.set(error=str(e))
                    logging.warning(f"book_test attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(delay)
                slept += delay
                delay *= 2
        return BookingResult(
            status="booking_failed_needs_human_intervention",
            ticket_id=f"CARE_{random.randint(10000, 99999)}",
            message="I'm sorry, we couldn't complete your booking right now. A care coordinator will call you back within 15 minutes.",
            retry_latency_s=slept)
