# Final Status (2026-11-23)

This replaces the earlier version, which said gateway bypasses were "PRESENT" and cited 510 tests. Both are out of date.
The full evidence is in `SUBMISSION_READINESS_REPORT.md`.

## ADK integration
- Google ADK **2.11.0**. `saathi_workflow = Workflow(...)` runs real `@node` functions (`app/workflow/adk_graph.py`).
- `ADKModelGateway(BaseLlm)` in `app/workflow/gateway.py` is the **only** place a `ModelClient` is built or called. Source
  search of `app/` finds no other caller of `.generate()`, `.call_model()` or the provider HTTP functions: the triage gate,
  `_llm_route`, the coach and the grounding engine all go through the gateway. (Verified 2026-11-23 by grep.)
- **Not native ADK networking.** The gateway implements ADK's `generate_content_async(LlmRequest)` interface, but the HTTP
  calls to Gemini / OpenAI / Ollama / vLLM are still the project's own `requests` calls in `model_client.py`. Do not describe
  this as ADK's built-in model handlers.
- One call is outside the gateway: the **semantic-cache embedding request** (`app/grounding/semantic_cache.py`, direct
  `requests.post`). It is an embedding call, not generation, and does not use the gateway's retry/fallback.

## Defects found and fixed in this pass
1. **Gateway crash without a trace id (safety-relevant).** `generate_content_async` read `llm_request.custom_metadata`, which
   ADK 2.11's `LlmRequest` does not have. Any call without a trace id raised; the triage gate swallowed it and returned
   GREEN, so its LLM second stage was silently off. Deterministic red-flag rules were never affected. Fixed; regression test
   `tests/test_gateway_no_trace.py`.
2. **"Show my bookings" mid-booking** re-prompted for slots. Listing is now read-only and works with an open draft.
3. **Mimi vs voice.** The voice screen was titled "Talk to Mimi" and embedded the Mimi mascot. The brief says Mimi is only the
   chat persona. Voice is now "Voice assistant" with its own waveform orb and no mascot.

## Tests executed
- `pytest tests`: **515 passed, 0 failed** (after the fixes above).
- Frontend: `tsc --noEmit` clean; `vitest`: **31 passed**.
- Playwright (real backend, isolated ports, no real alerts): **39 passed** before the voice redesign; after it,
  `voice.spec.ts` + `saathi.spec.ts` were re-run: **32 passed**. `citations.spec.ts` and `incident_drill.spec.ts` were not re-run
  after the change.
- Deterministic eval: red-flag recall 27/27 and 13/13, no-diagnosis 25/25, wrong-booking 0/108, chaos recovery 50/50.
- Live eval (`python -m evaluations.run_evals`, real Gemini/OpenAI calls, run `20261123T041209Z`, not promoted): see
  the report. Misses are stated there, including lexical groundedness 78.3% against an 80% target.

## Not verified live
Langfuse cloud dashboard, Telegram/real lab-partner delivery (deliberately not triggered), provider failover under a real
outage, real STT/TTS with a human speaker, and the 5-8 min demo video. The simulated booking failure rate defaults to **0**;
the brief's 15% needs `LAB_FAILURE_RATE=0.15`.
