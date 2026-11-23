# Saathi Care Production Runbook

## Initialization & Startup
1. Set the `.env` variables `GEMINI_API_KEY`, `OPENAI_API_KEY`, and `SAATHI_PROMPT_VERSION`.
2. Confirm ADK runtime environment dependencies using `pytest tests/test_production_readiness.py`.
3. Stand up the API via Uvicorn/FastAPI: `uvicorn app.api:app --host 0.0.0.0 --port 8000`.

## Handling Outages & Circuit Breaking
The `ADKModelGateway` auto-recovers via `fallback_model` configuration in `models.yaml`.
**Action:** When a primary model cluster (e.g. `gemini-3.5-flash-lite`) sustains 5 consecutive connection timeouts, the circuit breaks. Operations will gracefully shed to the configured fallback route (e.g. `gpt-4o-mini`). No human intervention is needed.
**Audit:** Check the `Langfuse` telemetry UI; failure spans will map to `llm:{model_id}` with `failed=True`.

## Modifying Provider Routing
Routing requires zero application restarts.
Modify `config/models.yaml` (using Kubernetes configmaps or direct mounts) and dynamically change the `default_model` for a tier to trigger seamless shift.