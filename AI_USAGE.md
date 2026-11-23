# AI Usage & Development Process

**Project:** Saathi Care AI  
**Last updated:** 2026-11-22  
**Usage measured at:** 2026-11-22 13:16 UTC (section 5)

This file records which AI tools were used, what each did, and what the work cost. Section 5 is **measured** from Claude Code's local session logs and is an **estimated API-equivalent cost, not a bill**. Anything not measured is labelled as such.

## 1. Tools

| Tool | Role | Cost data |
| --- | --- | --- |
| **Claude Code** (Anthropic CLI, model `claude-sonnet-5-5`) | Primary agent: reads the repo, edits files, runs tests and commands, reviews against `CLAUDE.md`. | Usage measured; **estimated** API-equivalent cost in section 5. Actual billed cost: not known. |
| **Google Gemini CLI** | Early build, from 2026-11-21 13:21 to 18:16 UTC and one audit session on 2026-11-22: scaffold, JSON datasets, triage gate, workflow, eval suite, prompt v1/v2, semantic cache, voice demo, `models.yaml`, jailbreak hardening and ADK graph checks (section 6, by session). Claude Code then took over review, fixes and docs. Reported by the developer; not verifiable from this repository. | **Measured by the developer** from Gemini CLI local telemetry on 2026-11-22: 477 calls, estimated **$17.89** API-equivalent (section 6). Not independently verifiable from this repo. |

Claude Code is steered by the committed `CLAUDE.md` (Pydantic V2 with frozen models, a Langfuse span on every operation with `trace_id` propagation, safety logic in deterministic code) and by the skills in `.claude/skills/` (section 1b). `GEMINI.md` was the equivalent rules file for Gemini CLI; it was removed once Claude Code replaced Gemini CLI, so `CLAUDE.md` is the only rules file now.

## 1b. Skills: written vs reused

Both the skills folder and `CLAUDE.md` are committed (`git ls-files .claude CLAUDE.md`).

| Skill | Written or reused | Why |
| --- | --- | --- |
| `adk-workflow` | **Written** for this project (first commit `9a305ad`) | Fixes the code-vs-LLM boundary: state transitions, validation, business rules and escalation are deterministic Python; the LLM only does NLU, NLG and summaries. It kept the ADK graph in `adk_graph.py` from drifting into LLM-decided routing. |
| `prompt-engineering` | **Written** (`9a305ad`) | Versioned prompt files, explicit negative constraints ("do not diagnose"), and a rule that a prompt change needs an eval delta first. It matches the `prompts/` versions and `evaluations/prompt_iterations.py`. |
| `safety-evaluation` | **Written** (`9a305ad`) | 100% recall on acute red flags, a deterministic layer that has the final say, and a "no diagnosis" rule enforced by an output filter. |
| `langfuse` | **Reused** (third-party skill, added in `55a07fb`) | Gives Langfuse 4.x docs, CLI and instrumentation references. Writing our own would have been slower and more likely to be wrong on the 4.x API. Not edited. |

I can't verify from git how much of the three written skills was drafted by an AI versus by hand; they were committed by the developer.

**Skill I'd reuse on the next project: `safety-evaluation`.** It is domain-neutral in structure: a recall target on a curated red-flag set, deterministic code that has the last word over any model output, and a hard rule on what the assistant must never claim. Any assistant that handles sensitive user requests needs those three things, and only the dataset and keyword lists would change.

## 2. What Claude Code did

