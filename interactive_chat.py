import sys
import time
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from colorama import init, Fore, Style
    init()
except ImportError:
    class Fore:
        GREEN = ""
        CYAN = ""
        YELLOW = ""
        RED = ""
        BLUE = ""
        RESET = ""
    class Style:
        BRIGHT = ""
        RESET_ALL = ""

from app.workflow.state import UserSessionState, MemberProfile, BookingDraft
from app.workflow.graph import execute_turn

def print_slow(text, color=""):
    sys.stdout.write(color)
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(0.01) # Simulated voice TTS speed
    sys.stdout.write(Style.RESET_ALL + "\n")

def chat():
    print(Fore.CYAN + Style.BRIGHT + "===================================================")
    print("🏥 Welcome to Saathi Care AI Interactive Demo 🏥")
    print("===================================================" + Style.RESET_ALL)
    print(Fore.YELLOW + "Here are some things you can try:")
    print(" 🌿 Wellness: 'What yoga helps with exhaustion?' or 'Tell me a good diet plan'")
    print(" 🔬 Booking:  'Can I check my thyroid?' or 'Book a full body checkup'")
    print(" 🚨 Red Flag: 'Mere seene mein dard hai' or 'I feel like I want to die'")
    print("\nCommands: 'clear'/'reset' to restart session | 'quit'/'exit' to close." + Style.RESET_ALL)
    
    member = MemberProfile(member_id="DEMO_USER", name="Demo Candidate", age=30)
    session = UserSessionState(channel="terminal", member=member, active_node="start", booking_draft=BookingDraft())
    
    while True:
        try:
            user_input = input(Fore.GREEN + Style.BRIGHT + "\nYou: " + Style.RESET_ALL)
            input_lower = user_input.lower().strip()
            
            if input_lower in ['quit', 'exit', 'q']:
                print_slow("Thank you for using Saathi Care AI. Goodbye!", Fore.CYAN)
                break
            
            if input_lower in ['clear', 'reset']:
                session = UserSessionState(channel="terminal", member=member, active_node="start", booking_draft=BookingDraft())
                print_slow("Session reset. How can I help you anew?", Fore.CYAN)
                continue
            
            response, session = execute_turn(user_input, session)
            print()
            sys.stdout.write(Fore.BLUE + Style.BRIGHT + "Saathi Care AI: " + Style.RESET_ALL)
            print_slow(response, Fore.CYAN)
            
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(Fore.RED + f"\nError processing request: {e}" + Style.RESET_ALL)

if __name__ == "__main__":
    chat()
