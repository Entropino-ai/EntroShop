# 01 · Getting started

## Requirements

- Python **3.10+** (stdlib-only core; optional routes need `transformers`).
- The official participant kit — either a clone of
  `TechJam2026/techjam-conversational-search` or just its data files.
- `numpy` + `scikit-learn` (see `requirements.txt`) for the dense route —
  the deterministic core runs without them.

## 1. Get the data

```bash
mkdir -p data
curl -L -o catalog.jsonl.gz https://github.com/TechJam2026/techjam-conversational-search/releases/download/participant-kit/catalog.jsonl.gz
gzip -dk catalog.jsonl.gz && mv catalog.jsonl data/catalog.jsonl
curl -L -o data/public_set.jsonl https://raw.githubusercontent.com/TechJam2026/techjam-conversational-search/main/data/public_set.jsonl
```

## 2. Run the official local evaluation

Overlay our agent onto a kit clone (the evaluator imports `starter.agent`).
The evaluator reads `data/catalog.jsonl` from the kit's own `data/`
directory, so the catalog downloaded in step 1 must be copied there too:

```bash
git clone https://github.com/TechJam2026/techjam-conversational-search.git ../techjam-kit
cp -r starter agent_lib ../techjam-kit/
cp data/catalog.jsonl ../techjam-kit/data/
cd ../techjam-kit && python3 -m evaluator.local_evaluator
```

Expected output (public set, 200 sessions):

| Metric | Value |
|---|---|
| Hit Rate@10 | 1.000 |
| MRR | 0.723 |
| MTTC | 1.59 |
| Efficiency | 0.9415 |
| TechnicalScore | 0.9053 |

Or run the self-contained evaluation from this repo (symlinked data):

```bash
PYTHONPATH=../techjam-conversational-search python3 -m evaluator.local_evaluator
```

## 3. Run the demo UI

```bash
pip install --target vendor transformers        # optional MiniLM dense route
PYTHONPATH=vendor python3 demo/server.py        # http://127.0.0.1:8090
# MiniLM is NOT used by default (TF-IDF keeps turns snappy); enable it with:
#   TECHJAM_DEMO_USE_TRANSFORMER=1 PYTHONPATH=vendor python3 demo/server.py
```

- **Free chat** works standalone. **Example presets** replay the simulator,
  so they need the kit on `PYTHONPATH` (above command already sets it).
- If the official evaluator cannot be imported, the server still runs in a
  degraded mode (free chat works, examples are disabled).

### Optional LLM rerank

Any OpenAI-compatible endpoint; DeepSeek is the tested default.

```bash
export TECHJAM_LLM_API_BASE="https://api.deepseek.com/v1"
export TECHJAM_LLM_API_KEY="..."          # never commit keys
export TECHJAM_LLM_MODEL="deepseek-v4-flash"
```

The server pings the endpoint at startup and on every configuration change;
if it is unreachable, the LLM route is disabled gracefully and the system
falls back to the fully offline deterministic core.

## 4. Run the policy optimizer

```bash
PYTHONPATH=../techjam-conversational-search python3 analysis/rl_policy_search.py
```

See [04 · Policy optimization](04-policy-optimization.md) for what it
searches and how to read its output.
