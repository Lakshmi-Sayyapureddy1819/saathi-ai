
import re
import logging
from typing import Tuple, Dict

from app.observability.redact import redact
from app.safety.alerts import dispatch_emergency
from app.workflow.replies import MSG

# --- Care-team alert (real channels: Telegram / e-mail / Twilio, see app/safety/alerts.py) ---
def dispatch_emergency_sms(member_id: str, details: str):
    """Queue an emergency alert to the care team on every configured channel; never blocks, never raises.

    (Name kept for the callers; delivery is no longer a mock. With no channel configured it logs CRITICAL only, which
    APP_ENV=production refuses to start with.)

    PRIVACY: `details` must never contain the member's own words (health data). Callers pass the crisis category
    and `redact(user_text)` (length + opaque per-process tag), which is enough to correlate and triage.
    """
    category, _, tag = details.partition(";")
    logging.critical("Emergency alert queued for member %s (%s; %s)", member_id, category.strip(), tag.strip())
    try:
        dispatch_emergency(member_id, category.strip(), tag.strip())
    except Exception:  # noqa: BLE001 - the member's emergency reply must never depend on the alert pipeline
        logging.critical("could not queue the emergency alert for member %s (%s)", member_id, category, exc_info=True)
    return {"status": "alert_queued", "details": details}

# --- Compiled Regex for RED_CRISIS Flags ---
# Using \b for word boundaries to avoid matching substrings in larger words.
# Using re.IGNORECASE for broader matching.

COMPILED_RED_FLAGS = {
    # Cardiac / Stroke. Common misspellings and Hinglish spellings are listed explicitly (no fuzzy matching in the
    # safety gate: every accepted variant is visible here and covered by tests/test_red_flag_variants.py).
    "CARDIAC_EMERGENCY": re.compile(
        r"\b((?:chest|chst|chesst|cheast)\s*(?:pain|pian|pane|paine|tightness|pressure|heaviness)|(?:heart|hart)\s*attac?k|"
        r"stroke|lakwa|left\s*arm\s*pain|(?:seene|sine|seeney)\s*(?:mein|me|main|mei)\s*(?:\w+\s+){0,2}(?:dard|jalan|dabav|dabaav|bhaari|bhari)|"
        r"(?:dil|dill)\s*ka\s*(?:daura|dora)|radiating\s*pain|"
        r"chest\s*(?:is\s*)?(?:hurt\w*|ach\w*|burn\w*)|pressure\s*(?:on|in)\s*(?:my\s*)?chest|"
        r"left\s*arm\s*(?:feels?\s*)?(?:numb|heavy)|numb(?:ness)?\s*(?:in|on)\s*(?:my\s*)?left\s*arm|"
        r"(?:chhati|chhaati|chaati|chati)\s*(?:mein|me|main|mei)\s*(?:\w+\s+){0,2}(?:dard|jalan|dabav|dabaav)|"
        r"face\s*(?:is\s*)?droop\w*|slurred\s*speech|speech\s*(?:is\s*)?slurred|sudden\s*weakness|"
        r"weakness\s*(?:on|in)\s*(?:one|the\s*left|the\s*right)\s*side|numbness\s*on\s*one\s*side)\b",
        re.IGNORECASE
    ),
    # Respiratory / Syncope
    "RESPIRATORY_SYNCOPE_EMERGENCY": re.compile(
        r"\b(breathless(?:ness)?|short(?:ness)?\s*of\s*breath|cannot\s*breat?he|can'?t\s*breat?he?|"
        r"(?:difficulty|trouble|struggling|hard)\s*(?:to\s*|in\s*)?breath(?:e|ing)|gasping|"
        r"(?:saans|sans|saas)\s*(?:phool|nahi|ruk)|(?:saans|sans|saas)\s*lene\s*(?:mein|me)\s*(?:\w+\s+){0,2}(?:takleef|dikkat|mushkil)|"
        r"(?:dum|dam)\s*ghut|(?:cannot|can'?t|unable\s*to)\s*(?:catch|get)\s*(?:my|his|her|a)\s*(?:breath|air)|"
        r"chakk?h?ar.{0,40}\bgir\s*(?:gaya|gayi|gaye|jaunga|jaungi)\b|"
        r"faint(?:ed|ing)?|pass(?:ed|ing)?\s*out|unconscious|behosh(?:i)?|chakkhar|collapsed|not\s*breathing)\b",
        re.IGNORECASE
    ),
    # Acute Self-Harm / Suicidal Ideation
    "SELF_HARM_EMERGENCY": re.compile(
        r"\b(suicid(?:e|al)?|sucide|suiside|kill(?:ing)?\s*(?:my\s*self|myself)|end(?:ing)?\s*(?:my\s*life|it\s*all)|want(?:ing)?\s*to\s*die|"
        r"(?:don'?t|dont|do\s*not)\s*want\s*to\s*(?:live|be\s*alive)|no\s*reason\s*to\s*live|"
        r"marna\s*chaht[ai]|mar\s*jan[ae]\s*chaht[ai]|jeena\s*nahi\s*chaht[ai]|jeene\s*ka\s*mann\s*nahi|"
        r"zindagi\s*khatam|aatmahatya|khudkushi|jaan\s*dena|harm\s*myself|nuksan\s*pahuncha|marne\s*ka\s*mann|nuksan\s*karna)\b",
        re.IGNORECASE
    ),
    # Seizure / severe allergic reaction / poisoning or overdose
    "SEIZURE_ALLERGY_POISON_EMERGENCY": re.compile(
        r"\b(seizures?|convulsions?|mirgi|(?:throat|tongue|lips|face)\s*(?:is\s*)?swell\w*|anaphyla\w*|"
        r"(?:swallowed|drank|ate)\s*(?:\w+\s+){0,2}(?:poison|bleach|pesticide)|overdosed|took\s*an?\s*overdose|"
        r"took\s*too\s*many\s*(?:pills|tablets)|zeher\s*(?:kha|pi))\b",
        re.IGNORECASE
    ),
    # Severe Hemorrhage / Vomiting Blood. "khoon" alone is an emergency word, EXCEPT when it is plainly a lab request
    # ("khoon ki jaanch", "khoon ka test"), which is how members ask for a blood test in Hinglish.
    "HEMORRHAGE_EMERGENCY": re.compile(
        r"\b(bleeding\s*(?:heavily|badly|profusely|a\s*lot)|coughing\s*(?:up\s*)?blood|heavy\s*bleeding|"
        r"bleeding\s*(?:that\s*)?(?:will\s*not|won'?t|does\s*not|doesn'?t)\s*stop|vomit.*blood|blood.*vomit|"
        r"khoon(?!\s*(?:ki|ka|ke)\s*(?:jaanch|janch|test|report|checkup|check)\b)|vomiting\s*blood|khoon\s*ki\s*ulti|"
        r"uncontrolled\s*bleeding|severe\s*bleeding|heavy\s*blood\s*loss)\b",
        re.IGNORECASE
    )
}

