---
description: Reproduce the official BM25 baseline in the starter kit directory
---

Reproduce the organizer's weak BM25 baseline to sanity-check the harness.

1. Run:
   `cd data/kit/techjam-conversational-search && python3 -m evaluator.local_evaluator`
2. Confirm the results match the official reference in
   `data/kit/techjam-conversational-search/docs/baseline_results.json`:
   Hit@10 0.125, MRR 0.068034, MTTC 9.81, Efficiency 0.119, TechnicalScore 0.10671.
3. Report whether the run matches and any discrepancy.
