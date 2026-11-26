"""Out-of-scope questions must say what the assistant covers; fragments keep the warm nudge."""
import pytest

from app.workflow.graph import execute_turn, is_question
from app.workflow.replies import is_no_context_reply, say
from evaluations.run_evals import new_session


@pytest.mark.parametrize("text", ["what is ai?", "What is the capital of France", "who won the cricket match",
                                  "tell me a joke", "AI kya hai?", "how do I fix my laptop"])
def test_real_questions_are_questions(text):
    assert is_question(text)


@pytest.mark.parametrize("text", ["08:30 am ?", "?", "ok", "10:30 AM", "nine fifty"])
def test_fragments_are_not_questions(text):
    assert not is_question(text)


@pytest.mark.parametrize("text", ["what is ai?", "tell me a joke"])
def test_off_topic_question_gets_scope_reply(text):
    reply, _ = execute_turn(text, new_session("OOS"))
    assert reply == say("en", "out_of_scope")
    assert "only help with your Saathi program" in reply
    assert is_no_context_reply(reply)  # excluded from groundedness: it makes no factual claim


def test_fragment_still_gets_warm_nudge():
    reply, _ = execute_turn("08:30 am ?", new_session("OOS2"))
    assert reply == say("en", "voice_clarify")


def test_hinglish_scope_reply_is_hinglish():
    s = new_session("OOS3")
    s.reply_lang = "hinglish"
    reply, _ = execute_turn("AI kya hai?", s)
    assert reply == say("hinglish", "out_of_scope")


def test_mode_b_off_topic_question_gets_scope_reply():
    s = new_session("OOS4", mode="mode_b_facts")
    reply, _ = execute_turn("what is ai?", s)
    assert reply == say("en", "out_of_scope")


def test_mode_b_in_scope_question_is_not_refused():
    s = new_session("OOS5", mode="mode_b_facts")
    reply, _ = execute_turn("What is my enrolled program?", s)
    assert reply != say("en", "out_of_scope")


def test_mode_b_keyword_scope_check():
    from app.workflow.graph import WorkflowGraph
    g = WorkflowGraph()
    assert not g._in_scope("what is ai?")
    assert g._in_scope("how do I do sheetali pranayama?")
    assert g._in_scope("which lab test checks my thyroid?")
