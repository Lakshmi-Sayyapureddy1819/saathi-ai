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
    "ek": 1, "teen": 3, "char": 4, "paanch": 5, "chhe": 6, "saat": 7, "aath": 8, "nau": 9,
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
    # ASR often drops the colon: "9 30" means 9:30, never 9:00 (the minutes must not be silently ignored).
    def _spaced(m: "re.Match[str]") -> str:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23:
            out.append((h, mi, m.group(3)))
            return " "
        return m.group(0)
    t = re.sub(r"\b(\d{1,2})\s+([0-5]\d)\b(?:\s*(am|pm)\b)?", _spaced, t)
    # Digits: 8, 8:30, 08:30 am, 830 am
    for m in re.finditer(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", t):
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if 0 <= h <= 23 and 0 <= mi <= 59 and (m.group(2) or ap):
            out.append((h, mi, ap))
        elif 1 <= h <= 12 and not m.group(2):
            out.append((h, 0, ap))
    # Words: "seven thirty", "half past seven", "saadhe saat"
    words = re.findall(r"[a-z]+", t)
    out.extend(_word_times(words)[0])
    return out


def _num(words: List[str], i: int) -> Optional[int]:
    return _UNITS.get(words[i]) if 0 <= i < len(words) else None


def _minutes_at(words: List[str], i: int) -> tuple[Optional[int], int]:
    """Parse a minute expression at i ('quarter', 'fifteen', 'twenty five'). Returns (minutes, next_index)."""
    if i < len(words) and words[i] == "quarter":
        return 15, i + 1
    v = _num(words, i)
    if v is None or v < 13:
        return None, i
    nxt = _num(words, i + 1)
    if v in (20, 30, 40, 50) and nxt is not None and 1 <= nxt <= 9:
        return v + nxt, i + 2
    return v, i + 1


def _word_times(words: List[str]) -> tuple[List[tuple[int, int, Optional[str]]], bool]:
    """Parse spoken times. Returns (candidates, unparsed_minute_words).

    Handles: 'seven thirty', 'half past seven', 'fifteen past nine' (9:15), 'quarter to eight' (7:45),
    'twenty to ten', 'saadhe saat'. Any minute word (>12) we could not attach to an hour sets the flag, so the
    caller must NOT fall back to the bare hour (that is how 'fifteen past nine' could become 9:00)."""
    out: List[tuple[int, int, Optional[str]]] = []
    consumed: set[int] = set()
    ap_after = lambda j: next((x for x in words[j:j + 3] if x in ("am", "pm")), None)  # noqa: E731
    for i, w in enumerate(words):
        # "<minutes> past|to <hour>"
        mins, j = _minutes_at(words, i)
        if mins is not None and j < len(words) and words[j] in ("past", "to"):
            h = _num(words, j + 1)
            if h is not None and 1 <= h <= 12:
                if words[j] == "past":
                    out.append((h, mins, ap_after(j + 2)))
                else:
                    out.append(((h - 2) % 12 + 1, 60 - mins, ap_after(j + 2)))
                consumed.update(range(i, j + 2))
                continue
        # "half past <hour>" / "saadhe <hour>"
        if w in _HALF:
            k = i + 2 if i + 1 < len(words) and words[i + 1] == "past" else i + 1
            h = _num(words, k)
            if h is not None and 1 <= h <= 12:
                out.append((h, 30, ap_after(k + 1)))
                consumed.update(range(i, k + 1))
    for i, w in enumerate(words):
        if i in consumed:
            continue
        h = _num(words, i)
        if h is None or not 1 <= h <= 12:
            continue
        mins, j = _minutes_at(words, i + 1)
        if mins is not None and mins % 5 == 0 and mins >= 15 or (mins is not None and mins > 20):
            out.append((h, mins, ap_after(j)))
            consumed.update(range(i, j))
        else:
            nxt = words[i + 1] if i + 1 < len(words) else None
            ap = ap_after(i + 1)
            if ap or nxt in (None, "baje", "bje", "o", "oclock", "please", "sharp"):
                out.append((h, 0, ap))
                consumed.add(i)
    unparsed = any(i not in consumed and (_num(words, i) or 0) > 12 for i in range(len(words)))
    return out, unparsed


def match_slot(text: str, slots: List[str]) -> SlotMatch:
    """Match free text (or ASR transcript) to exactly one slot, or say it is ambiguous/unknown."""
    cands = _extract_times(text)
    if _word_times(re.findall(r"[a-z]+", text.lower()))[1]:
        return SlotMatch(status="ambiguous")  # a spoken minute we couldn't place: ask again, never guess the hour
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


_CONFIRM = re.compile(r"\b(ye+s+|yep|yea+h*|yup|confirm(?:ed)?|proceed|go\s+ahead|haan|haa+n?|han|hanji|ha|"
                      r"ji\s+haan|haan\s+ji|sahi\s+hai|theek\s+hai|thik\s+hai|book\s+it|kar\s*do|kardo)\b", re.I)
# A bare "ok"/"sure"/"ji" is only a yes when it is the whole message ("okay maybe" must not book anything).
_CONFIRM_ONLY = re.compile(r"^\s*(ok+|okay|sure|done|ji|book\s+kar\s*do)\s*[.!]*\s*$", re.I)
_NEGATE = re.compile(r"\b(no|nahi|nahin|don'?t|do\s+not|cancel|stop|wait|not\s+yet|ruko|mat|rehne\s+do|rahne\s+do|"
                     r"chhodo|chodo)\b", re.I)


def is_confirmation(text: str) -> bool:
    """Explicit yes only. Whole-word match; any negation vetoes (so 'ok' inside 'book' never counts)."""
    return (bool(_CONFIRM.search(text)) or bool(_CONFIRM_ONLY.match(text))) and not _NEGATE.search(text)


_MONTHS = {"jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5,
           "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
           "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12}
_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
_MON = "|".join(sorted(_MONTHS, key=len, reverse=True))
_DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:of\s+)?({_MON})\b", re.I)      # 25 november, 25th of nov
_MONTH_DAY = re.compile(rf"\b({_MON})\s*(\d{{1,2}})(?:st|nd|rd|th)?\b", re.I)               # november 25, nov 25th
_WEEKDAY = re.compile(r"\b(?:next\s+|on\s+|this\s+)?(" + "|".join(_WEEKDAYS) + r")\b", re.I)
# Any date expression resolve_date understands (also used by the router to recognise a date mid-booking).
DATE_WORD = re.compile(r"\b(today|aaj|tomorrow|kal|parso|day\s+after\s+tomorrow)\b|" + _DAY_MONTH.pattern + "|" +
                       _MONTH_DAY.pattern + "|" + _WEEKDAY.pattern, re.I)


def explicit_date(text: str, today: Optional[date] = None) -> Optional[date]:
    """An explicit calendar date ('25 November', 'Nov 25th') or weekday ('Friday', 'next Monday') in `text`, else None.
    A month-day that has already passed this year means next year. A weekday is its next occurrence after today."""
    today = today or date.today()
    m = _DAY_MONTH.search(text)
    day, mon = (int(m.group(1)), _MONTHS[m.group(2).lower()]) if m else (None, None)
    if not m:
        m = _MONTH_DAY.search(text)
        if m:
            day, mon = int(m.group(2)), _MONTHS[m.group(1).lower()]
    if m:
        for year in (today.year, today.year + 1):
            try:
                d = date(year, mon, day)
            except ValueError:
                return None            # e.g. 31 November: do not guess
            if d >= today:
                return d
        return None
    w = _WEEKDAY.search(text)
    if w:
        ahead = (_WEEKDAYS[w.group(1).lower()] - today.weekday()) % 7 or 7
        return today + timedelta(days=ahead)
    return None


def resolve_date(text: str, today: Optional[date] = None) -> date:
    """Resolve 'today'/'tomorrow'/'kal'/'parso', an explicit date ('25 November') or a weekday, relative to the real current
    date. Default when nothing is stated: tomorrow."""
    today = today or date.today()
    t = text.lower()
    if re.search(r"\b(today|aaj)\b", t):
        return today
    if re.search(r"\b(day after tomorrow|parso)\b", t):
        return today + timedelta(days=2)
    return explicit_date(text, today) or today + timedelta(days=1)


def has_time(text: str) -> bool:
    """True if the text contains any time-like expression (used for routing mid-booking turns)."""
    return bool(_extract_times(text))
