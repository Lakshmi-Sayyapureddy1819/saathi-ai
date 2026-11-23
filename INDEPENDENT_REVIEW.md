# Independent Code Review: Centralized ADK Model Integration

This document contains the verified findings of an independent audit of the Saathi Care AI platform following the complete centralization of model invocations through Google ADK 2.11.0.

## Verification Matrix

| Claim | Previous Status | Current Status | Actual Source Evidence | Test Evidence | Verdict |
|---|---|---|---|---|---|
| **Google ADK native BaseLlm integration** | PARTIALLY VERIFIED | **VERIFIED** | `ADKModelGateway` in `app/workflow/gateway.py` subclasses `google.adk.models.base_llm.BaseLlm`. It implements `generate_content_async(LlmRequest)` yielding `LlmResponse` with `types.Content` and `GenerateContentResponseUsageMetadata`. | `tests/test_centralized_adk_gateway.py::test_adk_model_gateway_subclasses_base_llm` passes. | **VERIFIED** |
| **All LLM invocations routed through Gateway** | INCORRECT (Bypasses in `_llm_route` & `triage_gate`) | **VERIFIED** | All 5 invocation paths (`node_program_coach`, `_llm_route`, `evaluate_safety_gate`, `explain_report`, and `GroundingPlanner._ask`) now invoke `ADKModelGateway` using native `LlmRequest` and `generate_request()`. | `tests/test_centralized_adk_gateway.py` (Coach, Route, Triage tests) pass. | **VERIFIED** |
| **Elimination of direct raw HTTP calls for Gemini** | INCORRECT (Raw `requests.post` to Google API) | **VERIFIED** | Direct `requests.post` to `generativelanguage.googleapis.com` has been completely eliminated. Gemini calls now execute natively via ADK's `google.adk.models.google_llm.Gemini` using `google.genai.Client`. | `test_no_application_direct_gemini_http_calls` passes with monkeypatched assertion. | **VERIFIED** |
| **Centralized model routing via `models.yaml`** | VERIFIED | **VERIFIED** | Model tiers (`cost_optimized`, `quality_optimized`, `voice`) are loaded dynamically from `config/models.yaml` by `ModelClient`. | `test_models_yaml_structure_and_providers` passes. | **VERIFIED** |
| **Bounded retries with exponential backoff & jitter** | PARTIALLY VERIFIED (Static delay) | **VERIFIED** | `_invoke_with_retry` enforces a strict bound of 3 retries (4 total attempts) with monotonic exponential backoff (`delay = base * 2^attempt * (1 + jitter)`). | `test_retry_attempts_are_bounded_and_backoff_increases` confirms 4 attempts and increasing delays. | **VERIFIED** |
| **Multi-provider fallback** | VERIFIED | **VERIFIED** | `ModelClient.generate()` catches primary provider failure, records health metrics, and falls back to secondary provider (`gpt-4o-mini`). | `test_fallback_works_after_primary_failure` passes. | **VERIFIED** |
| **Zero accidental booking tool execution on LLM failure** | NOT AUDITED | **VERIFIED** | Booking tools (`LabTools.book_test`) are isolated in deterministic execution phases requiring verbal confirmation (`verbal_confirmed=True`) and valid slot selection. LLM failures never invoke booking tools. | `test_failed_requests_do_not_execute_booking_tools` passes. | **VERIFIED** |
| **Deterministic safety gate preservation** | VERIFIED | **VERIFIED** | Emergency red flags (chest pain, syncope, severe hemorrhage, self-harm) are evaluated in Step 1 using compiled regexes before any LLM is contacted. Works during 100% cloud outage. | `test_safety_emergencies_caught_deterministically_when_all_llms_down` passes across EN, HI, Hinglish. | **VERIFIED** |
| **Langfuse Observability & Span Metadata** | VERIFIED | **VERIFIED** | `app/observability/tracer.py` records root, node, tool, and LLM spans with prompt tokens, completion tokens, cost, latency, model id, and failure reasons. | `test_observability_captures_successful_and_failed_attempts` passes. | **VERIFIED** |
| **Passing test suite** | 510 tests | **526 tests** | Pytest execution ran 526 tests across all modules. | **526 passed, 0 failed** in 38.4s. | **VERIFIED** |

---

## Technical Audit Details

### 1. Model Invocation Path Audit
Every model call site in the application was audited:
1. **`app/workflow/graph.py` -> `node_program_coach`:** Uses `ADKModelGateway.generate_request(LlmRequest)`.
2. **`app/workflow/graph.py` -> `_llm_route`:** Uses `ADKModelGateway.generate_request(LlmRequest)`.
3. **`app/safety/triage_gate.py` -> `evaluate_safety_gate`:** Uses `ADKModelGateway.generate_request(LlmRequest)`.
4. **`app/tools/report_tools.py` -> `explain_report`:** Uses `ADKModelGateway.generate_request(LlmRequest)`.
5. **`app/grounding/engine.py` -> `GroundingPlanner._ask`:** Uses `ADKModelGateway.generate_request(LlmRequest)`.

### 2. Remaining Raw HTTP Calls and Their Justification
A full codebase search reveals the following non-generation HTTP calls remain, all outside the model invocation path:
1. **Semantic Cache Embedding (`app/grounding/semantic_cache.py`):** Calls `text-embedding-004:embedContent` for embedding generation. (Embeddings are vectors, not text generation, and do not use the LLM gateway).
2. **Credential Startup Check (`app/workflow/model_client.py` -> `check_credentials`):** Checks `/models` endpoint at server initialization to fail fast if API keys are misconfigured.
3. **SMS / Emergency Alerts (`app/safety/alerts.py`):** Outgoing webhooks to Telegram Bot API and Twilio REST API for emergency dispatch.
4. **Diagnostics Partner Backend (`app/tools/lab_backend.py` -> `HttpLabBackend`):** Standard REST calls to the diagnostic partner's booking and slot endpoints.

### 3. Native ADK Network Handling
- **Gemini Models:** Use native ADK `google.adk.models.google_llm.Gemini` which leverages the official `google.genai.Client`.
- **Non-Gemini Models (OpenAI, Ollama, vLLM):** Use `ADKModelGateway`'s provider adapter because the optional dependency `google-adk[openai]` is not installed in the environment.

### 4. Architectural Limitations
- **Singleton Graph:** Modifying `config/models.yaml` requires an application restart because `WorkflowGraph` is initialized globally in `adk_graph.py`.
- **In-Memory Sessions:** `InMemorySessionService` is used for session management. In a production cluster at 15M scale, this must be swapped for Redis.
