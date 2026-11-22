# Saathi Care AI

Wellness-coach + lab-booking assistant with a deterministic safety gate, tool-backed booking, a human-approval
handoff, tracing on every step, redacted logging and a measured evaluation harness. This repository is a prototype of
the architecture described in `ARCHITECTURE.md` (which also lists what is *not* implemented).

## Setup

```bash
python -m venv .venv           # Python 3.12 tested; google-adk 2.11.0, langfuse 4.x
.venv\Scripts\activate         # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
cp .env.example .env           # then fill in GEMINI_API_KEY and/or OPENAI_API_KEY (see below)
```

Never commit `.env`. If a key has ever been printed in a log or URL, rotate it.

`.env.example` lists every variable the code reads. Provider keys are left **empty** on purpose: an empty key means
"not configured" and the app runs in mock mode, whereas placeholder text would be treated as a real key.

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY`, `OPENAI_API_KEY` | LLM providers (models are chosen in `config/models.yaml`) |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | optional Langfuse tracing (both keys required) |
| `TRACE_FILE` | local span log (default `logs/traces.jsonl`) |
| `EMBED_MODEL` | embedding model for the semantic cache |
| `LAB_FAILURE_RATE` | simulated partner-lab failure rate (0 disables) |

## Run

```bash
python -m app.workflow.graph          # scripted demo: booking flow + emergency
python interactive_chat.py            # chat in the terminal
python voice_demo.py                  # simulated voice call: generic request -> which test? -> slot -> confirm -> booked
```

Without API keys the app still runs: LLM calls return a clearly flagged `[MOCK:...]` response and are excluded from
metrics. Booking, safety and routing need no LLM.

## Tests and evaluations

```bash
python -m pytest tests -q                 # hermetic: API keys are blanked, no network
python -m evaluations.run_evals           # live LLM calls if keys are set; writes to evaluations/runs/<stamp>/ (git-ignored)
python -m evaluations.run_evals --promote # same, then ALSO publish EVALS.md and add a new dated snapshot (see below)
python -m evaluations.freeze_calibration  # one-off: generate + freeze the responses humans will label (see below)
```

`EVALS.md` is the published report: every figure comes from the run it was promoted from, and it ends with a
**Limitations** section (small samples, judge caveats, a known retrieval issue). `N/A` means no real LLM call was made.

**Evaluation evidence and tracked files.** LLM output, trace ids and latencies change on every run, so tracking a
regenerated results file would create ~1,000-line diffs that mean nothing. A normal run therefore writes only to the
git-ignored `evaluations/runs/<UTC stamp>/` and changes no tracked file. The reviewer-facing evidence is the dated,
frozen `evaluations/snapshots/eval_results_2026-11-22.json` (provenance and SHA-256 in `evaluations/snapshots/README.md`).
`--promote` adds a *new* dated snapshot and rewrites `EVALS.md`; it never overwrites an existing snapshot. Promote
rarely, and commit the new snapshot together with the `EVALS.md` it belongs to.

## ADK 2.x workflow and human approval

`app/workflow/adk_graph.py` is a Google ADK 2.11 `Workflow` that wraps the *same* node logic as `graph.py`
(`WorkflowGraph(chain=False)`), with typed state stored as JSON in ADK session state. When booking fails after retries
the workflow pauses with a care-coordinator approval request (`RequestInput`) and resumes with approve or reject:

```python
app = AdkSaathi()
r = await app.turn("book thyroid test", session)          # ... slot, "yes"
if r.pending_interrupt_id:                                  # outage -> waiting for coordinator
    r = await app.resume(r.session, r.pending_interrupt_id, ApprovalDecision(approved=False, note="Lab closed"))
```

Approval pauses happen only on the ADK path; the plain chat/CLI path just tells the member a coordinator will call.
**The approval is not authenticated:** whoever holds the interrupt id can approve. A real deployment must put the
coordinator UI behind authentication and bind approvals to the coordinator's identity.

## Judge calibration (kappa)

Kappa only means something if the judge and the people scored the *same* responses, so generation and evaluation are
separate:

1. `python -m evaluations.freeze_calibration` generates the 15 answers and **freezes** them in
   `evaluations/datasets/calibration_responses.json` (read-only file + `calibration_responses.sha256`). It refuses to
   overwrite an existing set; `--force` is refused once any human label exists.
2. Two people label them **independently** (no discussion, not shown the judge's output) as `pass | marginal | fail`
   in `evaluations/datasets/human_labels.json` (`annotator_a`, `annotator_b`).
3. `run_evals` only *reads* the frozen set (verifying its hash) and judges those exact responses. It never regenerates
   or rewrites them; a tampered or missing hash is reported as an integrity failure instead of being trusted.

Until 15 complete label pairs exist, kappa is reported as N/A. Do not label with an LLM and do not edit labels after
seeing judge output. If the agent changes materially, start a *new* calibration round rather than replacing a labelled
set.

## Semantic cache

Embedding cosine similarity at threshold 0.88. Measured on 8 hand-picked pairs, paraphrases scored 0.76-0.85 and
different-intent pairs up to 0.745, so no threshold separates them cleanly; 0.88 is deliberately conservative
(near-zero hits, zero wrong answers). Tune only with a labelled set of >=100 pairs. Mode B (member-specific) answers
are never cached.

## Observability

Each user turn creates a root span; every node, tool call and LLM call is a child span carrying the same `trace_id`.
Spans are always written to `logs/traces.jsonl`. If both `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set they are
also sent to Langfuse with the 4.x observation API (`start_as_current_observation`): LLM spans become *generations*
with model, token usage and cost, and our `trace_id` is used as the Langfuse trace id.

