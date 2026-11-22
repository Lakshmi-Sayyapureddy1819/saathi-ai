# STUB / NOT WIRED IN: unverified ADK 2.x prototype. It still uses the removed `session.metadata` dict and
# untyped state, so it will not run against the current state.py. Port app/workflow/graph.py nodes here once
# google-adk 2.x is installed and verified (see README "Known gaps").
import asyncio
from google.adk.workflow import Workflow, node, START
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk import Event
import google.genai.types as glm

from app.workflow.state import UserSessionState, MemberProfile
from app.safety.triage_gate import evaluate_safety_gate

# --- Define Nodes as Functions ---

@node
async def safety_gate(state: dict):
    user_text = state['user_text']
    member_profile = state['member_profile']
    session = UserSessionState(channel="chat", member=member_profile, active_node="start")
    
    is_safe, status, payload = evaluate_safety_gate(user_text, session.member.member_id)
    session.triage_status = status
    state['session'] = session
    
    if not is_safe:
        session.metadata['next_node'] = 'node_emergency'
        session.metadata['emergency_payload'] = payload
        yield Event(route="emergency", output=state)
    else:
        session.metadata['next_node'] = 'node_intent_router'
        yield Event(route="intent_router", output=state)

@node
async def intent_router(state: dict):
    user_text = state['user_text']
    session = state['session']
    text_lower = user_text.lower()
    if "book" in text_lower or "test" in text_lower:
        yield Event(route="lab_booking", output=state)
    else:
        yield Event(route="program_coach", output=state)

@node
async def lab_booking(state: dict):
    session = state['session']
    output_text = f"This is the lab booking node. Session member: {session.member.name}"
    yield Event(output=output_text)

@node
async def program_coach(state: dict):
    session = state['session']
    output_text = f"This is the program coach node. Session member: {session.member.name}"
    yield Event(output=output_text)

@node
async def emergency(state: dict):
    session = state['session']
    output_text = f"This is the emergency node. Session member: {session.member.name}"
    yield Event(output=output_text)

# --- Create the Workflow ---

saathi_workflow = Workflow(
    name="SaathiWorkflow",
    edges=[
        (START, safety_gate),
        (safety_gate, {
            "emergency": emergency,
            "intent_router": intent_router
        }),
        (intent_router, {
            "lab_booking": lab_booking,
            "program_coach": program_coach
        }),
    ]
)

# --- Example Usage ---
if __name__ == '__main__':
    async def main():
        session_service = InMemorySessionService()
        runner = Runner(app_name="SaathiWorkflow", session_service=session_service, node=saathi_workflow, auto_create_session=True)

        user_id = "user123"
        session_id = "session456"

        user_text = "I want to book a test"
        new_message = glm.Content(role="user", parts=[glm.Part(text=user_text)])

        member = MemberProfile(member_id="MEM_1002", name="Priya Patel", age=28)
        initial_state = {'user_text': user_text, 'member_profile': member}

        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=new_message, state_delta=initial_state):
            print(event)

    asyncio.run(main())
