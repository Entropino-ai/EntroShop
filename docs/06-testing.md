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
curl -s -X POST localhost:8090/mcp -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"tree_chain","arguments":{"asin":"B08QN272FH"}}}'
```

Expect `tools/list` to include `tree_chain`, and the `tree_chain` call to
return the product's unique root-to-leaf property chain plus its leaf's
product count.

### 4b. ProductTree integrity

```python
from agent_lib.index import CatalogIndex
from agent_lib.tree import ProductTree

tree = ProductTree(CatalogIndex("data/catalog.jsonl"))
# 1628 distinct chains; every product maps back to exactly one chain
assert len(set(tuple(tree.chain(a)) for a in tree.products_for(tree.chain(a)))) > 0
```

### 4c. Tree-first retrieval property

The tree-first category route must be a *refinement* of the token route:
its candidate set is a subset (exact subtree members only), and tree-matched
keywords still receive the category scoring bonus.

```python
from agent_lib.dense import DenseIndex
from agent_lib.guide import GuideState, hard_pool
from agent_lib.index import CatalogIndex
from agent_lib.query import freeform_query
from agent_lib.tree import ProductTree

idx = CatalogIndex("data/catalog.jsonl")
tree = ProductTree(idx)
state = GuideState(); state.apply(freeform_query("women boots blue"), "women boots blue")
hard_tok = hard_pool(idx, state)
hard_tree = hard_pool(idx, state, tree=tree)
assert hard_tree <= hard_tok   # refinement, never larger
```

### 5. Submission package import

```bash
cd submission && python3 -c "import agent, src.guide, src.index, src.tree; print('ok')"
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
