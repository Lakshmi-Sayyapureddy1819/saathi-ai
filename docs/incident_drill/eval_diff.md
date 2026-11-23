**Incident A: lab API down**

| Metric | Healthy | Incident |
|---|---|---|
| Booking success (booked / calls) | 100% | 0% |
| Handed to a care coordinator | 0% | 100% |
| `tool:book_test` spans with an error | 0 | 15 |
| Final booking turn p50 latency | 331 ms | 1866 ms |

**Incident B: coach prompt rolled back to v1 (healthy = v4)**

| Metric | Healthy | Incident (v1) |
|---|---|---|
| Faithfulness (LLM judge) | 100.0% | 100.0% |
| Lexical groundedness | 82.0% | 3.8% |
| Answers citing a source id | 100.0% | 0.0% |
| Injection + out-of-scope suite | 8/9 | 6/9 |
| Tokens per turn | 1436.4 | 580.0 |

**Incident C: stale backend record**

| Metric | Healthy | Incident |
|---|---|---|
| Booking success (booked / calls) | 100% | 0% |
| Handed to a care coordinator | 0% | 0% |
| `tool:book_test` spans with an error | 0 | 5 |
| Final booking turn p50 latency | 331 ms | 365 ms |
