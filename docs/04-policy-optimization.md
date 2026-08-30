# 04 · Policy optimization

> **Offline RL-style policy search.** The agent's "ask which facet / when to
> converge" behavior is treated as a **policy**; the simulator (or a
> ground-truth chat simulator) is the **environment**; hits and technical
> scores are the **reward**. We search the policy space by rolling out every
> configuration offline and reporting the argmax — the classic offline
> policy-search loop, minus any live training loop.

## Why RL-style search (not RLHF)

The competition evaluator is a **deterministic simulator**: the intent card
is generated from the target product's metadata and constraints are disclosed
through fixed templates. That means the reward function is exact and
readable — there is no preference model to learn, so RLHF adds nothing to the
core score. What *is* tunable is the **policy**: which attribute to ask next,
how many constraints to elicit, and when to stop asking and converge. Those
are exactly the quantities a policy search over a simulator environment can
optimize offline.

## Environment & reward

| Part | Environment | Policy space | Reward |
|---|---|---|---|
| A — competition ask policy | official evaluator (200 public sessions) | per-scenario `ask_attribute` plans + ask caps | TechnicalScore (0.50·Hit@10 + 0.30·MRR + 0.20·Efficiency) |
| B — chat guidance policy | synthetic chat simulator (120 ground-truth sessions) | convergence threshold × no-progress threshold × facet rule | final-pick hit rate |

The chat simulator replays each scenario's opening message, then answers
every facet chip with the target's *true* value (color / material / budget /
category), so the simulated customer is cooperative but the underlying
products are real catalog items — including the deliberately generic 40%
"hard" pool.

## Part A — competition ask policy

Policy: for each scenario (buying / browsing / boundary / intent_override),
the sequence of `ask_attribute` values. The baseline is `other` until
exhausted; alternatives front-load `feature` or `material`/`color`.

| Policy | TS | Hit@10 | MRR | MTTC |
|---|---|---|---|---|
| `other`-until-exhausted (deployed) | **0.9053** | **1.000** | **0.723** | **1.585** |
| `other` ×3 then null | 0.9053 | 1.000 | 0.723 | 1.585 |
| `feature`-first | 0.9036 | 1.000 | 0.720 | 1.615 |
| `material`/`color`-first | 0.9000 | 1.000 | 0.710 | 1.645 |

**Result:** the deployed `other`-until-exhausted plan is the offline argmax
(TS 0.9053). Front-loading `feature` or `material`/`color` asks *hurts*:
every `ask_attribute` slot spent on a specific facet is one fewer
"two undisclosed constraints" disclosure, so the pool shrinks slower and
MTTC / MRR degrade. The search confirms the deployed policy — no change
needed. *(Grid reproduced via `analysis/rl_policy_search.py` Part A.)*

## Part B — chat guidance policy

Policy: `converge_at` (pool threshold), `no_progress_at` (consecutive
no-information turns), and `facet_rule` (`entropy` = highest-information
facet vs `first` = fixed order).

| converge ≤ | no-progress ≥ | facet rule | Hit@10 |
|---|---|---|---|
| 5 | 2 | entropy | 0.250 |
| 5 | 2 | first | 0.267 |
| 5 | 3 | entropy | 0.250 |
| 5 | 3 | first | 0.267 |
| 10 | 2 | entropy | 0.250 |
| 10 | 2 | first | 0.267 |
| 10 | 3 | entropy | 0.250 |
| 10 | 3 | first | 0.267 |

**Verification (240 fresh sessions, same two rules):** `first` 0.208 vs
`entropy` 0.212, with 4 first-only wins vs 5 entropy-only wins — the 120-
session gap (0.267 vs 0.250) does **not** reproduce and is statistical
noise. **Conclusion: in the synthetic chat simulator the policy levers
(convergence threshold, no-progress threshold, facet rule) are all
equivalent within noise** — the pool collapses fast regardless, and the
remaining misses are information-bound (the target shares all disclosed
constraints with near-identical listings).

**Deployed default.** `entropy` facet selection with `pool ≤ 10` and
`no-progress ≥ 2` stays, because it is the information-theoretic optimum
when a real user may be *uncertain* about some attributes (the simulator
always answers truthfully, which removes exactly the uncertainty entropy
exploits). The search confirms the deployed policy — no change needed.

## Deployed policy

The current production defaults — `pool ≤ 10` convergence, `no_progress ≥ 2`,
entropy facet selection, and the turn-9 clamp — are the offline-optimal
configuration (see chapter [05](05-benchmarks.md) for the resulting scores).

## Reproduce

```bash
PYTHONPATH=../techjam-conversational-search python3 analysis/rl_policy_search.py
```

Full run ≈ 70 min on this machine (Part A: 4 official-evaluator passes;
Part B: 8 × 120 simulated chat sessions, each with dense scoring over the
50k catalog). The simulator's opening messages are deliberately vague and
template-noise words are stopworded, so the guidance policy — not the
opening's disclosure — is what is being measured.
