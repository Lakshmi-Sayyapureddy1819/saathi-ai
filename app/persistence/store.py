"""Durable storage (SQLite today, behind one small interface so Postgres is an implementation swap, not a rewrite).

What is persisted: members (seeded from data/members.json once), confirmed lab bookings, API sessions (so a restart does
not log members out or lose a booking in progress) and an audit trail of emergency alerts. Session tokens are stored only
as SHA-256 hashes. Message text is stored as the member typed it (it is the conversation); keep DATABASE_URL on an
encrypted volume and apply the retention in ARCHITECTURE.md.

DATABASE_URL: sqlite:///relative/or/absolute/path.db  |  sqlite:///:memory:   (anything else is rejected loudly)
"""
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict

_SCHEMA = """
CREATE TABLE IF NOT EXISTS members (member_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bookings (
  booking_id TEXT PRIMARY KEY, member_id TEXT NOT NULL, package_id TEXT NOT NULL, package_name TEXT NOT NULL,
  date TEXT NOT NULL, slot TEXT NOT NULL, partner_ref TEXT, created_at REAL NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS ux_booking_slot ON bookings(package_id, date, slot);
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, member_id TEXT NOT NULL, payload TEXT NOT NULL,
  updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, member_id TEXT NOT NULL, category TEXT NOT NULL, channel TEXT NOT NULL,
  status TEXT NOT NULL, detail TEXT NOT NULL, at REAL NOT NULL);
"""


class StoredBooking(BaseModel):
    model_config = ConfigDict(frozen=True)
    booking_id: str
    member_id: str
    package_id: str
    package_name: str
    date: str          # ISO date
    slot: str
    partner_ref: Optional[str] = None


class StoredSession(BaseModel):
    model_config = ConfigDict(frozen=True)
    session_id: str
    token_hash: str
    member_id: str
    payload: str       # JSON of the API record
    updated_at: float


class AlertRow(BaseModel):
    model_config = ConfigDict(frozen=True)
    member_id: str
    category: str
    channel: str
    status: str        # sent | failed | no_channel
    detail: str
    at: float


class Store:
    def __init__(self, database_url: str = "sqlite:///data/saathi.db"):
        if not database_url.startswith("sqlite:///"):
            raise ValueError(f"DATABASE_URL={database_url!r}: only sqlite:/// is implemented in this build. "
                             "Add a Postgres implementation of Store to support it.")
        path = database_url[len("sqlite:///"):]
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            if path != ":memory:":
                self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(_SCHEMA)
            self._db.commit()

    # ---- members
    def seed_members(self, members: List[dict]) -> None:
        with self._lock:
            if self._db.execute("SELECT COUNT(*) FROM members").fetchone()[0]:
                return
            self._db.executemany("INSERT INTO members VALUES (?, ?)",
                                 [(m["member_id"], json.dumps(m)) for m in members])
            self._db.commit()

    def members(self) -> Dict[str, dict]:
        with self._lock:
            rows = self._db.execute("SELECT member_id, payload FROM members ORDER BY member_id").fetchall()
        return {r["member_id"]: json.loads(r["payload"]) for r in rows}

    # ---- bookings
    def put_booking(self, b: StoredBooking) -> None:
        with self._lock:
            self._db.execute("INSERT INTO bookings VALUES (?,?,?,?,?,?,?,?)",
                             (b.booking_id, b.member_id, b.package_id, b.package_name, b.date, b.slot, b.partner_ref,
                              time.time()))
            self._db.commit()

    def delete_booking(self, booking_id: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM bookings WHERE booking_id = ?", (booking_id,))
            self._db.commit()

    def bookings(self) -> List[StoredBooking]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM bookings ORDER BY created_at").fetchall()
        return [StoredBooking(**{k: r[k] for k in StoredBooking.model_fields}) for r in rows]

    # ---- sessions
    def save_session(self, s: StoredSession) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?)",
                             (s.session_id, s.token_hash, s.member_id, s.payload, s.updated_at))
            self._db.commit()

    def load_session(self, session_id: str) -> Optional[StoredSession]:
        with self._lock:
            r = self._db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return StoredSession(**{k: r[k] for k in StoredSession.model_fields}) if r else None

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            self._db.commit()

    def purge_sessions(self, older_than_s: float) -> int:
        with self._lock:
            cur = self._db.execute("DELETE FROM sessions WHERE updated_at < ?", (time.time() - older_than_s,))
            self._db.commit()
            return cur.rowcount

    # ---- alerts (audit trail of the safety path)
    def record_alert(self, a: AlertRow) -> None:
        with self._lock:
            self._db.execute("INSERT INTO alerts (member_id, category, channel, status, detail, at) VALUES (?,?,?,?,?,?)",
                             (a.member_id, a.category, a.channel, a.status, a.detail, a.at))
            self._db.commit()

    def alerts(self, limit: int = 100) -> List[AlertRow]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [AlertRow(**{k: r[k] for k in AlertRow.model_fields}) for r in rows]


_store: Optional[Store] = None
_store_lock = threading.Lock()


def get_store() -> Store:
    """Process-wide store from DATABASE_URL; members are seeded from data/members.json on first use."""
    global _store
    with _store_lock:
        if _store is None:
            from app.config import get_settings
            _store = Store(get_settings().database_url)
            try:
                _store.seed_members(json.loads(Path("data/members.json").read_text(encoding="utf-8")))
            except FileNotFoundError:
                pass
        return _store


def reset_store() -> None:
    """Drop the process-wide store (tests)."""
    global _store
    with _store_lock:
        _store = None