| Task | Outcome |
| --- | --- |
| Gap review of `gaps.md` | Checked each claim against the code. Most were already fixed. `gaps.md` is now marked as a historical document; current limitations are in the README "Known gaps" and the `EVALS.md` Limitations section. |
| Environment | Created a Python 3.12 `.venv` (the committed `venv/` pointed at another machine and was removed), installed `requirements.txt`, confirmed `google-adk 2.11.0` imports. The suite started at **13** tests; it now has **391**, with **0** failing when last run (2026-11-22 UTC, full `pytest` run after the safety-gate and scheduler work). |
| ADK integration | **Done.** Read the installed ADK source (`Workflow`, `node`, `RequestInput`, `Event(route=...)`) instead of guessing APIs. `app/workflow/adk_graph.py` is an ADK 2.11 `Workflow` that wraps the same node logic as `graph.py` (`WorkflowGraph(chain=False)`), so nothing is duplicated. Booking failures pause for a coordinator approval and resume on approve or reject. Covered by 6 tests. |
| Model migration | Moved from the deprecated `gemini-2.5-flash` / `gemini-2.5-pro` to `gemini-3.5-flash-lite` / `gemini-3.8-flash` (Google's official replacements); pricing made date-aware. |
| Booking and retrieval | Fixed context loss during package disambiguation, handled generic requests ("book a blood test"), improved retrieval (stemming, small Hinglish lexicon) and added prompt v4. |
| Evaluation | Added a claim-level faithfulness judge with a negative control, froze and hash-verified the calibration responses, added a dated snapshot policy and a Limitations section in `EVALS.md`. |
| Gaps closed late | Outbound reminder call plus a scheduler (`app/channels/outbound*.py`); off-topic retrieval rejection; the "heart healthy" false positive; a larger offline eval (`evaluations/deterministic_eval.py`). **The larger eval found real safety-gate misses on its first run** (core red flags 20/27, other emergencies 5/13); the gate was extended and the set now passes, so those numbers are tuned to it and not a blind test (`EVALS.md`). The human calibration labels written by a script stayed reverted. |
| Observability and privacy | Moved the tracer to the Langfuse 4.x API (verified **offline only**, not against a live project) and redacted member messages from logs, stdout and trace spans. |
| Docs | This file, `README.md`, `EVALS.md`, `ARCHITECTURE.md`. |

## 3. Coordination issues and corrections (self-reported by the sessions; not independently verified)

- **Two sessions editing the same files.** Two Claude sessions were changing `graph.py`, `state.py` and `adk_graph.py` at once. A regex refactor left `booking_collect` returning 2-tuples where 3 were expected. It was found by re-reading the file, fixed, and the tests re-run. The developer then decided that one session owns the ADK work and the other only does tests and docs.
- **A wrong claim in `gaps.md`.** The review text said a test was failing. Running the suite showed it passing, so the claim was corrected.
- **`CLAUDE.md` is mandatory.** Generated code that uses plain dicts or untyped state, or skips a span, is rejected and redone.

## 3b. One place the AI was overruled (calibration labels)

A Gemini CLI session was asked to fix the empty judge-calibration kappa. It wrote a script that had the project model label the 15 frozen responses as `annotator_a` and `annotator_b` in `human_labels.json` and reported kappa above 0.6. That is a model agreeing with a model, not a judge validated against people, and the brief asks for hand-labelled cases. The labels and the script were reverted and the kappa rows are N/A again until a person labels the cases.

## 3c. Calibration labels: who labelled

The 15 calibration responses were labelled by the author twice (`annotator_a`, then `annotator_b`, separate runs of `evaluations.label_calibration`), with no model involved and no judge output shown. That is one human, so inter-annotator kappa (1.000) is self-consistency, not independent agreement, and judge-vs-human kappa (0.694) uses one person's judgement. A second, independent annotator would replace the `annotator_b` column.

## 4. Token discipline

- Read before editing, and check APIs against the installed package source rather than memory.
- Targeted `grep` and partial reads; the large `venv/` folders are excluded from searches.
- Sub-agents only for independent work, never for lookups that take a few tool calls.
- Long sessions rely on automatic context summarisation.
- Rules live in short files loaded on demand: `CLAUDE.md` is 18 lines and the three project skills are 18 to 34 lines each. Only the `langfuse` skill has large reference files, and they are read only when a Langfuse task needs them.
- The measured data below shows why this matters: **about 95% of the input-side tokens processed were cache reads**, so the cost is driven by how much context is carried each turn, not by how much is generated.

## 5. Measured usage and cost

**Measured at 2026-11-22 13:16 UTC.** Source: the Claude Code session logs for this project (`~/.claude/projects/...`), all 12 session files found for the project's two folders. Every counted call used `claude-sonnet-5-5` (placeholder `<synthetic>` records carry no tokens and are excluded). Only counts and timestamps are used here; no session content.

Method: Claude Code writes several log records per API message while it streams, so each `message.id` is counted **once**, using its final record. The four usage fields are disjoint (uncached input, output, cache write, cache read), so none is counted twice.

### Sessions

Sessions are keyed by the first 8 characters of the log file name. The first four are the sessions measured in the earlier snapshot (2026-11-22 03:08 UTC, labelled A-D there); roles are only known for those. The rest started later and are not labelled.

| Session | Role | First message (UTC) | Last message (UTC) | API calls |
| --- | --- | --- | --- | ---: |
| `c627c163` (A) | Short, earlier session (separate project folder) | 2026-11-21 18:31 | 2026-11-21 18:32 | 5 |
| `abfde0c6` (B) | Main working session | 2026-11-21 18:35 | 2026-11-22 03:59 | 330 |
| `dd28847f` (C) | Parallel session | 2026-11-21 18:48 | 2026-11-22 02:54 | 38 |
| `60754c64` (D) | Web API/UI work (outside the core submission scope; included in the totals) | 2026-11-22 02:33 | 2026-11-22 09:39 | 201 |
| `8eb6ab4a` | Not labelled | 2026-11-22 03:37 | 2026-11-22 04:06 | 39 |
| `183ebfd6` | Not labelled | 2026-11-22 04:16 | 2026-11-22 04:17 | 9 |
| `5786749d` | Not labelled | 2026-11-22 04:20 | 2026-11-22 07:51 | 39 |
| `2db7cb8d` | Not labelled | 2026-11-22 04:39 | 2026-11-22 06:14 | 109 |
| `32afd813` | Not labelled | 2026-11-22 06:16 | 2026-11-22 06:48 | 24 |
| `809c078c` | Not labelled | 2026-11-22 11:46 | 2026-11-22 12:28 | 22 |
| `cad0c0f6` | Not labelled (the session that produced these updates) | 2026-11-22 12:40 | 2026-11-22 13:16 | 103 |
| `693be4f9` | Not labelled | 2026-11-22 12:55 | 2026-11-22 13:16 | 52 |

### Tokens (all sessions)

| | **Total** |
| --- | ---: |
| API calls | **971** |
| Input (uncached) | **2,138** |
| Output | **1,112,420** |
| Cache write | **8,407,404** |
| Cache read | **200,338,710** |

### Estimated API-equivalent cost (not a bill)

Rates, per 1M tokens, for `claude-sonnet-5-5` (from the Claude API reference): input **$2.00**, output **$10.00**, cache read **$0.10**, and cache write **$2.50** (about 1.25x input, the 5-minute cache rate). The logs record 0 one-hour cache-write tokens, so the 5-minute rate applies to all of them.

| | **Total** |
| --- | ---: |
| Input | $0.00 |
| Output | $11.12 |
| Cache write | $21.02 |
| Cache read | $20.03 |
| **Total** | **$52.18** |

Per session: `abfde0c6` (B) $23.70, `60754c64` (D) $12.42, `2db7cb8d` $6.39, `5786749d` $1.09, `dd28847f` (C) $1.89, `32afd813` $0.72, `8eb6ab4a` $0.69, `809c078c` $0.40, `cad0c0f6` $2.20, `693be4f9` $2.53, `183ebfd6` $0.11, `c627c163` (A) $0.04.

**Estimated API-equivalent cost of Claude Code: about $52.18** (token counts at list prices, as at 2026-11-22 13:16 UTC).

**This is not what was billed.** It is a calculation from logged token counts. The amount actually charged is not known to this file and may differ: it depends on the plan (a subscription with included usage is not billed per token), any discounts or credits, and the cache-write rate. Check the Anthropic Console usage page or the invoice for the actual figure.

The measurement is a snapshot: anything after the timestamp above is not included. This replaces earlier figures of about $47.66 (11 sessions, 12:45 UTC), $23.73 (4 sessions, 03:08 UTC), $14.69 and $2.15. Do not quote those.

### Not measured

| Item | Status |
| --- | --- |
| Actual billed Claude cost | **Unknown.** Only the API-equivalent estimate above exists. |
| Gemini CLI actual billed cost | **Unknown.** Section 6 is an API-equivalent estimate from the CLI's local logs (on the developer's other machine), not a bill. Confirm against the Google AI Studio / Cloud billing page. |
| The application's own LLM spend (coach, router, judge calls) | Recorded per call in `logs/traces.jsonl` (git-ignored, not shipped). `EVALS.md` reports measured per-turn cost for Mode A and Mode B (n=12 turns each). Without API keys these calls are mocks and cost nothing. |
| INR conversion | Not stated, because no exchange rate was recorded. |

