# 02 · Architecture

## Design principle

Shopping is treated as an **information-elicitation problem**: every turn the
agent picks the question with the highest expected information gain, narrows
the candidate pool, and converges to a single answer — like rendering a
scene, one sample at a time. Because the competition evaluator is a
deterministic simulator whose disclosure policy is fixed and readable, the
information structure of the task is explicit and therefore *engineerable*.

## Pipeline

```
user message
   │
   ▼
[message understanding]   template parse + phrase trie + synthetic regexes
   │
   ▼
[state machine]           intent routing (buying/browsing/override/boundary),
   │                      slot accumulation, recency decay, ask planner
   ▼
[multi-route retrieval]   exact conjunction → coarse-category exact match
   │                      → synthetic attributes → title → rating-style
   │                      → popularity → dense (TF-IDF / MiniLM) → LLM rerank
   ▼
[guidance & convergence]  entropy facet selection → chips → no-progress /
   │                      pool threshold / turn-9 clamp
   ▼
{message, ask_attribute, recommendations, usage}   →  👑 final pick
```

## The three key insights

1. **The simulator discloses constraints as verbatim catalog strings.**
   The intent card is generated from the target product's own metadata
   (material words, `color: x`, the first few feature/detail strings), so
   exact-phrase conjunction over an inverted index is the dominant retrieval
   signal. `ask_attribute="other"` returns two undisclosed constraints per
   turn, so the pool shrinks fast.

2. **The disclosed coarse category is the target's own last-two category
   parts, verbatim.** Replacing loose token intersection with an exact
   coarse-key match collapsed the one historically ambiguous pool from 459
   candidates to 9 and lifted Hit Rate 0.995 → **1.000**.

3. **Clarification is information elicitation.** Each turn asks the
   highest-entropy unconstrained facet (color / material / price / category)
   with pool-derived options, decays stale slots (latest batch full weight,
   older 0.3×), detects no-progress turns, and enforces a hard 10-turn budget
   with a forced single final pick.

## Routes and weights

| Route | Signal | Weight | Role |
|---|---|---|---|
| Exact-phrase conjunction | disclosed phrase ∈ product phrase set | 100 each | dominant; cascade relaxes to the largest non-empty subset |
| Coarse-category exact match | last-two category parts = disclosed coarse key | 60 | hard filter when pool > 10; target always inside |
| Synthetic attributes | material / color / budget | 20–50 | recency-weighted |
| Title overlap | constraint/category tokens ∩ title | 16/3 | strong-intent boost |
| Rating-style consistency | profile.rating_style ↔ rating | 20 | 75% aligned |
| Popularity prior | log(1+rating_number) | 8 | real-purchase targets skew popular |
| Dense route | TF-IDF / MiniLM cosine | 30–35 | large pools; offline |
| LLM rerank | optional DeepSeek top-15 | — | failure-safe |

## Convergence policy

Convergence fires when any of the following holds:

- explicit user convergence (`that's all` / `converge` …),
- candidate pool ≤ 10,
- two consecutive no-progress turns,
- guidance-round budget exhausted (4 guided turns),
- hard **turn-9 clamp** — every session finishes inside the competition's
  10-turn budget.

At convergence one champion is crowned from the exact matches.

## Product-property tree

Alongside the retrieval indexes, the catalog is organized as an **n-ary
property tree** (`agent_lib/tree.py`): every fork node is one product
property (a category segment), children branch by containment, and each
level is finer-grained than its parent:

```
root
 └─ Clothing, Shoes & Jewelry      (coarsest)
     ├─ Women
     │   ├─ Shoes
     │   │   ├─ Boots & Booties    (finer)
     │   │   │   └─ products: [B0…, B1…]   ← concrete product mapping
     │   │   └─ Sneakers
     └─ Men
```

A mapping lives on the tree: each node's `products` list maps that property
to the concrete catalog products it covers, and **every product corresponds
to exactly one unique chain** — the root-to-leaf sequence of its category
properties (guaranteed because `categories` is a fixed ordered list). The
tree backs the demo's "Property tree chain" panel (the final pick rendered
as a coarse-to-fine breadcrumb with the leaf's product count), the MCP
`tree_chain` tool, and `common_prefix` which exposes the shared disclosure
prefix of two products — the information-theoretic bound behind the
family-ambiguous corner cases.

### Tree-first category matching

The tree is also the **default category route** in retrieval. A
`value_index` maps each normalized property token to its nodes (root
breadcrumb segments like "Clothing, Shoes & Jewelry" are kept in the
structure but excluded from the index, so a keyword like "shoes" hits the
real `Shoes` segment instead of the whole catalog). `subtree_for_keyword`
resolves a keyword to the subtree products with one O(1) lookup per plural
variant — no token-posting scans. Both `freeform_retrieve*` (pool building)
and `hard_pool` (conjunctive narrowing) use it first and fall back to token
postings only for keywords the tree does not match. Result: category
candidates are exact subtree members (token-substring coincidences across
segments are dropped), so pools are equal-or-smaller than the token route,
and tree-matched keywords still receive the category scoring bonus.

**Performance.** Retrieval is embedded-hybrid and tree-gated: the category
route (tree, else token postings) plus material/color slots build the pool
first; the dense route only scores *within that pool* (never the 50k
catalog) and only when the pool is large; and once the tree pins the pool
to ≤ 300 exact members, the LLM rerank is skipped entirely — most turns
finish in well under a second with **zero tokens**. Keyword matching uses
pre-tokenized `corpus_tokens` sets instead of per-candidate full-text
regex. The convergence gate judges on the exact hard pool (not the
free-form top-200 sample), so tree-resolved queries never trigger a slow
network call.

**Depth-weighted scoring (binary-search thinking).** The tree is a decision
tree: each level splits the candidate space roughly in half, so a match on a
chain segment at depth `d` pins down a subset of about
`catalog / 2**d` products. `depth_weighted_bonus` therefore credits a match
with `log2(catalog_size / subtree_size)` — deeper (smaller) subtrees carry
exponentially more bits, exactly like binary search where each comparison
halves the remaining space. Because the gain is measured on subtree size
rather than raw depth, two products reaching the same node earn the same
contribution regardless of breadcrumb length above it. The term is added
to both the competition scorer (disclosed constraint words matching deep
chain segments, e.g. "leather" inside "Leather Belts") and the free-chat
scorer, resolving near-ties inside narrow pools that previously fell just
outside the top-10.

## Free chat (demo)

The demo's *Free chat* mode runs the same agent but against the live chat
loop (`demo/server.py`): every user message is parsed by `freeform_query`,
accumulated into a `GuideState`, ranked by `freeform_retrieve_with_pool`, and
guided with facet chips until convergence — with the MiroFish-style arena
visualization and chain-of-thought panel rendered live.

## Determinism and failure safety

- The offline core is fully deterministic: **0 LLM tokens**, in-memory
  indexes, no external vector DB.
- The dense route (TF-IDF) is pure stdlib; MiniLM is cached to
  `data/models/minilm_embeddings.npz` and optional.
- The LLM reranker is optional and failure-safe: startup ping probe,
  per-request timeout, truncated-output-tolerant parsing, and automatic
  disable after consecutive failures.
- **Tree when possible, LLM only when the tree is not enough**: the LLM
  rerank is gated on the product-property tree. When the tree alone pins
  the candidates (every category keyword resolves to a subtree and their
  conjunctive intersection with the pool is small), the deterministic
  ranking is kept and zero tokens are spent. Only when the tree does not
  converge (broad or unresolvable category words, large pools) does the
  optional LLM engage — so most sessions cost nothing even with a key
  configured.
