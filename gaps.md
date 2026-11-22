> **HISTORICAL DOCUMENT - SUPERSEDED. DO NOT READ AS THE CURRENT STATE.**
> This is an early audit written before most fixes. Several statements below are no longer true, e.g.:
> ADK is now installed and used (`app/workflow/adk_graph.py`, google-adk 2.11); the failing routing test and the
> syntax error are fixed (the suite is green); the tracer was rewritten; the exposed key was removed from tracked
> files (it must still be rotated); and the grounding, eval and booking issues listed were addressed.
> For the current status and remaining limitations see `README.md` (Known gaps) and the Limitations section of
> `EVALS.md`. Kept only as a record of what the audit found.

---

Short answer: no. The repo covers the happy-path skeleton of the brief and has major gaps. Several README, EVALS and ARCHITECTURE claims are not backed by the code. I read every source file and ran the tests. I did not run the evals.

Blocking problems

- Exposed API key. .env holds a real Gemini key, and the pytest log printed it in a URL. Rotate it now and make sure .env is never committed.
- A test fails. pytest gives 1 failed, 4 passed. test_intent_routing_synonyms_and_hinglish expects node_lab_booking and gets node_program_coach. This contradicts EVALS.md's "100% intent accuracy".
- Nothing is on ADK. google-adk isn't installed or in requirements.txt. graph.py is a hand-written class of nested function calls, not an ADK 2.0 Workflow. The brief's first Must is therefore missed.

Brief section by section

Section: 1. Workflow on ADK 2.0 (Must)                                                                  atus: Partial
Gap: No ADK. The safety gate (regex only, no LLM second pass), router, coach, booking node and emergencynode exist. There is no human-handoff s a ticket, but nothing routes to a
  handoff node. The router is regex, not an LLM. PLAN.md has no drawn graph and says "DAG" while the grais recursive. The "Lab Booking agent" h no LLM. Session state is used across
  turns, but past bookings are never updated.                                                           ──────────────────────────────────────
Section: 2. Grounding A/B (Must)                                                                        atus: Weak / mostly fake
Gap: Mode A is a substring/tag keyword search, not agentic RAG. query_lower in content almost never matca full question. Mode B returns "[INFOated…" and never builds or sends a
  prompt. There are no backend tools (schedule, catalogue). The Mode A vs B "comparison" table in EVALS.(2150 ms vs 850 ms, token counts) is ns no recommendation of when to use
  each. Mode switching isn't read from config.                                                          ──────────────────────────────────────
Section: 3. Voice (Should)                                                                              atus: Skeleton
Gap: voice_agent.py is sleep(0.5) plus a Hinglish dictionary, with no real STT/TTS or ADK live. There isbarge-in handling and no read-back logere is no latency budget or
  measurement. Slot matching is a text-match against the slot list, so it doesn't catch "fifteen" vs    "fifty". There are 15 voice cases in tfirmed they are scored for read-back
  correctness or turn latency. voice_demo.py has a stray "\\n".                                         ──────────────────────────────────────
Section: 4. Model-agnostic (Must)                                                                       atus: Not done
Gap: config/models.yaml is never read. graph.py hardcodes gemini-1.5-flash and gpt-4o-mini via requests.There is no non-Google model run and n50/p95 or cost per 1,000 conversations,
  and no routing policy (including a separate one for voice).                                           ──────────────────────────────────────
Section: 5. Prompts (Must)                                                                              atus: Partial
Gap: Versioned files exist (v1 and v2), but there is no structure showing role, rules, facts, tools, outformat and examples. There are no beforation. An injection test may exist in
  the 8 jailbreak cases, but no LLM is in the loop to defend.                                           ──────────────────────────────────────
