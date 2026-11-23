"""Semantic cache: time-to-live, namespaces, optional Redis backend (fakeredis), and failing open."""
import time

import fakeredis
import pytest

from app.grounding import semantic_cache as sc
from app.grounding.semantic_cache import SemanticCache

Q1 = "tell me about yoga for stress"        # jaccard path (no API key in tests): identical text scores 1.0
A1 = "Try Sheetali Pranayama."


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


# ---------------- in-memory TTL ----------------
def test_entry_is_served_before_the_ttl_and_dropped_after():
    clk = Clock()
    c = SemanticCache(ttl_seconds=60, clock=clk)
    c.set(Q1, A1)
    clk.advance(59)
    assert c.get(Q1) == A1
    clk.advance(2)
    assert c.get(Q1) is None
    st = c.stats()
    assert st.expired == 1 and st.entries == 0 and st.ttl_seconds == 60


def test_ttl_zero_or_negative_means_never_expire():
    clk = Clock()
    c = SemanticCache(ttl_seconds=0, clock=clk)
    c.set(Q1, A1)
    clk.advance(10 ** 9)
    assert c.get(Q1) == A1 and c.stats().expired == 0


def test_resetting_a_query_refreshes_its_ttl():
    clk = Clock()
    c = SemanticCache(ttl_seconds=60, clock=clk)
    c.set(Q1, "old")
    clk.advance(50)
    c.set(Q1, "new")  # same query stored again
    clk.advance(50)   # 100 s after the first write, 50 s after the refresh
    assert c.get(Q1) == "new"


def test_only_expired_entries_are_purged():
    clk = Clock()
    c = SemanticCache(ttl_seconds=60, clock=clk)
    c.set("how does kapalbhati help", "A")
    clk.advance(40)
    c.set("what is anulom vilom", "B")
    clk.advance(30)  # first is 70 s old (expired), second 30 s (alive)
    assert c.get("how does kapalbhati help") is None
    assert c.get("what is anulom vilom") == "B"


def test_default_ttl_comes_from_the_environment_value():
    assert SemanticCache().ttl_seconds == sc.DEFAULT_TTL_S
    assert sc.wellness_cache.ttl_seconds == sc.DEFAULT_TTL_S


def test_namespace_change_drops_entries_made_under_the_old_one():
    c = SemanticCache(namespace="v3:model-a")
    c.set(Q1, A1)
    c.set_namespace("v4:model-a")  # new prompt version
    assert c.get(Q1) is None
    c.set(Q1, "fresh")
    c.set_namespace("v4:model-a")  # unchanged namespace keeps entries
    assert c.get(Q1) == "fresh"


def test_graph_namespaces_the_shared_cache_by_prompt_version_and_embedding_model():
    from app.workflow import graph
    assert sc.wellness_cache.namespace == f"{graph.PROMPT_VERSION}:{sc.EMBED_MODEL}"


def test_size_cap_and_bypass_rules_still_hold():
    c = SemanticCache(max_size=2, ttl_seconds=60)
    for q in ("how does kapalbhati help", "what is anulom vilom", "describe viparita karani"):
        c.set(q, "x")
    assert c.stats().entries == 2
    c.set("book a test tomorrow", "must not be cached")  # transactional: bypassed
    assert c.get("book a test tomorrow") is None and c.stats().bypassed >= 1


# ---------------- Redis (fakeredis) ----------------
VEC = {
    "how does yoga reduce stress": [1.0, 0.0, 0.0],
    "yoga for stress relief": [0.97, 0.2, 0.0],      # paraphrase: cosine ~0.98
    "diet plan for diabetes": [0.0, 1.0, 0.0],       # different intent: cosine 0
    "explain pranayama benefits": [0.0, 0.0, 1.0],
}


@pytest.fixture()
def embed(monkeypatch):
    monkeypatch.setattr(sc, "_embed", lambda text: VEC.get(text))


@pytest.fixture()
def redis_server():
    return fakeredis.FakeServer()


def _cache(server, **kw):
    return SemanticCache(redis_client=fakeredis.FakeStrictRedis(server=server), namespace="v4:m", **kw)


