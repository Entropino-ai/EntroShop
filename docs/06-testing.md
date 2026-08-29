# 06 · Testing

## Smoke test suite

Everything below runs offline (no network, no LLM) and is the checklist used
for every release.

### 1. Official evaluator regression

```bash
PYTHONPATH=../techjam-conversational-search python3 -m evaluator.local_evaluator
```

Expect: Hit@10 = 1.000, TS ≥ 0.905 (drift guard), MTTC ≤ 1.6.

### 2. Convergence battery (13 cases)

Covers the convergence policy edge cases: pool ≤ 10, no-progress ≥ 2,
guide-rounds ≥ 4, turn-9 clamp, explicit converge, zero-information starter
chips, and combinations. Every case must terminate inside the turn budget
with a single champion.

```bash
PYTHONPATH=../techjam-conversational-search python3 - <<'PY'
from agent_lib.guide import GuideState, should_converge  # see analysis/ probes
PY
```

### 3. Demo server health + chat + example

```bash
PYTHONPATH=../techjam-conversational-search python3 demo/server.py &
curl -s localhost:8090/health            # expect {"ok": true, "llm_ok": ...}
curl -s -X POST localhost:8090/api/chat  -H 'Content-Type: application/json' \
  -d '{"message":"black leather belt under $30"}'
curl -s -X POST localhost:8090/api/example -H 'Content-Type: application/json' \
  -d '{"id":0}'
```

### 4. MCP tools

```bash
curl -s -X POST localhost:8090/mcp -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
curl -s -X POST localhost:8090/mcp -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"search_products","arguments":{"query":"leather belt"}}}'
```

### 5. Submission package import

```bash
cd submission && python3 -c "import agent, src.agent_lib.guide, src.agent_lib.index; print('ok')"
```

## Synthetic stress battery

300 harsh synthetic sessions (40% deliberately generic-feature products) +
23 adversarial chat inputs, reproducible via:

```bash
PYTHONPATH=../techjam-conversational-search python3 analysis/synthetic_stress.py
```

Full report: [STRESS_TEST.md](STRESS_TEST.md).

## Known limitations (not crashes)

- Negation ("not black") is not modeled — the color is added, not excluded.
- Typos are not corrected (pre-cleaned input assumed).
- Size attributes are not indexed as a facet.
- Pronoun references ("那条黑色的怎么样") are not resolved.
- Family-ambiguous sessions (identical disclosed constraints + coarse
  category across 218–1,069 near-identical listings) are at the
  disclosed-information bound; no agent can do better than a coin flip.
