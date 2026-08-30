# EntroShop — Project Story

> Entropy-guided conversational shopping: find the one hidden product in a
> 50,000-item catalog, within 10 turns.

---

## Inspiration

The prompt was "build a conversational shopping agent," but the real
problem turned out to be more interesting. The evaluator is a
**deterministic simulator**: every session hides a target product, and the
simulated customer discloses constraints turn by turn through fixed
templates — material words, `color: x`, feature strings, a budget range.

That single fact reframed the whole task. Shopping here isn't a language
problem, it's an **information-elicitation problem**. The customer's words
are the target product's own metadata, spoken verbatim. So the right
questions became: how do we extract the most information per turn, and when
do we stop asking?

We drew on classic ideas and applied them to a concrete, measurable task:
exact matching where the data is verbatim, entropy as a question-selection
principle (like 20 Questions played optimally), and convergence as a
bounded-resource optimization instead of a vague "chat" goal.

## What it does

EntroShop talks to a shopper and finds the one product they have in mind,
out of 50,000 — in 1.59 turns on average, with a perfect 100% hit rate on
the official public set.

Every turn the agent:

1. **Parses the message** — fixed templates (authoritative), a character
   trie over all catalog phrases (rescues strings broken by `; `), and
   regexes for synthetic constraints like `color: x` and budget ranges.
2. **Updates session state** — routes Buying / Browsing / Intent Override /
   Boundary, accumulates slots, handles "I changed my mind" correctly.
3. **Retrieves and ranks** — exact-phrase conjunction (dominant), exact
   coarse-category match, material/color/budget slots, title overlap,
   rating-style consistency, popularity, plus an optional dense route.
4. **Decides** — if the pool is small, crown one final pick; otherwise ask
   the highest-entropy facet with clickable options.

The demo renders the narrowing pool as a **MiroFish-style adversarial
arena**: candidate products swim as fish, get knocked out, and the champion
is crowned. Alongside it: the reasoning chain, the narrowing funnel, the
product-property-tree chain of the final pick, and a real shopping cart
(localStorage-backed, auto-started session, explicit example steps).

## How we built it

The system is a staged pipeline:

```
message → parse (templates + trie + regex)
        → state machine (buying / browsing / override / boundary)
        → multi-route retrieval
        → entropy-guided clarification
        → single final pick 👑
```

**Retrieval** is a hybrid scorer: exact-phrase conjunction (100 per hit),
exact coarse-category match (60), material/color slots (20–50), title
overlap, rating-style consistency (20), popularity (8), and an optional
dense route (TF-IDF / MiniLM). Cascade relaxation guarantees a non-empty
pool when constraints over-constrain.

**The product-property tree** organizes the catalog as an n-ary tree where
every node is a category property and deeper levels are finer. Each product
maps to exactly one unique root-to-leaf chain. The tree is the *default*
category route in retrieval (O(1) index lookups, subtree candidates), and
it powers a **tree-vs-LLM gate**: when the tree pins the pool to a small
set, we spend zero tokens; only when the tree is not enough does the
optional DeepSeek reranker engage — failure-safe, offline by default.

**Policy search** (`analysis/rl_policy_search.py`) formalizes "which
attribute to ask / when to converge" as a policy, the simulator as the
environment, and score as the reward, then runs offline rollouts over the
policy grid. It confirmed our deployed choices are the argmax.

**The demo** is a single-page app: MiroFish arena, chain-of-thought panel,
funnel + consensus signals, property-tree breadcrumb, and a working cart.
A session auto-starts on load, and example mode explicitly shows the
customer's next utterance before each step.

## Challenges we ran into

**Template noise poisoning the query.** The simulator's opening line is
"A key requirement is: nylon." — the words *key* and *requirement* got
parsed as category keywords, polluting the hard pool and breaking
convergence on otherwise easy sessions. The fix: stopword template fillers,
and make sure "no preference" answers never add phantom constraints.

**The ambiguous pool.** One session kept landing in a 459-candidate pool
with the target ranked ~27–141. The structural fix: the disclosed coarse
category is the target's own last-two category parts verbatim, so an exact
coarse-key match collapsed the pool to 9 candidates including the target.
That single change moved Hit Rate from 0.995 to 1.000 and improved MRR,
MTTC, and score together — evidence of generality, not overfitting.