PATTERNS_RED_CRISIS = COMPILED_RED_FLAGS

# The LLM second stage also flags personal medical-safety questions ("is it safe for someone with high blood pressure?"),
# which the diagnosis wording below does not fit. Same deterministic rule (no medical advice), accurate wording.
YELLOW_PERSONAL_SAFETY_MESSAGE = (
    "I can't give personal medical advice or a diagnosis, so I can't say whether this is safe for you; your doctor can. "
    "I can tell you what our program library says about who should avoid a practice, or help you book a lab test. "
    "What would you like?")

# --- Compiled Regex for YELLOW_WARNING Flags (No Diagnosis Rule) ---
PATTERNS_YELLOW_WARNING = {
    "DIAGNOSIS_REQUEST": re.compile(
        r"\b("
        # "do I have a checkup due / any appointment / a booking ..." asks about the member's own admin records, not
        # about a condition. Only these explicit administrative nouns are exempt; "do I have a tumour" still matches.
        r"do\s+i\s+(?:have|got|hav)\b(?!\s+(?:an?\s+|any\s+|my\s+|the\s+|upcoming\s+|pending\s+)*"
        r"(?:check-?ups?|appointments?|bookings?|lab\s+tests?|tests?\s+(?:booked|due|scheduled)|packages?|reports?|"
        r"programs?|goals?|slots?|sessions?|reminders?|plans?|due|pending|upcoming)\b)"
        r"|(?:if|whether)\s+i\s+(?:have|got|am\s+suffering\s+from)\b"
        r"|am\s+i\s+(?:suffering\s+from|diabetic|sick|ill|dying)"
        r"|(?:is|could|might|can)\s+(?:this|it|that)\s+(?:(?:be|mean|a\s+sign\s+of)\s+)?(?:a\s+|an\s+)?"
        r"(?:cancer|diabetes|diabetic|malaria|dengue|thyroid|typhoid|covid|tb|tumou?r|infection|disease|heart)"
        # "is it heart healthy / heart friendly / thyroid safe ..." asks about food or habits, not about a diagnosis
        r"(?!\s*(?:healthy|friendly|safe|good|smart|diet|food|health))"
        r"|what\s+(?:disease|illness|condition)\s+do\s+i\s+have"
        r"|what(?:'s|\s+is)\s+wrong\s+with\s+me"
        r"|(?:diagnose|diagnosis)\b"
        r"|tell\s+me\s+(?:my|what)\s+(?:illness|disease|condition)"
        r"|mujhe\s+(?:\w+\s+)?(?:hai\s+kya|ho\s+gaya\s+hai\s+kya|ki\s+bimari\s+hai)"
        r"|kya\s+mujhe\s+\w+\s+(?:hai|ho\s+sakta)"
        r"|mujhe\s+(?:\w+\s+){0,2}hai\s+ya\s+nahi"
        r"|(?:which|what)\s+(?:medicine|medication|tablet|drug|pill)s?\s+(?:should|can|do)\s+i\s+(?:take|use|have)"
        r"|should\s+i\s+(?:take|stop|start|increase|skip)\s+(?:\w+\s+){0,2}(?:medicine|medication|tablets?|pills?|"
        r"metformin|insulin|thyroxine|levothyroxine|statins?|paracetamol|antibiotics?)"
        r"|(?:konsi|kaun\s*si)\s+(?:dawa|dawai|medicine|tablet)"
        r")",
        re.IGNORECASE,
    )
}

