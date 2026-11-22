# SKILL: ADK 2.0 Workflow Engineering

This skill defines the architectural pattern for building and managing complex, multi-turn workflows using the Agent Development Kit (ADK) 2.0.

## 1. DAGs as the Source of Truth
- All workflows are defined as Directed Acyclic Graphs (DAGs).
- Each node in the DAG represents a specific state or decision point.
- Edges represent valid state transitions.

## 2. State Transitions
- State is managed centrally in the \UserSessionState\ Pydantic model.
- A transition from one node to another is a pure function that takes the current state and returns a new state.
- Side effects (e.g., API calls, database writes) are managed by tools, not within the state transition logic itself.

## 3. Code vs. LLM Boundaries
- **Code (Deterministic Logic):**
  - State validation and transitions.
  - Business rule enforcement (e.g., checking eligibility).
  - Safety-critical checks and escalations.
  - Tool orchestration and execution.
- **LLM (Non-deterministic Logic):**
  - Natural Language Understanding (NLU) to extract intent and entities.
  - Natural Language Generation (NLG) to formulate responses.
  - Summarization of complex histories.
  - Non-critical recommendations or suggestions.
