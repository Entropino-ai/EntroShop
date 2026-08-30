# Demo Video Script — EntroShop (3-minute version)

Style: WWDC / NVIDIA engineer walkthrough. Casual voice-over over screen
recording, like the person who wrote it is showing you. Target: **2:45 to
3:00** (hard cap; the official Devpost requirement is a public 3-minute
YouTube demo video). Narrator pace ≈150 words/min → ~450 words of VO.

Screen beats and VO are interleaved below. Cut the tree section first if
you run long; never cut the multi-turn session (rule 5.10).

---

## EntroShop — 50,000 products down to one

### [0:00] Open (VO ≈45 words)

(Product wall, slow zoom. Overlay: "50,000 products. 1 target. 10 turns.")

So the task: there's one hidden product in a 50,000-item catalog, a
simulated customer answers questions, you get ten turns. Chatting is easy.
Converging is the hard part. We hit 200 out of 200 on the public set,
1.59 turns average, zero tokens offline.

### [0:20] Scene 1 — the simulator is a text match (VO ≈70 words)

(Product card fields highlight: material, color: x, features, budget.)

First thing you learn from the simulator: it doesn't paraphrase. The
customer repeats the product's own metadata, word for word. "Leather"
comes back as "leather." So exact match wins. Phrase trie over the whole
catalog, regexes for `color: x` and budget, Chinese and English both work.
The LLM is only an optional rerank when the tree can't decide.

### [0:55] Scene 2 — watch the pool die (VO ≈110 words)

(Demo: free chat "black leather belt under 30 dollars". Fish swim, get
knocked out. Funnel 50k → 28 → 3 → 1. Chips clicked, crown appears, cart
add.)

Here's the fun part. Every product is a fish. Each turn we ask the
question that splits the pool the most, fish die, the winner gets a crown.
Each turn is parse, update state, retrieve and rank, decide. Pool small
enough, crown it. Otherwise ask color, material, price, or category, with
clickable options. Watch it: black leather belt under thirty, it narrows
to a handful, then the champion. This is the multi-turn session end to
end, one of the required deliverables.

### [1:45] Scene 3 — the tree gives you the funnel for free (VO ≈45 words)

(Tree grows on the left, final breadcrumb highlights on the right.)

Underneath is an n-ary tree of category properties. Every product maps to
one chain, coarse to fine. Two uses. Category lookup is O(1), and when the
tree pins the pool small we skip the LLM, zero tokens, which is most
turns. And the final pick shows its chain as a breadcrumb, so you can see
why.

### [2:15] Scene 4 — MCP: drive it from anywhere (VO ≈80 words)

(Terminal: `claude mcp add entroship -- ...`. Chat window calling
search_products, clarify, tree_chain.)

We also made it an MCP server. Four tools: search_products,
product_details, clarify, tree_chain. JSON-RPC 2.0, stdlib only, no
install. Claude Desktop, Cursor, VS Code, anything that speaks MCP can
drive it. Ask "search black leather belt under 30 dollars," it returns
ranked products, clarify asks the next question, tree_chain shows where it
sits. Same deterministic core as the scored path, so MCP behavior matches
the competition behavior.

### [2:50] The numbers + close (VO ≈40 words)

(Benchmark table, hold 3 seconds. Fade to repo URL.)

Hit rate 100%. MRR 0.723. MTTC 1.59 vs 9.81 baseline. TechnicalScore
0.9053 vs 0.107. Offline zero tokens, network-off fallback just works.
Repo: Entropino-ai/EntroShop.

---

## Recording checklist

- 1080p screen capture, casual voice-over, English.
- The arena segment IS the required multi-turn session: start free chat
  "black leather belt under 30 dollars", click chips until the crown,
  show the cart add. That alone satisfies rule 5.10.
- MCP segment: real `claude mcp add entroship -- ...`, then one
  conversation calling search_products, clarify, tree_chain.
- Benchmark table freezes 3 seconds so the numbers are readable.
- Hard cap 3:00. If over: cut Scene 3 (tree) first; keep the MCP beat and
  the multi-turn session.