- Langfuse problems never break a turn, but they are never silent: each failure is counted, logged, kept in
  `app.observability.tracer.tracing_status()` and written to the affected local span as `langfuse_error`.
- **Credentials are checked at startup.** The SDK exports spans in the background, so wrong keys would otherwise only
  show up as `Failed to export span batch ... 401` log lines. When the keys are rejected, Langfuse is switched off
  with an actionable warning (`tracing_status().auth_verified` is `False`) and local tracing continues; an unreachable
  Langfuse is reported as unverified instead. Set `LANGFUSE_AUTH_CHECK=0` to skip the check. Set `LANGFUSE_HOST` to your
  project's region (for example `https://us.cloud.langfuse.com`): keys from one region are rejected by the others.
- **Verification status:**
  - *Offline:* the real Langfuse 4.15.6 SDK with an in-memory OpenTelemetry exporter (nesting, trace id, generation
    model/usage/cost, error level, credential check).
  - *Live (2026-11-22, US region):* credentials accepted by the startup check, and a booking turn's spans were read
    back from Langfuse's API (`turn`, `node_safety_gate`, `node_intent_router`, `node_lab_booking`, `tool:book_test`).
  - *Not yet verified live:* LLM *generation* spans (model, token usage, cost), which need a turn that calls the LLM,
    and how traces look in the Langfuse UI (checked through the API only).

```bash
jq 'select(.kind=="llm") | {trace_id, model: .metadata.model, tokens: (.metadata.prompt_tokens + .metadata.completion_tokens), latency_ms}' logs/traces.jsonl
```

## Privacy

Members' messages can contain health data. Logs, stdout and trace spans never contain message text: the safety gate
logs the crisis category, member id and `<redacted len=N tag=...>` (an HMAC with a per-process random salt, so it
correlates within a run but cannot be dictionary-checked and changes on restart). Tool spans record redacted queries.
Not covered: the in-memory session (`turn_history`) and the ADK in-memory session store hold raw text, and `member_id` is
logged; a production deployment needs retention limits on both.

## Layout

- `app/safety/` deterministic triage gate (red flags, no-diagnosis rule)
- `app/workflow/` state (Pydantic V2), graph, ADK wrapper, model client (driven by `config/models.yaml`)
- `app/grounding/` Mode A retrieval, Mode B facts + backend tools, embedding semantic cache
- `app/tools/` lab catalogue/schedule/booking tools, slot/confirmation parsing
- `app/observability/` tracer (local JSONL + Langfuse) and redaction
- `prompts/v3/`, `prompts/v4/` structured prompts (role, rules, facts, tools, output format, examples, injection defense); v4 is active
- `evaluations/` datasets, `run_evals.py`, frozen calibration tooling, dated `snapshots/` (tracked), `runs/` (ignored)

## Known gaps

- **Langfuse:** node and tool spans verified live; LLM generation spans and the UI view not yet (see Observability).
- **Retrieval is lexical** (stemming + a small Hinglish lexicon in `app/grounding/engine.py`). New Hindi vocabulary needs
  a lexicon entry until embedding retrieval is added. *Known issue:* off-topic queries can still retrieve an unrelated
  document (e.g. "what is the weather" retrieves the Sheetali Pranayama doc because it mentions summer weather);
  there is no off-topic rejection, so the coach prompt must decline to use irrelevant context. Not evaluated.
- **No-diagnosis rule false positive:** "Is it heart healthy to eat oats?" gets the canned no-diagnosis reply, because the
  rule treats "is it ... heart" as a diagnosis question. It errs on the cautious side but blocks a legitimate question.
- **Generic requests:** "book a blood test" asks *which test*; the catalogue deliberately ignores generic words like
  "blood", "test", "panel", so they never match packages on their own.
- **Evaluation evidence is thin:** wrong-booking n=4 and chaos recovery n=5, red-flag n=8; the faithfulness judge is
  not human-validated, is from the same vendor as the generator and its negative control has 3 cases (details in
  `EVALS.md`). Strict lexical groundedness cannot score Hindi/Hinglish translations.
- **Judge kappa is N/A** until two independent annotators label the 15 frozen responses.
- **Voice channel:** STT/TTS and barge-in are simulated (hook + latency metrics exist; no real audio).
- **Approval is unauthenticated** (see ADK section); the simulated emergency SMS is a log line, not a real Twilio call.
- `ARCHITECTURE.md` LLM costs are measured (n=12 per mode); voice, STT/TTS and Redis costs are not, and its dollar
  projections in section 3 are marked historical.
- `gaps.md` is a historical audit and is out of date; see this README instead.
