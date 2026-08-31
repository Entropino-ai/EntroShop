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
  0.9053 TechnicalScore.
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

## Guidance, coordination & delivery support (no code contributions)

### cray-xiaocheng

- Participated in all offline team discussions and project meetings
  throughout the hackathon.
- Took part in brainstorming on project positioning, target users, core
  needs, and feature scenarios; contributed a short-video user-and-creator
  perspective to product design and feature refinement.
- Helped shape the overall direction: guiding principles, staged goals, task
  priorities, and team division, and helped the team converge on a common
  plan across competing proposals.
- Joined the feasibility analysis: demo implementation difficulty, time
  cost, and presentation impact; helped separate must-have core features from
  optional extensions; gave opinions on risks, schedule, and resources.
- Provided financial support for development, testing, tools, and related
  resources.
- Took meeting notes covering key discussions, confirmed decisions, todos,
  and important deadlines.

### Siuuuuean

- Tracked team progress during development and provided support and
  coordination for team members.
- Participated in demo testing and usage feedback, and proposed revisions
  from the angles of product interaction, user experience, and real-world
  usage scenarios.
- In the final stage, contributed to the report deck, project story line,
  demo highlights, and submission materials; helped unify the project's
  expression and presentation direction; supported the team in completing
  the demo, the submission package, and the overall delivery.

Implementation work was carried by SakuraEntropia, YH122432, and
残酷な天使; cray-xiaocheng and Siuuuuean contributed guidance,
coordination, funding, testing feedback, and delivery support.
