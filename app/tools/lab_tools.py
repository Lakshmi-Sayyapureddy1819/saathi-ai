"""Lab catalogue + schedule backend tools. All inputs/outputs are typed (Pydantic V2)."""
import json
import logging
import os
import random
import time
from datetime import date as Date
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict

from app.observability.tracer import span, new_trace_id

FASTING_SLOTS = ["07:00 AM", "07:30 AM", "08:00 AM", "08:30 AM"]
REGULAR_SLOTS = ["09:00 AM", "09:30 AM", "10:00 AM", "10:30 AM", "11:00 AM"]
STOPWORDS = {"book", "test", "need", "want", "please", "lab", "package", "with", "that", "this", "have"}


class LabPackage(BaseModel):
    model_config = ConfigDict(frozen=True)
    package_id: str
    name: str
    test_count: int = 0
    fasting_required: bool = False
    fasting_hours: int = 0
    price_inr: int = 0
    target_symptoms: List[str] = []


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

    def search_packages(self, query: str, target_symptom: Optional[str] = None,
                        trace_id: Optional[str] = None) -> List[LabPackage]:
        with span("tool:search_packages", trace_id or new_trace_id(), kind="tool", query=query) as s:
            q = query.lower()
            words = [w for w in q.replace("_", " ").split() if len(w) > 3 and w not in STOPWORDS]
            results: List[LabPackage] = []
            for pkg in self.lab_packages:
                name = pkg.name.lower()
                name_match = pkg.package_id.lower() in q or name in q or any(w in name for w in words)
                if target_symptom:
                    sym = any(target_symptom.lower() in x.lower() for x in pkg.target_symptoms)
                else:
                    sym = any(x.lower() in q for x in pkg.target_symptoms)
                if name_match or sym:
                    results.append(pkg)
            s.set(n_results=len(results))
            return results

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