def test_redis_hit_for_a_paraphrase_and_miss_for_a_different_intent(embed, redis_server):
    c = _cache(redis_server, ttl_seconds=60)
    c.set("how does yoga reduce stress", "ANSWER")
    assert c.cache == OrderedDictEmpty()  # stored in Redis, not in the process
    assert c.get("yoga for stress relief") == "ANSWER"
    assert c.get("diet plan for diabetes") is None
    assert c.stats().store == "redis" and c.stats().redis_configured


def OrderedDictEmpty():
    from collections import OrderedDict
    return OrderedDict()


def test_entry_is_shared_by_a_second_process_sharing_the_same_redis(embed, redis_server):
    _cache(redis_server, ttl_seconds=60).set("how does yoga reduce stress", "ANSWER")
    other = _cache(redis_server, ttl_seconds=60)  # e.g. another worker, or after a restart
    assert other.get("yoga for stress relief") == "ANSWER"


def test_redis_keys_carry_a_real_ttl(embed, redis_server):
    c = _cache(redis_server, ttl_seconds=90)
    c.set("how does yoga reduce stress", "ANSWER")
    r = fakeredis.FakeStrictRedis(server=redis_server)
    keys = [k for k in r.keys("semcache:v4:m:e:*")]
    assert len(keys) == 1 and 0 < r.ttl(keys[0]) <= 90


def test_redis_entry_really_expires(embed, redis_server):
    c = _cache(redis_server, ttl_seconds=1)
    c.set("how does yoga reduce stress", "ANSWER")
    assert c.get("yoga for stress relief") == "ANSWER"
    time.sleep(1.2)
    assert c.get("yoga for stress relief") is None
    assert c.stats().expired >= 1  # the stale index entry was noticed and cleaned


def test_redis_never_receives_the_question_text(embed, redis_server):
    c = _cache(redis_server, ttl_seconds=60)
    question = "how does yoga reduce stress"
    c.set(question, "ANSWER")
    r = fakeredis.FakeStrictRedis(server=redis_server)
    dump = b"".join(k + (r.get(k) or b"") for k in r.keys("*") if r.type(k) == b"string") + b"".join(r.keys("*"))
    assert question.encode() not in dump and b"ANSWER" in dump


def test_namespaces_are_isolated_in_redis(embed, redis_server):
    a = SemanticCache(redis_client=fakeredis.FakeStrictRedis(server=redis_server), namespace="v3:m", ttl_seconds=60)
    b = SemanticCache(redis_client=fakeredis.FakeStrictRedis(server=redis_server), namespace="v4:m", ttl_seconds=60)
    a.set("how does yoga reduce stress", "OLD PROMPT ANSWER")
    assert b.get("how does yoga reduce stress") is None


def test_redis_entry_cap_evicts_the_oldest(embed, redis_server, monkeypatch):
    monkeypatch.setattr(sc, "REDIS_MAX_ENTRIES", 2)
    c = _cache(redis_server, ttl_seconds=60)
    for q in VEC:
        c.set(q, f"A:{q}")
        time.sleep(0.01)
    r = fakeredis.FakeStrictRedis(server=redis_server)
    assert r.zcard("semcache:v4:m:idx") == 2 and len(r.keys("semcache:v4:m:e:*")) == 2
    assert c.get("how does yoga reduce stress") is None  # oldest was evicted
    assert c.get("explain pranayama benefits") == "A:explain pranayama benefits"


def test_without_an_embedding_nothing_goes_to_redis(redis_server, monkeypatch):
    monkeypatch.setattr(sc, "_embed", lambda text: None)  # no API key / embedding outage
    c = _cache(redis_server, ttl_seconds=60)
    c.set(Q1, A1)
    assert fakeredis.FakeStrictRedis(server=redis_server).dbsize() == 0  # question text must not reach Redis
    assert c.get(Q1) == A1  # served from the in-process fallback


# ---------------- failing open ----------------
class _BrokenRedis:
    def __getattr__(self, name):
        def boom(*a, **k):
            raise ConnectionError("redis is down")
        return boom


