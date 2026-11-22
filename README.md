# Saathi Care AI

Wellness-coach + lab-booking assistant with a deterministic safety gate, tool-backed booking, a human-approval
handoff, tracing on every step, redacted logging and a measured evaluation harness. This repository is a prototype of
the architecture described in `ARCHITECTURE.md` (which also lists what is *not* implemented).

**Actual LLM Spend:** [FILL IN FINAL LLM SPEND HERE (<= INR 500)]

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
python voice_demo.py --outbound       # outbound reminder call: agent phones a member about a pending checkup and books it
```

Without API keys the app still runs: LLM calls return a clearly flagged `[MOCK:...]` response and are excluded from
metrics. Booking, safety and routing need no LLM.

## Web UI (localhost)

Stack: **React 19 + TypeScript + Vite** frontend (`frontend/`), **FastAPI** backend (`app/api.py`, wire models in
`app/api_schemas.py`) that drives the ADK 2.x workflow (`AdkSaathi`), so the web UI uses the same safety gate, routing,
booking tools and tracing as the CLI.

```powershell
# terminal 1: backend  (http://127.0.0.1:8000, Swagger at /docs)
.venv\Scripts\activate
$env:COORDINATOR_TOKEN = "choose-a-secret"      # optional; without it the coordinator console is disabled
python -m uvicorn app.api:app --host 127.0.0.1 --port 8000

# terminal 2: frontend  (http://127.0.0.1:5173)
cd frontend
npm install        # first time only
npm run dev
```

Open **http://127.0.0.1:5173**. Coordinator console: **http://127.0.0.1:5173/#/coordinator** (enter the token above).
Don't use `--reload` on Windows if you hit `WinError 10013`.

| Variable | Where | Purpose |
|---|---|---|
| `VITE_API_URL` | `frontend/.env` | backend URL (default `http://127.0.0.1:8000`). Never put secrets in `VITE_*` vars |
| `FRONTEND_ORIGINS` | backend | CORS allow-list (default `http://localhost:5173,http://127.0.0.1:5173`) |
| `COORDINATOR_TOKEN` | backend | shared secret for approve/reject; unset = endpoints return 503 |
| `SESSION_TTL_MINUTES`, `MAX_SESSIONS`, `MESSAGES_PER_MINUTE`, `SESSIONS_PER_MINUTE` | backend | expiry and abuse limits (120 / 200 / 30 / 20) |

**Model health:** the primary model is the first entry for each route in `config/models.yaml`; the fallback only runs when
it fails. Every failed call records its reason on the span (`error`), is counted, and a call served by a fallback logs a
warning. `GET /api/llm-status` shows per-model counts, the last error, `fallback_calls` and provider-key status (no
secrets, no message text). At startup the backend asks each provider whether its key is accepted and logs
`LLM credential check: <PROVIDER> key is rejected (HTTP 400)` if not.

**Language and intent:** short, misspelled or everyday input is understood by intent ("shugar test", "throid", "bp check",
"khoon ki jaanch"); deterministic replies follow the member's language (English or Roman-script Hinglish, chosen from
what they type, see `app/workflow/replies.py`). Members can list and cancel their confirmed bookings (`cancel <booking id>`,
owner-only, frees the slot). Red-flag detection is exact-match regex with explicit spelling variants
(`tests/test_red_flag_variants.py`); it deliberately has no fuzzy matching.
Not covered: Devanagari-script input; UI chrome (buttons, headings) is English only.

**Features:** dashboard, chat with typed message kinds (answer / safety notice / emergency / booking confirmed / handoff),
suggested prompts, Hinglish, optimistic send with retry, session create/resume/delete, searchable lab catalogue, booking
stepper with day/time chips, summary + explicit confirm, change time, cancel, booking id from the backend tool, handoff
status with a coordinator console, mobile layout (tabbed), accessible labels/roles/focus states.

