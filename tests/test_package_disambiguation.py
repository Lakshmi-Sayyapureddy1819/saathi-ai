"""Regression tests for LB-SEQ-008: a short follow-up must answer the pending 'which package?' question
instead of being re-run as a fresh catalogue search (which lost the whole conversation)."""
from app.tools.lab_tools import LabTools
from app.workflow.graph import WorkflowGraph, execute_turn
from app.workflow.state import MemberProfile, UserSessionState


def _g():
    g = WorkflowGraph()
    g.lab_tools = LabTools(failure_rate=0.0)
    return g


def _s(mid="DIS1"):
    return UserSessionState(channel="chat", member=MemberProfile(member_id=mid, name="T", age=30), active_node="start")


def _say(g, s, *msgs):
    out = ""
    for m in msgs:
        out, s = execute_turn(m, s, graph=g)
    return out, s


# ---- retrieval: generic category words must not create false ambiguity ----
def test_fever_panel_resolves_to_exactly_one_package():
    ids = [p.package_id for p in LabTools().search_packages("I need a fever panel")]
    assert ids == ["LP_011"]


def test_generic_words_alone_match_nothing():
    t = LabTools()
    assert t.search_packages("I need to schedule a lipid profile") == []   # 'profile' is not an identity
    assert t.search_packages("book a panel") == []


def test_genuine_tie_is_reported_as_ambiguous():
    ids = {p.package_id for p in LabTools().search_packages("senior citizen checkup")}
    assert ids == {"LP_006", "LP_007"}


# ---- the LB-SEQ-008 scenario end to end ----
def test_seq_008_fever_panel_then_time_then_confirm():
    g, s = _g(), _s()
    out, s = _say(g, s, "I need a fever panel")
    assert "Fever & Infection Panel" in out and s.booking_draft.package_id == "LP_011"
    out, s = _say(g, s, "10:30 AM")
    assert "10:30 AM" in out and "confirm" in out.lower() and s.booking_draft.selected_slot == "10:30 AM"
    out, s = _say(g, s, "go ahead")
    assert "Booking confirmed" in out and s.active_node == "node_lab_booking"
    assert any("10:30 AM" in b and "Fever" in b for b in s.member.past_bookings)


# ---- short follow-ups against a REAL ambiguous list ----
def test_name_fragment_selects_from_candidates():
    g, s = _g(), _s()
    out, s = _say(g, s, "book a senior citizen checkup")
    assert s.booking_draft.candidate_package_ids == ["LP_006", "LP_007"] and not s.booking_draft.package_id
    out, s = _say(g, s, "female")
    assert s.booking_draft.package_id == "LP_007" and s.booking_draft.candidate_package_ids == []
    assert "Available slots" in out


def test_ordinal_and_id_selection():
    for reply, want in [("the second one", "LP_007"), ("2", "LP_007"), ("first", "LP_006"), ("LP_006", "LP_006")]:
        g, s = _g(), _s()
        _, s = _say(g, s, "book a senior citizen checkup", reply)
        assert s.booking_draft.package_id == want, reply


def test_time_before_package_is_remembered_not_lost():
    g, s = _g(), _s()
    _, s = _say(g, s, "book a senior citizen checkup")
    out, s = _say(g, s, "8:00 AM")                       # a time, but we still need the package
    assert "which package" in out.lower() and not s.booking_draft.package_id
    assert s.booking_draft.candidate_package_ids == ["LP_006", "LP_007"]   # context preserved
    out, s = _say(g, s, "male")                          # now picks the package; remembered time is applied
    assert s.booking_draft.package_id == "LP_006" and s.booking_draft.selected_slot == "08:00 AM"
    assert "confirm" in out.lower()


def test_time_given_in_the_first_message_survives_disambiguation():
    g, s = _g(), _s()
    _, s = _say(g, s, "book a senior citizen checkup at 7:30 AM")
    assert s.booking_draft.pending_slot_text
    _, s = _say(g, s, "LP_007")
    assert s.booking_draft.selected_slot == "07:30 AM"


# ---- invalid / ambiguous selections ----
def test_invalid_reply_reasks_and_keeps_candidates():
    g, s = _g(), _s()
    _, s = _say(g, s, "book a senior citizen checkup")
    out, s = _say(g, s, "banana")
    assert "didn't recognise" in out and s.booking_draft.candidate_package_ids == ["LP_006", "LP_007"]
    assert s.active_node == "node_lab_booking"


def test_out_of_range_ordinal_is_invalid_not_a_crash():
    g, s = _g(), _s()
    _, s = _say(g, s, "book a senior citizen checkup")
    out, s = _say(g, s, "5")
    assert not s.booking_draft.package_id and s.booking_draft.candidate_package_ids


def test_ambiguous_reply_reasks():
    g, s = _g(), _s()
    _, s = _say(g, s, "book a senior citizen checkup")
    out, s = _say(g, s, "senior citizen")                 # still matches both
    assert "more than one" in out and not s.booking_draft.package_id


def test_gives_up_after_three_bad_replies_and_resets():
    g, s = _g(), _s()
    _, s = _say(g, s, "book a senior citizen checkup")
    out, s = _say(g, s, "banana", "mango", "kiwi")
    assert "start over" in out and s.booking_draft.candidate_package_ids == []


def test_naming_a_different_test_starts_a_new_search():
    g, s = _g(), _s()
    _, s = _say(g, s, "book a senior citizen checkup")
    out, s = _say(g, s, "actually book a thyroid test")
    assert s.booking_draft.package_id == "LP_002"


def test_cancel_while_choosing_a_package():
    g, s = _g(), _s()
    _, s = _say(g, s, "book a senior citizen checkup")
    out, s = _say(g, s, "cancel")
    assert "cancelled" in out and s.booking_draft.candidate_package_ids == []


def test_wellness_question_while_choosing_leaves_booking():
    g, s = _g(), _s()
    _, s = _say(g, s, "book a senior citizen checkup")
    _, s = _say(g, s, "how do I do surya namaskar")
    assert s.active_node == "node_program_coach" and s.booking_draft.candidate_package_ids == []
