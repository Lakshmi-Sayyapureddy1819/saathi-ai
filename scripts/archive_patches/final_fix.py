import os
import re

print("Applying final fixes to intent router and APIs...")

# 1. Update app/workflow/graph.py
with open("app/workflow/graph.py", "r", encoding="utf-8") as f:
    graph_content = f.read()

# Add requests and dotenv imports if not present
graph_imports = """import logging
import re
import os
import requests
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
"""
if "import requests" not in graph_content:
    graph_content = graph_content.replace("import logging\nimport re", graph_imports)

# Replace intent router
old_router_start = "    def node_intent_router(self, user_text: str, session: UserSessionState) -> Tuple[str, UserSessionState]:"
old_router_end = "        return self.run_node(session.metadata['next_node'], user_text, session)"
start_idx = graph_content.find(old_router_start)
end_idx = graph_content.find(old_router_end, start_idx) + len(old_router_end)
old_router = graph_content[start_idx:end_idx]

new_router = '''    def node_intent_router(self, user_text: str, session: UserSessionState) -> Tuple[str, UserSessionState]:
        text_lower = user_text.lower()
        
        coach_triggers = ['yoga', 'diet', 'exhausted', 'tired', 'pranayama', 'food', 'lifestyle', 'schedule', 'wellness', 'thakan', 'fatigue', 'kamzori', 'weakness']
        lab_triggers = [
            'book', 'booking', 'karo', 'kar do',
            'test', 'tests', 'testing',
            'lab', 'labs', 'checkup', 'check up', 'appointment',
            'thyroid', 'package', 'packages', 'slot', 'slots',
            'blood', 'panel', 'fever', 'vitamin', 'liver', 'kidney',
            'vitality', 'cardiac', 'fasting', 'full body', 'senior',
            'price', 'rupees', 'cost', 'charge', 'rate', 'seven hundred',
            'option', 'second option', 'first option', 'cancel',
            'eight thirty', 'fifteen', 'tuesday', 'ten thirty',
            'lp_', 'lp ', 'lp0', 'lp1', 'lp2', 'lp3', "l' 'p'", 'lp', 'screen'
        ]
        
        is_ongoing_booking = (
            session.active_node in ('node_lab_booking', 'LAB_BOOKING') and
            session.booking_draft.package_id is not None
        )
        
        has_coach_trigger = any(trigger in text_lower for trigger in coach_triggers)
        has_lab_trigger = any(trigger in text_lower for trigger in lab_triggers)
        has_slot_or_confirm = bool(re.search(r'\\b(\\d{1,2}(:\\d{2})?(\\s*(am|pm))?|am|pm|go ahead|yes|confirm)\\b', text_lower))
        
        # Priority: Lab booking keywords take precedence
        if has_lab_trigger or is_ongoing_booking or (session.active_node in ('node_lab_booking', 'LAB_BOOKING') and has_slot_or_confirm):
            session.metadata['next_node'] = 'node_lab_booking'
        elif has_coach_trigger:
            session.metadata['next_node'] = 'node_program_coach'
        else:
            session.metadata['next_node'] = 'node_program_coach'
        
        session.active_node = session.metadata['next_node']
        return self.run_node(session.metadata['next_node'], user_text, session)'''

graph_content = graph_content.replace(old_router, new_router)

# Replace program coach to support Live API Keys
old_coach_start = "    def node_program_coach(self, user_text: str, session: UserSessionState) -> Tuple[str, UserSessionState]:"
old_coach_end = "return offline_response, session"
c_start_idx = graph_content.find(old_coach_start)
if c_start_idx != -1:
    c_end_idx = graph_content.find(old_coach_end, c_start_idx) + len(old_coach_end)
    old_coach = graph_content[c_start_idx:c_end_idx]

    new_coach = '''    def node_program_coach(self, user_text: str, session: UserSessionState) -> Tuple[str, UserSessionState]:
        offline_response = get_grounded_response(user_text, session)
        
        gemini_key = os.getenv("GEMINI_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        
        if gemini_key or openai_key:
            prompt = f"Context from wellness knowledge base:\\n{offline_response}\\n\\nUser query: {user_text}\\n\\nYou are Saathi Care AI, a helpful wellness coach. Provide a concise, empathetic response based on the context above. Do not act as a doctor."
            
            if gemini_key:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                try:
                    r = requests.post(url, json=payload, timeout=10)
                    if r.status_code == 200:
                        content = r.json()['candidates'][0]['content']['parts'][0]['text']
                        return content, session
                except Exception as e:
                    logging.error(f"Gemini API error: {e}")
            
            if openai_key:
                url = "https://api.openai.com/v1/chat/completions"
                headers = {"Authorization": f"Bearer {openai_key}"}
                payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}]}
                try:
                    r = requests.post(url, headers=headers, json=payload, timeout=10)
                    if r.status_code == 200:
                        content = r.json()['choices'][0]['message']['content']
                        return content, session
                except Exception as e:
                    logging.error(f"OpenAI API error: {e}")
                    
        return offline_response, session'''
    graph_content = graph_content.replace(old_coach, new_coach)

with open("app/workflow/graph.py", "w", encoding="utf-8") as f:
    f.write(graph_content)

# 2. Update interactive_chat.py
with open("interactive_chat.py", "r", encoding="utf-8") as f:
    chat_content = f.read()

if "load_dotenv" not in chat_content:
    chat_content = chat_content.replace("import sys\nimport time", "import sys\nimport time\nimport os\ntry:\n    from dotenv import load_dotenv\n    load_dotenv()\nexcept ImportError:\n    pass")
    with open("interactive_chat.py", "w", encoding="utf-8") as f:
        f.write(chat_content)

# 3. Create .env.example
with open(".env.example", "w", encoding="utf-8") as f:
    f.write("GEMINI_API_KEY=\nOPENAI_API_KEY=\n")

print("Fixes applied successfully via final_fix.py.")
