# Team Contributions

TikTok TechJam 2026 · Track 4 Shopping Copilot · EntroShop Team
GitHub org: [Entropino-ai](https://github.com/Entropino-ai) · Repo:
[Entropino-ai/EntroShop](https://github.com/Entropino-ai/EntroShop)

The contribution record below is grounded in the repository's git history.
Non-code work is listed where it maps to specific deliverables.

## Engineering & code (git history)

### SakuraEntropia — project lead

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
- Policy optimization (RL-style rollout search) and the chapter-per-file
  documentation restructure.
- Project write-ups: `docs/PROJECT.md` (mini-paper), `docs/DEMO_SESSION.md`
  (demonstrated multi-turn session), `docs/STRESS_TEST.md`, `DEVPOST.md`
  (written description + tech stack).

### YH122432

- Project tooling and `.venv` dev-environment setup.
- Guide-chip selection fix: stopped `budget` leaking as a keyword; added chip
  feedback.

### Xxp20080101

- Repository hygiene: ignore `.venv`, removed a stray catalog archive.

## Non-code & delivery (to be confirmed by the team)

- cray-xiaocheng: (to be filled — e.g. registration logistics, testing,
  documentation, video)
- Siuuuuean: (to be filled — e.g. registration logistics, testing,
  documentation, video)

> The two members above have no commits in the current repository history;
> their non-code contributions should be listed here before submission, since
> the track rules require a team-contributions record.
