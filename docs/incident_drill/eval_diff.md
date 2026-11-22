**Incident A: lab API down**

| Metric | Healthy | Incident |
|---|---|---|
| Booking success (booked / calls) | 100% | 0% |
| Handed to a care coordinator | 0% | 100% |
| `tool:book_test` spans with an error | 0 | 15 |
| Final booking turn p50 latency | 352 ms | 1888 ms |

**Incident B: coach prompt rolled back to v1 (healthy = v4)**

| Metric | Healthy | Incident (v1) |
|---|---|---|
| Faithfulness (LLM judge) | 100.0% | 100.0% |
| Lexical groundedness | 82.8% | 3.1% |
| Answers citing a source id | 100.0% | 0.0% |
| Injection + out-of-scope suite | 9/9 | 6/9 |
| Tokens per turn | 901.0 | 141.8 |
