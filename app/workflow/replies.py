"""User-facing wording for deterministic replies, in English and Hinglish (Roman-script Hindi).

All booking/handoff/emergency wording lives here so tone is reviewed in one place. Hinglish lines are written in
the polite "aap" form and avoid gendered verb endings, so they read correctly for any speaker.

Language is chosen per member from what they type (see `detect_lang`), never from an LLM, so it is deterministic.
"""
import re
from typing import Literal

Lang = Literal["en", "hinglish"]

# Distinctive Hinglish words only. Words that are also common English ("do", "to", "me", "so") are left out so an
# English sentence is never mistaken for Hinglish.
_HINGLISH = frozenset("""
hai hain hoon nahi nahin haan haa ji kya kyun kyu mujhe mujhko mera meri mere aap aapka aapki aapko chahiye chahta
chahti karo karna karwana karwani karvana karvani kar kardo kal aaj parso baje subah shaam dard bukhar jaanch janch
thakan madad batao bataiye bataye theek thik accha acha rehne rahne ruko kaise kitna kitne mein wala wali dena
dijiye kijiye karein sakta sakti raha rahi hoga hogi lagta lagti ka ke ki ko liye bhi toh aur
""".split())


GREETING = re.compile(
    r"^\s*(hi+|hello+|hey+|hiya|namaste|namaskar|good\s+(morning|afternoon|evening)|howdy)"
    r"(\s+(there|saathi|team|ji|to\s+you))?"
    r"(\s*,?\s*(how\s+are\s+you|how\s+r\s+u|how's\s+it\s+going|kaise\s+ho|kya\s+haal\s+hai|sab\s+theek))?\s*[!.?,]*\s*$",
    re.I
)
THANKS = re.compile(
    r"^\s*(many\s+thanks|bahut\s+shukriya|thanks?|thank\s+(you|u)|thx|shukriya|dhanyavaad|dhanyawad)"
    r"(\s+(a\s+lot|so\s+much|very\s+much|saathi|ji|again))?\s*[!.?]*\s*$",
    re.I
)
CLOSING = re.compile(
    r"^\s*(no\s*(thanks?|thank\s+(you|u))?|nothing(\s+else)?|that'?s\s+all|nope|nahi(\s+shukriya)?|kuch\s+nahi|bas(\s+itna\s+hi)?|bye|goodbye|bye\s+bye|take\s+care|see\s+you|alvida)\s*[!.?]*\s*$",
    re.I
)
VOICE_CHECK = re.compile(
    r"\b(can\s+you\s+hear\s+(me)?|are\s+you\s+(there|listening)|hear\s+me|"
    r"sun\s+rahe\s+ho|awaaz\s+aa\s+rahi\s+hai|kya\s+tum\s+sun\s+rahe\s+ho|"
    r"mic\s+test|mic\s+check|audio\s+check|sound\s+check|"
    r"who\s+are\s+you|what\s+can\s+you\s+do|voice\s+agent)\b",
    re.I
)


def detect_lang(text: str, previous: Lang = "en") -> Lang:
    """Hinglish if any distinctive Hinglish word is present; English if the message is a clear English sentence
    (3+ words, none Hinglish); otherwise keep the previous language ("9:30 am", "yes" carry no language signal)."""
    words = re.findall(r"[a-z]+", text.lower())
    if any(w in _HINGLISH for w in words):
        return "hinglish"
    if len(words) >= 3:
        return "en"
    return previous


