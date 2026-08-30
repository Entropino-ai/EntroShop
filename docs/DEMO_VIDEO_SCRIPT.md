# Demo Video Script — EntroShop

Style: NVIDIA tutorial / Houdini / Apple WWDC technical video.
Screen-recording driven, narrator explains design decisions, demo-first.
Duration target: 7.5–8 min. English only (repo language).

Timing notes: [mm:ss] markers are approximate. The demo footage should be
captured from the real app at `http://127.0.0.1:8090`; the MCP segment
uses a real `claude mcp add entroship -- ...` terminal session.

---

## Title: EntroShop — Converging 50,000 products to one answer in 1.59 turns

### [0:00] Open — the problem on screen

(Full-screen: a wall of product cards, 50,000 thumbnails, slow zoom in.
Text overlay: "50,000 products. One target. Ten turns.")

Every shopping chatbot promises to "understand" you. This one has a harder
job. The evaluator hides one product in a 50,000-item catalog, and a
simulated customer answers your questions through fixed templates. Ten
turns. That is the entire budget. So the question is not "can it chat," it
is "can it ask the right questions and stop."

We built EntroShop around that constraint. On the official public set, it
hits the hidden target 200 out of 200 sessions, in 1.59 turns on average.
The whole thing runs offline on the deterministic core, zero tokens. Here
is how it works, and what we learned building it.

### [1:10] Scene 1 — the simulator is a disclosure machine

(Screen: a product card expands, its fields highlight one by one.
Text overlay: "material words", "color: x", "feature strings",
"budget range".)

The first thing you notice when you read the simulator: it does not
paraphrase. The customer speaks the target product's own metadata,
verbatim. A material word like "leather" comes back as "leather." A
feature string comes back as the exact string.

That fact decides the architecture. Exact matching beats semantic matching
when the data is verbatim, so the retrieval core is a phrase trie over the
catalog, plus regexes for synthetic constraints like `color: x` and budget
ranges. Chinese and English both parse. The deterministic core costs zero
tokens; the LLM is an optional rerank that only runs when the tree cannot
decide.

### [2:20] Scene 2 — the arena: watch the pool converge

(Screen: the demo. Fish swim across the screen, get knocked out, fade
where they died. The funnel shows 50,000 → 28 → 3 → 1.)

This is the part we enjoyed building. The demo renders the candidate pool
as a swarm. Each product is a fish. Every turn, the agent asks the
highest-entropy question, the pool narrows, and fish die. The champion
gets the crown.

Under the visuals, each turn does four things: parse the message, update
session state, retrieve and rank, then decide. If the pool is small
enough, crown one final pick. Otherwise ask the facet with the most
remaining information: color, material, price, or category, with clickable
options.

The state machine matters more than it sounds. It routes Buying, Browsing,
Intent Override, and Boundary. "I changed my mind" erases only the
superseded preference, not the whole conversation. The boundary case,
where the customer has no preference, still converges in three turns at
rank one.

### [4:05] Scene 3 — the product-property tree: one chain per product

(Screen: a tree grows on the left, the final pick's breadcrumb highlights
on the right.)

Underneath the arena sits an n-ary tree over the catalog's category
properties. Coarse to fine: Clothing, Shoes & Jewelry → Men → Accessories
→ Belts. Every product maps to exactly one root-to-leaf chain. That sounds
abstract until you use it for two things.

First, retrieval. The tree is the default category route. One O(1) lookup
per keyword variant, no postings scan. When the tree pins the pool to a
small set, the LLM is skipped entirely, zero tokens. That is most turns.

Second, explainability. The final pick renders its chain as a breadcrumb.
You can see why the agent chose it. And the tree is what the MCP server
exposes.

### [5:15] Scene 4 — MCP: hand the tools to any agent

(Screen: terminal, `claude mcp add entroship -- ...` followed by a chat
window showing calls to search_products, clarify, tree_chain.)

The MCP server is a thin stdio layer over the same retrieval core. Four
tools: `search_products`, `product_details`, `clarify`, and `tree_chain`.
JSON-RPC 2.0, standard library only, no install step. Claude Desktop,
Cursor, VS Code Copilot, anything that speaks MCP can drive the copilot.

In the demo, an agent asks "search black leather belt under 30 dollars."
`search_products` returns ranked products. `clarify` asks the next
question: any material preference. `tree_chain` shows the product's path
in the tree. The whole loop runs on the same deterministic core the
competition path uses, so the MCP behavior matches the scored behavior.

### [6:40] Scene 5 — numbers, honestly

(Screen: benchmark table. BM25 baseline vs EntroShop. Hit rate, MRR, MTTC,
TechnicalScore. Then a token bar: baseline N/A, ours 0.)

The numbers on the public set:

Hit rate at 10: 100%. MRR: 0.723. Mean turns to conversion: 1.59, versus
9.81 for the BM25 baseline. TechnicalScore 0.9053, baseline 0.107.

The offline core uses zero tokens. Online rerank is equivalent, 0.905405
versus 0.905305. If judging runs without network, the fallback just
works. That was a requirement from day one.

### [7:30] Close — what we'd do next

(Screen: the arena again, a single fish crowned. Fade to the repo URL.)

A few things we want to try: richer MCP tools with streaming results,
multi-turn context so a host can carry a whole shopping conversation, and
more synthetic stress families beyond the current battery. The tree is the
part we keep coming back to, because it gives you the funnel for free.

EntroShop is open source. The repo is Entropino-ai/EntroShop. The docs
walk through the architecture chapter by chapter. Try it, break it, and
tell us where it falls over.

---

## Recording checklist

- Capture at 1080p, screen only, narrator off-camera or voice-over later.
- The arena segment: start a free-chat session with "black leather belt
  under 30 dollars", click chips until the crown appears, show the cart
  add.
- The MCP segment: show `claude mcp add entroship -- ...`, then one
  conversation where the agent calls search_products, clarify, and
  tree_chain in sequence.
- Benchmark table: freeze on the numbers for 3 seconds so they are
  readable.
- Keep total under 8 minutes; the sections can be trimmed independently.
