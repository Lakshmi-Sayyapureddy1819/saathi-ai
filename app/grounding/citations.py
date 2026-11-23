"""Deterministic citation verification. The LLM is asked to cite sources in square brackets ([PROG_Y_001] in Mode A,
[bookings] in Mode B), but the model is not trusted to cite correctly: code checks every bracketed id against the
context the model was actually given.

- cited id that IS in the context      -> kept, becomes a Citation shown to the member
- cited id that is NOT in the context  -> fabricated: stripped from the text, recorded on the trace, never shown
- sources used but none cited inline   -> shown as 'consulted' (cited=False) so the member still sees the evidence
"""
import re
from typing import Dict, List

from pydantic import BaseModel, ConfigDict

from app.workflow.state import Citation

# What a source id looks like: library doc ids, lab/booking ids, or a Mode B fact group.
_ID_SHAPE = re.compile(r"^(?:[A-Z]{2,6}_[A-Za-z0-9_]+|member_profile|bookings|lab_schedule|lab_catalogue)$")
_CITE = re.compile(r"\s?\[([A-Za-z][A-Za-z0-9_]{2,40})\]")

FACT_LABELS: Dict[str, str] = {"member_profile": "Your profile", "bookings": "Your bookings",
                               "lab_schedule": "Lab schedule", "lab_catalogue": "Lab package catalogue"}


class CitationCheck(BaseModel):
    model_config = ConfigDict(frozen=True)
    text: str                       # the answer with fabricated citations removed
    citations: List[Citation]
    fabricated: List[str]
    uncited: bool                   # sources were available but the answer cited none


def _kind(source_id: str) -> str:
    return "backend_fact" if source_id in FACT_LABELS else "document"


def verify_citations(text: str, sources: List[str], titles: Dict[str, str]) -> CitationCheck:
    allowed = set(sources)
    cited: List[str] = []
    fabricated: List[str] = []

    def _sub(m: "re.Match[str]") -> str:
        sid = m.group(1)
        if sid in allowed:
            if sid not in cited:
                cited.append(sid)
            return m.group(0)
        if _ID_SHAPE.match(sid):          # looks like a source id but was never retrieved: invented
            if sid not in fabricated:
                fabricated.append(sid)
            return ""
        return m.group(0)                 # ordinary bracketed text, leave alone

    clean = _CITE.sub(_sub, text)

    def _mk(sid: str, was_cited: bool) -> Citation:
        return Citation(source_id=sid, title=titles.get(sid) or FACT_LABELS.get(sid, sid), kind=_kind(sid),  # type: ignore[arg-type]
                        cited=was_cited)
    citations = [_mk(s, True) for s in cited]
    uncited = bool(sources) and not cited
    if uncited:
        citations = [_mk(s, False) for s in sources]
    return CitationCheck(text=clean, citations=citations, fabricated=fabricated, uncited=uncited)
