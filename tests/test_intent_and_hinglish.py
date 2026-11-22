"""Everyday/short/misspelled input is understood by intent; replies follow the member's language; emergency wording
is warm but detection and helplines are unchanged."""
import pytest

from app.safety.triage_gate import evaluate_safety_gate
from app.tools.lab_tools import LabTools
from app.tools.slots import is_confirmation
from app.workflow.graph import WorkflowGraph, execute_turn
from app.workflow.replies import MSG, detect_lang, say
from app.workflow.state import MemberProfile, UserSessionState


def _setup():
    g = WorkflowGraph()
    g.lab_tools = LabTools(failure_rate=0.0)
    s = UserSessionState(channel="chat", member=MemberProfile(member_id="IH1", name="T", age=30), active_node="start")
    return g, s


def _say(g, s, *msgs):
    out = ""
    for m in msgs:
        out, s = execute_turn(m, s, graph=g)
    return out, s


# ---------------- intent from everyday words ----------------
@pytest.mark.parametrize("msg,package", [
    ("sugar test", "Advanced Diabetic Profile"),
    ("shugar check karwana hai", "Advanced Diabetic Profile"),
    ("mujhe sugar ki jaanch karwani hai", "Advanced Diabetic Profile"),
    ("thyroid", "Thyroid Screening Profile"),
    ("throid", "Thyroid Screening Profile"),
    ("bp check", "Cardiac Risk Assessment"),
    ("heart ka test", "Cardiac Risk Assessment"),
    ("dengue", "Fever & Infection Panel"),
    ("shaadi ke liye checkup", "Pre-Wedding Health Screen"),
    ("full body checkup", "Comprehensive Full Body Blood Checkup"),
    ("vitamn d", "Vitamin D & B12 Panel"),
    ("kidny test", "Liver & Kidney Function Panel"),
])
def test_everyday_words_find_the_right_package(msg, package):
    g, s = _setup()
    _, s = _say(g, s, msg)
    assert s.active_node == "node_lab_booking" and s.booking_draft.package_name == package


def test_wellness_words_still_go_to_the_coach():
    g, s = _setup()
    _, s = _say(g, s, "less sugar in my diet")
    assert s.active_node == "node_program_coach"
    g, s = _setup()
    _, s = _say(g, s, "what yoga helps with stress")
    assert s.active_node == "node_program_coach"


def test_unrecognised_reply_mid_booking_keeps_the_draft():
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test", "9 am", "okay maybe")
    assert s.active_node == "node_lab_booking" and s.booking_draft.package_name == "Thyroid Screening Profile"
    assert s.member.past_bookings == [] and "yes" in out.lower()  # re-asks politely, books nothing
    out, s = _say(g, s, "yes")
    assert "Booking confirmed" in out


@pytest.mark.parametrize("yes", ["ok", "okay", "sure", "yess", "yeahh", "kar do", "haan ji", "ji haan", "Yes please"])
def test_casual_yes_confirms(yes):
    assert is_confirmation(yes)


@pytest.mark.parametrize("no", ["okay maybe", "book", "no", "ok wait", "ruko", "mat karo", "rehne do", "yes no wait"])
def test_not_a_yes(no):
    assert not is_confirmation(no)


@pytest.mark.parametrize("word", ["rehne do", "mat karo", "chhodo"])
def test_hinglish_cancel_words(word):
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test", "9 am", word)
    assert s.booking_draft.package_id is None and s.member.past_bookings == []


# ---------------- language follows the member ----------------
def test_detect_lang():
    assert detect_lang("mujhe thyroid test karwana hai") == "hinglish"
    assert detect_lang("Book a blood test") == "en"
    assert detect_lang("9:30 am", "hinglish") == "hinglish"   # no signal: keep
    assert detect_lang("yes", "en") == "en"
    assert detect_lang("please book my thyroid test tomorrow", "hinglish") == "en"  # clear English sentence: switch


