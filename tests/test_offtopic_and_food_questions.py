"""Regression tests for two known gaps: off-topic retrieval and the 'heart healthy' false positive."""
import pytest

from app.grounding.engine import GroundingEngine
from app.safety.triage_gate import PATTERNS_YELLOW_WARNING

_DIAG = PATTERNS_YELLOW_WARNING["DIAGNOSIS_REQUEST"]


@pytest.mark.parametrize("query", [
    "what is the weather", "who won the cricket match", "how do I fix my laptop",
    "what is the capital of France", "tell me a joke", "stock market tips"])
def test_off_topic_questions_retrieve_nothing(query):
    ctx = GroundingEngine().mode_a_retrieval(query)
    assert ctx.empty and ctx.sources == []


@pytest.mark.parametrize("query", [
    "what is the schedule for morning yoga", "diet guidance for diabetes", "sheetali pranayama benefits"])
def test_on_topic_questions_still_retrieve(query):
    assert not GroundingEngine().mode_a_retrieval(query).empty


@pytest.mark.parametrize("text", [
    "Is it heart healthy to eat oats?", "is it heart friendly to eat ghee", "Is it safe to eat oats",
    "is this thyroid friendly food"])
def test_food_and_habit_questions_are_not_diagnosis_requests(text):
    assert not _DIAG.search(text)


@pytest.mark.parametrize("text", [
    "Is this heart disease?", "could it be a heart attack", "is this thyroid", "do i have diabetes",
    "what is wrong with me", "can you diagnose me"])
def test_real_diagnosis_requests_are_still_caught(text):
    assert _DIAG.search(text)
