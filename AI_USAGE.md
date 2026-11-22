# AI Usage & Development Process

**Project:** Saathi Care AI  
**Last updated:** 2026-11-22  
**Usage measured at:** 2026-11-22 03:08 UTC (section 5)

This file records which AI tools were used, what each did, and what the work cost. Section 5 is **measured** from Claude Code's local session logs and is an **estimated API-equivalent cost, not a bill**. Anything not measured is labelled as such.

## 1. Tools

| Tool | Role | Cost data |
| --- | --- | --- |
| **Claude Code** (Anthropic CLI, model `claude-sonnet-5-5`) | Primary agent: reads the repo, edits files, runs tests and commands, reviews against `CLAUDE.md`. | Usage measured; **estimated** API-equivalent cost in section 5. Actual billed cost: not known. |
| **Google Gemini CLI** | Initial scaffold only (directories, first module drafts, datasets, docs), as reported by the developer; not verifiable from this repository. Replaced by Claude Code for review and fixes. | **Unverified.** No usage data is available to this file, so no figure is claimed. |

Claude Code is steered by the committed `CLAUDE.md` (Pydantic V2 with frozen models, a Langfuse span on every operation with `trace_id` propagation, safety logic in deterministic code) and by the skills in `.claude/skills/` (`adk-workflow`, `prompt-engineering`, `safety-evaluation`). `GEMINI.md` holds the equivalent rules for Gemini CLI.

## 2. What Claude Code did

