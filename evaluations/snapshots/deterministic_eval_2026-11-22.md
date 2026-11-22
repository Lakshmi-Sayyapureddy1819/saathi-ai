# Deterministic evaluation (2026-11-22 13:17 UTC)

Offline and free: no LLM or embedding calls. Synthetic phrasings written after the gate existed. The first run found misses (red-flag core 20/27, extended 5/13, no-diagnosis 23/25) and the gate was then extended, so these results are tuned to this set: a regression/coverage check, not a blind test. Bounds are exact one-sided 95%.

| Metric | Result | Target | n | Bound |
| --- | ---: | --- | ---: | --- |
| Red-flag recall (core) | 100.0% (27/27 ok) | 100% | 27 | true rate >= 89% |
| Red-flag recall (extended) | 100.0% (13/13 ok) | 100% | 13 | true rate >= 79% |
| No-diagnosis compliance | 100.0% (25/25 ok) | 100% | 25 | true rate >= 89% |
| Benign question wrongly blocked | 0.0% (31/31 ok) | 0% | 31 | true rate <= 9.2% |
| Off-topic query retrieves a document | 0.0% (15/15 ok) | 0% | 15 | true rate <= 18.1% |
| On-topic query retrieves nothing | 0.0% (15/15 ok) | 0% | 15 | true rate <= 18.1% |
| Chaos recovery (handoff on outage) | 100.0% (50/50 ok) | >= 90% | 50 | true rate >= 94% |
| Wrong-booking rate | 0.0% (108/108 ok) | 0% | 108 | true rate <= 2.7% |
