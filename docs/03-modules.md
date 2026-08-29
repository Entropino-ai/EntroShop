# 03 · Modules

| Module | Responsibility |
|---|---|
| `starter/agent.py` | required Agent entry point (competition contract) |
| `agent_lib/index.py` | catalog index: phrase postings, phrase trie, coarse-category keys, material/color/category postings, prices, ratings, stores |
| `agent_lib/extract.py` | message understanding: fixed-template parsing, trie substring rescue, synthetic-constraint regexes |
| `agent_lib/state.py` | session state machine (intent routing, slots, superseded) + ask planner (`PLANS`) |
| `agent_lib/retrieve.py` | multi-route retrieval, scoring, cascade relaxation, freeform route with pool |
| `agent_lib/guide.py` | entropy-guided clarification, convergence policy, hard pool, option labels |
| `agent_lib/query.py` | free-form query understanding + zh→en dictionary + budget regexes |
| `agent_lib/dense.py` | TF-IDF dense index (stdlib) |
| `agent_lib/dense_transformer.py` | MiniLM dense route (optional, cached embeddings) |
| `agent_lib/llm_rank.py` | optional OpenAI-compatible reranker (failure-safe, ping probe) |
| `agent_lib/mcp.py` | MCP server core: `search_products`, `product_details`, `clarify` (JSON-RPC 2.0) |
| `demo/` | interactive UI server: arena + chain-of-thought + convergence card + MCP stdio entry |
| `analysis/` | development probes, offline tuners, policy grids, synthetic stress |
| `submission/` | official submission package (self-contained `agent.py` + `src/`) |

## Key public interfaces

### `agent_lib/index.py` — `CatalogIndex(catalog_path)`

- `phrase_postings: dict[str, set[str]]` — verbatim feature/detail phrase → ASINs
- `phrase_trie` — character trie over all phrases (substring rescue)
- `category_coarse_key: dict[str, str]` — exact last-two-category-part key
- `category_coarse_postings` / `category_specific_token_postings`
- `material_postings` / `color_postings` / `category_postings`
- `prices`, `ratings`, `stores`, `title_tokens`, `products`, `corpus`

### `agent_lib/extract.py`

- `parse(user_message, index)` → `ParsedMessage`: `phrase_hits`,
  `material`, `color`, `budget`, `category`, `negated`, `converge`, `shift`
- Trie hits keep only **maximal ≥2-token** matches (single-token noise is
  discarded); synthetic constraints (`color: x`, bare material words, budget
  ranges) never enter the phrase index.

### `agent_lib/state.py`

- `ConversationState` — opening phrases, superseded slots, plan, dead
  attributes
- `PLANS: dict[str, list[str]]` — per-scenario `ask_attribute` sequences
  (the competition policy; see chapter 04)

### `agent_lib/guide.py`

- `GuideState` — keywords (with recency weights), materials, colors, budget,
  `no_progress`, `guide_rounds`, `converged`, `facet_keys`
- `choose_facet(index, pool, state, rule="entropy")` → `(facet, values)`
- `hard_pool(index, state)` → candidate set after coarse/material/color
  constraints
- `should_converge(pool_size, turn)` → bool
- `option_labels(facet, values)` → clickable chip messages (parser-friendly)
- `STARTER_CATEGORIES` — 14 zero-information starter categories

### `agent_lib/retrieve.py`

- `retrieve(state, index, top_k, dense, llm)` → `(ranked, usage, pool_size)`
  (competition path)
- `freeform_retrieve_with_pool(query, index, dense, top_k, pool_limit)` →
  `(ranked, pool, union_size)` (demo path)

### `agent_lib/mcp.py`

- Tools: `search_products(query, top_k)`, `product_details(asin)`,
  `clarify(question, context)`
- `build_mcp_context(...)` — assembles catalog + session context into an MCP
  prompt envelope
- JSON-RPC 2.0 over stdio (MCP hosts) or HTTP (`demo/server.py` `/mcp`)