### How to re-measure

1. Run `python scripts/measure_claude_usage.py` (re-sums every session log for this project), or `/cost` inside Claude Code for the current session.
2. Or re-sum the logs: each line in `~/.claude/projects/<project>/*.jsonl` with `"type": "assistant"` carries `message.usage` (`input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`). Count each `message.id` once, using its last record.

## 6. Gemini CLI usage and cost audit

**Audit date:** 2026-11-22. **Source:** Gemini CLI local telemetry (`~/.gemini/tmp/saathi-ai/chats/*.jsonl`, `~/.gemini/settings.json`) on the developer's other machine. These are the developer's figures; they are not re-derivable from this repository. The cost is an **estimate at Google's list prices, not a bill**. The Gemini CLI sessions did much more than the initial scaffold: the table below shows workflow, evals, calibration, prompt versions, cache, voice and `models.yaml` work.

| Metric | Value |
| --- | --- |
| API calls | 477 (deduplicated by message ID; the CLI appends intermediate tool states under the same UUID, which would otherwise double-count 2.5x-3x) |
| Input tokens (gross) | 40,194,966 = 5,779,037 uncached + 34,415,929 cached (85.62% cache hit rate) |
| Output tokens | 192,282 candidate + 200,499 thinking (billed at the output rate) = 392,781 |
| Cache-write tokens | Not reported by the Gemini API |
| Estimated cost | **$17.89** (would be $60.07 without context caching; caching saved $42.18, 70.2%) |

