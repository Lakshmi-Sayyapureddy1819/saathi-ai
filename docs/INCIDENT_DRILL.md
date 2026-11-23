# Incident drill (brief section 7)

Reproduce everything with `python -m evaluations.incident_drill`, then
`cd frontend && npx playwright test e2e/incident_drill.spec.ts` for the screenshots. Artifacts are in
`docs/incident_drill/`. Two incidents were broken on purpose; each is compared with a healthy baseline run in the same
process, same code, same cases.

| | Incident A: partner lab API down | Incident B: bad prompt change | Incident C: stale backend record |
|---|---|---|---|
| What was broken | Every `book_test` call fails (`failure_rate = 1.0`, same switch as `LAB_FAILURE_RATE=1`) | Active coach prompt rolled back from v4 to v1 (`SAATHI_PROMPT_VERSION=v1`) | Selected slot is already claimed in backend (`(pkg, date, slot) in _booked`) |
| Member-visible symptom | "A care coordinator will call you back"; ticket created; never a false "booked" | Fluent, friendly answers that ignore the question and the library | "I'm sorry, that slot was just taken. Could you please pick another time?" |
| Alert signal (eval output) | Booking success 100% -> **0%**, handoff 0% -> **100%**, final booking turn p50 352 -> **1888 ms** | Lexical groundedness 82.8% -> **1.4%**, source citations 100% -> **0%**, injection + out-of-scope 9/9 -> **6/9**, tokens/turn 1407 -> **569** | Booking success 100% -> **0%**, handoff 0% -> **0%**, tool errors 0 -> **5**, p50 latency fast (~340 ms, no retry) |
| Cause visible in the trace | 3 `tool:book_test` spans per turn, each with `error=PartnerLabAPIConnectionRefused 500`, then `node_human_handoff` | `prompt_version=v1` on every node span; the `llm:` span has `prompt_tokens=26 / prompt_chars=113` vs `851 / 3595` healthy | 1 `tool:book_test` span with `error=SlotAlreadyBooked: slot is no longer available (stale record / conflict)` |
| Fix | Restore the partner API (or switch it off in the UI); handed-off tickets are worked by the coordinator | Set `SAATHI_PROMPT_VERSION` back to v4 (or revert the prompt file), re-run `evaluations.prompt_iterations` | Refresh slots cache / backend sync; member is prompted to pick another available slot |

Full tables: `docs/incident_drill/eval_diff.md`. Run numbers and trace ids: `docs/incident_drill/drill_results.json`.

## Screenshots
- `01-incident-A-eval-diff-and-trace.png` - eval diff and span waterfall of one failed booking turn next to the healthy one (red = span with an error).
- `02-incident-B-eval-diff-and-trace.png` - eval diff and trace of one coach turn under the bad prompt next to the healthy one.
- `03-incident-A-member-view-handoff.png` - the real UI against a backend whose lab API always fails: "Waiting for a care coordinator", no booking claimed.
- `04-incident-C-stale-record.png` - eval diff and waterfall trace showing fast fail with `SlotAlreadyBooked` error when booking a stale slot record.

The waterfall screenshots are rendered by `evaluations/incident_drill.py` from the local span log (`logs/drill_traces.jsonl`).
The same spans are also exported to Langfuse when keys are set, so the trace ids can be pasted into Langfuse's trace
search; **I did not capture Langfuse UI screenshots** (that needs a logged-in browser session).

## Runbook: find the cause from a cold start
Each step is one command or one filter. I did not time a human following it, so I make no "under 10 minutes" claim
beyond: every step below runs in seconds.

1. **Which metric moved?** Re-run `python -m evaluations.run_evals` (or the drill). Booking success / chaos recovery down -> tool side. Groundedness, citation rate, or injection suite down -> prompt/model side.
2. **Find a bad trace.** Filter spans for errors: `jq -c 'select(.metadata.error)' logs/traces.jsonl | head` (Langfuse: filter the trace list by the span name `tool:book_test` and non-empty `error`). Take its `trace_id`.
3. **Read the tree.** Every node, tool and LLM call of the turn carries that `trace_id`. Look at the tool spans (attempt number, error text) and at `prompt_version`, `model`, `prompt_tokens` on the node and `llm:` spans.
4. **Decide.**
   - Same error on every attempt and every member (`PartnerLabAPIConnectionRefused`) = dependency down (Incident A).
   - `prompt_version` or prompt size changed (`prompt_tokens` drastically lower) = bad deploy (Incident B).
   - Single attempt error (`SlotAlreadyBooked`) with 0ms retry delay = stale backend slot record / concurrent booking race (Incident C).
   - Different `model` than the routing config says = fallback model in use.
5. **Mitigate and verify.** Roll back / restore, then re-run the same eval and confirm the metric returned to baseline.

## What the drill taught (kept, not hidden)
- **The faithfulness judge did not catch incident B** (100% before and after): answers that say almost nothing contain almost no false claims. Groundedness, citation rate and prompt token count caught it. A faithfulness number alone must never be the prompt-regression alarm.
- **Voice latency finding from the same traces:** the synchronous Langfuse flush at the end of each turn added about 400 ms to the median voice turn. Fixed: voice turns now flush in the background (`flush(background=True)`).
- **Stale slot detection:** slot conflicts fail immediately without exhausting retries or triggering an emergency coordinator ticket; the member is reprompted directly.
