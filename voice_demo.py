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
    print("User (Audio): I want to book a blood test for kal subah.")
    session = agent.process_voice_turn("I want to book a blood test for kal subah.", session)
    
    print("\nUser (Audio): 09:00 AM")
    session = agent.process_voice_turn("09:00 AM", session)
    
    print("\nUser (Audio): yes confirm")
    session = agent.process_voice_turn("yes confirm", session)

if __name__ == "__main__":
    run_demo()
