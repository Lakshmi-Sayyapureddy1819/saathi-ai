import re

print("Applying Architect Fixes to Saathi Care AI...")

# --- 1. Fix Intent Classification in app/workflow/graph.py ---
graph_path = "app/workflow/graph.py"
with open(graph_path, "r", encoding="utf-8") as f:
    graph_content = f.read()

old_router_start = "    def node_intent_router(self, user_text: str, session: UserSessionState) -> Tuple[str, UserSessionState]:"
old_router_end = "        return self.run_node(session.metadata['next_node'], user_text, session)"
start_idx = graph_content.find(old_router_start)
end_idx = graph_content.find(old_router_end, start_idx) + len(old_router_end)
old_router = graph_content[start_idx:end_idx]

new_router = '''    def node_intent_router(self, user_text: str, session: UserSessionState) -> Tuple[str, UserSessionState]:
        text_lower = user_text.lower()
        
        coach_triggers = ['yoga', 'diet', 'food', 'lifestyle', 'pranayama', 'breathing', 'exhausted', 'tired', 'stress', 'sleep', 'wellness', 'thakan', 'fatigue', 'kamzori', 'weakness']
        lab_triggers = ['checkup', 'test', 'thyroid', 'package', 'slot', 'book', 'blood', 'screen', 'schedule test']
        
        is_ongoing_booking = (
            session.active_node in ('node_lab_booking', 'LAB_BOOKING') and
            session.booking_draft.package_id is not None
        )
        
        has_coach_trigger = any(trigger in text_lower for trigger in coach_triggers)
        has_lab_trigger = any(trigger in text_lower for trigger in lab_triggers)
        has_slot_or_confirm = bool(re.search(r'\\b(\\d{1,2}(:\\d{2})?(\\s*(am|pm))?|am|pm|go ahead|yes|confirm)\\b', text_lower))
        
        # Priority: explicit explicit coach triggers without lab triggers
        if has_coach_trigger and not has_lab_trigger:
            session.metadata['next_node'] = 'node_program_coach'
        elif has_lab_trigger or is_ongoing_booking or (session.active_node in ('node_lab_booking', 'LAB_BOOKING') and has_slot_or_confirm):
            session.metadata['next_node'] = 'node_lab_booking'
        else:
            session.metadata['next_node'] = 'node_program_coach'
        
        session.active_node = session.metadata['next_node']
        return self.run_node(session.metadata['next_node'], user_text, session)'''

graph_content = graph_content.replace(old_router, new_router)

with open(graph_path, "w", encoding="utf-8") as f:
    f.write(graph_content)

print(f"Updated {graph_path}")

# --- 2. Fix interactive_chat.py ---
chat_path = "interactive_chat.py"
with open(chat_path, "r", encoding="utf-8") as f:
    chat_content = f.read()

old_welcome = '''    print(Fore.CYAN + Style.BRIGHT + "===================================================")
    print("🏥 Welcome to Saathi Care AI Interactive Demo 🏥")
    print("===================================================" + Style.RESET_ALL)
    print(Fore.YELLOW + "Type your query (or 'quit' to exit).")
    print("Try booking a lab test, asking for wellness coaching, or triggering an emergency." + Style.RESET_ALL)'''

new_welcome = '''    print(Fore.CYAN + Style.BRIGHT + "===================================================")
    print("🏥 Welcome to Saathi Care AI Interactive Demo 🏥")
    print("===================================================" + Style.RESET_ALL)
    print(Fore.YELLOW + "Here are some things you can try:")
    print(" 🌿 Wellness: 'What yoga helps with exhaustion?' or 'Tell me a good diet plan'")
    print(" 🔬 Booking:  'Can I check my thyroid?' or 'Book a full body checkup'")
    print(" 🚨 Red Flag: 'Mere seene mein dard hai' or 'I feel like I want to die'")
    print("\\nCommands: 'clear'/'reset' to restart session | 'quit'/'exit' to close." + Style.RESET_ALL)'''

chat_content = chat_content.replace(old_welcome, new_welcome)

old_loop = '''    while True:
        try:
            user_input = input(Fore.GREEN + Style.BRIGHT + "\\nYou: " + Style.RESET_ALL)
            if user_input.lower() in ['quit', 'exit', 'q']:
                print_slow("Thank you for using Saathi Care AI. Goodbye!", Fore.CYAN)
                break
            
            response, session = execute_turn(user_input, session)'''

new_loop = '''    while True:
        try:
            user_input = input(Fore.GREEN + Style.BRIGHT + "\\nYou: " + Style.RESET_ALL)
            input_lower = user_input.lower().strip()
            
            if input_lower in ['quit', 'exit', 'q']:
                print_slow("Thank you for using Saathi Care AI. Goodbye!", Fore.CYAN)
                break
            
            if input_lower in ['clear', 'reset']:
                session = UserSessionState(channel="terminal", member=member, active_node="start")
                print_slow("Session reset. How can I help you anew?", Fore.CYAN)
                continue
            
            response, session = execute_turn(user_input, session)'''

chat_content = chat_content.replace(old_loop, new_loop)

with open(chat_path, "w", encoding="utf-8") as f:
    f.write(chat_content)

print(f"Updated {chat_path}")
print("All Architect fixes applied successfully.")
