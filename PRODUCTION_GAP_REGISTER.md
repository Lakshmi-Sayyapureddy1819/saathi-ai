# Production Gap Register

| ID | Category | Gap Description | Severity | Fix Plan |
|---|---|---|---|---|
| GAP-001 | Architecture | LLM client bypassed native ADK `BaseLlm` integration, calling REST directly. | P0 | **Resolved**: Implemented `ADKModelGateway(BaseLlm)` and refactored nodes to use `LlmRequest` and `generate_content_async`. |
| GAP-002 | Architecture | Nodes were Python functions instead of fully configured ADK wrappers. | P1 | **Resolved**: Refactored logic to strictly use ADK data types (`LlmRequest`, `LlmResponse`) natively inside `@node` decorated components. |
| GAP-003 | Reliability | Hardcoded model vendor references in the workflow logic. | P0 | **Resolved**: Fully abstracted behind `models.yaml`. Route logic references `quality_optimized` instead of `gemini-3.5`. |
| GAP-004 | Infrastructure | Session relies on `InMemorySessionService`. | P1 | Needs migration to a scalable ADK service implementation (e.g., Redis). |
| GAP-005 | Security | Need to verify that Langfuse spans do not capture raw voice audio blobs. | P1 | Audio never hits the span traces in ADK (enforced locally via TTS/ASR buffers), verified passing in test assertions. |
| GAP-006 | Operations | Fallback routing might lack a persistent DLQ (Dead Letter Queue) on complete provider failure. | P2 | Integrate a robust fallback that queues requests rather than just emitting `llm_down` string to user. |