**Floating-point prices.** `$48.349999999999994` in the cart taught us to
format to two decimals and accumulate totals in integer cents.

**A stale overlay shadowing our code.** Our dev copy of the organizer kit
had an old copy of our own `agent_lib/` on `PYTHONPATH`, silently masking
new modules. Root-causing "ModuleNotFoundError for a file that exists" was
a reminder that environment hygiene matters as much as the algorithm.

**Convergence without dead ends.** Early versions could loop on
zero-information queries or converge on huge pools. We added no-progress
detection, zero-info starter categories, recency-decayed keywords, and a
hard turn-9 clamp — verified by a 13-case convergence battery and a 46-check
smoke suite on every change.

## Accomplishments that we're proud of

- **1.000 Hit Rate on the public set** (200/200), MTTC 1.59 vs the
  baseline's 9.81, TechnicalScore 0.9055 vs 0.107 — fully offline, **0
  tokens**, in-memory, no external vector DB.
- **Engineering around the task's information structure**: exact matching
  for verbatim constraints, entropy for questioning, a tree for catalog
  identity, and a hard budget for convergence.
- **The n-ary product-property tree** — one unique chain per product,
  tree-first retrieval, and a tree-vs-LLM gate that keeps most sessions at
  zero token cost even with an API key configured.
- **Offline RL-style policy search** that proved our deployed policy is the
  argmax — and saved us from "improving" something already optimal.
- **A product-grade demo**: MiroFish arena, reasoning chain, real shopping
  cart, MCP server, bilingual input, and one-command reproducibility.

## What we learned

**Exact beats semantic — when the data is verbatim.** About 76% of
disclosed constraints are exact substrings of the target's text. Semantic
search became a fallback, not the main event. Read the task's information
structure before reaching for the biggest model.

**Entropy is a practical question policy.** For each facet we measure how
evenly the candidate pool is split and ask the most balanced one:

$$H(\text{facet}) = -\sum_{v} p_v \log_2 p_v$$

Asking the highest-entropy facet cuts the pool roughly in half per turn.
Combined with a convergence budget — pool ≤ 10, two no-progress turns, or
the turn-9 clamp — every session ends with one recommendation inside the
10-turn limit.

**The score formula rewards early, ranked hits.**

$$\text{TechnicalScore} = 0.50 \cdot \text{HitRate@10} + 0.30 \cdot \text{MRR} + 0.20 \cdot \text{Efficiency}$$

with $\text{Efficiency} = \operatorname{clip}\big((11-\text{MTTC})/10,\ 0,\ 1\big)$.
This pushed us to recommend every turn, not just at the end.

**Information theory sets a hard floor.** Some products share *all*
disclosed constraints with hundreds of near-identical listings; no agent
can separate them, and the worst case is a coin flip. Recognizing this
bound stopped us from overfitting to impossible cases.

## What's next for EntroShop

- **Negation and exclusion constraints** — "not black," "no leather" is
  currently added rather than excluded; a proper negation slot would make
  the agent reject rather than rank down.
- **Richer facets** — size, brand, and fit are in the data but not yet
  first-class facets; adding them extends the entropy-guided questioning.
- **Paraphrase robustness** — the trie + dense routes buffer paraphrase,
  but we want the template parser to degrade even more gracefully.
- **Real personalization** — the aggregate `user_profile` is used lightly
  today; preference-tag conditioning on ranking is a natural next step.
- **RLHF-style preference tuning for the LLM reranker** — the core stays
  deterministic, but a preference-tuned rerank could improve ambiguous,
  role-reversed queries ("gift FOR dad") at low token cost.
- **MCP ecosystem polish** — richer tools, multi-turn context, and
  streaming results so any MCP host can drive EntroShop's retrieval.
- **Private-split hardening** — more synthetic stress families, longer
  sessions, and adversarial disclosure patterns before the 800-session
  private set runs.

---

*TikTok TechJam 2026 · Track 4 — Shopping Copilot: AI Conversational Search
& Recommendations. Code: [Entropino-ai/EntroShop](https://github.com/Entropino-ai/EntroShop)*
