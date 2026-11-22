"""
Saathi Care AI: Voice Channel Demo (Simulation)

Note: WebRTC telephony integration was de-scoped in favor of production graph safety and evaluation depth.
This script serves as an ASR/TTS audio pipeline architecture simulation, designed to test phonetic 
normalization and verbal confirmation logic before booking.
"""
from app.channels.voice_agent import VoiceAgent
from app.workflow.graph import WorkflowGraph
from app.workflow.state import UserSessionState, MemberProfile

def run_demo():
    print("--- Saathi Care AI: Voice Channel Demo ---")
    agent = VoiceAgent(graph=WorkflowGraph(model_node="voice"))
    member = MemberProfile(member_id="VOICE_USER", name="Voice User", age=30)
    session = UserSessionState(channel="voice", member=member, active_node="start")

    print("Simulating inbound call...")
    # Generic request -> the agent asks WHICH test; the caller answers; then time and confirmation.
    turns = [
        "I want to book a blood test for kal subah.",
        "the thyroid one",
        "09:00 AM",
        "yes confirm",
    ]
    for utterance in turns:
        print()
        print(f"User (Audio): {utterance}")
        session = agent.process_voice_turn(utterance, session)

    print()
    print(f"Bookings on file: {session.member.past_bookings or None}")
    if agent.metrics:
        last = agent.metrics[-1]
        print(f"Last turn latency (ms): stt={last.stt_ms} graph={last.graph_ms} tts_first_chunk={last.tts_first_chunk_ms}")


if __name__ == "__main__":
    run_demo()


def run_outbound_demo(member_id: str = "MEM_1001") -> None:
    """Outbound reminder call: the agent phones a member about a pending checkup and books it."""
    import json
    from app.channels.outbound import OutboundCall

    print("--- Saathi Care AI: Outbound Reminder Call Demo ---")
    src = next(m for m in json.load(open("data/members.json", encoding="utf-8")) if m["member_id"] == member_id)
    member = MemberProfile(member_id=src["member_id"], name=src["name"], age=src["age"],
                           language_pref=src["language_preference"], past_bookings=src["past_bookings"],
                           pending_checkups=src["pending_checkups"])
    before = list(member.past_bookings)
    call = OutboundCall(member)
    call.start()
    for utterance in ["haan kar do", "kal subah", "09:00 AM", "yes confirm"]:
        if call.finished:
            break
        print(f"\nMember (Audio): {utterance}")
        call.reply(utterance)
    res = call.result(before)
    print(f"\nOutcome: {res.outcome}  bookings: {res.booking_ids}  trace_id: {res.trace_id}")


if __name__ == "__main__":
    import sys
    if "--outbound" in sys.argv:
        run_outbound_demo()
