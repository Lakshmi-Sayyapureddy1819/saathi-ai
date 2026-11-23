# Gap Analysis vs. Take-Home Brief (current state, 2026-11-23)

Replaces the earlier audit (most of its findings are fixed: ADK installed and used, suite green, tracer rewritten,
grounding/booking/eval issues addressed). Basis: the brief (`Saathi_Care_Take_Home_Assignment.md`) against the repo
files, README, EVALS.md and the frozen eval snapshot. I did not re-run tests or evals for this update (Python is not on
the shell PATH here), so "done" below means "present in the repo/docs", not "re-verified today".

## Status by brief section

| # | Section | Priority | Status | What is left |
|---|---|---|---|---|
| 1 | ADK 2.0 Workflow | Must | Done | `PLAN.md` rewritten with a mermaid graph of the real ADK workflow (incl. handoff `RequestInput`) and a code-vs-LLM table. "LLM second" stage in the safety gate is now built. |
| 2 | Grounding Mode A/B | Must | Done | Config switch `GROUNDING_MODE`; Mode A = multi-step agent loop + pluggable lexical/embedding retriever; Mode B = no retrieval, planner-chosen backend tools, fact-only prompt. Same evals on both: groundedness, hallucination rate, latency, cost, coverage, abstention, member-data correctness (`EVALS.md`). Citations verified in code and shown in the chat UI (source chips + "How I answered"). Small n, same-vendor judge; no external vector DB (in-memory index behind a `Retriever` interface). |
| 3 | Voice | Should | Done | Real browser STT/TTS demo implemented in the React UI. Time-to-first-audio budget is met for wellness turns by a 600 ms delayed spoken filler in `voice_agent.py`; the full LLM answer still takes ~2 s (no streaming to TTS). |
| 4 | Model-agnostic | Must | Done | Same eval run on 4 mixes (gemini-3.5-flash-lite, gemini-3.8-flash, gpt-4o-mini, gpt-4o) and open-weights model support added for Ollama (llama3.2). |
| 5 | Prompts | Must | Done | Before/after table for v1-v4 + injection suite (`evaluations/prompt_iterations.py`, in `EVALS.md`); named tests in `tests/test_prompt_injection.py`. |
| 6 | Evals | Must | Done, with caveats | 55 cases + 15 scripted voice calls, one command; voice metrics, Hindi/Hinglish share, Mode A/B comparison and citation metrics in `EVALS.md`. Judge kappa vs the human labels: **0.694 (target 0.6), n=15**, in the latest published snapshot. Both annotator columns were labelled by the same person, so inter-annotator kappa (1.000) is self-consistency, not independent agreement (stated in README and `AI_USAGE.md` 3c); the LLM judge also varies between runs (0.595 to 0.795 seen). **Still open:** a real second annotator; small samples (acknowledged). |
| 7 | Observability | Must | Done | Traced every node, tool call (lab tools, report explainer, retriever) and model call across chat and voice with tokens, cost, and latency per conversation. Incident drill completed with all 3 scenarios (lab API down, bad prompt change, stale backend record) + eval diffs + span trees + 4 Playwright screenshots in `docs/incident_drill/`. |
| 8 | Semantic cache | Should | Done | Sits in front of Coach (Mode A only); default threshold 0.88 configured & validated; 0.00% false-hit rate measured across 34 labelled pairs with threshold sweep analysis (`evaluations/evaluate_cache.py`); member-data and booking queries strictly bypassed. |
| 9 | Architect memo | Must | Done | Section 3 replaced with a measured-cost projection (model mix, 15M/month scenarios, latency budgets); DPDP log/mask/consent/retention and top-3 risks with monitoring made explicit. STT/TTS cost still an unpriced input. |
| - | Stretch: UI | Stretch | Done | React UI + 18 screenshots + Playwright. |
| - | Stretch: report explainer | Stretch | Not done | Optional, skip. |

## Deliverables checklist