def test_full_hinglish_booking_conversation():
    g, s = _setup()
    out, s = _say(g, s, "mujhe blood test karwana hai")
    assert s.reply_lang == "hinglish" and "Aap kaun si jaanch" in out
    out, s = _say(g, s, "thyroid")
    assert "slots khaali" in out
    out, s = _say(g, s, "kal subah 9 baje")
    assert "confirm" in out and "haan/nahi" in out
    out, s = _say(g, s, "haan ji")
    assert "Booking confirm ho gayi" in out and "BOK_IH1_" in out
    assert any("09:00 AM" in b for b in s.member.past_bookings)


def test_english_conversation_stays_english():
    g, s = _setup()
    out, s = _say(g, s, "Book a blood test", "thyroid", "9 am", "yes")
    assert s.reply_lang == "en" and "Booking confirmed" in out


def test_hinglish_cancel_and_unavailable_time():
    g, s = _setup()
    out, s = _say(g, s, "mujhe thyroid test karwana hai", "9 pm")
    assert "available nahi" in out
    out, s = _say(g, s, "rehne do")
    assert "cancel" in out.lower() and s.booking_draft.package_id is None


def test_every_message_has_both_languages_and_matching_placeholders():
    import re
    for key, (en, hi) in MSG.items():
        assert en.strip() and hi.strip(), key
        assert set(re.findall(r"{(\w+)}", en)) == set(re.findall(r"{(\w+)}", hi)), key
    assert say("hinglish", "cancelled_booking") != say("en", "cancelled_booking")


@pytest.mark.parametrize("msg", ["khoon ki jaanch karwani hai", "khoon ka test karwana hai", "janch karwani hai"])
def test_hinglish_blood_test_request_asks_which_test(msg):
    g, s = _setup()
    out, s = _say(g, s, msg)
    assert s.triage_status.status != "RED_CRISIS" and s.reply_lang == "hinglish"
    assert s.active_node == "node_lab_booking" and s.booking_draft.candidate_package_ids
    assert "kaun si jaanch" in out


def test_fasting_test_explains_why_nine_is_not_offered():
    g, s = _setup()
    out, s = _say(g, s, "sugar test", "9 am")
    assert "isn't available" in out and "fasting" in out and "07:00 AM" in out
    out, s = _say(g, s, "kal subah 9 baje")
    assert "available nahi" in out and "khaali pet" in out and s.booking_draft.selected_slot is None
    out, s = _say(g, s, "7:30 am")  # a real fasting slot still works
    assert "07:30 AM" in out and s.booking_draft.selected_slot == "07:30 AM"


# ---------------- emergency: warmer wording, same detection ----------------
def test_emergency_message_is_warm_and_keeps_helplines():
    ok, status, payload = evaluate_safety_gate("I have severe chest pain", "T")
    assert (ok, status) == (False, "RED_CRISIS")
    assert "sorry" in payload["message"].lower() and "emergency" in payload["message"].lower()
    assert set(payload["helplines"].values()) == {"112", "108", "14416"}


def test_hinglish_emergency_reply_has_hinglish_wording_and_helplines():
    g, s = _setup()
    out, s = _say(g, s, "mere seene mein dard hai")
    assert s.triage_status.status == "RED_CRISIS" and "afsos" in out and "112" in out
    assert "afsos" in s.emergency_payload.message and "112" in s.emergency_payload.helplines.values()


def test_english_emergency_reply():
    g, s = _setup()
    out, s = _say(g, s, "I can't breathe")
    assert s.triage_status.status == "RED_CRISIS" and "sorry" in out.lower() and "112" in out


def test_safety_gate_wins_over_booking_context():
    g, s = _setup()
    out, s = _say(g, s, "book thyroid test", "9 am", "mujhe seene mein dard hai")
    assert s.triage_status.status == "RED_CRISIS" and s.booking_draft.package_id is None
