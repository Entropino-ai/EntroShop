# Demo Video Script — EntroShop (3-minute version)

Style: Houdini Foundations walkthrough. Screen recording, casual
step-by-step narration, the person who built it walking you through the
network the way a Houdini tutorial walks you through a node graph.
Target: **2:45 to 3:00** (official Devpost cap: a public 3-minute YouTube
demo video). Narrator pace ≈150 words/min → ~450 words of VO.

Screen beats and VO are interleaved. If you run long, cut the tree
section first; keep the multi-turn session (rule 5.10) and the MCP beat.

---

## EntroShop — let's converge this

### [0:00] Open (VO ≈45 words)

(Product wall, slow zoom. Overlay: "50,000 products. 1 target. 10 turns.")

So here's the setup. Somewhere in a 50,000-item catalog there's one
product we have to find. A simulated customer answers our questions, and
we get ten turns to do it. So we built a little agent that asks the right
questions and converges. 200 out of 200 on the public set, 1.59 turns
average, zero tokens offline. Let's go ahead and walk through it.

### [0:20] Scene 1 — the simulator hands you the data (VO ≈75 words)

(Product card fields highlight one by one: material, color: x, features,
budget.)

First, let's talk about what the simulator gives us. It doesn't paraphrase
anything. The customer literally repeats the product's own metadata, word
for word. You ask about material, you get "leather" back, exactly as
written. So what we're doing here is exact matching. We built a phrase
trie over the whole catalog, plus a few regexes for things like `color: x`
and budget. Chinese works, English works. There's an optional LLM rerank,
but it only kicks in when the tree can't decide. Offline, we're at zero
tokens.

### [0:55] Scene 2 — let's watch the pool die (VO ≈115 words)

(Demo: free chat "black leather belt under 30 dollars". Fish swim, get
knocked out. Funnel 50k → 28 → 3 → 1. Chips clicked, crown appears, cart
add.)

Now this is the fun part. We render the whole candidate pool as fish, so
you can actually watch it converge. Each turn we ask the question that
splits the pool the most, fish die, and the last one standing gets the
crown. So the flow is: parse the message, update state, retrieve and
rank, then decide. If the pool is small enough, we crown it. Otherwise we
ask color, material, price, or category, with clickable options.

So let's go ahead and run one. Black leather belt, under thirty dollars.
Watch it narrow. 50,000 down to a handful, then the champion. That's a
full multi-turn session, end to end, which is one of the deliverables.

### [1:45] Scene 3 — the tree gives you the funnel for free (VO ≈50 words)

(Tree grows on the left, final breadcrumb highlights on the right.)

Under the hood there's an n-ary tree of category properties, coarse to
fine. Every product maps to exactly one chain. Category lookups are O(1),
and once the tree pins the pool down to a small set, we skip the LLM
entirely. Zero tokens, and that's most turns. You'll also notice the
final pick shows its chain as a breadcrumb, so you can see exactly why we
chose it.

### [2:15] Scene 4 — MCP: plug it into anything (VO ≈80 words)

(Terminal: `claude mcp add entroship -- ...`. Chat window calling
search_products, clarify, tree_chain.)

We also exposed the same core as an MCP server. Four tools:
search_products, product_details, clarify, tree_chain. JSON-RPC 2.0, stdlib
only, no install. So you can plug it into Claude Desktop, Cursor, VS Code,
anything that speaks MCP. Let's go ahead and do that: add the server, ask
it to search for a black leather belt under thirty, and it comes back with
ranked products. clarify asks the next question, tree_chain shows where
the product sits. Same deterministic core, so the MCP behavior is the
scored behavior.

### [2:50] The numbers + close (VO ≈40 words)

(Benchmark table, hold 3 seconds. Fade to repo URL.)

So, the numbers. Hit rate 100%. MRR 0.723. MTTC 1.59 versus 9.81
baseline. TechnicalScore 0.9053 versus 0.107. Offline zero tokens, and if
judging runs without network, the fallback just works. Repo's up at
Entropino-ai/EntroShop. Go ahead and try it.

---

## Recording checklist

- 1080p screen capture, casual step-by-step voice-over, English.
- Arena segment IS the required multi-turn session: free chat "black
  leather belt under 30 dollars", click chips until the crown, show the
  cart add.
- MCP segment: real `claude mcp add entroship -- ...`, then one
  conversation calling search_products, clarify, tree_chain.
- Benchmark table freezes 3 seconds.
- Hard cap 3:00. Over? Cut Scene 3 (the tree) first; keep the multi-turn
  session and the MCP beat.
