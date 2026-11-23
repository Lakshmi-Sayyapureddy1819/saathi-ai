# Retriever comparison (lexical vs embedding)

Run 2026-11-22. on-topic n=27, off-topic n=15. Hit = non-empty result. Small labelled sets: use as direction, not as a benchmark.

| Backend | On-topic answered | Off-topic wrongly answered |
|---|---|---|
| lexical | 27/27 | 0/15 |
| embedding, min_score=0.5 | 27/27 | 1/15 |
| embedding, min_score=0.55 | 27/27 | 0/15 |
| embedding, min_score=0.6 | 27/27 | 0/15 |
| embedding, min_score=0.65 | 25/27 | 0/15 |
| embedding, min_score=0.7 | 23/27 | 0/15 |
| embedding, min_score=0.75 | 20/27 | 0/15 |

Best threshold on this set (off-topic answers weighted 2x): **0.55**. Set EMBED_RETRIEVAL_MIN_SCORE to this value when RETRIEVER=embedding.