**API** (all under `/api`; interactive docs at `/docs`):

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /health`, `/config`, `/members`, `/packages?q=`, `/programs` | none | status and catalogue (no keys exposed) |
| `POST /sessions` `{member_id}` | none | create; returns a one-time `session_token` |
| `GET / DELETE /sessions/{id}` | `Authorization: Bearer <session_token>` | state / delete |
| `POST /sessions/{id}/messages` `{text}` (1-500 chars) | Bearer | one turn; returns full `SessionView` |
| `GET /coordinator/approvals`, `POST /coordinator/approvals/{id}` `{approved, note}` | `X-Coordinator-Token` | list / decide handed-off bookings |

**Security model and limits (local demo, not deployable as is):** per-session bearer token; a member's token can never
approve its own booking; coordinator access is ONE shared secret (no per-person identity, no audit trail of who
approved); sessions and raw transcripts are in process memory (idle expiry, caps, rate limits, lost on restart);
no TLS, no user login; the `session_token` is kept in the tab's `sessionStorage`. Without an LLM key, wellness answers are
`[MOCK]` and the UI says so.

## Evaluations

```powershell
python -m pytest tests -q                 # backend incl. tests/test_api.py (auth, isolation, booking, safety, handoff)
cd frontend; npm run typecheck; npm test  # TypeScript + vitest unit tests
cd frontend; npx playwright test          # 15 browser tests (system Edge) against real backends on :8000/:8001
```

The Playwright run starts its own backends (one with lab outages forced on to exercise the coordinator handoff) and
saves screenshots to `frontend/e2e/screenshots/`.


```bash
python -m pytest tests -q                 # hermetic: API keys are blanked, no network
python -m evaluations.run_evals           # live LLM calls if keys are set; writes to evaluations/runs/<stamp>/ (git-ignored)
python -m evaluations.run_evals --promote # same, then ALSO publish EVALS.md and add a new dated snapshot (see below)
python -m evaluations.freeze_calibration  # one-off: generate + freeze the responses humans will label (see below)
python -m evaluations.voice_eval          # 15 scripted voice calls with simulated ASR errors (also part of run_evals)
python -m evaluations.prompt_iterations   # same coach agent on prompt v1..v4: metrics + injection suite per version
python -m evaluations.incident_drill      # break the lab API and the prompt on purpose; see docs/INCIDENT_DRILL.md
```

`EVALS.md` is the published report: every figure comes from the run it was promoted from, and it ends with a
**Limitations** section (small samples, judge caveats, a known retrieval issue). `N/A` means no real LLM call was made.

**Evaluation evidence and tracked files.** LLM output, trace ids and latencies change on every run, so tracking a
regenerated results file would create ~1,000-line diffs that mean nothing. A normal run therefore writes only to the
git-ignored `evaluations/runs/<UTC stamp>/` and changes no tracked file. The reviewer-facing evidence is the dated,
frozen `evaluations/snapshots/eval_results_2026-11-22_061107.json` (latest; earlier snapshots are kept) (provenance and SHA-256 in `evaluations/snapshots/README.md`).
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

Label with `python -m evaluations.label_calibration` (add `--annotator b` for a second person): it shows each case
without any judge output, saves after every answer and can be resumed. One annotator is enough for the judge-vs-human
kappa; the inter-annotator row needs both. Until 15 labels exist for the relevant annotator(s), kappa is reported as N/A. Do not label with an LLM and do not edit labels after
seeing judge output. If the agent changes materially, start a *new* calibration round rather than replacing a labelled
set.

## Semantic cache

Embedding cosine similarity at threshold 0.88. Measured on 8 hand-picked pairs, paraphrases scored 0.76-0.85 and
different-intent pairs up to 0.745, so no threshold separates them cleanly; 0.88 is deliberately conservative
(near-zero hits, zero wrong answers). Tune only with a labelled set of >=100 pairs. Mode B (member-specific) answers
are never cached.

**Time to live.** Every entry expires `SEMANTIC_CACHE_TTL_SECONDS` (default 3600; 0 = never) after it was stored, and an
expired entry is never served. Entries are also namespaced by prompt version and embedding model, so changing the prompt
(`SAATHI_PROMPT_VERSION`) or `EMBED_MODEL` starts with an empty cache instead of serving the old prompt's answers.

**Redis (optional).** Set `REDIS_URL` (e.g. `redis://localhost:6379/0`) to share the cache across workers and restarts,
with native key expiry (`SET ... EX`). Redis receives only the embedding and the generic answer, never the member's question
text (a hash is the key); without an embedding (no Gemini key or an embedding outage) nothing goes to Redis. It fails open:
a Redis error is counted and logged and the in-process cache is used for 30 s before reconnecting. Scaling limit: lookups
scan at most 300 entries and compute cosine locally; beyond that use a vector index (RediSearch/HNSW).
`GET /api/cache-status` reports TTL, store (`memory`/`redis`), entries, hits, expirations and Redis errors (never the URL).
**Verification status:** tested against `fakeredis` (real Redis command semantics, including expiry). It has **not** been run
against a real Redis server, because none was available; try it once with a real instance before relying on it.

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
  a lexicon entry until embedding retrieval is added. Off-topic queries are rejected: a document needs a title/tag match
  or at least two distinct body words (`MIN_BODY_HITS`), so "what is the weather" no longer retrieves the Sheetali
  Pranayama doc (15 off-topic and 15 on-topic queries in `evaluations/deterministic_eval.py`). Trade-off: an on-topic
  question whose only link to a document is one body word now retrieves nothing and gets the "no matching document" reply.
