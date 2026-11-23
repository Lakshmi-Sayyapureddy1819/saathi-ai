# Submission Readiness Report: Saathi Care AI

Date: 2026-11-23 (reconciled after the second verification pass). Every number comes from a command run in these sessions
unless marked otherwise. Labels: **VERIFIED**, **IMPLEMENTED BUT NOT LIVE-VERIFIED**, **PARTIALLY IMPLEMENTED**,
**NOT IMPLEMENTED**. Unit-test results and assignment-evaluation results are kept separate (sections 2 and 5).

## 1. Startup and health
| Item | Result |
|---|---|
| Backend | `python -m uvicorn app.api:app --host 127.0.0.1 --port 8000`; `GET /api/health` -> `{"status":"ok"}` (`/health` is 404: the route lives under `/api`) |
| API docs | `/docs` -> 200 |
| Frontend | `npm run dev` on `http://127.0.0.1:5173` -> 200, with working calls to `/api/members`, `/api/config`, `/api/programs` |
| `/api/readiness` on the dev server | LLM real, DB real, **lab partner "real HTTP adapter", Telegram alerts "real"**, telephony simulated |
| Sandbox | Workflow testing used a second backend (port 8200, since stopped) and isolated Playwright ports (8100/8101/5273/5274) with alerts, keys and lab API blanked, so no test traffic reached real channels |

## 2. Unit and integration tests (not assignment evaluation)
| Suite | Result |
|---|---|
| Backend `python -m pytest tests -q`, **no exclusions** | **526 passed, 0 failed, 0 skipped** (36 test files). Final code: 525, 525, then 526 after the test replacement below |
| Frontend `tsc --noEmit` | clean |
| Frontend `vitest run` | **31 passed** |
| Browser end-to-end, full suite (6 spec files, real backends on isolated ports, mock LLM) | **38 passed** in 7.2 min |
| Fresh virtualenv | Earlier run: new venv, `pip install -r requirements.txt` succeeded, **515 passed** with the then-new file excluded. **Not re-run on the final code**, so the final 526 is verified in the main venv only |

### The previously excluded file: `tests/test_centralized_adk_gateway.py`
- **What it was:** a new test file added by a second AI session while mine was running. I excluded it from my "515 passed" figure
  because it failed intermittently (7 failures in the fresh venv, 4 later in the main venv) while that session was still editing
  `gateway.py`, `triage_gate.py`, `model_client.py` and the file itself.
- **Why it failed:** work in progress, with real findings inside it. That session's commit `b2a9d94` fixed (a) a **self-harm
  regex gap** ("killing myself", "ending my life", "wanting to die" were not matched), (b) **retry jitter that was not monotonic**
  (a later retry could wait less than an earlier one), (c) an obsolete assertion on the emergency payload shape, and (d) a
  mis-indented block.
- **A test I replaced rather than silenced:** `test_no_application_direct_gemini_http_calls` claimed to prove Gemini goes through
  native ADK, but it ran in mock mode with no API key, so it could never reach Gemini and passed vacuously. I replaced it with
  `test_provider_http_egress_is_confined_to_known_files` (fails if any file outside `model_client.py` and `semantic_cache.py`
  talks to a provider) and `test_gateway_mock_mode_makes_no_network_call`. One meaningless test became two real ones.
- **Result now:** the file runs alone at 11 passed and the full suite has no exclusions.

## 3. Real user workflows
Driven through the real API against the sandbox with the **real LLM**, plus the Playwright suite.
| Workflow | Result |
|---|---|
| Dashboard, every nav item, no console errors across a tour | VERIFIED (Playwright) |
| Wellness question; Hinglish question | VERIFIED (real LLM through the API; mock LLM in Playwright) |
| Emergency (Hinglish chest pain) | VERIFIED: deterministic response with 112 / 108, booking draft cleared |
| Medication request; prompt-injection attempt | VERIFIED: no diagnosis or advice, no prompt leak |
| Lab search -> package -> slot -> explicit confirm -> booking id | VERIFIED (Hinglish "9 baje" correctly refused for a fasting test with valid slots offered) |
| Repeat "yes" after booking | VERIFIED: answers "nothing pending", one booking only |
| Booking history; cancel with dialog confirmation | VERIFIED (Playwright) |
| Human handoff, coordinator approve and reject | VERIFIED (Playwright, stack where every lab call fails) |
| Session isolation | VERIFIED: another member's token returns 401 |
| API-error UI with retry; invalid input | VERIFIED (Playwright tests 12, 13) |
| Voice screen controls and error states | VERIFIED with a fake microphone and **speech doubles**; real human speech not tested |
| Responsive layouts 1440 / 1280 / 768 / 390, accessibility basics | VERIFIED by Playwright overflow and focus tests |
| Mimi mascot | VERIFIED in chat and on the dashboard; **absent from the voice screen by design** (screenshots viewed: voice, mobile chat, dashboard, emergency) |

