import os
import re

print("Applying logging fixes...")

# 1. Update app/safety/triage_gate.py for clean [SAFETY GATE] console logging
triage_gate_path = 'app/safety/triage_gate.py'
with open(triage_gate_path, 'r', encoding='utf-8') as f:
    triage_content = f.read()

old_dispatch = '''def dispatch_emergency_sms(member_id: str, details: str):
    """Mocks a Twilio API call to dispatch an emergency SMS."""
    print(f"[CRITICAL] Firing Twilio SMS to emergency contacts for member {member_id}. Details: {details}")
    # In a real scenario, this would be:
    # from twilio.rest import Client
    # client = Client(account_sid, auth_token)
    # message = client.messages.create(...)
    logging.critical(f"Emergency SMS dispatched for member {member_id}. Details: {details}")
    return {"status": "sms_dispatched", "details": details}'''

new_dispatch = '''def dispatch_emergency_sms(member_id: str, details: str):
    """Mocks a Twilio API call to dispatch an emergency SMS."""
    print(f"\\n\\033[91m🚨 [SAFETY GATE] RED CRISIS INTERCEPTED FOR {member_id} 🚨\\033[0m")
    print(f"\\033[93m   [TWILIO OUTBOUND SMS] -> Emergency Contacts\\033[0m")
    print(f"\\033[90m   [DETAILS] {details}\\033[0m\\n")
    logging.critical(f"Emergency SMS dispatched for member {member_id}. Details: {details}")
    return {"status": "sms_dispatched", "details": details}'''

if old_dispatch in triage_content:
    triage_content = triage_content.replace(old_dispatch, new_dispatch)
    with open(triage_gate_path, 'w', encoding='utf-8') as f:
        f.write(triage_content)
    print(f"Updated {triage_gate_path} for clean SMS dispatch logging.")
else:
    print(f"Could not find old_dispatch in {triage_gate_path}")


# 2. Update evaluations/run_evals.py to suppress Python warnings
evals_path = 'evaluations/run_evals.py'
with open(evals_path, 'r', encoding='utf-8') as f:
    evals_content = f.read()

if 'import logging' not in evals_content:
    evals_content = evals_content.replace('import sys', 'import sys\\nimport logging')

if 'logging.basicConfig(level=logging.ERROR)' not in evals_content:
    evals_content = evals_content.replace('async def main():', 'logging.basicConfig(level=logging.ERROR)\\n\\nasync def main():')

with open(evals_path, 'w', encoding='utf-8') as f:
    f.write(evals_content)

print(f"Updated {evals_path} to format console logging cleanly.")
