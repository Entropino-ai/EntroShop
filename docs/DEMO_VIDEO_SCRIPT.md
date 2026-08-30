# Demo Video Script — EntroShop

Style: WWDC / NVIDIA engineer walkthrough. Screen-recording with casual
voice-over, like the person who wrote the code is showing it to you.
Duration target: 5 min. English only.

---

## EntroShop — 50,000 products down to one, in 1.59 turns

### Open (0:00)

(Product wall, slow zoom. Overlay: "50,000 products. 1 target. 10 turns.")

So the task is: there's a hidden product in a 50,000 item catalog, a
simulated customer answers your questions, and you get ten turns. That's
it. Chatting is easy. Converging is the hard part.

We got 200 out of 200 on the public set, 1.59 turns average, zero tokens
offline. Let me show you how.

### The simulator is basically a text match (0:40)

(Product card fields highlight: material, color: x, features, budget.)

First thing you learn reading the simulator: it doesn't paraphrase. The
customer repeats the product's own metadata, word for word. "Leather"
comes back as "leather."

So exact match wins. We built a phrase trie over the whole catalog, plus
regexes for `color: x` and budget. Chinese and English both work. The LLM
is just an optional rerank that runs when the tree can't decide. Offline,
zero tokens.

### Watch the pool die (1:30)

(Demo: fish swimming, getting knocked out. Funnel 50k → 28 → 3 → 1.)

This is the fun part. Every product is a fish. Each turn we ask the
question that splits the pool the most, fish die, and the winner gets a
crown.

Each turn is: parse, update state, retrieve and rank, decide. Pool small
enough? Crown it. Otherwise ask color, material, price, or category, with
clickable options.

The state machine handles the weird cases. "I changed my mind" only erases
the superseded preference. The boundary case, where the customer has no
preference at all, still lands rank one in three turns.

### The tree gives you the funnel for free (3:00)

(Tree grows, final breadcrumb highlights.)

Underneath is an n-ary tree of category properties, coarse to fine. Every
product maps to one chain. Two uses.

One, retrieval. Category lookup is O(1) per keyword variant. When the tree
pins the pool small, we skip the LLM entirely. That's most turns.

Two, explainability. The final pick shows its chain as a breadcrumb, so
you can see why. And it's what the MCP server exposes.

### And you can drive it from anywhere (3:40)

(Terminal: claude mcp add entroship. Chat window calling tools.)

We also made it an MCP server. Four tools: search_products,
product_details, clarify, tree_chain. JSON-RPC 2.0, stdlib only, no
install. Claude Desktop, Cursor, VS Code, anything that speaks MCP can
drive it.

So you can ask, "search black leather belt under 30 dollars," it returns
ranked products, clarify asks the next question, tree_chain shows where it
sits in the tree. Same deterministic core as the competition path, so the
MCP behavior is the scored behavior.

### The numbers (4:30)

(Benchmark table, hold 3 seconds.)

Hit rate at 10: 100%. MRR 0.723. MTTC 1.59 vs 9.81 baseline. TechnicalScore
0.9053 vs 0.107. Offline zero tokens, online equivalent, network-off
fallback just works.

Repo: Entropino-ai/EntroShop. Try it, break it, tell us where.

---

## Recording checklist

- 1080p screen capture, casual voice-over.
- Arena segment: free chat "black leather belt under 30 dollars", click
  chips, show the crown and the cart.
- MCP segment: real `claude mcp add entroship -- ...`, then one
  conversation calling search_products, clarify, tree_chain in sequence.
- Benchmark table: freeze 3 seconds.
- Keep it under 5 minutes. Cut the tree section if you need to.
