# Team Contributions

TikTok TechJam 2026 · Track 4 Shopping Copilot · EntroShop Team
GitHub org: [Entropino-ai](https://github.com/Entropino-ai) · Repo:
[Entropino-ai/EntroShop](https://github.com/Entropino-ai/EntroShop)

The contribution record below follows the team's own authorship record.
Note on commit metadata: teammate code was frequently committed under the
lead's GitHub account, so git authors alone undercount teammate contributions.
Non-code work is listed where it maps to specific deliverables.

## Engineering & code (git history)

### SakuraEntropia — project lead (Devpost: faputa)

- Core agent design and implementation: message understanding (template
  parser, catalog phrase trie, synthetic constraint regex), intent routing
  state machine (Buying / Browsing / Intent Override / Boundary), multi-route
  retrieval and ranking (exact-phrase conjunction, exact coarse-category
  match, dense routes, popularity prior), entropy-guided clarification, hard
  10-turn clamp. Led the public-set score from the BM25 baseline (0.107) to
  0.9055 TechnicalScore.
- Official submission package (required layout) with the README disclosures
  (network policy, cost, latency, token usage).
- Optional LLM rerank (OpenAI-compatible, DeepSeek measured) with liveness
  probe, failure handling, and silent fallback.
- Demo UI: standalone chat, MiroFish-style swarm view, chain-of-thought panel,
  guide chips.
- MCP server (`search_products`, `product_details`, `clarify`).
- Retrieval engine v2: n-ary product-property tree with unique per-product
  chains, tree-first category matching in retrieval and hard-pool filtering,
  and a tree-vs-LLM gate (tree when possible, LLM only when the tree is not
  enough). Most demo turns now finish under 0.5 s with zero tokens.
- Policy optimization (RL-style rollout search) and the chapter-per-file
  documentation restructure.
- Demo productization: unified convergence UI, real shopping cart
  (2-decimal pricing, integer-cent totals), auto-start sessions, and guided
  next-step hints in every question.
- Project write-ups: `docs/PROJECT.md` (mini-paper), `docs/DEMO_SESSION.md`
  (demonstrated multi-turn session), `docs/STRESS_TEST.md`, `DEVPOST.md`
  (written description + tech stack); refreshed all scores from fresh
  official-evaluator and stress runs.

### hsen (GitHub: YH122432)

- Project tooling and `.venv` dev-environment setup.
- Guide-chip selection fix: stopped `budget` leaking as a keyword; added chip
  feedback.
- Recorded the 3-minute YouTube demo video for the Devpost submission.

### 残酷な天使 (GitHub: Xxp20080101)

- Proposed the tree-structure optimization and depth weighting behind the
  retrieval engine v2 (n-ary product-property tree, tree-first matching,
  depth-weighted scoring); implemented together with the lead, committed
  under the lead's account.
- Repository hygiene: ignore `.venv`, removed a stray catalog archive.

## Team members without build-window contributions

- cray-xiaocheng: registered and listed as a team member; contributed
  early-stage suggestions on project direction before the build window;
  unavailable during the build window due to academic commitments, no code
  contributions.
- Siuuuuean: registered and listed as a team member; unavailable during
  the build window due to academic commitments, no code or delivery
  contributions.

The three members above (SakuraEntropia, YH122432, Xxp20080101) carried the
implementation and delivery work.
