"""Embedding-based semantic cache with a time-to-live, an optional Redis backend and measured statistics.

Embeddings come from the Gemini embeddings REST API when GEMINI_API_KEY is set. Without a key the in-memory cache
degrades to token-overlap similarity and reports `backend="jaccard-fallback"`. Queries containing PII-ish /
transactional content bypass the cache entirely.

TTL: every entry expires `ttl_seconds` after it was stored (default SEMANTIC_CACHE_TTL_SECONDS=3600; <=0 disables
expiry). An expired entry is never served, so an answer cannot outlive a change to the program library by more than the
TTL. Entries are also namespaced by prompt version and embedding model: a new prompt or embedding model starts with an
empty cache instead of serving answers produced by the old one.

Redis (optional, set REDIS_URL): shared across processes and restarts, with native key expiry (SET ... EX). Redis only
ever receives the embedding and the answer, never the member's question text (a hash is the key), and only generic
Mode-A answers are cached at all (see graph.py). Redis problems never break a turn: any error is counted, logged,
and the cache falls back to the in-process store; a failed connection is not retried for 30 s.
Scaling note: lookups scan the (capped) entry list and compute cosine locally, which is fine for a few hundred
entries. Beyond that use a vector index (RediSearch HNSW or a vector database) instead of this scan.
"""
import base64
import hashlib
import json
import logging
import math
import os
import re
import threading
import time
from array import array
from collections import OrderedDict
from typing import Callable, List, Optional

import requests
from pydantic import BaseModel, ConfigDict

EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")
DEFAULT_TTL_S = int(os.getenv("SEMANTIC_CACHE_TTL_SECONDS", "3600"))
REDIS_MAX_ENTRIES = 300  # each Redis entry holds a 3072-float embedding; the lookup scans them all
REDIS_RETRY_AFTER_S = 30.0
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
    ttl_seconds: int = 0
    store: str = "memory"  # "memory" or "redis" (redis = configured AND currently connected)
    entries: int = 0  # in-process entries (Redis entries live in Redis)
    expired: int = 0  # entries dropped because their TTL elapsed
    redis_errors: int = 0
    redis_configured: bool = False


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


def _pack(vec: List[float]) -> str:
    """float32, base64: 4 bytes per dimension instead of ~20 as JSON text."""
    return base64.b64encode(array("f", vec).tobytes()).decode("ascii")


def _unpack(blob: str) -> List[float]:
    a = array("f")
    a.frombytes(base64.b64decode(blob))
    return list(a)


