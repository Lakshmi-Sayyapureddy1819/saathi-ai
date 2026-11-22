import os

print("Writing .env.example...")
with open('.env.example', 'w', encoding='utf-8') as f:
    f.write("GEMINI_API_KEY=\nOPENAI_API_KEY=\n")

print("Updating interactive_chat.py for python-dotenv...")
with open('interactive_chat.py', 'r', encoding='utf-8') as f:
    content = f.read()

dotenv_import = """import sys
import time
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
"""
if "from dotenv import load_dotenv" not in content:
    content = content.replace("import sys\nimport time", dotenv_import)
    with open('interactive_chat.py', 'w', encoding='utf-8') as f:
        f.write(content)

print("Updating app/workflow/graph.py for intent routing and API keys...")
with open('app/workflow/graph.py', 'r', encoding='utf-8') as f:
    graph_content = f.read()

# Add requests and dotenv imports to graph.py
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

old_intent_router = '''    def node_intent_router(self, user_text: str, session: UserSessionState) -> Tuple[str, UserSessionState]:
        text_lower = user_text.lower()
        
        # Broad synonyms and Hinglish triggers for lab booking
        lab_triggers = [
            'book', 'booking', 'karo', 'kar do',
            'test', 'tests', 'testing',
            'lab', 'labs', 'checkup', 'check up', 'appointment',
            'thakan', 'tired', 'fatigue', 'kamzori', 'weakness',
            'thyroid', 'package', 'packages', 'slot', 'slots',
            'blood', 'panel', 'fever', 'vitamin', 'liver', 'kidney',
            'vitality', 'cardiac', 'fasting', 'full body', 'senior',
            'price', 'rupees', 'cost', 'charge', 'rate', 'seven hundred',
            'option', 'second option', 'first option', 'cancel',
            'eight thirty', 'fifteen', 'tuesday', 'ten thirty',
            'lp_', 'lp ', 'lp0', 'lp1', 'lp2', 'lp3', "l' 'p'", 'lp'
        ]
        
        is_ongoing_booking = (
            session.active_node in ('node_lab_booking', 'LAB_BOOKING') and
            session.booking_draft.package_id is not None
        )
        
        has_lab_trigger = any(trigger in text_lower for trigger in lab_triggers)
        has_slot_or_confirm = bool(re.search(r'\\b(\\d{1,2}(:\\d{2})?(\\s*(am|pm))?|am|pm|go ahead|yes|confirm)\\b', text_lower))
        
        if has_lab_trigger or is_ongoing_booking or (session.active_node in ('node_lab_booking', 'LAB_BOOKING') and has_slot_or_confirm):
            session.metadata['next_node'] = 'node_lab_booking'
        else:
            session.metadata['next_node'] = 'node_program_coach'
        
        session.active_node = session.metadata['next_node']
        return self.run_node(session.metadata['next_node'], user_text, session)'''

new_intent_router = '''    def node_intent_router(self, user_text: str, session: UserSessionState) -> Tuple[str, UserSessionState]:
        text_lower = user_text.lower()
        
        coach_triggers = ['yoga', 'diet', 'exhausted', 'tired', 'pranayama', 'food', 'lifestyle', 'schedule', 'wellness']
        lab_triggers = ['checkup', 'test', 'thyroid', 'package', 'slot', 'book', 'blood', 'screen']
        
        is_ongoing_booking = (
            session.active_node in ('node_lab_booking', 'LAB_BOOKING') and
            session.booking_draft.package_id is not None
        )
        
        has_coach_trigger = any(trigger in text_lower for trigger in coach_triggers)
        has_lab_trigger = any(trigger in text_lower for trigger in lab_triggers)
        has_slot_or_confirm = bool(re.search(r'\\b(\\d{1,2}(:\\d{2})?(\\s*(am|pm))?|am|pm|go ahead|yes|confirm)\\b', text_lower))
        
        if has_coach_trigger:
            session.metadata['next_node'] = 'node_program_coach'
        elif has_lab_trigger or is_ongoing_booking or (session.active_node in ('node_lab_booking', 'LAB_BOOKING') and has_slot_or_confirm):
            session.metadata['next_node'] = 'node_lab_booking'
        else:
            session.metadata['next_node'] = 'node_program_coach'
        
        session.active_node = session.metadata['next_node']
        return self.run_node(session.metadata['next_node'], user_text, session)'''

if old_intent_router in graph_content:
    graph_content = graph_content.replace(old_intent_router, new_intent_router)

old_program_coach = '''    def node_program_coach(self, user_text: str, session: UserSessionState) -> Tuple[str, UserSessionState]:
        response = get_grounded_response(user_text, session)
        return response, session'''

new_program_coach = '''    def node_program_coach(self, user_text: str, session: UserSessionState) -> Tuple[str, UserSessionState]:
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

if old_program_coach in graph_content:
    graph_content = graph_content.replace(old_program_coach, new_program_coach)

with open('app/workflow/graph.py', 'w', encoding='utf-8') as f:
    f.write(graph_content)

print("Done.")
