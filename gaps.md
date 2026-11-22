# Gap Analysis vs. Take-Home Brief (current state, 2026-11-22)

Replaces the earlier audit (most of its findings are fixed: ADK installed and used, suite green, tracer rewritten,
grounding/booking/eval issues addressed). Basis: the brief (`Saathi_Care_Take_Home_Assignment.md`) against the repo
files, README, EVALS.md and the frozen eval snapshot. I did not re-run tests or evals for this update (Python is not on
the shell PATH here), so "done" below means "present in the repo/docs", not "re-verified today".

## Status by brief section

| # | Section | Priority | Status | What is left |
|---|---|---|---|---|
| 1 | ADK 2.0 Workflow | Must | Mostly done | `PLAN.md` rewritten with a mermaid graph of the real ADK workflow (incl. handoff `RequestInput`) and a code-vs-LLM table. **Still open:** the brief's "LLM second" stage in the safety gate is not built (stated in PLAN.md). |
| 2 | Grounding Mode A/B | Must | Done, thin | Recommendation paragraph added to `EVALS.md` (numbers computed from the run). **Still open:** hallucination rate per mode (the faithfulness judge scores Mode A only). |
| 3 | Voice | Should | Simulated audio, real metrics | 15 scripted calls with ASR errors: read-back 100% (20/20), wrong-booking 0/15, TTFA vs 1.5 s budget reported in `EVALS.md`. **Still open:** real STT/TTS (browser Web Speech demo), wellness-by-voice turns miss the budget. |
| 4 | Model-agnostic | Must | Done, thin | Same eval run on 4 mixes (gemini-3.5-flash-lite, gemini-3.8-flash, gpt-4o-mini, gpt-4o) with faithfulness, injection suite, p50/p95 and cost per 1k conversations; routing policy + separate `voice` route in `EVALS.md` / `models.yaml`. **Still open:** n=12 + 18 per mix, one run (quality differences not resolvable); no open-weights (Ollama) mix; voice wellness turns still over the 1.5 s budget. |
| 5 | Prompts | Must | Done | Before/after table for v1-v4 + injection suite (`evaluations/prompt_iterations.py`, in `EVALS.md`); named tests in `tests/test_prompt_injection.py`. |
| 6 | Evals | Must | Mostly done | 55 cases + 15 scripted voice calls, one command; voice metrics now in `EVALS.md`. **Still open:** judge kappa (needs 15 hand labels from you, N/A), Hindi/Hinglish share not reported, small samples (acknowledged). |
| 7 | Observability | Must | Mostly done | Incident drill done: `docs/INCIDENT_DRILL.md` (lab API down + bad prompt, eval diff, span trees, 3 screenshots). **Still open:** Langfuse UI screenshots (need a logged-in browser) and a stale-record drill. |
| 8 | Semantic cache | Should | Done, weak | Threshold 0.88 stated; false-hit measured on only 8 pairs. State this honestly (already in README); member-data answers never cached. |
| 9 | Architect memo | Must | Done | Section 3 replaced with a measured-cost projection (model mix, 15M/month scenarios, latency budgets); DPDP log/mask/consent/retention and top-3 risks with monitoring made explicit. STT/TTS cost still an unpriced input. |
| - | Stretch: UI | Stretch | Done | React UI + 18 screenshots + Playwright. |
| - | Stretch: report explainer | Stretch | Not done | Optional, skip. |

## Deliverables checklist

- [x] README, EVALS.md, ARCHITECTURE.md, AI_USAGE.md, `.claude/skills/`, CLAUDE.md
- [ ] **PLAN.md as the first commit**: not satisfiable now (history already exists). Say so in AI_USAGE/README, don't fake it.
- [ ] **5-8 min video**: chat demo, voice demo, trace walkthrough, Mode A vs B, routing decision. Not recorded.
- [ ] **Actual LLM spend in README** (<= INR 500): README has no spend figure. Build-tool spend is now in `AI_USAGE.md` section 6; add measured runtime Gemini/OpenAI spend.
- [ ] Public GitHub repo / deployed link: confirm it is pushed and public.
- [ ] Rotate the Gemini key that was once exposed (still needed).
- [ ] Repo clutter: `scripts/archive_patches/` (13 patch scripts), `model_client_old.py`, `GEMINI.md`, `.docx` blueprint. Consider deleting or explaining.
- [x] `AI_USAGE.md` section 3b records a concrete overruling (AI-generated calibration labels reverted).
- [ ] `gaps.md` was self-labelled historical; this file replaces it, and README's last "Known gaps" bullet should point here or be dropped.

## Known honesty items (keep them stated, graders score "honesty about gaps")

- Judge kappa N/A; faithfulness judge same-vendor and unvalidated.
- Wrong-booking n=4, chaos n=5, red-flag n=8: statistically weak.
- Retrieval is lexical; off-topic queries can retrieve unrelated docs.
- Approval/coordinator is a shared secret, not real auth.

## Priority order for the remaining time

Done in the repo: model mixes, incident drill, prompt iterations, PLAN.md graph, voice metrics, architect memo,
Mode A/B recommendation, AI_USAGE overruling example (section 3b).

Only you can do these:
1. **Hand-label the 15 calibration responses** in `evaluations/datasets/human_labels.json`, then run
   `python -m evaluations.run_evals`. An earlier AI-generated labelling was reverted: it is not human calibration.
2. **Rotate the exposed Gemini key**, and add the measured runtime spend (<= INR 500) to the README.
3. **Record the 5-8 min video**, with Langfuse UI screenshots (drill trace, one LLM generation span).
4. **Commit and push** to a public repo (nothing is committed yet). Optionally delete `scripts/archive_patches`,
   `model_client_old.py`, `GEMINI.md`.

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
