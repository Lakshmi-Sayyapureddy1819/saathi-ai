"""Citations are verified by code, not trusted from the model, and reach the API/UI as typed fields."""
import pytest
from fastapi.testclient import TestClient

from app import api
from app.grounding.citations import verify_citations
from app.tools.lab_tools import LabTools
from app.workflow.model_client import LLMResult

TITLES = {"PROG_Y_001": "Surya Namaskar", "PROG_P_002": "Kapalbhati"}


def test_valid_citation_is_kept_and_titled():
    c = verify_citations("Start slowly [PROG_Y_001].", ["PROG_Y_001"], TITLES)
    assert c.text == "Start slowly [PROG_Y_001]." and c.fabricated == [] and not c.uncited
    assert [(x.source_id, x.title, x.cited, x.kind) for x in c.citations] == [("PROG_Y_001", "Surya Namaskar", True, "document")]


def test_fabricated_citation_is_stripped_and_reported():
    c = verify_citations("It cures things [PROG_Y_999] and helps [PROG_Y_001].", ["PROG_Y_001"], TITLES)
    assert "PROG_Y_999" not in c.text and c.fabricated == ["PROG_Y_999"]
    assert [x.source_id for x in c.citations] == ["PROG_Y_001"]


def test_uncited_answer_shows_sources_as_consulted():
    c = verify_citations("Do it slowly.", ["PROG_Y_001", "PROG_P_002"], TITLES)
    assert c.uncited and all(not x.cited for x in c.citations) and len(c.citations) == 2


def test_mode_b_fact_groups_are_citable_and_labelled():
    c = verify_citations("You booked a thyroid test [bookings]. Also [lab_catalogue].", ["bookings"], {})
    assert c.fabricated == ["lab_catalogue"] and c.citations[0].title == "Your bookings"
    assert c.citations[0].kind == "backend_fact"


def test_ordinary_brackets_are_left_alone():
    c = verify_citations("Take a 5 minute break [optional] and see [MOCK].", ["PROG_Y_001"], TITLES)
    assert "[optional]" in c.text and c.fabricated == []


class _Model:
    def __init__(self, text):
        self.text = text

    def generate(self, prompt, trace_id=None):
        return LLMResult(text=self.text, model="fake")


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.delenv("COORDINATOR_TOKEN", raising=False)
    g = api._GRAPH
    g.lab_tools = LabTools(failure_rate=0.0)
    g.use_cache, g.planner = False, None
    api._records.clear(); api._create_log.clear()
    with TestClient(api.app) as c:
        yield c
    api._records.clear(); api._create_log.clear()
    g.use_cache = True


def _new(c):
    b = c.post("/api/sessions", json={"member_id": "MEM_1002"}).json()
    return b["session"]["session_id"], {"Authorization": f"Bearer {b['session_token']}"}


def _say(c, sid, hdr, text):
    return c.post(f"/api/sessions/{sid}/messages", json={"text": text}, headers=hdr).json()["messages"][-1]


def test_api_returns_verified_citations_and_grounding_panel(client, monkeypatch):
    sid, hdr = _new(client)
    doc = api._GRAPH.engine.mode_a_retrieval("Tell me about Kapalbhati").sources[0]
    monkeypatch.setattr(api._GRAPH, "model_client", _Model(f"A breathing practice [{doc}] that heals all [PROG_Z_404]."))
    m = _say(client, sid, hdr, "Tell me about Kapalbhati")
    assert [c["source_id"] for c in m["citations"]] == [doc] and m["citations"][0]["title"]
    assert "PROG_Z_404" not in m["text"]
    assert m["grounding"]["mode"] == "mode_a_rag" and m["grounding"]["search_queries"]


def test_non_coach_messages_have_no_citations(client, monkeypatch):
    sid, hdr = _new(client)
    doc = api._GRAPH.engine.mode_a_retrieval("Tell me about Kapalbhati").sources[0]
    monkeypatch.setattr(api._GRAPH, "model_client", _Model(f"Kapalbhati [{doc}]"))
    assert _say(client, sid, hdr, "Tell me about Kapalbhati")["citations"]
    booking = _say(client, sid, hdr, "Book a blood test")           # next turn must not inherit the old citations
    assert booking["citations"] == [] and booking["grounding"] is None


