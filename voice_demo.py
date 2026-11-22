"""
Saathi Care AI: Voice Channel Demo (Simulation)

Note: WebRTC telephony integration was de-scoped in favor of production graph safety and evaluation depth.
This script serves as an ASR/TTS audio pipeline architecture simulation, designed to test phonetic 
normalization and verbal confirmation logic before booking.
"""
from app.channels.voice_agent import VoiceAgent
from app.workflow.state import UserSessionState, MemberProfile

def run_demo():
    print("--- Saathi Care AI: Voice Channel Demo ---")
    agent = VoiceAgent()
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
