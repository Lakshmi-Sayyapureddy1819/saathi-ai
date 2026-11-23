"""Lab partner scheduling service: a small, real, separately deployed HTTP service that owns lab slots and bookings.

It implements the wire contract in app/tools/lab_backend.py (the Saathi app talks to it through HttpLabBackend):

  GET    /slots?package_id=LP_001&date=2026-12-01   -> 200 {"slots": [free slots]}
  POST   /bookings   header Idempotency-Key           -> 201 {"booking_ref", ...} | 409 slot taken | 422 invalid
  DELETE /bookings/{booking_ref}                      -> 204 (also when already cancelled) | 404 unknown
  GET    /bookings                                    -> 200 list (read-only admin view)
  GET    /health                                      -> 200 (no auth)

Guarantees: its own SQLite database (LAB_PARTNER_DB, default data/lab_partner.db); one confirmed booking per
(package, date, slot) enforced by a database unique index (so two concurrent requests cannot both win); idempotent
bookings (the same Idempotency-Key returns the same booking, never a second one); bearer-token auth; no booking in the
past or outside a package's slot window. Run it with:  python -m services.lab_partner
Environment: LAB_API_KEY (required, the bearer token the app sends), LAB_PARTNER_DB, LAB_PARTNER_PACKAGES
(catalogue with fasting flags, default data/lab_packages.json), LAB_PARTNER_PORT (default 8100).
"""
import hmac
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
from datetime import date as Date
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

FASTING_SLOTS = ["07:00 AM", "07:30 AM", "08:00 AM", "08:30 AM"]
REGULAR_SLOTS = ["09:00 AM", "09:30 AM", "10:00 AM", "10:30 AM", "11:00 AM"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
  booking_ref TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE, package_id TEXT NOT NULL,
  member_id TEXT NOT NULL, date TEXT NOT NULL, slot TEXT NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL,
  cancelled_at REAL);
CREATE UNIQUE INDEX IF NOT EXISTS ux_confirmed_slot ON bookings(package_id, date, slot) WHERE status = 'confirmed';
"""


class BookingRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    package_id: str = Field(min_length=1, max_length=40)
    member_id: str = Field(min_length=1, max_length=60)
    date: Date
    slot: str = Field(min_length=1, max_length=20)


class BookingOut(BaseModel):
    model_config = ConfigDict(frozen=True)
    booking_ref: str
    package_id: str
    member_id: str
    date: Date
    slot: str
    status: str


class SlotsOut(BaseModel):
    model_config = ConfigDict(frozen=True)
    package_id: str
    date: Date
    slots: List[str]


class Schedule:
    """The partner's data: package slot windows plus the bookings table."""

    def __init__(self, db_path: str, packages_path: str):
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            if db_path != ":memory:":
                self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(_SCHEMA)
            self._db.commit()
        with open(packages_path, encoding="utf-8") as f:
            self.fasting: Dict[str, bool] = {p["package_id"]: bool(p.get("fasting_required")) for p in json.load(f)}

    def base_slots(self, package_id: str) -> List[str]:
        return FASTING_SLOTS if self.fasting[package_id] else REGULAR_SLOTS

    def free_slots(self, package_id: str, day: Date) -> List[str]:
        with self._lock:
            taken = {r["slot"] for r in self._db.execute(
                "SELECT slot FROM bookings WHERE package_id=? AND date=? AND status='confirmed'",
                (package_id, day.isoformat()))}
        return [s for s in self.base_slots(package_id) if s not in taken]

    def book(self, req: BookingRequest, idempotency_key: str) -> "tuple[BookingOut, bool]":
        """(booking, created). Replays of the same key return the original booking. Raises KeyError (unknown package),
        ValueError (invalid), LookupError (slot taken)."""
        if req.package_id not in self.fasting:
            raise KeyError(req.package_id)
        if req.date < Date.today():
            raise ValueError("date is in the past")
        if req.slot not in self.base_slots(req.package_id):
            raise ValueError(f"slot {req.slot!r} is not offered for {req.package_id}")
        with self._lock:
            row = self._db.execute("SELECT * FROM bookings WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if row is not None:
                same = (row["package_id"], row["member_id"], row["date"], row["slot"]) == (
                    req.package_id, req.member_id, req.date.isoformat(), req.slot)
                if not same:
                    raise ValueError("Idempotency-Key was already used for a different request")
                return self._out(row), False
            ref = f"LP-{req.date:%y%m%d}-{secrets.token_hex(3).upper()}"
            try:
                self._db.execute("INSERT INTO bookings VALUES (?,?,?,?,?,?,?,?,NULL)",
                                 (ref, idempotency_key, req.package_id, req.member_id, req.date.isoformat(), req.slot,
                                  "confirmed", time.time()))
                self._db.commit()
            except sqlite3.IntegrityError as e:
                self._db.rollback()
                if "ux_confirmed_slot" in str(e) or "bookings.package_id" in str(e):
                    raise LookupError("slot taken") from e
                raise
            return self._out(self._db.execute("SELECT * FROM bookings WHERE booking_ref=?", (ref,)).fetchone()), True

    def cancel(self, ref: str) -> bool:
        with self._lock:
            row = self._db.execute("SELECT status FROM bookings WHERE booking_ref=?", (ref,)).fetchone()
            if row is None:
                return False
            if row["status"] == "confirmed":
                self._db.execute("UPDATE bookings SET status='cancelled', cancelled_at=? WHERE booking_ref=?",
                                 (time.time(), ref))
                self._db.commit()
            return True

    def all(self, limit: int = 200) -> List[BookingOut]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM bookings ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._out(r) for r in rows]

    @staticmethod
    def _out(r: sqlite3.Row) -> BookingOut:
        return BookingOut(booking_ref=r["booking_ref"], package_id=r["package_id"], member_id=r["member_id"],
                          date=Date.fromisoformat(r["date"]), slot=r["slot"], status=r["status"])