def test_voice_never_speaks_citation_markers():
    from app.channels.voice_agent import VoiceAgent
    v = VoiceAgent(tts_char_delay=0, verbose=False)
    v.speak("Kapalbhati is a breathing practice [PROG_P_002]. Also see [bookings].")
    assert "[" not in v.last_spoken and "PROG_P_002" not in v.last_spoken


# ---------------- UI mode switch (Mode A <-> Mode B per session) ----------------
def test_mode_can_be_chosen_at_creation_and_switched_mid_session(client, monkeypatch):
    b = client.post("/api/sessions", json={"member_id": "MEM_1002", "grounding_mode": "mode_b_facts"}).json()
    assert b["session"]["grounding_mode"] == "mode_b_facts"
    sid, hdr = b["session"]["session_id"], {"Authorization": f"Bearer {b['session_token']}"}

    monkeypatch.setattr(api._GRAPH, "model_client", _Model("You are enrolled in your programs [member_profile]."))
    m = _say(client, sid, hdr, "Which programs am I enrolled in? Tell me about my yoga program")
    assert m["grounding"]["mode"] == "mode_b_facts" and m["citations"][0]["title"] == "Your profile"
    assert m["citations"][0]["kind"] == "backend_fact"

    view = client.post(f"/api/sessions/{sid}/grounding", json={"mode": "mode_a_rag"}, headers=hdr).json()
    assert view["grounding_mode"] == "mode_a_rag" and "Library search" in view["messages"][-1]["text"]
    doc = api._GRAPH.engine.mode_a_retrieval("Tell me about Kapalbhati").sources[0]
    monkeypatch.setattr(api._GRAPH, "model_client", _Model(f"A breathing practice [{doc}]."))
    m2 = _say(client, sid, hdr, "Tell me about Kapalbhati")                  # the switch reached the stored ADK session
    assert m2["grounding"]["mode"] == "mode_a_rag" and m2["citations"][0]["kind"] == "document"


def test_switching_requires_the_session_token_and_a_valid_mode(client):
    sid, hdr = _new(client)
    assert client.post(f"/api/sessions/{sid}/grounding", json={"mode": "mode_b_facts"}).status_code in (401, 403)
    assert client.post(f"/api/sessions/{sid}/grounding", json={"mode": "vector_db"}, headers=hdr).status_code == 422


def test_follow_up_turns_see_earlier_coach_turns_through_the_api(client, monkeypatch):
    """Regression: ADK's stored session used to miss the previous turn, so the coach never had conversation memory."""
    seen = []

    class Spy(_Model):
        def generate(self, prompt, trace_id=None):
            seen.append(prompt)
            return super().generate(prompt, trace_id)
    doc = api._GRAPH.engine.mode_a_retrieval("Tell me about Kapalbhati").sources[0]
    monkeypatch.setattr(api._GRAPH, "model_client", Spy(f"Kapalbhati is a breathing practice [{doc}]."))
    sid, hdr = _new(client)
    _say(client, sid, hdr, "Tell me about Kapalbhati")
    _say(client, sid, hdr, "Tell me more about Kapalbhati and breathing")
    assert "Tell me about Kapalbhati" in seen[-1] and "Earlier turns of this conversation" in seen[-1]
    assert "Earlier turns" not in seen[0]                                   # the first turn has no history


def test_cache_hit_for_a_second_member_keeps_verified_citations(client, monkeypatch):
    from app.grounding.semantic_cache import wellness_cache
    wellness_cache.cache.clear()
    api._GRAPH.use_cache = True
    doc = api._GRAPH.engine.mode_a_retrieval("Tell me about Kapalbhati").sources[0]
    calls = []

    class Counting(_Model):
        def generate(self, prompt, trace_id=None):
            calls.append(1)
            return super().generate(prompt, trace_id)
    monkeypatch.setattr(api._GRAPH, "model_client", Counting(f"Kapalbhati is a breathing practice [{doc}]."))
    s1, h1 = _new(client)
    first = _say(client, s1, h1, "Tell me about Kapalbhati")
    s2, h2 = _new(client)
    second = _say(client, s2, h2, "Tell me about Kapalbhati")
    assert len(calls) == 1                                                  # the second member was served from the cache
    assert [c["source_id"] for c in second["citations"]] == [doc] == [c["source_id"] for c in first["citations"]]
    assert second["grounding"] is None and first["grounding"] is not None   # nothing was retrieved on the cache hit
    wellness_cache.cache.clear()
