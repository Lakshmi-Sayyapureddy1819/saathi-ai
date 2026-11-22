import json
import re

# 1. Fix graph.py
graph_file = 'app/workflow/graph.py'
with open(graph_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace intent router logic
old_intent_logic = '''        coach_triggers = ['yoga', 'diet', 'food', 'lifestyle', 'pranayama', 'breathing', 'exhausted', 'tired', 'stress', 'sleep', 'wellness', 'thakan', 'fatigue', 'kamzori', 'weakness']
        lab_triggers = ['checkup', 'test', 'thyroid', 'package', 'slot', 'book', 'blood', 'screen', 'schedule test', 'panel', 'fever', 'fifteen', 'second option', 'cancel', 'lp', 'seven hundred', 'price', "l' 'p'", 'zero', 'one', 'two']
        
        is_ongoing_booking = (
            session.active_node in ('node_lab_booking', 'LAB_BOOKING') and
            session.booking_draft.package_id is not None
        )
        
        has_coach_trigger = any(trigger in text_lower for trigger in coach_triggers)
        has_lab_trigger = any(trigger in text_lower for trigger in lab_triggers)
        has_slot_or_confirm = bool(re.search(r'\\b(\\d{1,2}(:\\d{2})?(\\s*(am|pm))?|am|pm|go ahead|yes|confirm|fifteen|pandrah)\\b', text_lower))
        
        # Priority: explicit explicit coach triggers without lab triggers
        if has_coach_trigger and not has_lab_trigger:
            session.metadata['next_node'] = 'node_program_coach'
        elif has_lab_trigger or is_ongoing_booking or (session.active_node in ('node_lab_booking', 'LAB_BOOKING') and has_slot_or_confirm):
            session.metadata['next_node'] = 'node_lab_booking'
        else:
            session.metadata['next_node'] = 'node_program_coach'
'''

new_intent_logic = '''        coach_triggers = ['yoga', 'diet', 'food', 'lifestyle', 'pranayama', 'breathing', 'kriya', 'meditation']
        lab_triggers = ['book', 'slot', 'schedule', 'appointment', 'blood test', 'lab package', 'checkup']
        
        is_ongoing_booking = (
            session.active_node in ('node_lab_booking', 'LAB_BOOKING') and
            session.booking_draft.package_id is not None
        )
        
        has_coach_trigger = any(trigger in text_lower for trigger in coach_triggers)
        has_lab_trigger = any(trigger in text_lower for trigger in lab_triggers)
        has_slot_or_confirm = bool(re.search(r'\\b(\\d{1,2}(:\\d{2})?(\\s*(am|pm))?|am|pm|go ahead|yes|confirm|fifteen|pandrah)\\b', text_lower))
        
        if has_coach_trigger:
            session.metadata['next_node'] = 'node_program_coach'
            session.booking_draft = BookingDraft()
        elif has_lab_trigger or is_ongoing_booking or (session.active_node in ('node_lab_booking', 'LAB_BOOKING') and has_slot_or_confirm):
            session.metadata['next_node'] = 'node_lab_booking'
        else:
            session.metadata['next_node'] = 'node_program_coach'
'''
if old_intent_logic in content:
    content = content.replace(old_intent_logic, new_intent_logic)
else:
    print("WARNING: Could not find old intent logic to replace in graph.py")
    
with open(graph_file, 'w', encoding='utf-8') as f:
    f.write(content)

# 2. Update interactive_chat.py
chat_file = 'interactive_chat.py'
with open(chat_file, 'r', encoding='utf-8') as f:
    chat_content = f.read()

old_init = 'session = UserSessionState(channel="terminal", member=member, active_node="start")'
new_init = 'session = UserSessionState(channel="terminal", member=member, active_node="start", booking_draft=BookingDraft())'

if old_init in chat_content:
    chat_content = chat_content.replace(old_init, new_init)
else:
    print("WARNING: Could not find old init in interactive_chat.py")
    
if 'from app.workflow.state import UserSessionState, MemberProfile' in chat_content and 'BookingDraft' not in chat_content:
    chat_content = chat_content.replace('from app.workflow.state import UserSessionState, MemberProfile', 'from app.workflow.state import UserSessionState, MemberProfile, BookingDraft')

with open(chat_file, 'w', encoding='utf-8') as f:
    f.write(chat_content)

# 3. Add to data/programs.json
programs_file = 'data/programs.json'
with open(programs_file, 'r', encoding='utf-8') as f:
    programs = json.load(f)

# check if we already added it
if not any(p["doc_id"] == "PROG_Y_006" for p in programs):
    new_program_1 = {
        "doc_id": "PROG_Y_006",
        "title": "Restorative Yoga for Fatigue (Viparita Karani)",
        "category": "Yoga",
        "content": "Viparita Karani, or Legs-Up-The-Wall pose, is a restorative yoga practice that is excellent for combating exhaustion and fatigue. Lie on your back with your sitting bones close to a wall and extend your legs straight up the wall. This pose helps drain lymphatic fluid from the legs, improves circulation, and calms the nervous system. Combine it with gentle Pranayama (deep breathing) for maximum benefit. It is ideal for those who feel burnt out or physically tired.",
        "tags": ["yoga", "fatigue", "exhaustion", "restorative", "breathing"]
    }

    new_program_2 = {
        "doc_id": "PROG_D_005",
        "title": "Ayurvedic Diet for Fatigue and Low Energy",
        "category": "Diet",
        "content": "An Ayurvedic fatigue diet focuses on balancing Vata dosha, which is often responsible for feeling exhausted or depleted. Include warm, nourishing foods like kitchari (rice and mung dal), warm milk with a pinch of nutmeg before bed, and sweet, juicy fruits like peaches and melons. Avoid dry, cold, or highly processed foods. Incorporate grounding spices such as ginger, cardamom, and cinnamon. Staying well-hydrated with warm water or herbal teas also helps restore energy levels.",
        "tags": ["diet", "fatigue", "exhaustion", "ayurveda", "energy"]
    }

    programs.append(new_program_1)
    programs.append(new_program_2)

    with open(programs_file, 'w', encoding='utf-8') as f:
        json.dump(programs, f, indent=4)

print("Fixes applied successfully.")
