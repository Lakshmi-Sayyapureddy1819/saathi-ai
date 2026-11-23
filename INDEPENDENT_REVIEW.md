> **Superseded.** This is an earlier review snapshot. Its "bypass" finding for `triage_gate.py` and `graph._llm_route` has since been fixed (all generation now goes through `ADKModelGateway`); the custom-HTTP finding still stands. See `FINAL_STATUS.md` and `SUBMISSION_READINESS_REPORT.md` for current status.

# Independent Code Review

This document contains the findings of an independent verification of the claims made by the Gemini CLI agent regarding the Saathi Care AI platform's implementation.

## Verification Matrix

| Claim | Gemini's conclusion | Actual source evidence | Test evidence | Verdict |
|---|---|---|---|---|
| Google ADK native BaseLlm integration. | PASS | `ADKModelGateway` subclasses `BaseLlm`, however, it wraps a custom HTTP client (`ModelClient`) rather than using ADK's native `google.genai` LLM handlers. ADK's `LlmRequest` is constructed manually to bridge to the gateway in `node_program_coach`. Furthermore, other nodes (`triage_gate.py`, `graph._llm_route`) bypass the gateway entirely, calling `ModelClient.generate()` directly. | Tests pass, but they validate the custom HTTP client wrapper rather than true native ADK LLM execution. | **PARTIALLY VERIFIED** |
| Centralized model routing. | PASS | `config/models.yaml` defines routing nodes (`cost_optimized`, `quality_optimized`, `voice`) and `ModelClient` reads these settings dynamically. | `test_models_yaml_structure_and_providers` passes. | **VERIFIED** |
| Bounded retries and exponential backoff. | PASS | Initially, `_invoke_with_retry` was hardcoded to a single retry with a static 0.4s delay, lacking both exponential backoff and jitter. **(Fixed during review to properly support up to 3 retries with jittered exponential backoff.)** | Source code inspection confirmed the absence of the claimed backoff mechanism prior to fixing. | **PARTIALLY VERIFIED (Fixed during review)** |
| Multi-provider fallback. | PASS | `ModelClient.generate()` iterates gracefully through `primary` and `fallback_model` as defined in `models.yaml`. | Fallback logic is explicitly tested and passes. | **VERIFIED** |
| Langfuse tracing. | PASS | `app/observability/tracer.py` wraps LLM, tool, and root-level calls with detailed Langfuse span tracking, capturing tokens, cost, and latency. | `test_langfuse_tracing.py` runs and verifies the spans. | **VERIFIED** |
| 509 passing tests. | PASS | Executing `pytest tests/` in the environment resulted in 510 passing tests and 0 failures. | 510 tests passed successfully. | **VERIFIED** |
| Zero direct LLM call bypasses. | PASS | `ModelClient._invoke` directly executes `requests.post()`, bypassing any ADK network abstractions. Additionally, `triage_gate.py` and `_llm_route` bypass `ADKModelGateway` by directly invoking `ModelClient.generate()`. | Source code inspection confirms the presence of direct REST calls and ADK wrapper bypasses. | **INCORRECT** |

## Additional Findings

- **Config Reloads:** Configuration changes to `models.yaml` currently require an application restart. The `WorkflowGraph` (and by extension `ModelClient`) is instantiated as a global singleton (`_GRAPH`) in `adk_graph.py`.
- **Booking Idempotency & Simulated Failure:** Verified in `app/tools/lab_tools.py` and `app/tools/lab_backend.py`. `LabTools.book_test` passes an `idempotency_key` based on member, package, date, and slot. The 15% random failure rate is correctly implemented in `SimulatedLabBackend`.
- **InMemorySessionService:** Verified that `adk_graph.py` actively relies on `google.adk.sessions.InMemorySessionService` to persist `UserSessionState` between turns.

## Post-Review Actions
1. **Fixed P0/P1 Defect:** Refactored `ModelClient._invoke_with_retry` to implement genuine exponential backoff (with configurable base delay and up to 3 retries) and random jitter, replacing the hardcoded single-retry static sleep.
2. Updated `FINAL_STATUS.md` to accurately reflect the true state of the ADK integration and the remaining architectural gaps.