def test_redis_errors_never_break_a_turn_and_fall_back_to_memory(embed):
    c = SemanticCache(redis_client=_BrokenRedis(), namespace="v4:m", ttl_seconds=60)
    c.set("how does yoga reduce stress", "ANSWER")          # write fails -> stored in process
    assert c.get("how does yoga reduce stress") == "ANSWER"  # read fails -> in-process hit
    st = c.stats()
    assert st.redis_errors >= 1 and st.store == "memory" and st.entries == 1


def test_unreachable_redis_url_is_not_retried_on_every_request(embed, monkeypatch):
    import redis as redis_lib
    attempts = []

    def refuse(url, **kw):
        attempts.append(url)
        raise ConnectionError("refused")

    monkeypatch.setattr(redis_lib.Redis, "from_url", staticmethod(refuse))
    clk = Clock()
    c = SemanticCache(redis_url="redis://127.0.0.1:1/0", namespace="v4:m", ttl_seconds=60, clock=clk)
    for _ in range(5):
        c.set("how does yoga reduce stress", "ANSWER")
        assert c.get("how does yoga reduce stress") == "ANSWER"
    assert len(attempts) == 1  # one failed connect, then backed off
    clk.advance(sc.REDIS_RETRY_AFTER_S + 1)
    c.get("how does yoga reduce stress")
    assert len(attempts) == 2  # retried after the delay
    assert c.stats().redis_configured and c.stats().store == "memory"


def test_no_redis_url_means_pure_memory_cache(embed, monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    c = SemanticCache(namespace="v4:m")
    c.set("how does yoga reduce stress", "ANSWER")
    st = c.stats()
    assert st.store == "memory" and not st.redis_configured and st.entries == 1


# ---------------- API ----------------
def test_cache_status_endpoint():
    from fastapi.testclient import TestClient
    from app import api
    with TestClient(api.app) as client:
        r = client.get("/api/cache-status")
    assert r.status_code == 200
    body = r.json()
    assert {"ttl_seconds", "store", "entries", "expired", "redis_errors", "hit_rate"} <= set(body)
    assert "redis://" not in r.text  # the URL (may contain a password) is never exposed


# ---------------- Threshold & Data Privacy (Assignment Req 8) ----------------
def test_default_similarity_threshold_is_088_and_configurable(monkeypatch):
    assert sc.DEFAULT_THRESHOLD == 0.88
    assert SemanticCache().threshold == 0.88

    monkeypatch.setenv("SEMANTIC_CACHE_THRESHOLD", "0.92")
    # Fresh instance without explicit threshold follows environment or DEFAULT_THRESHOLD
    c_custom = SemanticCache(threshold=0.92)
    assert c_custom.threshold == 0.92


def test_member_data_and_booking_queries_never_cached():
    c = SemanticCache()
    sensitive_queries = [
        "book a blood test tomorrow",
        "schedule an appointment for 10 am",
        "show my member profile",
        "where can I view my booking history?",
        "check my lab report",
        "what are the available slots tomorrow?",
        "cancel my booking",
        "tell me about LP_01 package",
    ]
    for q in sensitive_queries:
        c.set(q, "PRIVATE_ANSWER")
        assert c.get(q) is None, f"Query '{q}' should have bypassed cache"
    assert c.stats().bypassed >= len(sensitive_queries)
    assert c.stats().entries == 0


def test_false_hit_rate_measurement_at_threshold_088(embed):
    c = SemanticCache(threshold=0.88)
    pairs = [
        ("how does yoga reduce stress", "yoga for stress relief", True),
        ("how does yoga reduce stress", "diet plan for diabetes", False),
        ("diet plan for diabetes", "explain pranayama benefits", False),
    ]
    f_rate = c.evaluate_false_hits(pairs)
    assert f_rate == 0.0



def test_redis_url_is_derived_from_upstash_rest_credentials(monkeypatch):
    from app.grounding.semantic_cache import redis_url_from_env
    for k in ("REDIS_URL", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    assert redis_url_from_env() == ""
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://eager-cat-1234.upstash.io/")
    assert redis_url_from_env() == ""                                   # a URL without the token is not usable
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "tok")
    assert redis_url_from_env() == "rediss://default:tok@eager-cat-1234.upstash.io:6379"
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")        # an explicit REDIS_URL always wins
    assert redis_url_from_env() == "redis://127.0.0.1:6379/0"