Section: 6. Evals (Must)                                                                                atus: Partial, partly fabricated
Gap: The dataset has 55 cases (12 wellness, 12 lab, 8 red-flag, 8 jailbreak, 15 voice). Hindi and Hinglicoverage is unverified. The LLM judge C_GROUND_TRUTH. The "Kappa 0.9" is
  therefore meaningless, and the brief requires 15 hand-labelled cases. The code has no tool-call-argumecorrectness metric, groundedness metritent accuracy of 100% conflicts with
  the failing test. I'd also check whether the router was tuned against the eval cases. Safety recall isjust regex run on cases the regex was
────────────────────────────────────────                                                                ction: 7. Observability (Must)
Status: Broken / unused                                                                                 p: tracer.py imports langfuse.model.Crt in the installed langfuse 4.x, so it
  always falls back to in-memory. trace_node uses random but only imports it under __main__, so it wouldraise NameError. Tokens and cost are re isn't applied to any node, tool or
  LLM call. There is no trace_id propagation and no incident drill or screenshots. This also violates   CLAUDE.md's Langfuse mandate.
────────────────────────────────────────                                                                ction: 8. Semantic cache (Should)
Status: Fake                                                                                            p: The "similarity" is token-overlap Jre_cache_performance() prints hardcoded
  "32% hit / 0.0% false-hit". Nothing measures them. A keyword bypass ('am', 'pm', 'test') is a substrinmatch, so it blocks "exam", "name" andsses the safety gate order.
────────────────────────────────────────                                                                ction: 9. Architect memo (Must)
Status: Present, unverified                                                                             p: It exists, but the cost figures ($4ved from any measurement. I haven't
  checked it for DPDP consent and retention detail, call-audio masking, or the top 3 risks.             
Deliverables and process                                                                                
- Git: Is a git repository: false. The brief wants a public repo with PLAN.md as the first commit.      README: it is only a "LLM spend" stub o docker compose or uv/pip sequence, andno one-command eval.                                                                                  Spend: the ₹180 figure doesn't match a
- Data: 17 docs and 12 packages meet the target. There are only 5 members, and the data has no program  schedules or past bookings.
- Repo clutter: about 10 one-off patch scripts sit in the root (apply_fixes.py, final_fix*.py, fix_*.py,build_final.py, finalize_evals.py, imp. They are signs of last-minute patching.
- Skills and AI_USAGE.md:                                                                               - .claude/skills/ has 3 short skills.
  - AI_USAGE.md describes a Gemini/Claude workflow, but it lacks the token-discipline answer and a concr  "one place I overruled it".
  - GEMINI.md is also committed.                                                                        CLAUDE.md rules: state uses plain dicte no frozen=True models, and tool returns are untyped dicts. The Pydantic and no-Dict mandates are violated.                                    
Smaller correctness bugs                                                                                
- Dead code: triage_gate.py has an unreachable duplicated block after the first return.                 Roleplay bypass: the gate returns GREEoleplay" or "pretend you are", before the red-flag check. "Pretend … I have chest pain" skips escalation, which breaks the 100% recall target.  Booking confirmation: 'ok' counts as a also matches inside words like "book".The "explicit yes" rule is fragile, and wrong-booking could occur.                                    Date handling: date is hardcoded to 20res it.
- Booking state: a booking is never saved back to past_bookings. book_test retries inside the tool with time.sleep, so latency is hidden.
- Safety gate coverage: it only warns on a narrow diagnosis regex, and a misspelled or paraphrased request
  passes.

Recommended order of work

1. Rotate the key. Initialise git and cl
2. Install ADK 2.0 and rebuild graph.py as a Workflow with a handoff node. Wire models.yaml to the LLM calls,
   and fix the roleplay bypass.
3. Make Mode B real with backend tools and a real prompt. Make Mode A real retrieval, then measure both.
4. Replace the mock judge with real handailing intent test. Addtool-call-correctness and groundedness metrics.
5. Fix tracing with real token and cost ll, and add screenshots.
6. Write the README with run steps and the real eval tables. Strip any numbers that haven't been measured.

I can start on any of these. I'd begin with the key, the failing test and the safety bypass, because they are small and high-risk.