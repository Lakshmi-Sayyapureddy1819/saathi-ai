## Model mixes (brief section 4): same eval, four mixes

`python -m evaluations.model_mix` (snapshot: `evaluations/snapshots/model_mix_2026-11-22.json`). Same 12 golden wellness questions through the real workflow (coach and router fallback both on the mix's model, prompt v4, cache off) plus the 9-case injection / out-of-scope suite x 2 repeats. Each mix is a routing node with **no fallback**, so failures are counted, not hidden. Faithfulness is scored by one fixed judge (`gemini-3.8-flash`) for every mix, so it is same-vendor for the Gemini rows and not human-validated.

| Mix | Model | Faithfulness (judge) | Lexical grounded. | Cites id | <=120 words | Injection + OOS | Errors | Latency p50 / p95 (ms) | Tokens/turn | Cost / 1k LLM turns | Cost / 1k conversations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gemini_lite | gemini-3.5-flash-lite | 100.0% (n=12) | 84.0% | 100.0% | 100.0% | 18/18 | 0 | 2075.9 / 2813.1 (n=36) | 906.9 | $0.596 | $1.192 |
| gemini_flash | gemini-3.8-flash | 100.0% (n=12) | 73.7% | 100.0% | 100.0% | 17/18 | 0 | 7507.5 / 11679.3 (n=36) | 1717.0 | $4.159 | $8.318 |
| openai_mini | gpt-4o-mini | 99.1% (n=12) | 68.8% | 100.0% | 100.0% | 18/18 | 0 | 1930.6 / 4201.2 (n=36) | 868.0 | $0.191 | $0.382 |
| openai_4o | gpt-4o | 99.2% (n=12) | 60.7% | 100.0% | 91.7% | 18/18 | 0 | 2129.7 / 4445.9 (n=36) | 886.7 | $3.374 | $6.748 |

Latency is per LLM call (12 coach calls + 24 suite calls = n=36), so p95 is the 2nd-slowest call. Cost per 1k conversations assumes **2 coach-LLM turns per conversation** (an assumption: booking, safety and handoff turns make no LLM call); cost per 1k LLM turns is measured. Single run, provider load moves latency about 2x (see Limitations).

**Reading it.** Quality is statistically indistinguishable here: faithfulness 99-100% everywhere and 100% citation, so with n=12 the data cannot rank the models on answer quality. Differences that are real: `gemini-3.8-flash` is a thinking model, 3.6x slower (p50 7.5 s) and 7x the cost of flash-lite, and failed one injection case (17/18); `gpt-4o` is 18x the cost of `gpt-4o-mini` for no measured gain and broke the <=120-word rule once. Lexical groundedness is English-only and noisy (see Limitations), so it is not used to choose.

### Proposed Routing Policy (implemented in `config/models.yaml`)

| Route | Used for | Default | Fallback | Why |
|---|---|---|---|---|
| `cost_optimized` | Chat coach answers, router LLM fallback | gemini-3.5-flash-lite | gpt-4o-mini | Passed all gates at ~$0.60 / 1k LLM turns; fallback is a different vendor, so a Google outage does not stop chat. |
| `quality_optimized` | Eval judge and the lab-report explainer (`report_tools.py`, the only member-facing use) | gemini-3.8-flash | gpt-4o | Reasoning over report text and judging; not on the chat or voice coaching path, where latency matters. |
| `voice` | Voice channel (`WorkflowGraph(model_node="voice")`, used by `voice_demo.py`) | gemini-3.5-flash-lite | gpt-4o-mini | Latency first: lowest p95 (2.8 s) among mixes that passed the gates (injection 100%, faithfulness >= 90%, 0 errors). `gpt-4o-mini` has a slightly lower p50 but a worse p95 (4.2 s), and is the fallback. |

Rules: transactional, safety and handoff turns never call an LLM (deterministic code). Escalate to a larger model only for a measured failure, not by default. Swapping a model is a YAML edit; a new price needs a `PRICING` entry (a test enforces coverage).

### Why Voice Is Treated Separately

**Voice wellness turns now meet the first-audio budget via a spoken filler (full answers are still ~2 s).** The best voice model has p50 2.1 s / p95 2.8 s per call, against a 1.5 s time-to-first-audio budget that also has to fit STT and TTS. The route choice does not fix that; streaming tokens into TTS and a spoken filler ("let me check") are still needed and are not built. Booking turns (no LLM) are within budget.