- **No-diagnosis rule:** "Is it heart healthy to eat oats?" used to get the canned no-diagnosis reply; "is it heart/thyroid
  ... healthy / friendly / safe / good / diet / food" is now treated as a food question. Medication requests ("should I take
  metformin") are now caught as well. The rule is regex-based, so unusual phrasings can still slip through or be over-blocked
  (31 benign controls, 0 blocked, in the deterministic eval).
- **Generic requests:** "book a blood test" asks *which test*; the catalogue deliberately ignores generic words like
  "blood", "test", "panel", so they never match packages on their own.
- **Evaluation evidence:** the golden-set numbers are still small (wrong-booking n=4, chaos n=5, red-flag n=8), so
  `python -m evaluations.deterministic_eval` adds an offline, free run with n=27 core red flags, 13 other emergencies,
  25 diagnosis requests, 31 benign controls, 108 booking scenarios and 50 outage runs (`EVALS.md`). Its first run found
  real misses in the safety gate (20/27 core red flags); the gate was extended and the set now passes, so those results
  are tuned to that set and are not a blind test. The faithfulness judge is
  not human-validated, is from the same vendor as the generator and its negative control has 3 cases (details in
  `EVALS.md`). Strict lexical groundedness cannot score Hindi/Hinglish translations.
- **Judge kappa is N/A** until two independent annotators label the 15 frozen responses.
- **Browser voice demo (new, manual):** in the web UI tick "Voice mode" (Chrome/Edge). Uses the browser Web Speech API
  for STT/TTS (`frontend/src/voice.ts`), sends the transcript through the same `/messages` endpoint, speaks each reply,
  cuts the speech when you tap the mic (barge-in) and shows time-to-first-audio. It is typecheck- and unit-tested
  (`toSpeakable`) but **not covered by an automated browser test and not yet measured on real speech**; hi-IN
  recognition quality depends on the browser. The eval figures below still come from the simulated path.
- **Outbound reminder call (new):** `app/channels/outbound.py`. The call opens by naming the member's pending checkup
  (`pending_checkups` in `data/members.json`, English or Hinglish), pre-fills the booking draft, and then every reply goes
  through the normal workflow: safety gate and red-flag escalation first, then slot read-back and confirmation. A plain
  "no" ends the call; "no, I have chest pain" still escalates. Dialling, STT and TTS are simulated (as for inbound
  voice); there is no real telephony provider. `app/channels/outbound_scheduler.py` decides who to call and when (due within 14 days
  or overdue, calling window 09:00-19:00, at most 3 attempts 4 h apart, do-not-call list, no repeat after a booking or a
  decline) behind a `Dialler` interface that a provider would implement; nothing runs it on a timer yet. Covered by
  `tests/test_outbound_call.py` and `tests/test_outbound_scheduler.py`.
- **Voice eval path:** audio is simulated: ASR errors are injected as text, STT is a fixed sleep and TTS is text, so real
  STT/TTS latency is not measured. Read-back, wrong-booking, latency and time-to-first-audio are measured through the real
  workflow (`EVALS.md`, Voice). Wellness answers by voice miss the 1.5 s budget (LLM latency, no streaming to TTS).
- **Approval is unauthenticated** (see ADK section); the simulated emergency SMS is a log line, not a real Twilio call.
- `ARCHITECTURE.md` LLM costs are measured (n=12 per mode); voice, STT/TTS and Redis costs are not, and its dollar
  projections in section 3 were replaced by a measured-cost estimate with its assumptions stated.
