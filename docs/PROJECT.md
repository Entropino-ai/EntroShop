<div style="page-break-after: always;"></div>

# Part I — Mini Paper

---

# EntroShop: An Entropy-Guided Conversational Shopping Agent with Bounded-Turn Convergence

**【TiktokTechJam2026】** · TikTok TechJam 2026 Track 4 — Shopping Copilot: AI Conversational Search & Recommendations

**Authors:** EntroShop Team (solo entry) — GitHub [SakuraEntropia/EntroShop](https://github.com/SakuraEntropia/EntroShop)

**Keywords:** conversational recommender systems · hybrid retrieval · clarification policy · information elicitation · swarm-intelligence UI · Model Context Protocol

## Abstract

Conversational commerce agents must converge to a single decision within a bounded interaction budget, yet most "chatbot-first" designs never converge and keyword search never captures intent. We present **EntroShop**, a deterministic-first conversational shopping agent over a 50,000-product clothing catalog. Three insights drive the design. *(i) The simulator discloses constraints as verbatim catalog strings*, so exact-phrase conjunction over an inverted index is the dominant retrieval signal (median conjunction size = 1). *(ii) The disclosed coarse category is the target's own last-two category parts, verbatim* — replacing loose token intersection with an exact coarse-key match collapsed the one historically ambiguous pool from 459 candidates to 9 and lifted Hit Rate from 0.995 to **1.000**. *(iii) Clarification is an information-elicitation problem* — each turn the agent asks the highest-entropy facet (color/material/price/category) with pool-derived options, decays stale slots, and enforces a hard 10-turn budget with a forced single final pick. On the official TechJam 2026 public set (200 sessions): **Hit@10 = 1.000, MRR = 0.724, MTTC = 1.59, TechnicalScore = 0.906**, versus the weak BM25 baseline (0.125 / 0.068 / 9.81 / 0.107), with **zero LLM tokens** in the offline core. Optional components — a MiniLM dense route, a failure-safe DeepSeek LLM reranker, an MCP server, and a MiroFish-style adversarial arena UI — make the system a complete product, not a metric.

## 1 Introduction

Traditional e-commerce search matches keywords against product text; a request like *"black leather belt under \$30"* either over- or under-filters. Conversational agents that simply "chat" accumulate context without narrowing it. EntroShop treats shopping as an information-elicitation problem: every turn picks the question with the highest expected information gain, narrows the candidate pool, and converges to one answer — like rendering a scene one sample at a time. The competition evaluator is a deterministic simulator whose disclosure policy is fixed and readable, which makes the information structure of the task explicit and therefore *engineerable*.

**Contributions.**
1. Exact-phrase conjunction + exact coarse-category matching as the retrieval backbone (data-set independent, private-split safe).
2. An entropy-guided clarification policy with recency-weighted slots, no-progress detection, and a hard 10-turn convergence clamp.
3. A staged multi-route pipeline (catalog → conjunction → coarse → hybrid score → LLM rerank → final 1) that is 100% offline-deterministic by default.
4. A product-grade demo: MiroFish-style adversarial arena, chain-of-thought panel, MCP server, bilingual input, MiniLM/LLM optional routes.

## 2 Method

### 2.1 Message understanding
Messages are parsed through three complementary channels: *(a)* fixed-template parsing (authoritative — constraints arrive in machine-generated templates), *(b)* a character trie over all catalog phrases that rescues long feature strings broken by `"; "` (only maximal ≥2-token matches are kept, to avoid single-token noise), and *(c)* regexes for synthetic constraints (bare material words, `color: x`, budget ranges) which must never enter the phrase index. Chinese input is mapped through a clothing-domain zh→en dictionary; filler words are stopworded so they never reset progress.

### 2.2 State machine and routing
A per-session state machine accumulates category / exact-phrase / material / color / budget slots, routes the opening message into Buying / Browsing / Intent Override / Boundary, and on an override erases only the opening preference (the target still matches it, so it survives as a weak signal). Slots carry recency: the latest keyword batch and the latest material/color mention receive full weight while older ones decay.

### 2.3 Multi-route retrieval
| Route | Signal | Weight | Role |
|---|---|---|---|
| Exact-phrase conjunction | disclosed phrase ∈ product phrase set | 100 each | dominant; cascade relaxes to the largest non-empty subset |
| Coarse-category exact match | last-two category parts equal the disclosed coarse key | 60 | hard filter when pool > 10; target always inside |
| Synthetic attributes | material / color / budget | 20–50 | recency-weighted |
| Title overlap | constraint/category tokens ∩ title | 16/3 | strong-intent boost |
| Rating-style consistency | profile.rating_style ↔ rating | 20 | 75% aligned |
| Popularity prior | log(1+rating_number) | 8 | real-purchase targets skew popular |
| Dense route | TF-IDF / MiniLM cosine | 30–35 | large pools; offline |
| LLM rerank | optional DeepSeek top-15 | — | failure-safe |

### 2.4 Guidance and convergence policy
From the surviving pool (top-200 sample) the agent computes value distributions over four facets and asks the highest-entropy unconstrained one, presenting clickable options with live counts (facet navigation). Convergence fires on: pool ≤ 5, two consecutive no-progress turns, exhaustion of guidance rounds, explicit user convergence, or the hard **turn-9 clamp** (every session finishes within the competition's 10-turn budget). At convergence one champion is crowned from the exact matches.

### 2.5 Optional components
A MiniLM (`all-MiniLM-L6-v2`) dense route with cached 50k embeddings; a DeepSeek (OpenAI-compatible) reranker of the top-15 with truncated-output-tolerant parsing and full fallback; an MCP server (`search_products`, `product_details`, `clarify`) over stdio or HTTP; and a demo UI with an adversarial arena (keyed-DOM fish that swim, get knocked out, and crown a champion) plus the champion's chain-of-thought panel.

## 3 Experiments

**Setup.** Official evaluator, 200 labeled public sessions (80 buying, 80 browsing, 30 intent override, 10 boundary), 50k-product frozen catalog.

| Metric | BM25 baseline | EntroShop |
|---|---|---|
| Hit@10 | 0.125 | **1.000** |
| MRR | 0.068 | **0.724** |
| MTTC | 9.81 | **1.59** |
| Efficiency | 0.119 | 0.934 |
| TechnicalScore | 0.107 | **0.906** |

**Scenario breakdown (all 1.000 Hit@10):** buying (MRR 0.749), browsing (0.626), intent_override (0.942), boundary (0.653); MTTC 1.15 / 1.26 / 3.60 / 1.60.

**Ablation — exact coarse-category filter.** Loose token intersection left the single ambiguous session with 459 candidates and the target ranked ≈27–141; the exact last-two-category match collapsed it to 9 candidates including the target. This structural fix moved Hit@10 0.995 → 1.000 and improved TS, MRR, and MTTC simultaneously — evidence it is a generality improvement, not per-sample tuning.

**Ablation — ask policy.** A grid over the real evaluator: `other`-until-exhausted (TS 0.8917) > feature-first (0.8857) > mixed (0.8867).

**Self-designed behavioral battery (17/17).** Bilingual parsing, budget/color constraints, vague-input guidance, rejection-reopen, topic shift, no-progress convergence, zero-info starter categories, turn-9 clamp, contradictory-constraint resolution, and all four simulator scenarios hit.

## 4 Conclusion

EntroShop shows that a conversational shopping agent can be both *convergent* and *100% accurate on the target task* by respecting the task's information structure: verbatim constraints → exact matching; disclosed category → exact coarse identity; clarification → entropy-guided elicitation; budget → hard clamp. The offline deterministic core needs zero tokens, and the optional LLM/dense/MCP components keep it competitive as a real product.

## References

1. Lei et al., *Estimation–Action–Reflection: Towards Deep Interaction Between Conversational and Recommender Systems*, WSDM 2020. arXiv:2002.09102
2. Sekulić et al., *Evaluating Mixed-initiative Conversational Search Systems via User Simulation*, SIGIR 2022. arXiv:2204.08046
3. Yao et al., *ReAct: Synergizing Reasoning and Acting in Language Models*, ICLR 2023. arXiv:2210.03629
4. Bocha-Labs, *MiroFish: A Simple and Universal Swarm Intelligence Engine*, github.com/Bocha-Labs/MiroFish
5. McAuley Lab, *Amazon Reviews 2023*, amazon-reviews-2023.github.io
6. TikTok TechJam 2026, *Track 4 Problem Statement* (Early Bird Access)

```bibtex
@misc{entroshop2026,
  title  = {{EntroShop}: An Entropy-Guided Conversational Shopping Agent
            with Bounded-Turn Convergence},
  author = {{EntroShop Team}},
  year   = {2026},
  note   = {TikTok TechJam 2026 Track 4 submission. https://github.com/SakuraEntropia/EntroShop}
}
```

---

<div style="page-break-after: always;"></div>

# Part II — Project Documentation

# 【TiktokTechJam2026】EntroShop

> **The generative shopping engine: seed a need, watch the candidate swarm converge, and get the one product you actually want.**

## What is EntroShop?

EntroShop is a conversational shopping agent that treats product search as an
**information-elicitation problem** — the same way a simulation engine treats a
scene: render it progressively, one sample at a time, until it converges.
Every turn it asks the highest-information question, narrows the candidate
pool, and settles on a single final recommendation within the competition's
10-turn budget. The offline core is fully deterministic: **0 LLM tokens,
in-memory, no external vector DB**.

## Quick start

```bash
# 1. one-time: catalog from the official participant kit (50k products)
gzip -dk catalog.jsonl.gz && mv catalog.jsonl data/catalog.jsonl

# 2. official local evaluator (from the organizer kit)
python3 -m evaluator.local_evaluator      # Hit@10 1.000, TS 0.906

# 3. interactive demo UI (optional MiniLM dense route)
pip install --target vendor transformers
PYTHONPATH=vendor python3 demo/server.py   # http://127.0.0.1:8090
```

Optional LLM rerank (any OpenAI-compatible endpoint, e.g. DeepSeek):

```bash
export TECHJAM_LLM_API_BASE="https://api.deepseek.com/v1"
export TECHJAM_LLM_API_KEY="..."          # never commit keys
export TECHJAM_LLM_MODEL="deepseek-v4-flash"
```

## Features

- **🎯 100% hit rate** on the official public set (200/200), MTTC 1.59 vs 9.81 baseline
- **🧭 Entropy-guided clarification** — facet chosen by pool entropy, clickable chips, no-progress auto-convergence, hard 10-turn clamp
- **⚔️ MiroFish-style adversarial arena** — candidates compete, get knocked out each round, the champion is crowned; chain-of-thought panel alongside
- **🔍 Hybrid retrieval** — exact-phrase conjunction + coarse-category exact match + TF-IDF/MiniLM dense route + optional LLM rerank (failure-safe)
- **🔌 MCP server** — `search_products`, `product_details`, `clarify` over stdio or HTTP (JSON-RPC 2.0, stdlib-only)
- **🈶 Bilingual input** — Chinese and English free-form queries

## Architecture

```
user message
   │
   ▼
[message understanding]  template parse + phrase trie + synthetic regexes
   │
   ▼
[state machine]  intent routing (buying/browsing/override/boundary),
   │             slot accumulation, recency decay, ask planner
   ▼
[multi-route retrieval]  exact conjunction → coarse-category exact
   │                     → synthetic attributes → title → consistency
   │                     → dense (TF-IDF / MiniLM) → LLM rerank
   ▼
[guidance & convergence]  entropy facet selection → chips →
   │                      no-progress / pool≤5 / turn-9 clamp
   ▼
{message, ask_attribute, recommendations, usage}   →  👑 final pick
```

## Modules

| Module | Responsibility |
|---|---|
| `starter/agent.py` | required Agent entry point (competition contract) |
| `agent_lib/index.py` | catalog index: phrase postings, trie, coarse-category keys, material/color/category postings |
| `agent_lib/extract.py` | message understanding (templates + trie + synthetic slots) |
| `agent_lib/state.py` | session state machine + ask planner |
| `agent_lib/retrieve.py` | multi-route retrieval, scoring, cascade relaxation, freeform route |
| `agent_lib/guide.py` | entropy-guided clarification, convergence policy, hard pool |
| `agent_lib/dense.py` / `dense_transformer.py` | TF-IDF / MiniLM dense routes |
| `agent_lib/llm_rank.py` | optional OpenAI-compatible reranker (failure-safe) |
| `agent_lib/mcp.py` | MCP server core (JSON-RPC 2.0) |
| `agent_lib/query.py` | free-form query understanding + zh→en dictionary |
| `demo/` | interactive UI server, arena + chain-of-thought, MCP stdio entry |
| `analysis/` | development probes, offline tuners, policy grids |

## Robustness (synthetic stress)

Synthetic data — 300 mini-private-set sessions (40% deliberately
generic-feature products) plus 23 adversarial chat inputs — is bundled in
[`STRESS_TEST.md`](STRESS_TEST.md) and reproducible via
`analysis/synthetic_stress.py`. Headline: no retrieval bugs (`not-in-pool` =
0); all synthetic misses are family-ambiguous sessions at the disclosed-
information bound; the adversarial chat battery runs 23/23 without crashes.

## Benchmarks

| Metric | BM25 baseline | EntroShop |
|---|---|---|
| Hit@10 | 0.125 | **1.000** |
| MRR | 0.068 | **0.724** |
| MTTC | 9.81 | **1.59** |
| TechnicalScore | 0.107 | **0.906** |

Scenario breakdown (Hit@10 = 1.000 everywhere): buying MTTC 1.15 · browsing 1.26 · intent_override 3.60 · boundary 1.60.

## Tutorials

1. **Free chat** — pick *Free chat*, type `black leather belt under $30` (Chinese works too), click the facet chips until the 👑 champion appears.
2. **Example scenarios** — pick an *Example · …*, step with *Next turn* and watch the simulator disclose constraints; every scenario hits.
3. **MiroFish Arena** — open *🌊 MiroFish Arena*: fish swim, get knocked out, the champion is crowned; the reasoning chain below shows why.
4. **MCP** — `PYTHONPATH=vendor python3 demo/mcp_server.py` registers in any MCP host; or `curl -X POST localhost:8090/mcp` for HTTP.

## FAQ

- **Why no pure-LLM approach?** The task's information structure is deterministic and readable; exact matching beats semantic smoothing on the public set (TF-IDF 0.9045 vs MiniLM 0.9034 on the simulator pipeline), and the offline core costs zero tokens.
- **Does the private split hold?** The winning mechanisms (exact conjunction, exact coarse-category identity, clamp) are data-independent — they follow from the simulator's disclosure rules, not from the 200 public sessions.
- **What if the organizer paraphrases?** The trie + dense routes buffer paraphrase as long as constraint strings survive verbatim; the template parser degrades gracefully.

## Acknowledgments

Built on the organizer-provided starter kit; data from Amazon Reviews 2023 (`Clothing_Shoes_and_Jewelry`); design references: Genesis/Blender-style documentation, MiroFish (swarm-intelligence visualization), EAR / mixed-initiative conversational search / ReAct.
