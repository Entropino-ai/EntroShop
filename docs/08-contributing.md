# 08 · Contributing

## Repo layout

```
starter/          competition entry point (Agent contract)
agent_lib/        retrieval / state / guidance / query / dense / llm / mcp
demo/             interactive UI server
analysis/         probes, tuners, policy search, stress tests
submission/       official submission package (self-contained)
docs/             this documentation
```

## Dev workflow

1. **Symlinked data** — `data/catalog.jsonl` etc. symlink to the kit clone
   (`../techjam-conversational-search/data/`); never commit catalog data.
2. **Run everything with** `PYTHONPATH=../techjam-conversational-search`
   so `evaluator` and vendored `transformers` resolve.
3. **English only** in this repository (public GitHub project).
4. **Every change passes the smoke suite** in
   [06 · Testing](06-testing.md): evaluator regression, convergence battery,
   demo health/chat/example, MCP tools, submission import.
5. **Commit + push** to `main` (we rebase rather than squash to preserve
   history; pull --rebase before pushing).

## Running experiments

```bash
# policy search (chapter 04)
PYTHONPATH=../techjam-conversational-search python3 analysis/rl_policy_search.py

# synthetic stress (chapter 06)
PYTHONPATH=../techjam-conversational-search python3 analysis/synthetic_stress.py

# demo with MiniLM dense route
PYTHONPATH=../techjam-conversational-search:vendor python3 demo/server.py
```

## Conventions

- Keep the offline core stdlib-only and deterministic (no surprise network
  or LLM calls); optional routes must degrade to the deterministic core.
- New message features belong in `agent_lib/extract.py` or `query.py` with a
  probe in `analysis/`.
- New facets / guidance rules belong in `agent_lib/guide.py` with a
  convergence-battery case and a policy-search config (chapter 04).
- Never edit the evaluator, the kit files, or the scoring code.