## 4. Defects found and fixed
| Pri | Defect | Fix |
|---|---|---|
| P0 (safety) | Gateway read `llm_request.custom_metadata`, absent in ADK 2.11. Any trace-less call raised; the triage gate swallowed it and returned GREEN, silently disabling its **LLM second stage**. Deterministic rules were unaffected | `getattr` guard + `tests/test_gateway_no_trace.py` |
| P0 (safety) | Self-harm phrasings not matched by the regex (found by the other session's tests) | Fixed in `b2a9d94`; not my change |
| P1 | Retry delays not monotonic | Fixed in `b2a9d94`; not my change |
| P1 | "Show my bookings" mid-booking re-prompted for slots | Listing is read-only and works with an open draft |
| P1 (brief) | Voice screen was "Talk to Mimi" with the mascot; brief says Mimi is chat-only | Renamed "Voice assistant", own waveform orb, tests/docs updated |
| P2 | Vacuous "native ADK" test | Replaced (section 2) |

## 5. Assignment evaluation (live run `20261123T045127Z`, promoted to `EVALS.md`)
Command: `python -m evaluations.run_evals --promote` (real Gemini and OpenAI calls; 55 chat cases, 14.5% Hindi/Hinglish; 15 voice calls).
| Metric | Result | Target | n |
|---|---|---|---|
| Intent accuracy | 95.83% (23/24) | >= 95% | 24 |
| Red-flag recall | 100% | 100% | 8 |
| No-diagnosis compliance | 100% | 100% | 5 |
| Tool-call argument correctness | 100% | 100% | 33 |
| Groundedness, lexical proxy | **73.8% (misses target)** | >= 80% | 13 |
| Faithfulness, LLM claim-level | 97.8% (judge control PASS) | >= 80% | 13 |
| Wrong-booking rate | 0% | 0% | 4 |
| Chaos recovery | 100% | >= 90% | 5 |
| Voice read-back correctness / wrong-booking | 100% (20/20) / 0% (0/15 calls) | 100% / 0% | simulated ASR |
| Voice time-to-first-audio p50 / p95 | 57 / 65 ms | <= 1500 | **simulated STT/TTS, not real latency** |
| Judge kappa vs human labels | 0.795 | >= 0.6 | 15 |

Offline deterministic set (`python -m evaluations.deterministic_eval`, free): red-flag core 27/27, extended 13/13, no-diagnosis
25/25, benign wrongly blocked 0/35, off-topic retrieval 0/15, on-topic miss 0/15, chaos 50/50, wrong-booking 0/108. This set was
extended after first-run misses, so it is a **tuned regression check, not a blind test**.

**Run-to-run variation (live runs):** lexical groundedness 74.6% / 78.3% / 73.8% (never reaches 80%, so a real miss);
faithfulness 96.9% / 100% / 97.8%; intent 100% / 95.83% / 95.83%; judge kappa 0.694 / 0.795. Explained in `EVALS.md`.
Kappa rests on one human who filled both annotator columns.

**Grounding comparison (same 12 questions):**
| Mode | Mean latency | p95 | Tokens/turn | Cost/turn | Faithfulness | Hallucination | Member-data correct |
|---|---|---|---|---|---|---|---|
| A (agentic RAG) | 18.6 s | 29.3 s | 2129 | $0.003985 | 100% | 0% | **0%** (n=5) |
| B (facts + tools) | 12.8 s | 22.2 s | 1286 | $0.002521 | n/a | n/a | **100%** (n=5) |

Caveats: the earlier run today gave Mode A $0.000858 and 1431 tokens/turn (4.6x lower) and Mode B slower than A; I did not find
out why, so neither cost figure should be quoted as settled. This promoted run also **overlapped with the 7-minute browser suite
on the same machine**, which may have inflated latency. Mode B answers 0% of library questions by design.

**Not re-run in this pass** (frozen 2026-11-22 snapshots, kept inside the INR 500 cap): four-model comparison, prompt versions
v1-v4 with the injection suite, retriever comparison, cache threshold sweep, incident drill. Prompt injection was exercised today
only by unit tests and the API check in section 3.

## 6. ADK, provider and fallback
- ADK 2.11.0 real `Workflow` + `@node`: **VERIFIED**.
- **Single LLM entry point: VERIFIED** by source search. Only `gateway.py` builds and calls `ModelClient`.
- **Gemini generation uses ADK's native `Gemini` class** (read in `model_client.py`; the live eval ran Gemini models through it, but
  I did not isolate a single live Gemini call). **OpenAI, Ollama and vLLM use the project's own `requests` calls: PARTIALLY native.**
