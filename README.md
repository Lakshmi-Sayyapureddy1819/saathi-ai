# Saathi Care AI

Wellness-coach + lab-booking assistant with a deterministic safety gate, tool-backed booking,
tracing on every step, and a measured evaluation harness.

## Setup

```bash
python -m venv venv            # the committed venv/ points at another machine; recreate it
venv\Scripts\activate          # Windows  (source venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
cp .env.example .env           # add GEMINI_API_KEY and/or OPENAI_API_KEY; optional LANGFUSE_* keys
```

Never commit `.env`. If a key has ever been printed in a log or URL, rotate it.

## Run

```bash
python -m app.workflow.graph          # scripted demo: booking flow + emergency
python interactive_chat.py            # chat in the terminal
python voice_demo.py                  # simulated voice channel (no real STT/TTS yet)
```

Without API keys the app still runs: LLM calls return a clearly flagged `[MOCK:...]` response and
are excluded from metrics.

## Tests and evaluations

```bash
python -m pytest tests -q
python -m evaluations.run_evals       # writes EVALS.md and evaluations/eval_results.json
```

`EVALS.md` is generated: every figure comes from that run. `N/A` means no real LLM call was made.

## Observability

Each user turn creates a root span; every node, tool call and LLM call is a child span carrying the same
`trace_id`. Spans are written to `logs/traces.jsonl` (set `TRACE_FILE` to change) and mirrored to Langfuse
when `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` are set. LLM spans carry provider-reported token counts and
estimated cost.

```bash
jq 'select(.kind=="llm") | {trace_id, model: .metadata.model, tokens: (.metadata.prompt_tokens + .metadata.completion_tokens), latency_ms}' logs/traces.jsonl
```

## Layout

- `app/safety/` deterministic triage gate (red flags, no-diagnosis rule)
- `app/workflow/` state (Pydantic V2), graph, model client (driven by `config/models.yaml`)
- `app/grounding/` Mode A retrieval, Mode B facts + backend tools, embedding semantic cache
- `app/tools/` lab catalogue/schedule/booking tools, slot/confirmation parsing
- `prompts/v3/` structured prompts (role, rules, facts, tools, output format, examples, injection defense)

## Known gaps

- Workflow is a hand-written graph, not yet an ADK 2.0 `Workflow` (`app/workflow/adk_graph.py` is a stub).
- Voice channel has no real STT/TTS or barge-in.
- Judge kappa uses placeholder labels until independent human labels exist.
- Cost figures in `ARCHITECTURE.md` are projections, not measurements.