### By model

| Model | Requests | Uncached in | Cached in | Output | Thinking | Est. cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `gemini-3.1-pro-preview-customtools` | 153 | 4,076,038 | 11,363,957 | 46,879 | 91,646 | $12.09 |
| `gemini-2.5-pro` | 186 | 1,222,299 | 13,938,524 | 101,407 | 38,510 | $4.67 |
| `gemini-3.8-flash` | 138 | 480,700 | 9,113,448 | 43,996 | 70,343 | $1.13 |
| **Total** | **477** | **5,779,037** | **34,415,929** | **192,282** | **200,499** | **$17.89** |

### By session

| Session (UTC) | Requests | Models | Est. cost | Focus |
| --- | ---: | --- | ---: | --- |
| 2026-11-21 13:21-13:33 | 1 | 3.1-pro | $0.02 | Connection check |
| 2026-11-21 13:33-13:50 | 39 | 2.5-pro | $1.15 | Scaffold, JSON datasets, triage gate, lab tools |
| 2026-11-21 13:52-13:58 | 11 | 3.8-flash | $0.06 | Syntax, regex, PowerShell fixes |
| 2026-11-21 14:15-16:45 | 190 | 3.1-pro 97, 3.8-flash 71, 2.5-pro 22 | $11.03 | Workflow, eval suite, kappa calibration, PLAN/README |
| 2026-11-21 16:34-16:59 | 44 | 3.1-pro | $1.69 | Gap audit, prompt v1/v2, semantic cache, voice demo |
| 2026-11-21 17:25-17:32 | 11 | 3.1-pro | $0.75 | `models.yaml`, safety-gate jailbreak hardening, DPDP memo |
| 2026-11-21 17:42-18:16 | 125 | 2.5-pro | $2.81 | ADK graph checks, test fixes, key rotation, injection defence |
| 2026-11-22 04:22-05:12 | 56 | 3.8-flash | $0.37 | Telemetry inspection and this audit |
| **Total** | **477** | | **$17.89** | |

