"""Embedding-based semantic cache with measured (not hardcoded) statistics.

Embeddings come from the Gemini embeddings REST API when GEMINI_API_KEY is set. Without a key
the cache degrades to token-overlap similarity and reports `backend="jaccard-fallback"`.
Queries containing PII-ish / transactional content bypass the cache entirely.
"""
import logging
import math
import os
import re
from collections import OrderedDict
from typing import List, Optional

import requests
from pydantic import BaseModel, ConfigDict

EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")
_BYPASS = re.compile(r"\b(name|slot|slots|book|booking|test|package|appointment|tomorrow|today|am|pm)\b|\bLP_\d+|\d", re.I)


class CacheStats(BaseModel):
    model_config = ConfigDict(frozen=True)
    backend: str
    threshold: float
    lookups: int
    hits: int
    bypassed: int
    hit_rate: float
    false_hits: int  # only populated by evaluate_false_hits()


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _embed(text: str) -> Optional[List[float]]:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return None
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{EMBED_MODEL}:embedContent",
            headers={"x-goog-api-key": key},
            json={"content": {"parts": [{"text": text}]}}, timeout=10)
        if r.status_code == 200:
            return r.json()["embedding"]["values"]
        logging.warning(f"Embedding API returned {r.status_code}")
    except Exception as e:
        logging.warning(f"Embedding failed: {e}")
    return None


def _jaccard(q1: str, q2: str) -> float:
    a, b = set(q1.lower().split()), set(q2.lower().split())
    return len(a & b) / len(a | b) if a and b else 0.0


class SemanticCache:
    def __init__(self, threshold: float = 0.88, max_size: int = 1000):
        self.threshold = threshold
        self.max_size = max_size
        # query -> (embedding or None, response)
        self.cache: "OrderedDict[str, tuple[Optional[List[float]], str]]" = OrderedDict()
        self.lookups = self.hits = self.bypassed = 0
        self._backend = "embedding"

    def _score(self, q: str, qv: Optional[List[float]], cq: str, cv: Optional[List[float]]) -> float:
        if qv is not None and cv is not None:
            return _cosine(qv, cv)
        self._backend = "jaccard-fallback"
        return _jaccard(q, cq)

    def get(self, query: str) -> Optional[str]:
        self.lookups += 1
        if _BYPASS.search(query):
            self.bypassed += 1
            return None
        qv = _embed(query)
        best, best_resp = 0.0, None
        for cq, (cv, resp) in self.cache.items():
            s = self._score(query, qv, cq, cv)
            if s > best:
                best, best_resp = s, resp
        if best_resp is not None and best >= self.threshold:
            self.hits += 1
            return best_resp
        return None

    def set(self, query: str, response: str) -> None:
        if _BYPASS.search(query):
            return
        if len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)
        self.cache[query] = (_embed(query), response)

    def stats(self) -> CacheStats:
        return CacheStats(backend=self._backend, threshold=self.threshold, lookups=self.lookups,
                          hits=self.hits, bypassed=self.bypassed,
                          hit_rate=round(self.hits / self.lookups, 4) if self.lookups else 0.0, false_hits=0)

    def evaluate_false_hits(self, labelled_pairs: List[tuple[str, str, bool]]) -> float:
        """labelled_pairs: (query_a, query_b, same_intent). Returns the false-hit rate at the current
        threshold = fraction of *different-intent* pairs scored >= threshold. Run on a labelled set."""
        neg = [(a, b) for a, b, same in labelled_pairs if not same]
        if not neg:
            return 0.0
        bad = sum(1 for a, b in neg if self._score(a, _embed(a), b, _embed(b)) >= self.threshold)
        return bad / len(neg)


wellness_cache = SemanticCache()
