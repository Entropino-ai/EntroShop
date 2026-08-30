# 05 · Benchmarks

## Official public set (200 sessions)

| Metric | Weak BM25 baseline | EntroShop |
|---|---|---|
| Hit Rate@10 | 0.125 | **1.000** |
| MRR | 0.068 | **0.723** |
| MTTC (mean turns to conversion) | 9.81 | **1.59** |
| Efficiency | 0.119 | 0.9415 |
| TechnicalScore | 0.107 | **0.9053** |

## Scenario breakdown (all Hit@10 = 1.000)

| Scenario | MRR | MTTC |
|---|---|---|
| buying (80) | 0.749 | 1.15 |
| browsing (80) | 0.626 | 1.26 |
| intent_override (30) | 0.942 | 3.60 |
| boundary (10) | 0.653 | 1.60 |

## Ablations

### Exact coarse-category filter

Loose token intersection left the single ambiguous session with 459
candidates and the target ranked ≈27–141; the exact last-two-category match
collapsed it to 9 candidates including the target. This structural fix moved
Hit@10 0.995 → 1.000 and improved TS, MRR, and MTTC simultaneously — evidence
it is a generality improvement, not per-sample tuning.

### Competition ask policy (grid over the real evaluator)

`other`-until-exhausted (TS 0.8917) > feature-first (0.8857) > mixed
(0.8867). Chapter [04](04-policy-optimization.md) formalizes this as an
offline policy search.

### Dense route comparison (simulator pipeline)

TF-IDF 0.9045 vs MiniLM 0.9034 on the full pipeline — the deterministic
exact routes dominate; dense routes matter for paraphrase-heavy free chat.

## Behavioral battery (17/17)

Bilingual parsing, budget/color constraints, vague-input guidance,
rejection-reopen, topic shift, no-progress convergence, zero-info starter
categories, turn-9 clamp, contradictory-constraint resolution, and all four
simulator scenarios hit.

## Synthetic stress (see [STRESS_TEST.md](STRESS_TEST.md))

300 harsh sessions (40% generic-feature products), answerable-by-construction:
Hit@10 **1.000**, MRR 0.7446, MTTC 2.13, TS 0.9007. Every session is
solvable in principle (the full disclosed-constraint pool is ≤ 10 and
contains the target), so the run measures convergence quality instead of
luck; zero misses and zero retrieval bugs (`not-in-pool = 0`).

## Online mode (LLM rerank) vs offline fallback

Measured on the official public set (200 sessions), `deepseek-v4-flash`
reranking pools of 11–60 candidates:

| Metric | Offline (deterministic) | Online (LLM rerank) |
|---|---|---|
| Hit Rate@10 | 1.000 | 1.000 |
| MRR | 0.723351 | 0.723543 |
| MTTC | 1.585 | 1.585 |
| Efficiency | 0.9415 | 0.9415 |
| TechnicalScore | 0.905305 | 0.905405 |
| Tokens | 0 | 244,742 |

The rerank reorders candidate lists but changes no session outcome on the
public set (TS +0.000036). It is kept as a hedge against paraphrase drift on
unseen splits and as the product-mode ranking; it costs ≈245k tokens per
200-session run (≈$0.1–0.2 at public list prices) and falls back silently to
the deterministic ranking on any failure.
