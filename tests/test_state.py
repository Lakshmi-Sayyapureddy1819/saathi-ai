import pytest
from datetime import datetime
from app.workflow.state import (
    MemberProfile,
    BookingDraft,
    TriageStatus,
    GroundingMode,
    UserSessionState,
)

def test_member_profile_instantiation():
    profile = MemberProfile(
        member_id="M123",
        name="Jane Doe",
        age=30,
    )
    assert profile.member_id == "M123"
    assert profile.name == "Jane Doe"
    assert profile.language_pref == "en-US"
    assert profile.enrolled_programs == []

def test_user_session_state_defaults():
    profile = MemberProfile(member_id="M123", name="Jane Doe", age=30)
    session = UserSessionState(
        channel="whatsapp",
        member=profile,
        active_node="start",
    )
    assert session.channel == "whatsapp"
    assert session.booking_draft.verbal_confirmed is False
    assert session.triage_status.status == "GREEN_NORMAL"
    assert session.grounding_mode.mode == "mode_a_rag"
    assert session.session_id is not None
