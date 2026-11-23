"""Partner-lab scheduling backends behind one interface.

`LabTools` (catalogue search, slot choice, booking rules, retries, human handoff) is backend-agnostic. Two backends:

- SimulatedLabBackend: in-process, for development and tests. Can inject random outages (chaos tests). NEVER used when
  APP_ENV=production unless ALLOW_SIMULATORS=1 is set explicitly (see app/config.py).
- HttpLabBackend: a real partner over HTTPS with timeouts, an idempotency key on every booking (so a retry after a
  timeout cannot double-book) and typed errors. The wire contract is below; map it to your partner's actual API by
  editing `_slots_request` / `_book_request` / `_cancel_request` only.

Wire contract (JSON over HTTPS, `Authorization: Bearer $LAB_API_KEY`):
  GET    {LAB_API_URL}/slots?package_id=LP_001&date=2026-12-01   -> 200 {"slots": ["09:00 AM", ...]}  (FREE slots)
  POST   {LAB_API_URL}/bookings   header Idempotency-Key: <stable key>
         body {"package_id","member_id","date","slot"}           -> 201 {"booking_ref": "..."} | 409 slot taken | 5xx
  DELETE {LAB_API_URL}/bookings/{booking_ref}                    -> 204 | 404
"""
import os
import random
from datetime import date as Date
from typing import List, Optional, Protocol

import requests
from pydantic import BaseModel, ConfigDict


class SlotTaken(Exception):
    """The partner says this slot is no longer free (a conflict, not an outage: do not retry it)."""


class PartnerUnavailable(RuntimeError):
    """Timeout, connection error or 5xx from the partner: transient, safe to retry with the same idempotency key."""


class PartnerBooking(BaseModel):
    model_config = ConfigDict(frozen=True)
    booking_ref: str


class LabBackend(Protocol):
    name: str

    def free_slots(self, package_id: str, day: Date, base_slots: List[str]) -> Optional[List[str]]:
        """Free slots according to the partner, or None if the partner does not report availability."""

    def reserve(self, *, package_id: str, member_id: str, day: Date, slot: str, idempotency_key: str) -> PartnerBooking:
        """Reserve the slot. Raises SlotTaken (conflict) or PartnerUnavailable (transient)."""

    def release(self, booking_ref: str) -> None:
        """Cancel at the partner. Best effort; raises PartnerUnavailable on a transient failure."""


class SimulatedLabBackend:
    name = "simulator"

    def __init__(self, failure_rate: float = 0.0):
        self.failure_rate = failure_rate

    def free_slots(self, package_id: str, day: Date, base_slots: List[str]) -> Optional[List[str]]:
        return None  # LabTools' own schedule state is the source of truth in simulation

    def reserve(self, *, package_id: str, member_id: str, day: Date, slot: str, idempotency_key: str) -> PartnerBooking:
        if random.random() < self.failure_rate:  # simulated partner-API outage (chaos tests only)
            raise PartnerUnavailable("PartnerLabAPIConnectionRefused 500")
        return PartnerBooking(booking_ref=f"SIM-{random.randint(100000, 999999)}")

    def release(self, booking_ref: str) -> None:
        return None


class HttpLabBackend:
    name = "http"

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, timeout_s: Optional[float] = None,
                 session: Optional[requests.Session] = None):
        self.base_url = (base_url or os.getenv("LAB_API_URL", "")).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("LAB_API_KEY", "")
        self.timeout_s = timeout_s or float(os.getenv("LAB_API_TIMEOUT_SECONDS", "8"))
        self.http = session or requests.Session()
        if not self.base_url:
            raise ValueError("LAB_API_URL is required for the http lab backend.")

    def _headers(self, extra: Optional[dict] = None) -> dict:
        h = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        h.update(extra or {})
        return h

    def _call(self, method: str, path: str, **kw) -> requests.Response:
        try:
            return self.http.request(method, f"{self.base_url}{path}", timeout=self.timeout_s, **kw)
        except (requests.Timeout, requests.ConnectionError) as e:
            raise PartnerUnavailable(f"{type(e).__name__} calling partner lab API") from e

    def free_slots(self, package_id: str, day: Date, base_slots: List[str]) -> Optional[List[str]]:
        r = self._call("GET", "/slots", params={"package_id": package_id, "date": day.isoformat()}, headers=self._headers())
        if r.status_code >= 500:
            raise PartnerUnavailable(f"partner slots returned {r.status_code}")
        if r.status_code != 200:
            return []
        return [s for s in r.json().get("slots", []) if isinstance(s, str)]

    def reserve(self, *, package_id: str, member_id: str, day: Date, slot: str, idempotency_key: str) -> PartnerBooking:
        r = self._call("POST", "/bookings", headers=self._headers({"Idempotency-Key": idempotency_key}),
                       json={"package_id": package_id, "member_id": member_id, "date": day.isoformat(), "slot": slot})
        if r.status_code == 409:
            raise SlotTaken(slot)
        if r.status_code >= 500 or r.status_code == 429:
            raise PartnerUnavailable(f"partner booking returned {r.status_code}")
        if r.status_code not in (200, 201):
            raise PartnerUnavailable(f"partner booking rejected the request ({r.status_code})")
        ref = r.json().get("booking_ref")
        if not ref:
            raise PartnerUnavailable("partner booking response had no booking_ref")
        return PartnerBooking(booking_ref=str(ref))

    def release(self, booking_ref: str) -> None:
        r = self._call("DELETE", f"/bookings/{booking_ref}", headers=self._headers())
        if r.status_code >= 500:
            raise PartnerUnavailable(f"partner cancel returned {r.status_code}")


def make_backend(failure_rate: float = 0.0) -> LabBackend:
    from app.config import get_settings
    s = get_settings()
    if s.lab_backend == "http":
        return HttpLabBackend()
    if not s.allow_simulators:
        raise RuntimeError("The simulated lab backend is disabled (production). Set LAB_BACKEND=http and LAB_API_URL.")
    return SimulatedLabBackend(failure_rate)
