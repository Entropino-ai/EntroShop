# EntroShop — Claude Code Guide

Entropy-guided conversational shopping agent for **TikTok TechJam 2026 · Track 4**
(Shopping Copilot). Every turn it asks the highest-information question, narrows
a 50k-product swarm, and converges to the one product the customer wants —
within 10 turns. Bilingual: Chinese and English input.

Official public-set results (200 sessions): **Hit@10 1.000 · MRR 0.724 · MTTC 1.59 ·
TechnicalScore 0.9055**. Offline deterministic core — 0 LLM tokens; optional
MiniLM dense route and DeepSeek LLM rerank (failure-safe fallbacks).

## Quick commands (run from repo root)

| Command | Purpose |
|---|---|
| `python3 -m evaluator.local_evaluator` | Official score → prints metrics, writes `results.json` |
| `cd data/kit/techjam-conversational-search && python3 -m evaluator.local_evaluator` | Reproduce official BM25 baseline (TS 0.10671) |
| `python3 demo/server.py --port 8090` | MiroFish swarm demo UI → http://127.0.0.1:8090 |
| `python3 analysis/synthetic_stress.py` | Harsh synthetic stress test (300 sessions) |

Deps: numpy + scikit-learn in `/opt/miniconda3/bin/python3` (already installed).

## Repository layout

```text
starter/agent.py   REQUIRED competition entry point — exports class Agent
agent_lib/         catalog index, message understanding, state machine,
                   multi-route retrieval, dense routes, MCP core, guidance,
                   n-ary product-property tree (tree.py: unique per-product
                   chains + product mapping)
demo/              HTTP server + single-page UI
evaluator/         official judge (organizer kit artifact — READ-ONLY)
data/              catalog.jsonl (50k products), public_set.jsonl (200 sessions)
                   — gitignored, downloaded from the official participant kit
analysis/          development probes, offline tuners, stress tests
docs/              mini-paper (PROJECT.md) + stress report (STRESS_TEST.md)
```

## Agent contract (must never break)

```python
class Agent:
    def reset(self, session_id: str, user_profile: dict) -> None: ...
    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        return {"message": str, "ask_attribute": str|None,
                "recommendations": [{"parent_asin": str}], "usage": {"prompt_tokens": int, "completion_tokens": int}}
```

`ask_attribute` ∈ {category, material, color, size, style, brand, budget, feature,
use_case, other, null}. Only exact `parent_asin` equality scores. Scored = first 10
valid unique IDs, ordered best→worst.

## Hard rules

- **NEVER edit** `evaluator/**`, `data/**`, or `results.json` — official artifacts
  (a PreToolUse hook blocks this; if you must, say why and get explicit approval).
- **NEVER commit API keys.** LLM config is env-only:
  `TECHJAM_LLM_API_BASE`, `TECHJAM_LLM_API_KEY`, `TECHJAM_LLM_MODEL`
  (or `DEEPSEEK_API_KEY` / `~/.dsh/.credentials.yaml` local default).
- The offline core must keep working with no network and no LLM — every optional
  route has a failure-safe fallback; keep it that way.
- Tuning weights on the 200 public sessions is expected, but keep robustness for
  the 800 unseen private sessions (no overfitting to disclosed templates alone).
- Simulator discloses constraints as verbatim catalog strings → exact-phrase
  conjunction is the dominant retrieval signal; coarse-category exact match
  resolves ambiguous pools.

## Git collaboration

```text
origin  = https://github.com/Entropino-ai/EntroShop  (pull source, no push rights)
fork    = https://github.com/YH122432/EntroShop      (personal push remote)
```

Workflow: `git pull` → branch → `git push fork <branch>` →
`gh pr create --repo Entropino-ai/EntroShop --head YH122432:<branch> --fill`.
Local git identity: `YH122432 <254116711+YH122432@users.noreply.github.com>`.
