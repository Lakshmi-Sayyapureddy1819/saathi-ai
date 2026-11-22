"""Red-flag recall for real-world spellings/inflections, and no over-triggering on ordinary requests.

The safety gate is deterministic regex (no fuzzy matching), so every accepted variant is listed here."""
import pytest

from app.safety.triage_gate import evaluate_safety_gate


def _status(text):
    return evaluate_safety_gate(text, "T")[1]


@pytest.mark.parametrize("text", [
    # cardiac / stroke
    "I have severe chest pain", "chest pian", "chst pain", "chest tightness", "chest heaviness", "hart attack",
    "heart attak", "I think it is a heart attack", "seene me dard", "seene mein dard hai", "sine me dard",
    "seene mein bhaari pan", "dil ka dora", "dil ka daura pada hai", "lakwa", "stroke symptoms",
    # breathing / fainting
    "I can't breathe", "cant breath", "cannot breathe", "breathless", "breathlessness since morning",
    "shortness of breath", "short of breath", "difficulty breathing", "trouble breathing", "struggling to breathe",
    "it is hard to breathe", "he is gasping", "saans nahi aa rahi", "sans nahi aa rahi", "saas phool rahi hai",
    "dum ghut raha hai", "my father fainted", "she is fainting", "I passed out", "he passed out", "unconscious",
    "behoshi", "behosh ho gaya",
    # self-harm
    "suicide", "I am suicidal", "sucide", "suiside", "I want to kill my self", "I want to end it all",
    "I want to die", "I don't want to live", "dont want to live", "no reason to live", "marna chahta hoon",
    "marna chahti hoon", "mar jana chahti hoon", "jeena nahi chahta", "jeene ka mann nahi hai",
    "zindagi khatam karni hai", "khudkushi", "aatmahatya",
    # bleeding
    "bleeding heavily", "bleeding badly", "bleeding a lot", "coughing blood", "vomiting blood",
    "bahut khoon beh raha hai", "khoon ki ulti",
])
def test_emergency_variants_are_caught(text):
    assert _status(text) == "RED_CRISIS", text


@pytest.mark.parametrize("text", [
    "khoon ki jaanch karwani hai", "khoon ka test karwana hai", "mujhe khoon ke test ki booking karni hai",
    "blood test book karo", "book a blood test", "sugar test", "bp check", "I want to book a thyroid test",
    "What yoga helps with exhaustion?", "I feel a little tired today", "Tell me about Kapalbhati",
    "thakan rehti hai", "chest workout tips", "mera chakkar wala mood hai",
])
def test_ordinary_requests_are_not_emergencies(text):
    # "chest workout tips" is deliberately not an emergency: only chest pain/tightness/pressure/heaviness are.
    assert _status(text) != "RED_CRISIS", text


def test_emergency_still_wins_over_a_booking_request():
    assert _status("book a blood test, I also have chest pain") == "RED_CRISIS"


def test_diagnosis_questions_are_still_yellow():
    assert _status("do I have diabetes?") == "YELLOW_WARNING"
    assert _status("what's wrong with me") == "YELLOW_WARNING"
