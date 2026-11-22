
import re
import logging
from typing import Tuple, Dict

from app.observability.redact import redact

# --- Mock Twilio Dispatcher ---
def dispatch_emergency_sms(member_id: str, details: str):
    """Mocks a Twilio API call to dispatch an emergency SMS.

    PRIVACY: `details` must never contain the member's own words (health data). Callers pass the crisis category
    and `redact(user_text)` (length + opaque per-process tag), which is enough to correlate and triage.
    """
    alert = f"[SAFETY GATE] RED CRISIS for member {member_id} -> emergency contacts notified ({details})"
    logging.critical("Emergency SMS dispatched: %s", alert)
    return {"status": "sms_dispatched", "details": details}

# --- Compiled Regex for RED_CRISIS Flags ---
# Using \b for word boundaries to avoid matching substrings in larger words.
# Using re.IGNORECASE for broader matching.

COMPILED_RED_FLAGS = {
    # Cardiac / Stroke
    "CARDIAC_EMERGENCY": re.compile(
        r'\b(chest\s*(pain|tightness|pressure)|heart\s*attack|stroke|left\s*arm\s*pain|seene\s*mein\s*(dard|jalan|dabav)|dil\s*ka\s*daura|radiating\s*pain)\b',
        re.IGNORECASE
    ),
    # Respiratory / Syncope
    "RESPIRATORY_SYNCOPE_EMERGENCY": re.compile(
        r"\b(breathless|shortness\s*of\s*breath|cannot\s*breathe|can'?t\s*breathe|saans\s*(phool|nahi|ruk|lene\s*mein\s*takleef)|faint|unconscious|behosh|chakkhar|collapsed|not\s*breathing)\b",
        re.IGNORECASE
    ),
    # Acute Self-Harm / Suicidal Ideation
    "SELF_HARM_EMERGENCY": re.compile(
        r'\b(suicid|kill\s*myself|end\s*my\s*life|want\s*to\s*die|marna\s*chahta|khudkushi|jaan\s*dena|harm\s*myself|nuksan\s*pahuncha|marne\s*ka\s*mann|nuksan\s*karna)\b',
        re.IGNORECASE
    ),
    # Severe Hemorrhage / Vomiting Blood
    "HEMORRHAGE_EMERGENCY": re.compile(
        r'\b(bleeding\s*heavily|coughing\s*blood|vomit.*blood|blood.*vomit|khoon|vomiting\s*blood|khoon\s*ki\s*ulti|uncontrolled\s*bleeding|severe\s*bleeding|heavy\s*blood\s*loss)\b',
        re.IGNORECASE
    )
}

PATTERNS_RED_CRISIS = COMPILED_RED_FLAGS

# --- Compiled Regex for YELLOW_WARNING Flags (No Diagnosis Rule) ---
PATTERNS_YELLOW_WARNING = {
    "DIAGNOSIS_REQUEST": re.compile(
        r"\b("
        r"do\s+i\s+(?:have|got|hav)\b"
        r"|(?:if|whether)\s+i\s+(?:have|got|am\s+suffering\s+from)\b"
        r"|am\s+i\s+(?:suffering\s+from|diabetic|sick|ill|dying)"
        r"|(?:is|could|might|can)\s+(?:this|it|that)\s+(?:(?:be|mean|a\s+sign\s+of)\s+)?(?:a\s+|an\s+)?"
        r"(?:cancer|diabetes|diabetic|malaria|dengue|thyroid|typhoid|covid|tb|tumou?r|infection|disease|heart)"
        r"|what\s+(?:disease|illness|condition)\s+do\s+i\s+have"
        r"|what(?:'s|\s+is)\s+wrong\s+with\s+me"
        r"|(?:diagnose|diagnosis)\b"
        r"|tell\s+me\s+(?:my|what)\s+(?:illness|disease|condition)"
        r"|mujhe\s+(?:\w+\s+)?(?:hai\s+kya|ho\s+gaya\s+hai\s+kya|ki\s+bimari\s+hai)"
        r"|kya\s+mujhe\s+\w+\s+(?:hai|ho\s+sakta)"
        r")",
        re.IGNORECASE,
    )
}

# --- National Helpline Information ---
HELPLINE_PAYLOAD = {
    "message": "It sounds like you are in a serious situation. Please contact emergency services immediately.",
    "helplines": {
        "National Emergency Number": "112",
        "Medical Helpline": "108",
        "Tele-MANAS (Mental Health)": "14416"
    }
}

def evaluate_safety_gate(user_text: str, member_id: str = "MEM_UNKNOWN") -> Tuple[bool, str, Dict]:
    # 1. Check for RED_CRISIS
    for crisis_type, pattern in COMPILED_RED_FLAGS.items():
        if pattern.search(user_text):
            logging.warning(f"RED_CRISIS Triggered: {crisis_type} for member {member_id}")
            dispatch_emergency_sms(member_id, f"{crisis_type}; message {redact(user_text)}")
            return (False, "RED_CRISIS", HELPLINE_PAYLOAD)


    # 2. Check for YELLOW_WARNING (No Diagnosis Rule)
    for warning_type, pattern in PATTERNS_YELLOW_WARNING.items():
        if pattern.search(user_text):
            logging.info(f"YELLOW_WARNING Triggered: {warning_type} for member {member_id}")
            payload = {
                "message": "I understand you're looking for answers, but as an AI assistant, I can't provide a medical diagnosis. The best course of action is to get a proper diagnostic test. I can help you book a lab package that covers these symptoms. Would you like to see some options?",
                "action": "steer_to_diagnostics"
            }
            return (True, "YELLOW_WARNING", payload)

    # 3. If no flags, it's GREEN_NORMAL
    return (True, "GREEN_NORMAL", {"message": "Input is within normal operational parameters."})

# Example Usage:
if __name__ == '__main__':
    # RED CRISIS Examples
    print(evaluate_safety_gate("I have severe chest pain and it's radiating to my arm", "MEM_123"))
    print(evaluate_safety_gate("mere seene mein bahut dard ho raha hai", "MEM_123"))
    print(evaluate_safety_gate("my father fainted and is unconscious", "MEM_456"))
    print(evaluate_safety_gate("I want to end my life, I can't take it anymore", "MEM_789"))
    
    # YELLOW WARNING Example
    print(evaluate_safety_gate("I have been feeling tired, do I have diabetes?", "MEM_101"))

    # GREEN NORMAL Example
    print(evaluate_safety_gate("I want to book a full body checkup", "MEM_202"))
