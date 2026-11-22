# Saathi Care AI - Architectural Plan

## 1. Architectural Problem
HeyDoc AI needs a reliable, scalable, and safe conversational agent to handle patient interactions across multiple channels (WhatsApp, voice, text). The challenge is balancing the flexibility of LLM-driven generation (for wellness coaching) with the rigid, deterministic constraints required for clinical safety (triage) and transactional accuracy (lab booking).

## 2. User Personas
- **The Patient / Member:** Seeking quick lab bookings, general wellness advice, or reporting symptoms. Needs empathetic, accurate, and safe responses.
- **The Care Coordinator (Human-in-the-loop):** Steps in when the AI cannot confidently book a test or when an emergency is flagged.
- **The AI Architect / Developer:** Needs a maintainable, observable, and modular system to update intents, add new tools, and monitor safety compliance.

## 3. Google ADK 2.0 Graph Topology
The system utilizes a directed acyclic graph (DAG) based on the Google Agent Development Kit (ADK) 2.0 architecture to ensure deterministic routing and state management:

1.  **SafetyGate (`node_safety_gate`):** The mandatory entry point for every turn. Uses regex-based patterns to intercept acute red flags (Cardiac, Respiratory, Self-Harm, Hemorrhage) and enforce the "No Diagnosis" rule.
    *   *Routing:* If RED_CRISIS -> `node_emergency`. If YELLOW_WARNING -> returns canned refusal/steer. Else -> `node_intent_router`.
2.  **IntentRouter (`node_intent_router`):** A fast, deterministic router that classifies the user's intent based on broad synonyms, Hinglish triggers, and active session context.
    *   *Routing:* Routes to either `node_program_coach` or `node_lab_booking`.
3.  **ProgramCoach (`node_program_coach`):** Handles wellness guidance and general inquiries using Agentic RAG (Mode A) or Fact-Grounded Prompting (Mode B).
4.  **LabBooking (`node_lab_booking`):** A multi-turn transactional node. Manages state for package selection, slot confirmation, and final API execution.
5.  **Emergency (`node_emergency`):** A terminal node that provides helpline information and triggers out-of-band alerts (e.g., Twilio SMS) without LLM intervention.

## 4. State Schema
The application relies on a strictly typed `UserSessionState` (Pydantic model) to persist context across turns:
- `session_id`: Unique identifier for the interaction.
- `member`: `MemberProfile` detailing demographics and history.
- `booking_draft`: `BookingDraft` tracking in-progress transactional state (package, date, slot, confirmation).
- `triage_status`: Tracks the current safety level (`GREEN_NORMAL`, `YELLOW_WARNING`, `RED_CRISIS`).
- `active_node`: The current position in the ADK graph.

## 5. Code vs. LLM Decisions
- **Code (Deterministic):**
  - **Safety Triage:** Regex and exact keyword matching are used for safety critical checks to guarantee 100% recall and zero latency variance. LLMs are explicitly bypassed for acute emergencies.
  - **Routing:** Rule-based routing ensures predictable navigation and prevents prompt injection from hijacking the flow.
  - **Transactional Execution:** The `LabTools` API calls and state transitions are handled in pure Python, not left to the LLM's tool-calling discretion.
- **LLM (Generative):**
  - **Content Generation:** Used exclusively in the `ProgramCoach` node for synthesizing empathetic, factually grounded wellness advice based on retrieved context.
