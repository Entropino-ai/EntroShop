# EntroShop: Tree-Guided Conversational Shopping Agent

**Track:** TikTok TechJam 2026, Track 4: Shopping Copilot (AI Conversational Search and Recommendations)

**Elevator pitch:** EntroShop: tree-guided shopping copilot that narrows 50,000 products to the one you meant in 1.6 turns, the way binary search narrows a sorted array.

## About the project

**What inspired us.** The track hands you a 50,000-product catalog and a customer who knows what they want but cannot name it. Keyword search never converges, and a chatbot that just chats never finishes. The problem is a clean information game: each turn the customer leaks a bit of the hidden target, and the agent picks the question. You win by asking the questions that cut the candidate pool fastest, then stopping at the right moment.

**What we tried first, and abandoned.** Our first build was LLM-heavy: an LLM reranker over retrieval, entropy-guided clarification, and an RLHF-style reward loop around the ask policy. It worked, and it taught us what did not matter. The evaluator is a deterministic simulator whose constraints arrive verbatim from the target product's metadata, so the reward is exact and readable. There is no preference model to learn, so RLHF added nothing to the score. The LLM rerank reordered lists but changed no session outcome on the public set (TechnicalScore +0.000036). The entropy part survived. The LLM and RLHF parts did not.

**What we built instead.** A tree-guided retriever. Every product's category path becomes one chain in an n-ary property tree: parents contain their children, deeper levels are progressively finer properties, and each product owns exactly one chain. Two products that share a chain are information-equivalent at the category level. Clarification became a walk down this tree in the spirit of binary search: each question should cut the remaining pool by the largest factor, and a match deeper in the tree is more discriminative, so deeper matches carry more weight in scoring. The deterministic ranking gets the tree first; the LLM fires only when the tree alone has not converged.

Let $P_t$ be the candidate pool at turn $t$. The ideal question maximizes the expected cut:

$$ a^* = \arg\max_a \ \mathbb{E}_v\!\left[\frac{|P_t \setminus P_{a=v}|}{|P_t|}\right] $$

The tree makes this cheap: a disclosed category chain pins a subtree, so one exact chain match can cut tens of thousands of products at once. In binary-search terms, a question worth asking roughly halves the pool. On the official public set, exact-phrase conjunction pins a single product for 66.5% of sessions and ten or fewer for 79%. The official score,

$$ \text{TechnicalScore} = 0.50 \cdot \text{Hit@10} + 0.30 \cdot \text{MRR} + 0.20 \cdot \text{Efficiency}, $$

lands at 0.9055 against the weak BM25 baseline's 0.107, with Hit@10 = 1.000 (200/200), MRR = 0.724, and MTTC = 1.59 turns. We also replay the agent against a 300-session synthetic stress set with 40% deliberately generic products; every miss there falls in the family-ambiguous corner, the same information bound the competition's disclosure policy cannot resolve.

**Challenges we hit.** The family-ambiguous corner: some targets share all four disclosed constraints with hundreds of near-identical listings, so no question can separate them. Exact coarse-category identity collapsed the historically ambiguous pool from 459 candidates to 9 and moved Hit@10 from 0.995 to 1.000. The second challenge was resisting the LLM: measured reranking costs about 245k tokens per 200-session run and changes nothing on the public set, so we kept it as a gate for pools the tree cannot converge, not as the default. The third was not overfitting the public 200: the deployed policy is the argmax of an offline search over the simulator, and its winning mechanisms follow from the disclosure rules rather than from the 200 sessions.

**What we learned.** Readable reward beats scale. When the objective is exact, a deterministic tree walk plus a few exact-match insights outperforms a pipeline of LLM reranking and RLHF by construction: zero tokens, 0.4 s per session, and a score that cannot drift because the core is a pure function of the catalog.

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
  -> multi-route retrieval (product-property tree first: exact chain matches
     and depth-weighted subtree scoring; then exact-phrase conjunction with
     cascade relaxation, synthetic attribute filters, title overlap,
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
- Demo video: (3-minute YouTube walkthrough; script ready at docs/DEMO_VIDEO_SCRIPT.md, URL to be added after recording)
- Data: Amazon Reviews 2023, McAuley Lab, UCSD; see DATA_ATTRIBUTION.md in the repo
