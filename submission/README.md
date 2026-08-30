# 【TiktokTechJam2026】EntroShop — Submission Package

Official submission layout: `agent.py` (exports `Agent`) + `src/` (helper
modules) + `requirements.txt` + this README.

## Requirements

- Python ≥3.10 (tested on 3.14)
- `numpy`, `scikit-learn` (optional — only the dense route needs them;
  the deterministic core is stdlib-only)

```bash
pip install -r requirements.txt
```

## Data

The frozen catalog (50,000 products) comes from the official participant kit:

```bash
mkdir -p data
curl -L -o catalog.jsonl.gz https://github.com/TechJam2026/techjam-conversational-search/releases/download/participant-kit/catalog.jsonl.gz
gzip -dk catalog.jsonl.gz && mv catalog.jsonl data/catalog.jsonl
curl -L -o data/public_set.jsonl https://raw.githubusercontent.com/TechJam2026/techjam-conversational-search/main/data/public_set.jsonl
```

## Run (one command, inside a kit clone with this package overlaid)

```bash
git clone https://github.com/TechJam2026/techjam-conversational-search.git ../techjam-kit
cp agent.py ../techjam-kit/starter/agent.py      # replaces the weak starter
cp -r src ../techjam-kit/src
cp requirements.txt ../techjam-kit/
cd ../techjam-kit && python3 -m evaluator.local_evaluator
# expect Hit@10 1.000, MRR 0.724, MTTC 1.59, TechnicalScore 0.906
```
*The official evaluator loads `starter.agent` — the entry file must replace it.*

## Network & Fallback Policy

- **Recommended: online** with the LLM rerank enabled (`TECHJAM_LLM_*`):
  product-mode ranking and a hedge against paraphrase drift on unseen splits.
- **Offline fallback:** 0 tokens, no network, no API keys. Still correct
  (hits every session). Measured on the public set the two modes are
  equivalent: TechnicalScore 0.905543 online vs 0.905507 offline, same
  Efficiency (0.9415).
- Final scoring may disable network access: the agent then runs the offline
  fallback automatically at the measured equivalent score.
- Keys are read from environment variables only and never committed;
  any rerank failure/timeout falls back silently to the deterministic ranking.

## Model & Cost Disclosure

- Offline fallback core: deterministic hybrid retrieval — 0 tokens, ≈0.4 s/session, **$0**.
- Optional dense: MiniLM `all-MiniLM-L6-v2` (local CPU, one-time ~5 min build,
  cached).
- LLM rerank (recommended online mode, pools 11–60): measured with
  `deepseek-v4-flash` ≈ 2–3k prompt + 1.5k completion tokens per call, 13–21 s,
  ≈ $0.002–0.003 per call at public list prices; 244,742 tokens ≈ $0.1–0.2
  per 200-session run. No measurable public-set score change (TS +0.000036).

## Interface

```python
from agent import Agent

agent = Agent("data/catalog.jsonl")   # optional: TECHJAM_LLM_* env for rerank
agent.reset(session_id, user_profile)
response = agent.respond(session_id, user_message, turn, top_k)
```
