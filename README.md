# 【TiktokTechJam2026】EntroShop

![EntroShop logo](demo/logo.png)

> **Entropy-guided conversational shopping.** EntroShop asks the highest-information question, watches the candidate swarm converge, and settles on the one product you actually want — within 10 turns.

**TikTok TechJam 2026 · Track 4 — Shopping Copilot: AI Conversational Search & Recommendations**

> 📖 Full documentation — chapter-per-file, open-source style:
> [`docs/`](docs/README.md) (getting started · architecture · modules ·
> policy optimization · benchmarks · testing · FAQ · contributing ·
> license). Mini-paper & strategy write-up:
> [`docs/PROJECT.md`](docs/PROJECT.md), [`SOLUTION.md`](SOLUTION.md).

| | Weak BM25 baseline | EntroShop |
|---|---|---|
| **Hit Rate@10** | 0.125 | **1.000** 🎯 |
| **MRR** | 0.068 | **0.724** |
| **MTTC (mean turns to conversion)** | 9.81 | **1.59** |
| **Efficiency** | 0.119 | **0.9415** |
| **TechnicalScore** | 0.107 | **0.9055** |

*All 200 public sessions hit the hidden target. Recommended mode: online (LLM rerank) as the product-mode ranking and a hedge against paraphrase drift. Measured on the public set, online and offline are equivalent (TS 0.905543 vs 0.905507); the fully offline deterministic fallback (0 tokens, in-memory, no external vector DB) hits every session at zero cost.*

---

## Why

Traditional e-commerce search matches keywords, not intent. A shopper who says *"I want a black leather belt under \$30"* fights a filter UI; a conversational agent that just "chats" never converges. EntroShop treats shopping as an **information-elicitation problem**: every turn it picks the question with the highest expected information gain, narrows the candidate pool, and converges to a single answer — like rendering a scene, one sample at a time.

## How it works

1. **Seed** — the customer's message is parsed into structured constraints (exact feature phrases via a catalog trie, plus material / color / budget slots) in Chinese or English.
2. **Intent graph** — a state machine routes Buying / Browsing / Intent Override / Boundary and accumulates slots; overrides erase only the superseded preference.
3. **Swarm simulation** — multi-route retrieval narrows the 50k-product world each turn:
   `catalog 50,000 → exact-phrase conjunction → coarse-category match → hybrid score → LLM rerank → final 1`
   Candidates are ranked by exact-phrase hits, category identity, materials, colors, budget, title overlap, rating-style consistency, and a popularity prior.
4. **Forecast** — the survivor is crowned 👑 as the single final recommendation, with the narrowing funnel and consensus signals shown.

The demo renders step 3 as a **MiroFish-style god-view world**: candidate products swim as fish, eliminated ones fade where they died, and the winner takes the crown.

## Features

- 🎯 **100% hit rate** on the official public set (200/200), MTTC 1.59 vs 9.81 baseline
- 🧭 **Entropy-guided clarification** — facet (color / material / price / category) chosen by pool entropy, clickable chips, no-progress auto-convergence, hard 10-turn clamp
- 🌊 **MiroFish-style world visualization** — live swarm convergence, pan / zoom, hover details
- 🛒 **Real shopping cart** — converged picks render as product pages with a working cart (add/remove/quantity/total, localStorage-persisted); a session auto-starts on page load so Send works immediately
- 🔍 **Hybrid retrieval** — exact-phrase conjunction + coarse-category exact match + TF-IDF/MiniLM dense route + optional DeepSeek LLM rerank (failure-safe)
- 🔌 **MCP server** — `search_products`, `product_details`, `clarify`, `tree_chain` tools over stdio or HTTP (JSON-RPC 2.0, stdlib-only)
- 🌳 **Product-property tree** — the catalog organized as an n-ary tree (coarse → fine properties); every product maps to one unique root-to-leaf chain, rendered as a breadcrumb on the final pick and exposed via the MCP `tree_chain` tool
- 🧠 **MiniLM dense route** (optional) — 50k product embeddings, one-time cache
- 🈶 **Bilingual input** — Chinese and English free-form queries

## Quick start

**Requirements:** Python ≥3.10 (tested on 3.14); `numpy` + `scikit-learn` are
optional (only the dense route needs them — the deterministic core is
stdlib-only).

