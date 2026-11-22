"""Grounding: builds typed context for the coach prompt. It does NOT call the LLM.

Mode A (retrieval): rank program docs by token overlap and return the top-k with source ids.
Mode B (facts + tools): inject member facts plus live backend data (schedule, lab catalogue)
as structured facts with negative constraints.
"""
import json
import logging
import re
from datetime import date, timedelta
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.observability.tracer import span, new_trace_id
from app.tools.lab_tools import LabTools
from app.workflow.state import UserSessionState

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {"what", "how", "the", "and", "for", "with", "this", "that", "about", "tell", "does", "have", "are",
         "mujhe", "kya", "hai", "ke", "ki", "ka", "kaise", "karte", "karo", "aur", "liye", "hain", "fayde", "ko", "se"}


# Hinglish/Hindi -> English retrieval vocabulary. The program library is written in English with a few Hindi
# titles, so a Hindi query word has no lexical overlap with the right document ("garmi" vs "cooling"/"summer").
# Small, explicit and deterministic; extend it as new query vocabulary shows up in the traces.
HINGLISH_EXPANSION = {
    "garmi": ["heat", "hot", "cooling", "summer"], "garmiyon": ["heat", "cooling", "summer"],
    "thakan": ["fatigue", "tired", "exhaustion"], "thakaan": ["fatigue", "exhaustion"],
    "tanav": ["stress", "relax"], "chinta": ["anxiety", "stress"], "neend": ["sleep", "insomnia"],
    "sardi": ["cold", "cough"], "pet": ["stomach", "digestion"], "vajan": ["weight"], "motapa": ["weight"],
    "paani": ["water", "hydration"], "pani": ["water", "hydration"], "aaram": ["relax", "relaxation"],
    "sehat": ["health", "healthy"], "khana": ["food", "diet"], "aahar": ["food", "diet"],
    "dard": ["pain"], "kamar": ["back", "pain"], "ghabrahat": ["anxiety"],
}


def _stem(token: str) -> str:
    """Cheap stemmer: tokens sharing a 5-char prefix are the same word (relax~relaxation, digest~digestion)."""
    return token[:5] if len(token) >= 5 else token


MIN_BODY_HITS = 2  # distinct query words a document body must contain when no title/tag word matches


class GroundingContext(BaseModel):
    model_config = ConfigDict(frozen=True)
    mode: str
    text: str
    sources: List[str] = []
    empty: bool = False


class GroundingEngine:
    def __init__(self, programs_path: str = "data/programs.json", lab_tools: Optional[LabTools] = None):
        try:
            with open(programs_path, "r", encoding="utf-8") as f:
                self.programs = json.load(f)
        except FileNotFoundError:
            logging.error(f"Programs data file not found at {programs_path}")
            self.programs = []
        self.lab_tools = lab_tools or LabTools()

    @staticmethod
    def _tokens(text: str) -> List[str]:
        return [t for t in _TOKEN.findall(text.lower()) if len(t) > 2 and t not in _STOP]

    def mode_a_retrieval(self, query: str, top_k: int = 2) -> GroundingContext:
        base = self._tokens(query)
        expanded = [e for t in base for e in HINGLISH_EXPANSION.get(t, [])]
        q = {_stem(t) for t in base} | {_stem(t) for t in expanded}
        scored = []
        for p in self.programs:
            title_tags = {_stem(t) for t in self._tokens(p["title"] + " " + " ".join(p.get("tags", [])))}
            body = {_stem(t) for t in self._tokens(p["content"])}
            title_hits, body_hits = len(q & title_tags), len(q & body)
            score = 3 * title_hits + body_hits  # title/tag hits weigh more
            # Off-topic guard: one stray body word ("weather", "match") is not evidence the document answers the
            # question. Need a title/tag match, or at least two distinct body words.
            if title_hits >= 1 or body_hits >= MIN_BODY_HITS:
                scored.append((score, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        if not scored:
            return GroundingContext(mode="mode_a_rag", text="(no matching documents)", empty=True)
        # Keep a runner-up only if it is nearly as relevant as the best hit: a weak match (e.g. sharing just
        # "fayde") is noise that dilutes the context and costs tokens.
        best = scored[0][0]
        hits = [p for sc, p in scored[:top_k] if sc >= 0.5 * best]
        text = "\n".join(f"[{h['doc_id']}] {h['title']}: {h['content']}" for h in hits)
        return GroundingContext(mode="mode_a_rag", text=text, sources=[h["doc_id"] for h in hits])

    def mode_b_facts(self, query: str, session: UserSessionState, trace_id: str) -> GroundingContext:
        m = session.member
        facts = {
            "member_name": m.name,
            "age": m.age,
            "enrolled_programs": m.enrolled_programs,
            "past_bookings": m.past_bookings,
            "health_goals": m.health_goals,
        }
        # Backend tools: schedule + lab catalogue, only when the question needs them.
        ql = query.lower()
        if re.search(r"\b(slot|schedule|available|timing|when)\b", ql):
            day = date.today() + timedelta(days=1)
            facts["schedule"] = {
                p.package_id: self.lab_tools.check_slots(p.package_id, day, trace_id).slots
                for p in self.lab_tools.lab_packages[:5]
            }
            facts["schedule_date"] = str(day)
        if re.search(r"\b(package|price|cost|lab|test|panel|checkup)\b", ql):
            facts["lab_catalogue"] = [
                {"id": p.package_id, "name": p.name, "price_inr": p.price_inr, "fasting": p.fasting_required}
                for p in self.lab_tools.lab_packages
            ]
        return GroundingContext(mode="mode_b_facts", text=json.dumps(facts, indent=2, default=str),
                                sources=["member_profile"] + (["lab_backend"] if len(facts) > 5 else []))


def get_grounding(query: str, session: UserSessionState, trace_id: Optional[str] = None,
                  engine: Optional[GroundingEngine] = None) -> GroundingContext:
    trace_id = trace_id or new_trace_id()
    engine = engine or GroundingEngine()
    mode = session.grounding_mode.mode
    with span(f"grounding:{mode}", trace_id, kind="tool", mode=mode, input=query) as s:
        if mode == "mode_a_rag":
            ctx = engine.mode_a_retrieval(query)
        elif mode == "mode_b_facts":
            ctx = engine.mode_b_facts(query, session, trace_id)
        else:
            raise ValueError(f"Invalid grounding mode: {mode}")
        s.set(n_sources=len(ctx.sources), empty=ctx.empty, context_chars=len(ctx.text))
        s.set_output({"sources": [str(x) for x in ctx.sources], "empty": ctx.empty})
        return ctx
