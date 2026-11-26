"""Semantic cache over the Upstash REST API (app/grounding/semantic_cache.py, UpstashRest).

The HTTP layer is replaced by a fake that runs each command on fakeredis, so the REST wiring is checked against real
Redis command semantics without network access. Embeddings are stubbed (no Gemini call).
"""
import pytest
import requests
import fakeredis

from app.grounding import semantic_cache as sc

URL = "https://example-db.upstash.io"
TOKEN = "test-token"
VEC_A = [1.0, 0.0, 0.0]
VEC_B = [0.0, 1.0, 0.0]


class _Resp:
    def __init__(self, status: int, payload: dict):
        self.status_code = status
        self._payload = payload
        self.content = b"x"

    def json(self):
        return self._payload


def _decode(v):
    """Shape a redis-py result like the Upstash REST JSON 'result' (strings for status replies, not bools)."""
    if isinstance(v, bytes):
        return v.decode("utf-8")
    if isinstance(v, list):
        return [_decode(x) for x in v]
    if v is True:  # redis-py returns True for +OK / +PONG status replies; REST returns the text
        return "OK"
    return v


@pytest.fixture
def fake_rest(monkeypatch):
    server = fakeredis.FakeServer()
    backend = fakeredis.FakeRedis(server=server)
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append((url, headers, json))
        assert url == URL
        assert headers["Authorization"] == f"Bearer {TOKEN}"
        if json[0] == "PING":
            return _Resp(200, {"result": "PONG"})
        result = backend.execute_command(*json)
        return _Resp(200, {"result": _decode(result)})

    monkeypatch.setattr(sc.requests, "post", fake_post)
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", URL)
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", TOKEN)
    monkeypatch.delenv("REDIS_URL", raising=False)
    return calls


@pytest.fixture
def stub_embed(monkeypatch):
    """Embedding returns a vector chosen by the query text; no network."""
    table = {}

    def fake_embed(text):
        return table.get(text)

    monkeypatch.setattr(sc, "_embed", fake_embed)
    return table


def test_rest_creds_are_read_from_env(fake_rest):
    cache = sc.SemanticCache(ttl_seconds=3600)
    assert cache._rest_url == URL
    assert cache._rest_token == TOKEN
    assert cache.stats().redis_configured is True


def test_rest_is_not_used_when_redis_url_is_set(fake_rest, monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    cache = sc.SemanticCache(ttl_seconds=3600)
    assert cache._rest_url == ""


def test_answer_is_stored_and_served_through_rest(fake_rest, stub_embed):
    stub_embed["What is kapalbhati?"] = VEC_A
    stub_embed["what is kapalbhati"] = VEC_A
    cache = sc.SemanticCache(threshold=0.88, ttl_seconds=3600)
    cache.set("What is kapalbhati?", "A breathing practice.", sync=True)
    assert cache.get("what is kapalbhati") == "A breathing practice."
    stats = cache.stats()
    assert stats.store == "redis"
    assert stats.hits == 1
    assert stats.redis_errors == 0
    assert any(body[0] == "SET" for _, _, body in fake_rest)


def test_second_process_shares_the_answer(fake_rest, stub_embed):
    stub_embed["What is kapalbhati?"] = VEC_A
    stub_embed["kapalbhati meaning"] = VEC_A
    writer = sc.SemanticCache(threshold=0.88, ttl_seconds=3600)
    writer.set("What is kapalbhati?", "A breathing practice.", sync=True)
    reader = sc.SemanticCache(threshold=0.88, ttl_seconds=3600)  # fresh in-process cache
    assert reader.get("kapalbhati meaning") == "A breathing practice."


def test_dissimilar_query_misses(fake_rest, stub_embed):
    stub_embed["What is kapalbhati?"] = VEC_A
    stub_embed["diet for diabetes"] = VEC_B
    cache = sc.SemanticCache(threshold=0.88, ttl_seconds=3600)
    cache.set("What is kapalbhati?", "A breathing practice.", sync=True)
    assert cache.get("diet for diabetes") is None


def test_personal_queries_are_never_stored(fake_rest, stub_embed):
    stub_embed["book my test tomorrow"] = VEC_A
    cache = sc.SemanticCache(threshold=0.88, ttl_seconds=3600)
    cache.set("book my test tomorrow", "Booked.", sync=True)
    assert not any(body[0] == "SET" for _, _, body in fake_rest)


def test_rest_failure_falls_back_to_memory_without_breaking_the_turn(monkeypatch, stub_embed):
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", URL)
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", TOKEN)
    monkeypatch.delenv("REDIS_URL", raising=False)

    def down(*a, **k):
        raise requests.ConnectionError("unreachable")

    monkeypatch.setattr(sc.requests, "post", down)
    stub_embed["What is kapalbhati?"] = VEC_A
    cache = sc.SemanticCache(threshold=0.88, ttl_seconds=3600)
    cache.set("What is kapalbhati?", "A breathing practice.", sync=True)
    assert cache.get("what is kapalbhati") is None or cache.get("what is kapalbhati") == "A breathing practice."
    stats = cache.stats()
    assert stats.store == "memory"
    assert stats.redis_errors >= 1


def test_rest_error_status_is_treated_as_failure(monkeypatch):
    monkeypatch.setattr(sc.requests, "post", lambda *a, **k: _Resp(401, {"error": "WRONGPASS"}))
    client = sc.UpstashRest(URL, TOKEN)
    with pytest.raises(RuntimeError) as exc:
        client.ping()
    assert "401" in str(exc.value)
    assert TOKEN not in str(exc.value)


def test_embed_calls_openai_embeddings_and_returns_the_vector(monkeypatch):
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, json=json)
        return _Resp(200, {"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(sc.requests, "post", fake_post)
    assert sc._embed("kapalbhati") == [0.1, 0.2, 0.3]
    assert seen["url"] == "https://api.openai.com/v1/embeddings"
    assert seen["headers"]["Authorization"] == "Bearer sk-test"
    assert seen["json"] == {"model": sc.EMBED_MODEL, "input": "kapalbhati"}
    assert sc.EMBED_MODEL == "text-embedding-3-small"


def test_embed_without_openai_key_returns_none(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert sc._embed("anything") is None
