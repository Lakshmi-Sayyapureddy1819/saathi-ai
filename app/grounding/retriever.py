"""Pluggable retrieval backends for Mode A (config: RETRIEVER=lexical|embedding, default lexical).

Not every client has a vector store on day one, so the agent talks to a `Retriever` interface and the backend is a
deployment choice:

- LexicalRetriever: stemmed keyword overlap + a small Hinglish lexicon. No index, no network, no cost; deterministic.
- EmbeddingRetriever: dense retrieval. Each document is embedded once (lazily, kept in process memory; the library is
  small, so no database server is needed) and queries are ranked by cosine similarity. If embeddings are unavailable
  (no key, outage) it falls back to the lexical backend for that query, so retrieval never goes down with the provider.
  For a large library, swap the in-memory matrix for a vector database behind this same interface.
"""
import logging
import re
import threading
from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional

from pydantic import BaseModel, ConfigDict

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
MIN_BODY_HITS = 2  # distinct query words a document body must contain when no title/tag word matches


def _stem(token: str) -> str:
    """Cheap stemmer: tokens sharing a 5-char prefix are the same word (relax~relaxation, digest~digestion)."""
    return token[:5] if len(token) >= 5 else token


def _tokens(text: str) -> List[str]:
    return [t for t in _TOKEN.findall(text.lower()) if len(t) > 2 and t not in _STOP]


class Hit(BaseModel):
    model_config = ConfigDict(frozen=True)
    doc_id: str
    title: str
    content: str
    score: float


class Retriever(ABC):
    name: str = "retriever"

    @abstractmethod
    def search(self, query: str, top_k: int = 2) -> List[Hit]:
        """Best passages first; an empty list means 'nothing in the library answers this' (never a forced match)."""


class LexicalRetriever(Retriever):
    name = "lexical"

    def __init__(self, programs: List[dict]):
        self.programs = programs

    def search(self, query: str, top_k: int = 2) -> List[Hit]:
        base = _tokens(query)
        expanded = [e for t in base for e in HINGLISH_EXPANSION.get(t, [])]
        q = {_stem(t) for t in base} | {_stem(t) for t in expanded}
        scored = []
        for p in self.programs:
            title_tags = {_stem(t) for t in _tokens(p["title"] + " " + " ".join(p.get("tags", [])))}
            body = {_stem(t) for t in _tokens(p["content"])}
            title_hits, body_hits = len(q & title_tags), len(q & body)
            score = 3 * title_hits + body_hits  # title/tag hits weigh more
            # Off-topic guard: one stray body word ("weather", "match") is not evidence the document answers the
            # question. Need a title/tag match, or at least two distinct body words.
            if title_hits >= 1 or body_hits >= MIN_BODY_HITS:
                scored.append((score, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        if not scored:
            return []
        # Keep a runner-up only if it is nearly as relevant as the best hit: a weak match (e.g. sharing just
        # "fayde") is noise that dilutes the context and costs tokens.
        best = scored[0][0]
        return [Hit(doc_id=p["doc_id"], title=p["title"], content=p["content"], score=float(sc))
                for sc, p in scored[:top_k] if sc >= 0.5 * best]


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = sum(x * x for x in a) ** 0.5, sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


class EmbeddingRetriever(Retriever):
    """Dense retrieval over an in-memory index. `min_score` rejects off-topic queries (no forced nearest-neighbour)."""
    name = "embedding"

    def __init__(self, programs: List[dict], embed: Callable[[str], Optional[List[float]]],
                 fallback: Optional[Retriever] = None, min_score: float = 0.6, relative_cut: float = 0.9):
        self.programs, self.embed = programs, embed
        self.fallback = fallback or LexicalRetriever(programs)
        self.min_score, self.relative_cut = min_score, relative_cut
        self._index: Optional[Dict[str, List[float]]] = None
        self._lock = threading.Lock()
        self.fallbacks = 0  # queries answered by the lexical backend because embeddings were unavailable

    def _build_index(self) -> Optional[Dict[str, List[float]]]:
        with self._lock:
            if self._index is not None:
                return self._index
            index: Dict[str, List[float]] = {}
            for p in self.programs:
                vec = self.embed(f"{p['title']}. {p['content']}")
                if vec is None:
                    logging.warning("Embedding index not built (embeddings unavailable); using lexical retrieval.")
                    return None  # try again on a later query, do not cache a partial index
                index[p["doc_id"]] = vec
            self._index = index
            return index

    def search(self, query: str, top_k: int = 2) -> List[Hit]:
        index = self._build_index()
        qv = self.embed(query) if index else None
        if not index or qv is None:
            self.fallbacks += 1
            return self.fallback.search(query, top_k)
        scored = sorted(((_cosine(qv, index[p["doc_id"]]), p) for p in self.programs), key=lambda x: x[0], reverse=True)
        best = scored[0][0]
        if best < self.min_score:
            return []
        return [Hit(doc_id=p["doc_id"], title=p["title"], content=p["content"], score=round(sc, 4))
                for sc, p in scored[:top_k] if sc >= self.min_score and sc >= self.relative_cut * best]


def make_retriever(programs: List[dict], name: Optional[str] = None,
                   embed: Optional[Callable[[str], Optional[List[float]]]] = None) -> Retriever:
    """Backend from config: RETRIEVER=lexical (default) | embedding."""
    import os
    choice = (name or os.getenv("RETRIEVER", "lexical")).strip().lower()
    lexical = LexicalRetriever(programs)
    if choice == "lexical":
        return lexical
    if choice in ("embedding", "dense", "vector"):
        if embed is None:
            from app.grounding.semantic_cache import _embed as embed  # same provider/model as the semantic cache
        min_score = float(os.getenv("EMBED_RETRIEVAL_MIN_SCORE", "0.6"))
        return EmbeddingRetriever(programs, embed, fallback=lexical, min_score=min_score)
    raise ValueError(f"RETRIEVER={choice!r} is invalid; use lexical or embedding.")
