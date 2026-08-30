# 07 · FAQ

**Why no pure-LLM approach?**

The task's information structure is deterministic and readable. The
simulator discloses constraints as verbatim catalog strings and the coarse
category as the target's own last-two category parts; exact matching over an
inverted index beats semantic smoothing on the public set (TF-IDF 0.9045 vs
MiniLM 0.9034 on the simulator pipeline), and the offline core costs **zero
tokens** — a hard requirement if final judging runs offline.

**Does the private split hold?**

The winning mechanisms — exact-phrase conjunction, exact coarse-category
identity, entropy-guided clarification, and the turn-9 clamp — follow from
the simulator's disclosure rules, not from the 200 public sessions. They are
data-set independent. The synthetic stress battery (chapter
[06](06-testing.md)) probes generalization beyond the public set.

**What if the organizer paraphrases?**

The phrase trie + dense routes buffer paraphrase as long as constraint
strings survive verbatim; the template parser degrades gracefully. Material
words and `color: x` are extracted by regex regardless of phrasing.

**What if the LLM endpoint is down?**

The LLM route is optional and failure-safe: startup ping, per-request
timeout, truncated-output-tolerant parsing, and automatic disable after
consecutive failures. The deterministic core never depends on it.

**Why does the demo have an "arena"?**

The MiroFish-style visualization (fish that swim, get knocked out, crown a
champion) makes the swarm-convergence metaphor visible: candidates compete
each round and the winner is crowned with a 👑. It is a UI metaphor, not a
separate algorithm.

**Is Chinese supported?**

Yes. Free chat maps Chinese input through a clothing-domain zh→en dictionary
(~100 entries) and parses budget/color/material phrases bilingually.

**Why entropy-guided facets instead of asking everything?**

The evaluator discloses at most 4 constraints per session and caps at 10
turns; asking the highest-entropy unconstrained facet minimizes the expected
turns to convergence (see chapter [04](04-policy-optimization.md)).

**How do I use the MCP server from Claude Desktop / Cursor?**

The MCP server exposes the four shopping-copilot tools
(`search_products`, `product_details`, `clarify`, `tree_chain`) over stdio
or HTTP. Register it in any MCP host (Claude Desktop, Cursor, ...) as a
stdio server:

```json
{
  "mcpServers": {
    "entroship": {
      "command": "python3",
      "args": ["<repo>/demo/mcp_server.py", "--catalog", "<repo>/data/catalog.jsonl"]
    }
  }
}
```

(Claude Desktop: `claude mcp add entroship -- python3 <repo>/demo/mcp_server.py --catalog <repo>/data/catalog.jsonl`.)
Stdout carries only newline-delimited JSON-RPC, so the host connection is
clean; progress banners and the optional MiniLM fallback go to stderr. The
HTTP transport is also available on a running demo server at
`POST http://127.0.0.1:8090/mcp` (JSON-RPC 2.0), which is what the
smoke suite exercises (chapter [06](06-testing.md)).