# key -> (English, Hinglish). Placeholders use str.format. English strings are relied on by tests and the web UI.
MSG: dict[str, tuple[str, str]] = {
    "greeting": (
        "Hello! 😊 I'm Saathi, your care companion. I can help with yoga, diet and lifestyle questions, "
        "book a lab test, or connect you with a care coordinator. What would you like to do today?",
        "Namaste! 😊 Main Saathi hoon, aapki care companion. Main yoga, diet aur lifestyle ke sawaalon mein, lab test "
        "book karne mein, ya care coordinator se jodne mein madad kar sakti hoon. Aaj aap kya karna chahenge?"),
    "thanks": (
        "You're most welcome! Is there anything else I can help you with?",
        "Aapka swagat hai! Kya aur kisi cheez mein madad chahiye?"),
    "closing": (
        "You're welcome! Take care and stay healthy. Feel free to reach out whenever you need assistance! 😊",
        "Aapka swagat hai! Apna khayal rakhein, aur jab bhi zaroorat ho, Saathi hamesha yahan hai. Aapka din shubh ho! 😊"),
    "coach_empty": (
        "I'm sorry, I couldn't find that in our program library. I'd be happy to connect you with a care "
        "coordinator or help you book a lab package.",
        "Maaf kijiye, yeh hamari program library mein mujhe nahi mila. Aap chahein toh hum aapko care coordinator "
        "se jod dete hain, ya lab package book karne mein madad kar dete hain."),
    "voice_check": (
        "Yes, I can hear you loud and clear! 😊 I'm Saathi, your care companion. I can help you book a lab test "
        "(like a thyroid screening or full body checkup) or answer questions on diet, yoga, and sleep. "
        "What would you like to do?",
        "Haan ji, main aapko bilkul saaf sun sakti hoon! 😊 Main Saathi hoon. Main lab test book karne mein "
        "ya yoga aur diet jaise wellness sawaalon mein aapki madad kar sakti hoon. Batayiye, aaj kya karna chahenge?"),
    "voice_clarify": (
        "I'm here! I didn't quite catch that. Would you like to book a lab test, check available packages, or ask about wellness?",
        "Main sun rahi hoon! Mujhe theek se samajh nahi aaya. Kya aap lab test book karna chahte hain, ya koi wellness sawaal poochna chahte hain?"),
    "handoff": (
        "I've asked a care coordinator to step in, and they will follow up with you shortly. Thank you for your patience.",
        "Humne ek care coordinator ko is mamle mein jod diya hai, woh jaldi hi aapse sampark karenge. Aapke intezaar ke "
        "liye shukriya."),
    "cancelled_pick": (
        "Of course, I've cancelled that. Is there anything else I can help you with?",
        "Theek hai, maine woh cancel kar diya. Kya aur kisi cheez mein madad chahiye?"),
    "cancelled_booking": (
        "No problem, I've cancelled that booking. Is there anything else I can help you with?",
        "Koi baat nahi, booking cancel kar di gayi hai. Kya aur kisi cheez mein madad chahiye?"),
    "start_over": (
        "I'm sorry, I'm still not sure which package you mean, so let's start over. Which test would you like to book?",
        "Maaf kijiye, mujhe abhi bhi samajh nahi aaya ki aap kaun sa package chahte hain, isliye hum dobara shuru "
        "karte hain. Aap kaun si jaanch book karwana chahenge?"),
    "lead_time": ("Thank you, I've noted your preferred time. ",
                  "Shukriya, aapka pasandida samay note kar liya hai. "),
    "lead_ambiguous": ("Thanks! That could match more than one package. ",
                       "Shukriya! Yeh ek se zyada package se match ho raha hai. "),
    "lead_unknown": ("Sorry, I didn't recognise that as one of the options. ",
                     "Maaf kijiye, yeh mujhe options mein se koi nahi laga. "),
    "which_package": (
        "{lead}Which package is it for?\n{lines}\nYou can reply with the name or the ID (for example, {example}).",
        "{lead}Yeh kaun se package ke liye hai?\n{lines}\nAap naam ya ID (jaise {example}) bata sakte hain."),
    "ask_test": (
        "I'd be happy to help you book a test. Which test would you like to book? For example:\n{lines}\n"
        "Or, if you're not sure, tell me about a symptom and I'll look for a suitable package.",
        "Zaroor, hum aapki madad karenge. Aap kaun si jaanch book karwana chahenge? Jaise:\n{lines}\n"
        "Ya agar aapko pata nahi hai, toh apni takleef bataiye, hum sahi package dhoondhne ki koshish karenge."),
    "none_found": (
        "I'm sorry, I couldn't find a lab package matching that. Could you tell me the name of the test, or describe a symptom?",
        "Maaf kijiye, is naam ka koi lab package mujhe nahi mila. Kya aap jaanch ka naam bata sakte hain, ya apni "
        "takleef bata sakte hain?"),
    "few_found": (
        "I found a few packages that could match:\n{lines}\nWhich one would you like?",
        "Mujhe kuch packages mile jo match ho sakte hain:\n{lines}\nAap kaun sa chunenge?"),
    "no_slots": (
        "I'm sorry, there are no slots available for that package on that day. Would you like to try another day or a different package?",
        "Maaf kijiye, us din is package ke liye koi slot khaali nahi hai. Kya aap koi aur din ya doosra package "
        "dekhna chahenge?"),
    "confirm_q": (
        "Just to confirm, I have {pkg} on {day} at {slot}. Shall I go ahead and book it? (yes/no)",
        "Bas ek baar confirm kar lein: {pkg}, {day}, {slot} par. Kya booking kar di jaye? (haan/nahi)"),
    "slot_unclear": ("Sorry, I couldn't quite catch that time. ",
                     "Maaf kijiye, samay theek se samajh nahi aaya. "),
    "slot_unavailable": ("I'm sorry, that time isn't available for this test. ",
                         "Maaf kijiye, yeh samay is jaanch ke liye available nahi hai. "),
    "llm_down": (
        "I'm sorry, my AI assistant isn't responding right now, so I can't put together a full answer. Here is what "
        "our program library says:\n{context}\n\nPlease try again in a minute. I can still help you book a lab test, "
        "or connect you with a care coordinator.",
        "Maaf kijiye, abhi hamara AI assistant jawab nahi de pa raha, isliye poora jawab nahi bana paaye. Hamari "
        "program library mein yeh likha hai:\n{context}\n\nKripya ek minute baad dobara koshish karein. Tab tak hum "
        "lab test book karne mein ya care coordinator se jodne mein madad kar sakte hain."),
    "slot_unavailable_fasting": (
        "I'm sorry, that time isn't available for this test. It needs fasting, so slots are early in the morning. ",
        "Maaf kijiye, yeh samay is jaanch ke liye available nahi hai. Isme khaali pet rehna hota hai, isliye slots "
        "subah jaldi ke hain. "),
    "slots_list": (
        "{prefix}Available slots for {pkg} on {day}:\n{slots}\nWhich time works best for you?",
        "{prefix}{day} ko {pkg} ke liye yeh slots khaali hain (Available slots):\n{slots}\nAapko kaun sa samay theek rahega?"),
    "reconfirm": (
        "I have {pkg} on {date} at {slot}. Could you please say 'yes' to confirm, or 'no' to cancel?",
        "{pkg}, {date}, {slot} par hai. Kripya 'haan' bolkar confirm karein, ya 'nahi' bolkar cancel karein."),
    "booked": (
        "Booking confirmed! Your booking ID is {id}. Thank you for choosing Saathi, and please let me know if there's anything else I can help with.",
        "Booking confirm ho gayi! Aapka booking ID hai {id}. Saathi chunne ke liye shukriya. Kuch aur madad chahiye "
        "toh bataiye."),
    "outage": (
        "I'm sorry, we couldn't complete your booking right now. A care coordinator will call you back within 15 minutes. (Ticket {ticket}) {handoff}",
        "Maaf kijiye, abhi hum aapki booking poori nahi kar paaye. Ek care coordinator 15 minute ke andar aapko call "
        "karenge. (Ticket {ticket}) {handoff}"),
    "slot_taken": (
        "I'm sorry, that slot was just taken. Could you please pick another time?",
        "Maaf kijiye, yeh slot abhi kisi aur ne le liya. Kya aap koi doosra samay chunenge?"),
    "booking_error": (
        "I'm sorry, something went wrong with the booking. Please try again.",
        "Maaf kijiye, booking mein kuch gadbad ho gayi. Kripya dobara koshish karein."),
    "approved": (
        "Good news: a care coordinator has approved {ticket} and will call you shortly to arrange your test. {note}",
        "Achhi khabar: care coordinator ne {ticket} ko approve kar diya hai, woh jaldi call karke aapki jaanch arrange "
        "karenge. {note}"),
    "rejected": (
        "I'm sorry, the care coordinator couldn't complete that booking. {note}Would you like to choose a different time?",
        "Maaf kijiye, care coordinator yeh booking poori nahi kar paaye. {note}Kya aap koi doosra samay chunna chahenge?"),
    "emergency": (
        "I'm really sorry you're going through this. What you describe could be serious, so please call emergency "
        "services now or go to the nearest hospital. You don't have to face this alone. If someone is nearby, please "
        "ask them to stay with you.",
        "Mujhe afsos hai ki aap is takleef se guzar rahe hain. Jo aap bata rahe hain woh gambhir ho sakta hai, isliye "
        "kripya abhi emergency number par call karein ya sabse paas ke aspatal jayein. Aap akele nahi hain. Agar koi "
        "aapke paas hai, toh unse kahiye ki woh aapke saath rahein."),
    "cancel_done": (
        "Done. I've cancelled your booking {id} ({pkg}, {date} at {slot}), and that slot is free again. Is there anything else I can help you with?",
        "Ho gaya. Aapki booking {id} ({pkg}, {date}, {slot}) cancel kar di gayi hai, aur woh slot phir se khaali hai. "
        "Kya aur kisi cheez mein madad chahiye?"),
    "cancel_which_one": (
        "I can cancel your booking {id}: {pkg} on {date} at {slot}. To go ahead, please reply 'cancel {id}'.",
        "Hum aapki booking {id} cancel kar sakte hain: {pkg}, {date}, {slot}. Aage badhne ke liye kripya 'cancel {id}' likhein."),
    "cancel_which_many": (
        "You have these bookings:\n{lines}\nWhich one should I cancel? Please reply 'cancel' followed by the booking ID.",
        "Aapki yeh bookings hain:\n{lines}\nKaun si cancel karni hai? Kripya 'cancel' ke saath booking ID likhein."),
    "cancel_not_found": (
        "I'm sorry, I couldn't find an active booking with that ID. It may already have been cancelled.",
        "Maaf kijiye, is ID ki koi active booking mujhe nahi mili. Ho sakta hai woh pehle hi cancel ho chuki ho."),
    "cancel_unavailable": (
        "I couldn't reach the lab partner to cancel that booking, so it is NOT cancelled yet. Please try again in a few minutes, or I can connect a care coordinator.",
        "Lab partner tak pahunch nahi paaye, isliye booking abhi cancel NAHI hui hai. Kripya kuch der baad dobara koshish karein, ya main care coordinator se jod sakta hoon."),
    "my_bookings": (
        "Here are your lab bookings:\n{lines}\nIf you want to cancel one, reply 'cancel' followed by the booking ID.",
        "Aapki lab bookings yeh hain:\n{lines}\nAgar koi cancel karni hai, toh 'cancel' ke saath booking ID likhein."),
    "no_bookings": (
        "You don't have any lab bookings yet. Would you like to book a test?",
        "Aapki abhi koi lab booking nahi hai. Kya aap koi jaanch book karwana chahenge?"),
    "nothing_to_confirm": (
        "There's no booking waiting for your confirmation right now. Tell me which test you'd like and I'll set it up.",
        "Abhi aapki koi booking confirmation ke liye pending nahi hai. Aap kaun si jaanch chahte hain, bataiye, hum book kar denge."),
    "helplines": ("Helplines:", "Helpline numbers:"),
}


def say(lang: Lang, key: str, **kw: str) -> str:
    en, hi = MSG[key]
    return (hi if lang == "hinglish" else en).format(**kw)


# ---- detectors: tests and evaluation scripts must not depend on exact wording ----------------------------------
def _lead(key: str, i: int) -> str:
    return MSG[key][i].split("{")[0].strip()[:60]


def is_llm_down_reply(text: str) -> bool:
    """True for the degraded reply shown when the model could not be reached (not a real model answer). Evaluation
    scripts use this to count it as an ERROR instead of scoring it. Also matches the pre-rewording text."""
    t = text.lstrip()
    return t.startswith(_lead("llm_down", 0)) or t.startswith(_lead("llm_down", 1)) \
        or t.startswith("Here is what our library says")


def is_no_context_reply(text: str) -> bool:
    """True for the 'not in our program library' reply (no retrieval hit, so no model answer was attempted)."""
    t = text.lstrip()
    return t.startswith(_lead("coach_empty", 0)) or t.startswith(_lead("coach_empty", 1)) or "I don't have" in t