```bash
# 1) data from the official participant kit (50k products + 200 public sessions)
mkdir -p data
curl -L -o catalog.jsonl.gz https://github.com/TechJam2026/techjam-conversational-search/releases/download/participant-kit/catalog.jsonl.gz
gzip -dk catalog.jsonl.gz && mv catalog.jsonl data/catalog.jsonl
curl -L -o data/public_set.jsonl https://raw.githubusercontent.com/TechJam2026/techjam-conversational-search/main/data/public_set.jsonl

# 2) official local evaluation (our agent overlaid onto a kit clone)
git clone https://github.com/TechJam2026/techjam-conversational-search.git ../techjam-kit
cp -r starter agent_lib ../techjam-kit/
cd ../techjam-kit && python3 -m evaluator.local_evaluator
# (offline fallback) expect Hit@10 1.000, MRR 0.724, MTTC 1.59, TechnicalScore 0.9055
# set TECHJAM_LLM_* to enable the recommended online rerank (better efficiency)

# 3) interactive demo UI — chat works standalone with just the catalog
pip install --target vendor transformers    # optional MiniLM dense route
PYTHONPATH=vendor python3 demo/server.py     # open http://127.0.0.1:8090
# with the organizer kit (enables the Example presets):
#   PYTHONPATH=vendor:../techjam-kit python3 demo/server.py
```
*The repo deliberately ships no organizer files (evaluator, data) — they come
from the participant kit above.*

LLM rerank (recommended online mode; DeepSeek or any OpenAI-compatible endpoint):

```bash
export TECHJAM_LLM_API_BASE="https://api.deepseek.com/v1"
export TECHJAM_LLM_API_KEY="..."            # never commit keys
export TECHJAM_LLM_MODEL="deepseek-v4-flash"
```

## Network & Fallback Policy

- **Recommended: online.** Set `TECHJAM_LLM_*` to enable the LLM rerank
  (product-mode ranking; hedge against paraphrase drift on unseen splits).
- **Offline fallback:** without a key or network, the deterministic core still
  runs and hits every session. Measured on the public set the two modes are
  equivalent (TechnicalScore 0.905543 online vs 0.905507 offline, same
  Efficiency); see `docs/05-benchmarks.md`.
- The organizer may **disable network access for final scoring**. The agent
  then runs the offline fallback automatically at the measured equivalent
  score.
- LLM keys are read from environment variables only (`TECHJAM_LLM_*`,
  `DEEPSEEK_API_KEY`) and never committed. Any rerank failure, timeout, or
  malformed response falls back silently to the heuristic ranking.
- The catalog must exist locally (downloaded once from the participant kit);
  the demo UI and MiniLM embeddings are local too.

## Model & Cost Disclosure

| Component | Model / resource | Tokens | Measured latency | Approx. cost |
|---|---|---|---|---|
| Core ranking (offline fallback) | deterministic hybrid retrieval | **0** | ~0.4 s / session (200 sessions ≈ 70 s incl. index) | **$0** |
| Dense route (optional) | MiniLM `all-MiniLM-L6-v2` (22M params, local CPU) | 0 | one-time embedding build ≈ 5 min (cached); query ≈ 60–100 ms | $0 (local) |
| LLM rerank (recommended online mode; no measurable public-set gain, see benchmarks) | OpenAI-compatible, measured with `deepseek-v4-flash` | ~2–3k prompt + ~1.5k completion per top-15 rerank | 13–21 s per call | ≈ $0.002–0.003 / call at public list prices |

The LLM path is the recommended configuration: set `TECHJAM_LLM_API_KEY`
(or a local DeepSeek default) to enable it; it reranks pools of 11–60
candidates — but only when the **product-property tree does not already
converge** ("tree when possible, LLM when the tree is not enough"). When
the tree pins the candidates to a small set, the deterministic ranking is
kept and **zero tokens are spent even with a key configured**. Without a
key, everything runs on the offline deterministic ranking at zero cost.

## Repository layout

```text
starter/agent.py        required Agent interface (entry point)
agent_lib/              catalog index, message understanding, state machine,
                        multi-route retrieval, dense routes, MCP core, guidance
demo/                   interactive UI server + MCP stdio entry
analysis/               development probes, offline tuners, policy grids
docs/                   chapter-per-file documentation (see docs/README.md)
SOLUTION.md             full architecture and strategy write-up
```

## License

[MIT](LICENSE) © 2026 EntroShop Team (Entropino-ai). Competition data
(catalog, evaluator, public set) stays with the organizers' participant kit —
see [docs/09-license.md](docs/09-license.md).

## Limitations

- A session whose target shares *all* disclosed top-4 features with hundreds of catalog products is information-theoretically ambiguous; exact coarse-category matching resolves these on the public set, but the same corner case can reappear on unseen splits.
- The message parser assumes the simulator's deterministic disclosure templates; the trie + dense routes buffer against paraphrase.
- Weights were tuned on the 200 public sessions; private splits may shift slightly.

## Team

Team of five ([Entropino-ai](https://github.com/Entropino-ai) org). Full
contribution record: [`docs/TEAM_CONTRIBUTIONS.md`](docs/TEAM_CONTRIBUTIONS.md).
Built on the organizer-provided starter kit. Data: Amazon Reviews 2023
`Clothing_Shoes_and_Jewelry` (see `SOLUTION.md` for attribution).