- Semantic-cache **embedding** calls bypass the gateway (direct HTTP, no gateway fallback), now guarded by the egress test.
- Retries (max 3, exponential backoff with jitter), timeouts, vendor fallback, circuit breaker: **VERIFIED by unit tests with
  mocked providers**. **Failover during a real provider outage: IMPLEMENTED BUT NOT LIVE-VERIFIED.**
- Both provider credentials checked "ok" by the app's credential check.

## 7. Voice
One shared workflow for chat and voice: **VERIFIED**. Browser STT/TTS with interrupt, mute, read-back, explicit confirmation, and
the permission-denied / no-mic / unsupported-browser / server-down / speech-error states: **VERIFIED with a fake mic and speech
doubles**. Real speech and accents, and telephony (outbound call is simulated): **IMPLEMENTED BUT NOT LIVE-VERIFIED**.

## 8. Safety and booking
Deterministic gate independent of the LLM: **VERIFIED**. No diagnosis, medication refusal, injection: **VERIFIED**. Explicit
confirmation, idempotency key on every retry, no duplicate on a repeated "yes", failure -> handoff: **VERIFIED**. The simulated
lab failure rate **defaults to 0**; the brief's 15% needs `LAB_FAILURE_RATE=0.15` (mechanism VERIFIED, not the default).
The lab HTTP adapter has never run against a real partner.

## 9. Observability, cache, frontend, scale
- Local trace JSONL for every node/tool/model call: **VERIFIED**. Langfuse cloud export: keys present and unit-tested with a stub;
  **I never inspected a live Langfuse project: IMPLEMENTED BUT NOT LIVE-VERIFIED.** Content redacted by default.
- Semantic cache (threshold 0.88, TTL, member data bypassed): **VERIFIED by tests**; 0% false hits on 34 labelled pairs is an
  earlier snapshot, not re-run. Redis path: **IMPLEMENTED BUT NOT LIVE-VERIFIED** (fakeredis).
- Frontend: all pages, loading/error/empty states, responsive and accessible basics: **VERIFIED by Playwright**.
- 15M interactions/month plan, routing and DPDP design: **PARTIALLY IMPLEMENTED** (design and cost model; **no load test**).

## 10. Documentation
Updated this pass: `PLAN.md` (section 11: status table, trade-offs), `ARCHITECTURE.md` (section 6: as-built graph, ADK, gateway and
bypasses, persistence, modes, booking, voice, observability, cache, scale/DPDP), `EVALS.md` (promoted run, change explanation,
commands, limitations), `AI_USAGE.md` (section 3d: corrections, concurrency, verified vs AI-generated), `FINAL_STATUS.md`,
`INDEPENDENT_REVIEW.md` (marked superseded). `README.md` and `TESTDEMO.md` only got the voice-name fix. AI token usage for these
sessions was not measured.

## 11. Actual LLM spend
About **USD 3.48** cumulative from `cost_usd` on non-mock LLM spans in `logs/*.jsonl`, measured **before** the second promoted
eval run, which added more that I did not re-total. It comes from the app's own pricing table, not a provider invoice. The brief's
cap is INR 500; with two full live evals added the margin is thin, so re-sum with the same method before quoting a final figure.