class SemanticCache:
    def __init__(self, threshold: float = 0.75, max_size: int = 1000, ttl_seconds: Optional[int] = None,
                 namespace: str = "default", redis_client=None, redis_url: Optional[str] = None,
                 clock: Callable[[], float] = time.monotonic):
        self.threshold = threshold
        self.max_size = max_size
        self.ttl_seconds = DEFAULT_TTL_S if ttl_seconds is None else ttl_seconds
        self.namespace = namespace
        self._clock = clock
        self._lock = threading.RLock()
        # query -> (embedding or None, response, stored_at). Insertion order == expiry order (see set()).
        self.cache: "OrderedDict[str, tuple[Optional[List[float]], str, float]]" = OrderedDict()
        self.lookups = self.hits = self.bypassed = self.expired = self.redis_errors = 0
        self._backend = "embedding"
        self._redis = redis_client
        self._redis_url = redis_url if redis_url is not None else os.getenv("REDIS_URL", "")
        self._redis_retry_at = 0.0
        self._redis_connected = redis_client is not None

    # ---------------- namespace / TTL ----------------
    def set_namespace(self, namespace: str) -> None:
        """Entries made under another namespace (prompt version / embedding model) are not served."""
        with self._lock:
            if namespace != self.namespace:
                self.namespace = namespace
                self.cache.clear()

    def _expired(self, stored_at: float) -> bool:
        return self.ttl_seconds > 0 and self._clock() - stored_at >= self.ttl_seconds

    def _purge_expired(self) -> None:
        if self.ttl_seconds <= 0:
            return
        while self.cache:
            oldest = next(iter(self.cache))
            if not self._expired(self.cache[oldest][2]):
                break
            del self.cache[oldest]
            self.expired += 1

    # ---------------- Redis (optional, fail-open) ----------------
    def _idx(self) -> str:
        return f"semcache:{self.namespace}:idx"

    def _rkey(self, query: str) -> str:
        return f"semcache:{self.namespace}:e:{hashlib.sha256(query.encode('utf-8')).hexdigest()[:32]}"

    def _client(self):
        """The Redis client, connecting lazily; None if not configured or recently failed."""
        if self._redis is not None:
            return self._redis
        if not self._redis_url or self._clock() < self._redis_retry_at:
            return None
        try:
            import redis  # optional dependency
            client = redis.Redis.from_url(self._redis_url, socket_timeout=0.5, socket_connect_timeout=0.5)
            client.ping()
            self._redis, self._redis_connected = client, True
            return client
        except Exception as e:  # noqa: BLE001 - never break a turn because of the cache
            self._redis_failed(e)
            return None

    def _redis_failed(self, exc: BaseException) -> None:
        self.redis_errors += 1
        self._redis_connected = False
        self._redis_retry_at = self._clock() + REDIS_RETRY_AFTER_S
        if self._redis_url:
            self._redis = None  # reconnect lazily after the retry delay
        logging.warning("Semantic cache: Redis unavailable (%s); using the in-process cache for %.0fs.",
                        type(exc).__name__, REDIS_RETRY_AFTER_S)

    def _redis_get(self, qv: List[float]) -> Optional[str]:
        r = self._client()
        if r is None:
            return None
        try:
            keys = r.zrange(self._idx(), 0, -1)
            if not keys:
                return None
            best, best_resp, dead = 0.0, None, []
            for key, raw in zip(keys, r.mget(keys)):
                if raw is None:  # the key's TTL elapsed
                    dead.append(key)
                    continue
                d = json.loads(raw)
                s = _cosine(qv, _unpack(d["v"]))
                if s > best:
                    best, best_resp = s, d["r"]
            if dead:
                r.zrem(self._idx(), *dead)
                self.expired += len(dead)
            return best_resp if best_resp is not None and best >= self.threshold else None
        except Exception as e:  # noqa: BLE001
            self._redis_failed(e)
            return None

    def _redis_set(self, query: str, qv: List[float], response: str) -> bool:
        r = self._client()
        if r is None:
            return False
        try:
            key = self._rkey(query)
            r.set(key, json.dumps({"v": _pack(qv), "r": response}), ex=self.ttl_seconds if self.ttl_seconds > 0 else None)
            r.zadd(self._idx(), {key: time.time()})
            if self.ttl_seconds > 0:
                r.expire(self._idx(), self.ttl_seconds * 2)
            over = r.zcard(self._idx()) - min(self.max_size, REDIS_MAX_ENTRIES)
            if over > 0:  # evict the oldest entries beyond the cap
                old = r.zrange(self._idx(), 0, over - 1)
                r.zrem(self._idx(), *old)
                r.delete(*old)
            return True
        except Exception as e:  # noqa: BLE001
            self._redis_failed(e)
            return False

    # ---------------- public API ----------------
    def _score(self, q: str, qv: Optional[List[float]], cq: str, cv: Optional[List[float]]) -> float:
        if qv is not None and cv is not None:
            return _cosine(qv, cv)
        self._backend = "jaccard-fallback"
        return _jaccard(q, cq)

    def get(self, query: str) -> Optional[str]:
        with self._lock:
            self.lookups += 1
            if _BYPASS.search(query):
                self.bypassed += 1
                return None
            self._purge_expired()
        qv = _embed(query)
        if qv is not None:
            shared = self._redis_get(qv)
            if shared is not None:
                with self._lock:
                    self.hits += 1
                return shared
        with self._lock:
            best, best_resp = 0.0, None
            for cq, (cv, resp, _stored) in self.cache.items():
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
        qv = _embed(query)
        if qv is not None and self._redis_set(query, qv, response):
            return  # shared store has it (embedding + answer only, never the question text)
        with self._lock:
            self._purge_expired()
            self.cache.pop(query, None)  # re-adding refreshes position, so insertion order stays expiry order
            if len(self.cache) >= self.max_size:
                self.cache.popitem(last=False)
            self.cache[query] = (qv, response, self._clock())

    def stats(self) -> CacheStats:
        with self._lock:
            self._purge_expired()
            return CacheStats(
                backend=self._backend, threshold=self.threshold, lookups=self.lookups, hits=self.hits,
                bypassed=self.bypassed, hit_rate=round(self.hits / self.lookups, 4) if self.lookups else 0.0,
                false_hits=0, ttl_seconds=self.ttl_seconds,
                store="redis" if self._redis_connected else "memory", entries=len(self.cache),
                expired=self.expired, redis_errors=self.redis_errors,
                redis_configured=bool(self._redis_url) or self._redis is not None)

    def evaluate_false_hits(self, labelled_pairs: List[tuple[str, str, bool]]) -> float:
        """labelled_pairs: (query_a, query_b, same_intent). Returns the false-hit rate at the current
        threshold = fraction of *different-intent* pairs scored >= threshold. Run on a labelled set."""
        neg = [(a, b) for a, b, same in labelled_pairs if not same]
        if not neg:
            return 0.0
        bad = sum(1 for a, b in neg if self._score(a, _embed(a), b, _embed(b)) >= self.threshold)
        return bad / len(neg)


wellness_cache = SemanticCache()