| Task | Outcome |
| --- | --- |
| Gap review of `gaps.md` | Checked each claim against the code. Most were already fixed. `gaps.md` is now marked as a historical document; current limitations are in the README "Known gaps" and the `EVALS.md` Limitations section. |
| Environment | Created a Python 3.12 `.venv` (the committed `venv/` pointed at another machine and was removed), installed `requirements.txt`, confirmed `google-adk 2.11.0` imports. The suite started at **13** tests; it now has **109**, with **0** failing when last run (2026-11-22 03:08 UTC). |
| ADK integration | **Done.** Read the installed ADK source (`Workflow`, `node`, `RequestInput`, `Event(route=...)`) instead of guessing APIs. `app/workflow/adk_graph.py` is an ADK 2.11 `Workflow` that wraps the same node logic as `graph.py` (`WorkflowGraph(chain=False)`), so nothing is duplicated. Booking failures pause for a coordinator approval and resume on approve or reject. Covered by 6 tests. |
| Model migration | Moved from the deprecated `gemini-2.5-flash` / `gemini-2.5-pro` to `gemini-3.5-flash-lite` / `gemini-3.8-flash` (Google's official replacements); pricing made date-aware. |
| Booking and retrieval | Fixed context loss during package disambiguation, handled generic requests ("book a blood test"), improved retrieval (stemming, small Hinglish lexicon) and added prompt v4. |
| Evaluation | Added a claim-level faithfulness judge with a negative control, froze and hash-verified the calibration responses, added a dated snapshot policy and a Limitations section in `EVALS.md`. |
| Observability and privacy | Moved the tracer to the Langfuse 4.x API (verified **offline only**, not against a live project) and redacted member messages from logs, stdout and trace spans. |
| Docs | This file, `README.md`, `EVALS.md`, `ARCHITECTURE.md`. |

## 3. Coordination issues and corrections (self-reported by the sessions; not independently verified)

- **Two sessions editing the same files.** Two Claude sessions were changing `graph.py`, `state.py` and `adk_graph.py` at once. A regex refactor left `booking_collect` returning 2-tuples where 3 were expected. It was found by re-reading the file, fixed, and the tests re-run. The developer then decided that one session owns the ADK work and the other only does tests and docs.
- **A wrong claim in `gaps.md`.** The review text said a test was failing. Running the suite showed it passing, so the claim was corrected.
- **`CLAUDE.md` is mandatory.** Generated code that uses plain dicts or untyped state, or skips a span, is rejected and redone.

## 4. Token discipline

- Read before editing, and check APIs against the installed package source rather than memory.
- Targeted `grep` and partial reads; the large `venv/` folders are excluded from searches.
- Sub-agents only for independent work, never for lookups that take a few tool calls.
- Long sessions rely on automatic context summarisation.
- The measured data below shows why this matters: **about 95% of the input-side tokens processed were cache reads**, so the cost is driven by how much context is carried each turn, not by how much is generated.

## 5. Measured usage and cost

**Measured at 2026-11-22 03:08 UTC.** Source: the Claude Code session logs for this project (`~/.claude/projects/...`), all four session files found for the project's folders. Every call used `claude-sonnet-5-5`. Only counts and timestamps are used here; no session content.

Method: Claude Code writes several log records per API message while it streams (1,044 records for 370 calls here), so each `message.id` is counted **once**, using its final record. The four usage fields are disjoint (uncached input, output, cache write, cache read), so none is counted twice.

### Sessions

| Session | Role | First message | Last message | API calls |
| --- | --- | --- | --- | ---: |
| A | Short, earlier session (separate project folder) | 2026-11-21 18:31 UTC | 2026-11-21 18:32 UTC | 5 |
| B | Main working session (still running at measurement time) | 2026-11-21 18:35 UTC | 2026-11-22 03:08 UTC | 271 |
| C | Parallel session | 2026-11-21 18:48 UTC | 2026-11-22 02:56 UTC | 39 |
| D | Separate session: web API/UI work (outside the core submission scope; its tokens are included in the totals) | 2026-11-22 02:33 UTC | 2026-11-22 03:07 UTC | 55 |

### Tokens

| | A | B | C | D | **Total** |
| --- | ---: | ---: | ---: | ---: | ---: |
| API calls | 5 | 271 | 39 | 55 | **370** |
| Input (uncached) | 12 | 568 | 86 | 126 | **792** |
| Output | 1,053 | 341,661 | 28,324 | 93,830 | **464,868** |
| Cache write | 6,608 | 3,483,012 | 500,801 | 300,311 | **4,290,732** |
| Cache read | 130,222 | 74,798,620 | 3,549,828 | 5,095,597 | **83,574,267** |

### Estimated API-equivalent cost (not a bill)

Rates, per 1M tokens, for `claude-sonnet-5-5` (from the Claude API reference): input **$2.00**, output **$10.00**, cache read **$0.10**, and cache write **$2.50** (about 1.25x input, the 5-minute cache rate). The logs record 0 one-hour cache-write tokens, so the 5-minute rate applies to all of them.

| | A | B | C | D | **Total** |
| --- | ---: | ---: | ---: | ---: | ---: |
| Input | $0.00 | $0.00 | $0.00 | $0.00 | $0.00 |
| Output | $0.01 | $3.42 | $0.28 | $0.94 | $4.65 |
| Cache write | $0.02 | $8.71 | $1.25 | $0.75 | $10.73 |
| Cache read | $0.01 | $7.48 | $0.35 | $0.51 | $8.36 |
| **Total** | $0.04 | $19.61 | $1.89 | $2.20 | **$23.73** |

**Estimated API-equivalent cost of Claude Code: about $23.73** (token counts at list prices, as at 2026-11-22 03:08 UTC).

**This is not what was billed.** It is a calculation from logged token counts. The amount actually charged is not known to this file and may differ: it depends on the plan (a subscription with included usage is not billed per token), any discounts or credits, and the cache-write rate. Check the Anthropic Console usage page or the invoice for the actual figure.

The measurement is a snapshot. The main session (B) was still running, so anything after the timestamp above, including the turns that edited this file, is not included. This replaces two earlier figures: about $2.15 (assumed turn counts and rates, never measured) and $14.69 (two sessions, measured at 2026-11-22 02:25 UTC). Do not quote either.

### Not measured

| Item | Status |
| --- | --- |
| Actual billed Claude cost | **Unknown.** Only the API-equivalent estimate above exists. |
| Gemini CLI usage and cost | **Unverified.** No local log or usage data. Read it from the Google AI Studio / Cloud usage page and add it here with its source. |
| The application's own LLM spend (coach, router, judge calls) | Recorded per call in `logs/traces.jsonl` (git-ignored, not shipped). `EVALS.md` reports measured per-turn cost for Mode A and Mode B (n=12 turns each). Without API keys these calls are mocks and cost nothing. |
| INR conversion | Not stated, because no exchange rate was recorded. |

### How to re-measure

1. Run `/cost` inside Claude Code for a live figure for the current session.
2. Or re-sum the logs: each line in `~/.claude/projects/<project>/*.jsonl` with `"type": "assistant"` carries `message.usage` (`input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`). Count each `message.id` once, using its last record.