## 12. Remaining limitations
1. Lexical groundedness misses its 80% target in every live run; intent accuracy has one case of slack.
2. Mode A/B cost and latency are unstable across runs (unexplained 4.6x cost difference; one run overlapped other load).
3. Judge kappa is based on one annotator; samples are small (red-flag 8, wrong-booking 4, chaos 5, calibration 15).
4. OpenAI/Ollama/vLLM and embeddings are not native ADK networking.
5. Voice latency is simulated; no real telephony; real-speech testing not done.
6. Langfuse cloud, Telegram delivery, a real lab partner, and real provider failover were not exercised.
7. An unexplained ADK warning ("Node 'lab_booking' has conditional/DEFAULT edges but none were matched ... The branch will end") and
   an `Event loop is closed` traceback from the genai async client at shutdown appear in logs; neither failed a test.
8. Visual nits not fixed: the "Demo mode" chip is clipped in the voice transcript, and mobile header text truncates ("Chat with
   Mi...", "Active - P..."). A broad frontend polish pass was not done.
9. Seed members' past bookings render as bare package ids (e.g. `LP_001`) beside real bookings.
10. Demo video not recorded; public repo state and rotation of a previously exposed Gemini key not confirmed.
11. Another AI session is committing to this repo at the same time (`gaps.md` was changed to mark the report-explainer stretch goal
    done; I did not verify that claim). Re-run the suite after any further change.

## 13. Recommended demo sequence
1. Start both servers. 2. Dashboard, pick Aarav. 3. Chat: Hinglish wellness question (citations, Mode A vs B toggle). 4. Medication
and injection refusal. 5. Emergency (on a stack with alerts off). 6. Hinglish lab booking -> confirm -> history; repeat "yes" for
idempotency. 7. `LAB_FAILURE_RATE=1` for handoff and coordinator approval. 8. Voice assistant page. 9. Insights. 10. Trace JSONL and `EVALS.md`.

## 14. Git state (nothing committed or pushed by me)
Final `git status`: modified `EVALS.md`, `SUBMISSION_READINESS_REPORT.md`; untracked
`evaluations/snapshots/eval_results_2026-11-23.json`. Everything else is already in commits made by the other session (latest
`1f0c909`), including my earlier edits. Scratch logs in the repo root are git-ignored (`*.log`). A scan of tracked and untracked
files for Gemini, OpenAI, Langfuse and Telegram key patterns found **no secrets**; `.env` is ignored and untracked.

Suggested logical commits for the two remaining files: (1) `docs(evals): publish 2026-11-23 live run with change explanation`
(`EVALS.md`, `evaluations/snapshots/eval_results_2026-11-23.json`); (2) `docs: reconcile submission readiness report`.

## 15. Addendum: "yes" not responding (reported by the user, same day)
- **Cause (reproduced):** `.env` sets `LAB_BACKEND=http`, `LAB_API_URL=http://127.0.0.1:8100`, but the partner service
  (`python -m services.lab_partner`) was not running. Slot lookup silently fell back to local data, so the flow looked normal until
  "yes": the booking call was refused, retried 3 times, and the chat handed off to a coordinator and paused. With the service up, the
  same flow books correctly over HTTP (verified on a throwaway partner + app with a temp DB).
- **Fixes:** `/api/readiness` now probes the partner and shows "PARTNER UNREACHABLE" plus a new `warnings` list (non-blocking, so
  production startup is unchanged); a bare "yes" after a confirmed booking now says nothing is pending instead of "I didn't quite
  catch that". Tests: `test_readiness_warns_when_the_http_lab_partner_is_unreachable`, `tests/test_bare_yes_after_booking.py`.
  Full suite: **529 passed**.
- **Still open:** with a dead partner the member still sees a handoff and a paused chat; that is the designed failure path, not a
  bug. Slot lookup falling back to local availability while bookings go to the partner can offer slots the partner will refuse.
- **Found in the dev server log:** Gemini returned **403** for `gemini-3.5-flash-lite`, so calls were served by the OpenAI fallback.
  The Gemini key or its API access needs checking; this also means the fallback path is being exercised for real.
- **Not committed.** The dev partner service on :8100 was started by hand and will not restart on its own.
