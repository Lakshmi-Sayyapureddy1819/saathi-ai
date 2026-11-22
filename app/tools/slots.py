"""Deterministic time-slot, date and confirmation parsing (shared by chat and voice).

Number words are converted to integers, so "fifteen" (15) can never match "fifty" (50).
"""
import re
from datetime import date, timedelta
from typing import List, Optional, Literal

from pydantic import BaseModel, ConfigDict

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50,
    # Hinglish
    "ek": 1, "do": 2, "teen": 3, "char": 4, "paanch": 5, "chhe": 6, "saat": 7, "aath": 8, "nau": 9,
    "das": 10, "gyarah": 11, "barah": 12, "pandrah": 15, "bees": 20, "tees": 30, "chalis": 40, "pachaas": 50,
}
_HALF = {"half", "saadhe", "sadhe"}


class SlotMatch(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: Literal["matched", "none", "ambiguous"]
    slot: Optional[str] = None
    heard: Optional[str] = None  # human-readable read-back of what we understood


def _slot_to_hm(slot: str) -> tuple[int, int]:
    m = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM)", slot.strip(), re.IGNORECASE)
    if not m:
        raise ValueError(f"Bad slot format: {slot}")
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3).upper()
    h = h % 12 + (12 if ap == "PM" else 0)
    return h, mi


def _extract_times(text: str) -> List[tuple[int, int, Optional[str]]]:
    """Return (hour, minute, 'am'|'pm'|None) candidates found in text."""
    t = text.lower()
    out: List[tuple[int, int, Optional[str]]] = []
    # Digits: 8, 8:30, 08:30 am, 830 am
    for m in re.finditer(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", t):
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if 0 <= h <= 23 and 0 <= mi <= 59 and (m.group(2) or ap):
            out.append((h, mi, ap))
        elif 1 <= h <= 12 and not m.group(2):
            out.append((h, 0, ap))
    # Words: "seven thirty", "half past seven", "saadhe saat"
    words = re.findall(r"[a-z]+", t)
    for i, w in enumerate(words):
        if w in _UNITS and _UNITS[w] <= 12:
            h = _UNITS[w]
            prev_half = i > 0 and words[i - 1] in _HALF | {"past"} and any(x in _HALF for x in words[max(0, i - 2):i])
            nxt = words[i + 1] if i + 1 < len(words) else None
            mi = 0
            if prev_half:
                mi = 30
            elif nxt in _UNITS and _UNITS[nxt] >= 15 and _UNITS[nxt] % 5 == 0 and nxt not in ("do",):
                mi = _UNITS[nxt]
                if i + 2 < len(words) and words[i + 2] in _UNITS and _UNITS[words[i + 2]] < 10 and mi >= 20:
                    mi += _UNITS[words[i + 2]]
            ap = next((x for x in words[i + 1:i + 4] if x in ("am", "pm")), None)
            if prev_half or mi or ap or (nxt in (None, "baje", "o", "oclock", "please", "bje")):
                out.append((h, mi, ap))
    return out


def match_slot(text: str, slots: List[str]) -> SlotMatch:
    """Match free text (or ASR transcript) to exactly one slot, or say it is ambiguous/unknown."""
    cands = _extract_times(text)
    if not cands:
        return SlotMatch(status="none")
    hits: set[str] = set()
    for h, mi, ap in cands:
        for slot in slots:
            sh, sm = _slot_to_hm(slot)
            if sm != mi:
                continue
            h12 = sh % 12 or 12
            if ap is None and h in (h12, sh) or (ap == "am" and sh < 12 and h in (h12, sh)) or (
                    ap == "pm" and sh >= 12 and h in (h12, sh)):
                hits.add(slot)
    if len(hits) == 1:
        s = next(iter(hits))
        return SlotMatch(status="matched", slot=s, heard=s)
    if len(hits) > 1:
        return SlotMatch(status="ambiguous")
    return SlotMatch(status="none")


_CONFIRM = re.compile(r"\b(yes|yep|yeah|confirm(?:ed)?|proceed|go\s+ahead|haan|han|ha|sahi\s+hai|theek\s+hai|book\s+it)\b", re.I)
_NEGATE = re.compile(r"\b(no|nahi|nahin|don'?t|do\s+not|cancel|stop|wait|not\s+yet)\b", re.I)


def is_confirmation(text: str) -> bool:
    """Explicit yes only. Whole-word match; any negation vetoes (so 'ok' inside 'book' never counts)."""
    return bool(_CONFIRM.search(text)) and not _NEGATE.search(text)


def resolve_date(text: str, today: Optional[date] = None) -> date:
    """Resolve 'today'/'tomorrow'/'kal'/'parso' relative to the real current date. Default: tomorrow."""
    today = today or date.today()
    t = text.lower()
    if re.search(r"\b(today|aaj)\b", t):
        return today
    if re.search(r"\b(day after tomorrow|parso)\b", t):
        return today + timedelta(days=2)
    return today + timedelta(days=1)


def has_time(text: str) -> bool:
    """True if the text contains any time-like expression (used for routing mid-booking turns)."""
    return bool(_extract_times(text))
