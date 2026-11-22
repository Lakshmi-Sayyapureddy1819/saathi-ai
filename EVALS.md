# Saathi Care AI - Final Evaluation Benchmarks

This document summarizes the final performance metrics for the Saathi Care AI agent.

## Final Benchmark Scores

```text

--- Evaluation Results ---
+----------------------------------------+---------------+----------+
| Metric                                 |    Result     |  Target  |
+========================================+===============+==========+
| Intent Classification Accuracy         |        73.33% |  >= 95%  |
| Red-Flag Crisis Recall                 |       100.00% |   100%   |
| No Diagnosis Rule Compliance           |        25.00% |   100%   |
| Wrong-Booking Rate                     |        0.00% |   0.0%   |
| Simulated Chaos Recovery Rate          |       100.00% |  >= 90%  |
| Calibrated LLM Judge Kappa             |        0.1000 |    -     |
+----------------------------------------+---------------+----------+
```

## System Performance Deltas

| Mode                          | Avg. Latency (p95) | Avg. Tokens per Turn (LLM) |
| ----------------------------- | ------------------ | -------------------------- |
| **Mode A (Agentic RAG)**      | 2150 ms            | ~1850 tokens               |
| **Mode B (Fact-Grounded)**    | 850 ms             | ~950 tokens                |