def create_app(api_key: Optional[str] = None, db_path: Optional[str] = None,
               packages_path: Optional[str] = None) -> FastAPI:
    key = api_key if api_key is not None else os.getenv("LAB_API_KEY", "")
    if not key:
        raise RuntimeError("LAB_API_KEY is required: it is the bearer token the Saathi app sends to this service.")
    schedule = Schedule(db_path or os.getenv("LAB_PARTNER_DB", "data/lab_partner.db"),
                        packages_path or os.getenv("LAB_PARTNER_PACKAGES", "data/lab_packages.json"))
    app = FastAPI(title="Lab partner scheduling service", version="1.0")

    def auth(authorization: Optional[str] = Header(default=None)) -> None:
        got = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else ""
        if not hmac.compare_digest(key, got):
            raise HTTPException(401, "invalid or missing bearer token")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/slots", response_model=SlotsOut, dependencies=[Depends(auth)])
    def slots(package_id: str = Query(min_length=1), date: Date = Query()) -> SlotsOut:
        if package_id not in schedule.fasting:
            raise HTTPException(404, "unknown package")
        free = [] if date < Date.today() else schedule.free_slots(package_id, date)
        return SlotsOut(package_id=package_id, date=date, slots=free)

    @app.post("/bookings", response_model=BookingOut, status_code=201, dependencies=[Depends(auth)])
    def book(req: BookingRequest, response: Response,
             idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key")) -> BookingOut:
        if not idempotency_key or len(idempotency_key) > 200:
            raise HTTPException(422, "Idempotency-Key header is required")
        try:
            out, created = schedule.book(req, idempotency_key)
        except KeyError:
            raise HTTPException(404, "unknown package")
        except ValueError as e:
            raise HTTPException(422, str(e))
        except LookupError:
            raise HTTPException(409, "slot is already booked")
        logging.info("booking %s %s %s %s (%s)", out.booking_ref, out.package_id, out.date, out.slot,
                     "created" if created else "replayed")
        response.status_code = 201 if created else 200
        return out

    @app.delete("/bookings/{booking_ref}", status_code=204, dependencies=[Depends(auth)])
    def cancel(booking_ref: str) -> Response:
        if not schedule.cancel(booking_ref):
            raise HTTPException(404, "unknown booking")
        return Response(status_code=204)

    @app.get("/bookings", response_model=List[BookingOut], dependencies=[Depends(auth)])
    def list_bookings() -> List[BookingOut]:
        return schedule.all()

    return app
