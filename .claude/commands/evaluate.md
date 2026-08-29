---
description: Run the official TechJam evaluator and report EntroShop's score
---

Run the official TechJam evaluator against EntroShop and report the score.

1. Execute `python3 -m evaluator.local_evaluator` from the repository root.
2. Read the printed JSON (or `results.json` after the run).
3. Report concisely: Hit@10, MRR, MTTC, Efficiency, TechnicalScore, the
   per-scenario breakdown (buying / browsing / intent_override / boundary), and
   reported token usage.
4. Compare against the official baseline (TS 0.10671) and the previous best
   (TS 0.906) if known.

Note: `evaluator/`, `data/`, and `results.json` are protected artifacts — never
edit them.