# --- National Helpline Information ---
HELPLINE_PAYLOAD = {
    # Wording lives in app/workflow/replies.py (English + Hinglish). The red-flag detection above is untouched.
    "message": MSG["emergency"][0],
    "helplines": {
        "National Emergency Number": "112",
        "Medical Helpline": "108",
        "Tele-MANAS (Mental Health)": "14416"
    }
}

# --- Fast transactional/booking bypass for safety gate latency ---
_TRANSACTIONAL_OR_SHORT = re.compile(
    r"^(\s*("
    r"yes(\s+confirm)?|confirm|haan|sure|ok|okay|yep|yup|done|fine|alright|"
    r"no|nahi|nahin|cancel|stop|ruko|change(\s+time)?|reschedule|"
    r"\d{1,2}(:\d{2})?\s*(am|pm|baje|bje|o'?clock)?|"
    r"today|tomorrow|aaj|kal(\s+subah|\s+shaam)?|parso|day\s+after\s+tomorrow|subah|shaam|morning|evening|"
    r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|thirty|forty|fifty|"
    r"half\s+past\s+\w+|quarter\s+past\s+\w+|\w+\s+thirty|\w+\s+am|\w+\s+pm|"
    r"lp_\d+|bok_\w+|the\s+\w+\s+one|thyroid|vitamin|cardiac|diabetic|package|test|blood\s+test|full\s+body|book\s+.*|"
    r"hi|hello|hey|namaste|thanks|thank\s+you"
    r")\s*)+$",
    re.IGNORECASE,
)

SAFETY_PROMPT = """You are a medical safety classifier for a wellness app. 
Analyze this user input: "{user_text}"
Decide if it represents:
- RED_CRISIS: acute medical emergency (severe chest pain, stroke, fainting, breathlessness, self-harm/suicide, heavy bleeding).
- YELLOW_WARNING: user explicitly asking for a medical diagnosis, medical interpretation of symptoms, or asking "do I have X disease/condition".
- GREEN_NORMAL: safe, e.g. booking a lab test, selecting a package name or time slot, or wellness question (yoga, diet, sleep). Note: mentioning a test name (e.g. "the thyroid one", "diabetes test") to book a test is GREEN_NORMAL, NOT a warning.

Reply strictly with one of:
RED_CRISIS
YELLOW_WARNING
GREEN_NORMAL
"""

def evaluate_safety_gate(user_text: str, member_id: str = "MEM_UNKNOWN", model_client: "ModelClient" = None) -> Tuple[bool, str, Dict]:
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

    # Fast path: transactional booking, slot, confirmation or package selection does not need second-stage LLM
    if _TRANSACTIONAL_OR_SHORT.match(user_text.strip()):
        return (True, "GREEN_NORMAL", {"message": "Input is within normal operational parameters."})

    # Fast path: general wellness/lifestyle queries with no crisis or diagnosis intent do not need second-stage LLM
    if re.search(r"\b(yoga|asana|pranayama|surya\s+namaskar|anulom\s+vilom|kapalbhati|meditation|dhyan|breathing|"
                 r"diet|food|nutrition|calorie|recipe|khana|aahar|sleep|neend|stress|exercise|workout|walk|"
                 r"hydration|water|paani|weight|lifestyle|wellness)\b", user_text, re.I):
        return (True, "GREEN_NORMAL", {"message": "Input is within normal operational parameters."})
            
    # 3. LLM second stage
    if model_client:
        prompt = SAFETY_PROMPT.format(user_text=user_text)
        try:
            from google.adk.models import LlmRequest
            from google.genai.types import Content, Part
            from app.workflow.gateway import ADKModelGateway

            gateway = model_client if isinstance(model_client, ADKModelGateway) else ADKModelGateway(client=model_client)
            req = LlmRequest(contents=[Content(role="user", parts=[Part(text=prompt)])], model="gateway")
            resp = gateway.generate_request(req)
            llm_result = ("".join(p.text for p in resp.content.parts if p.text) if resp.content and resp.content.parts else "").strip()
            if "RED_CRISIS" in llm_result:
                logging.warning(f"RED_CRISIS Triggered by LLM for member {member_id}")
                dispatch_emergency_sms(member_id, f"LLM_ESCALATION; message {redact(user_text)}")
                return (False, "RED_CRISIS", HELPLINE_PAYLOAD)
            if "YELLOW_WARNING" in llm_result:
                logging.info(f"YELLOW_WARNING Triggered by LLM for member {member_id}")
                payload = {
                    "message": YELLOW_PERSONAL_SAFETY_MESSAGE,
                    "action": "steer_to_diagnostics"
                }
                return (True, "YELLOW_WARNING", payload)
        except Exception as e:
            logging.error(f"LLM safety gate failed: {e}")

    # 4. If no flags, it's GREEN_NORMAL
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