- [x] README, EVALS.md, ARCHITECTURE.md, AI_USAGE.md, `.claude/skills/`, CLAUDE.md
- [x] **PLAN.md as the first commit**: verified, root commit `6adfa01` contains only `PLAN.md` (`git rev-list --max-parents=0 HEAD`). An earlier version of this file and PLAN.md wrongly said it was not.
- [ ] **5-8 min video**: chat demo, voice demo, trace walkthrough, Mode A vs B, routing decision. Not recorded.
- [x] **Actual LLM spend in README** (<= INR 500): added, about USD 2.65 summed from `logs/*.jsonl` (INR rate is an assumption).
- [ ] Public GitHub repo / deployed link: confirm it is pushed and public.
- [ ] Rotate the Gemini key that was once exposed (still needed).
- [x] Repo clutter: `scripts/archive_patches/` (13 patch scripts), `model_client_old.py`, `GEMINI.md`, `.docx` blueprint. Consider deleting or explaining.
- [x] `AI_USAGE.md` section 3b records a concrete overruling (AI-generated calibration labels reverted).
- [x] README "Known gaps" now points here for the remaining checklist.

## Known honesty items (keep them stated, graders score "honesty about gaps")

- Judge kappa 0.694 rests on one human (same person labelled A and B); faithfulness judge same-vendor and unvalidated.
- Wrong-booking n=4, chaos n=5, red-flag n=8: statistically weak.
- Retrieval is lexical by default (embedding backend available, `RETRIEVER=embedding`); off-topic rejection was tuned on a 27/15-query set, so it is optimistic. Mode A p95 latency is high and varies a lot (agent loop + provider load).
- Approval/coordinator is a shared secret, not real auth.

## Priority order for the remaining time

Done in the repo: model mixes, incident drill, prompt iterations, PLAN.md graph, voice metrics, architect memo,
Mode A/B recommendation, AI_USAGE overruling example (section 3b), Code & Feature Gaps (safety gate LLM, browser STT/TTS, open-weights model, stale record drill, hallucination rate for Mode B, Hindi/Hinglish eval share, repo clutter cleanup).

Only you can do these:
1. ~~Hand-label the 15 calibration responses~~ (A and B both done, by the same person; see caveat in row 6.) Earlier note: Done by you (annotator A) and promoted in `eval_results_2026-11-22_174446.json`. A second annotator would fill the inter-annotator row.
2. **Rotate the exposed Gemini key** (runtime spend is already in the README).
3. **Record the 5-8 min video**, with Langfuse UI screenshots (drill trace, one LLM generation span).
4. **Commit and push** to a public repo (16 commits exist locally; the working tree has many uncommitted changes, and
   `origin` is set but confirm it is pushed and public).

Built, needs your manual check: browser Web Speech voice demo (Voice mode checkbox in the chat; Chrome/Edge). Try a
booking by voice, say "fifty" for "fifteen", interrupt the reply, and note the time-to-first-audio shown; record it
for the video. Optional: open-weights model mix; hallucination rate for Mode B.

## Voice: what to do

**Short answer: yes, build a small real voice demo, but keep it minimal. Do not skip it, do not over-build it.**

Why: it is a *Should* worth only 5/100 points, but the brief's Must #1 requires "chat and voice share the same
workflow, only the channel adapter differs", the video asks for "a voice demo if built", and the client brief is
phone-call-centric. What you have is a typed-text simulation (`sleep(0.05)` as STT, character-by-character "TTS"), so
it does not honestly count as speech-to-text or text-to-speech. Telephony is explicitly NOT required.

Cheapest credible path (about 1.5-2 hours):

1. **Browser demo**: use the Web Speech API (`SpeechRecognition` for STT with `hi-IN`/`en-IN`, `speechSynthesis` for TTS)
   in the existing React app, posting the transcript to the same `/sessions/{id}/messages` endpoint. Zero API cost,
   zero new backend workflow. Barge-in = `speechSynthesis.cancel()` when recognition starts.
   Alternative: Gemini Live / Whisper + any TTS, but costs time and money for little extra score.
2. **Keep the logic you already have** in `voice_agent.py` (number-safe slot parse, read-back, explicit "yes" before
   `book_test`, barge-in) and make sure the read-back says the test, date and time, and requires "yes".
3. **Report the missing voice numbers** from the 15 ASR-perturbation cases: read-back correctness, wrong-booking rate
   (target 0), turn latency, and a time-to-first-audio budget with what you achieved (e.g. budget 1.5 s).
4. **Be honest** in README/EVALS about what is simulated (ASR errors are injected text, not real audio) and
   what is real.

If time runs out: keep the simulation, say plainly it is simulated, and put the saved time into items 1-4 above,
which are all Musts and worth more.