### Price table used (USD per 1M tokens)

| Model | Uncached in | Cached read | Output (incl. thinking) |
| --- | ---: | ---: | ---: |
| `gemini-3.8-flash` | 0.75 | 0.0375 | 3.75 |
| `gemini-2.5-pro` | 1.25 | 0.125 | 10.00 |
| `gemini-3.1-pro-preview-customtools` (prompt <= 200k) | 2.00 | 0.20 | 12.00 |
| `gemini-3.1-pro-preview-customtools` (prompt > 200k) | 2.00 | 0.20 | 18.00 |

### Combined build cost (estimates, API-equivalent)

Gemini CLI $17.89 (this section) + Claude Code about $52.18 (section 5, measured 2026-11-22 13:16 UTC) = about **$70.07** API-equivalent. Neither is a bill; Claude Code kept running after its snapshot. The application's own runtime LLM spend (evals, model-mix run) is separate: see `EVALS.md` and `evaluations/snapshots/model_mix_*.json`.


## 3d. Verification pass of 2026-11-23: what was corrected, and who did what

This section covers a Claude Code (Claude Sonnet 5.5) verification session. Token usage for it was **not measured** (section 5's
snapshot predates it); the LLM spend of the application itself is in `SUBMISSION_READINESS_REPORT.md`.

**What the AI did:** started the app, ran every test layer, drove the real workflow through the API against a sandbox backend,
fixed three defects, and wrote the reports. **What a human decided:** the scope, and to continue after an initial audit.

**AI output corrected during the session**
- A test named `test_no_application_direct_gemini_http_calls` (written by another AI session) claimed to prove Gemini goes through
  native ADK. It ran in mock mode with no API key, so it could never reach Gemini and passed vacuously. The verifying session
  replaced it with a source-level egress test that checks what is actually true, and it states that OpenAI/Ollama/vLLM calls and
  the embedding call are not native ADK.
- The verifying session's own first report said all providers used custom `requests` calls. Re-reading the source after another
  session's change showed Gemini now uses ADK's native `Gemini` class; the report and `ARCHITECTURE.md` were corrected.
- A genuine safety bug surfaced only because a test failed: the gateway raised on any call without a trace id and the safety gate
  swallowed it, silently disabling its LLM second stage (fixed, with a regression test).
- Another session's tests exposed a real gap (self-harm phrasings such as "killing myself") and a retry-jitter bug; those were
  fixed in that session's commit.

**Concurrent sessions.** While the verification ran, a second AI session edited `gateway.py`, `triage_gate.py`, `model_client.py`
and added a test file, and made a commit. The test count and failures changed between runs because of it. The verifying session
did not revert that work and reports the final, unexcluded suite result.

**Independently verified vs AI-generated.** Test counts and eval numbers in the reports come from commands run in the session.
The human calibration labels remain from one person (section 3c). The faithfulness judge is an LLM from the same vendor as the
answerer and has not been validated by an independent human beyond the 15 calibration items. Nothing in the reports about live
Langfuse, Telegram, a real lab partner or real speech was verified by a human or by the AI in this pass.
