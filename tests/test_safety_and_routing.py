import pytest
from app.safety.triage_gate import evaluate_safety_gate, COMPILED_RED_FLAGS
from app.workflow.graph import WorkflowGraph, execute_turn
from app.workflow.state import UserSessionState, MemberProfile
from evaluations.run_evals import normalize_intent

def test_triage_gate_red_flags():
    crisis_cases = [
        "I am feeling a lot of chest tightness and pain",
        "mere seene mein dard ho raha hai",
        "I can't breathe and I think I'm going to faint",
        "my friend just collapsed and is behosh",
        "I feel like I want to die",
        "mein khudkushi karna chahta hu",
        "there's blood in my vomit",
        "I want to end my life now",
    ]
    for text in crisis_cases:
        is_safe, status, payload = evaluate_safety_gate(text, member_id="TEST_USER")
        assert is_safe is False, f"Failed safe check for: {text}"
        assert status == "RED_CRISIS", f"Expected RED_CRISIS for: {text}"
        assert "helplines" in payload

def test_intent_routing_synonyms_and_hinglish():
    member = MemberProfile(member_id="TEST_001", name="Test User", age=30)
    
    lab_inputs = [
        "I need to book a thyroid test",
        "I'm feeling very tired lately, which test should I get?",
        "LP_009 book karo",
        "I need a fever panel",
        "checkup karwana hai",
        "what slots are available?",
    ]
    for text in lab_inputs:
        session = UserSessionState(channel="chat", member=member, active_node="start")
        graph = WorkflowGraph()
        _, updated_session = graph.node_safety_gate(text, session)
        assert updated_session.active_node == "node_lab_booking" or normalize_intent(updated_session.active_node) == "LAB_BOOKING"

    coach_inputs = [
        "How do you do Surya Namaskar?",
        "anulom vilom ke kya fayde hain?",
        "bahut thakan lag rahi hai",
        "mujhe healthy diet plan chahiye",
        "Tell me about Kapalbhati",
    ]
    for text in coach_inputs:
        session = UserSessionState(channel="chat", member=member, active_node="start")
        graph = WorkflowGraph()
        _, updated_session = graph.node_safety_gate(text, session)
        assert updated_session.active_node == "node_program_coach" or normalize_intent(updated_session.active_node) == "PROGRAM_COACH"

def test_pydantic_model_dump_compatibility():
    member = MemberProfile(member_id="M999", name="Model Dump Test", age=45)
    session = UserSessionState(channel="eval", member=member, active_node="start")
    dumped = session.model_dump(mode="json")
    assert isinstance(dumped, dict)
    assert dumped["member"]["member_id"] == "M999"
    assert "booking_draft" in dumped
