# EntroShop: Entropy-Guided Conversational Shopping Agent

**Track:** TikTok TechJam 2026, Track 4: Shopping Copilot (AI Conversational Search and Recommendations)

**One-liner:** A shopping copilot that finds the customer's hidden target product in 1.6 turns on average: an LLM-reranked online mode for the best efficiency, with a zero-token offline fallback.

## What it does

EntroShop talks to a customer across multiple turns to find the one hidden product they have in mind, out of a 50,000-product catalog. It recommends products on every turn instead of only asking questions, so a session ends the moment the target shows up. On the official public development set (200 sessions) it scores Hit Rate@10 = 1.000, MRR = 0.724, and MTTC = 1.59 turns, raising the TechnicalScore from the BM25 baseline's 0.107 to 0.9055.

## The insight

The official evaluator is a deterministic simulator. The customer's constraints come verbatim from the target product's metadata, and roughly 76% of disclosed constraints are exact substrings of its feature and detail text. The challenge is an information-gathering game with measurable structure, and four decisions follow from that:

1. **Exact-phrase conjunction first.** Joining verbatim constraint phrases narrows the pool to a single product for 66.5% of sessions, and to ten or fewer for 79%. Lexical overlap is the signal the simulator is aligned with, so we do not spend compute on semantic search where it adds nothing.
2. **Ask "other", not one attribute at a time.** Some attributes get a "no preference" answer, but an "other" question returns the two most useful undisclosed constraints. A grid search over question policies confirmed that asking "other" to the end beats probing attribute by attribute.
3. **Model scenario evolution, not just slots.** Buying, Browsing, Intent Override, and Boundary sessions each get their own route. An intent override erases only the opening preference and keeps everything learned by asking; a boundary reply costs one extra question and nothing else.
4. **Recommended online, safe offline.** The recommended configuration reranks the top-20 with a cheap OpenAI-compatible LLM as the product-mode ranking and a hedge against paraphrase drift. Without a key, or when the network is off, the deterministic standard-library core still runs and hits every session; measured on the public set the two modes are equivalent (TechnicalScore 0.905543 vs 0.905507), and any rerank failure falls back silently.

## Architecture

```
user message
  -> message understanding (template parser + phrase trie + synthetic constraint regex)
  -> dynamic state machine (slot accumulation, intent routing, question planner)
  -> multi-route retrieval (exact-phrase conjunction with cascade relaxation,
     category intersection, synthetic attribute filters, title overlap,
     TF-IDF dense route for large pools)
  -> weighted ranking with popularity prior
  -> optional LLM rerank of the top-20
  -> {message, ask_attribute, recommendations, usage}
```

The same agent is exposed as an MCP server (tools: `search_products`, `product_details`, `clarify`) and as a local demo UI with a live state inspector, so the whole pipeline can be watched in one browser tab.

## Results (official evaluator, public 200 sessions)

| Metric | BM25 baseline | EntroShop |
|---|---|---|
| Hit Rate@10 | 0.125 | 1.000 |
| MRR | 0.068 | 0.724 |
| MTTC (turns) | 9.81 | 1.59 |
| Efficiency | 0.119 | 0.9415 |
| TechnicalScore | 0.107 | 0.9055 (0.905543 online / 0.905507 offline) |

## Known limitations

- Sessions whose target shares all four disclosed constraints with hundreds of products cannot be separated by the disclosed information alone (1/200 on the public set).
- The message parser leans on the simulator's deterministic templates. The trie and TF-IDF routes buffer against paraphrase, but not against the organizer rewriting the constraint strings themselves.
- Weights are tuned on the public set, so the private split may shift them slightly.

## Tech stack

- Python 3.10+ (core engine uses the standard library only)
- numpy, scikit-learn (TF-IDF dense route)
- sentence-transformers / MiniLM-L6-v2 (optional dense embeddings for the demo chat)
- OpenAI-compatible LLM API (optional reranker, offline by default)
- MCP: JSON-RPC 2.0 over stdio and HTTP
- Frontend: vanilla JavaScript single-page demo, no build step

## Links

- Code: https://github.com/Entropino-ai/EntroShop
- Demo video: (to be added)
- Data: Amazon Reviews 2023, McAuley Lab, UCSD; see DATA_ATTRIBUTION.md in the repo
