# Claude Mandates for Saathi Care AI

This document outlines the core engineering and safety standards for all Claude-based agents operating within the Saathi Care AI ecosystem. Adherence to these rules is mandatory.

## 1. Core Principles
- **Type Safety:** All data structures exchanged between systems, agents, or tools MUST be defined using Pydantic V2 models. Strict typing is enforced. No `Any` or `Dict` without strongly typed value definitions.
- **Traceability:** Every operation, LLM call, or tool execution MUST be wrapped in a Langfuse span. The `trace_id` must be propagated through the entire call chain to ensure end-to-end observability.
- **Deterministic Safety:** Safety-critical rules are not open to LLM interpretation. All safety interventions (e.g., triage escalations, clinical handovers) MUST be implemented in deterministic Python code based on explicit state triggers.

## 2. Pydantic V2 Enforcement
- All models must inherit from `pydantic.BaseModel`.
- Use specific types (e.g., `UUID`, `datetime`, `Literal`, `Annotated`) where applicable.
- Models should be immutable (`frozen=True`) wherever possible to prevent unintended state mutations.

## 3. Langfuse Integration
- A root span MUST be created at the beginning of each user interaction.
- Every subsequent LLM call, tool use, or significant business logic function must create a child span.
- Spans must include relevant metadata, such as model names, prompt versions, and key state variables.
