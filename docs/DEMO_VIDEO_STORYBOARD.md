# Demo Video — Line-by-line storyboard with Manim scenes

This is the shot-by-shot companion to
[`DEMO_VIDEO_SCRIPT.md`](DEMO_VIDEO_SCRIPT.md). Every VO line is on its
own row with the screen beat it lands on. Abstract beats (the 50k→1
convergence, the product tree, the score table) are rendered as Manim
animations instead of raw screen capture; the code for each scene is at
the bottom of this file.

Three files are produced:

- `docs/manim/convergence.py` — open: 50,000 points collapse to one
- `docs/manim/tree.py` — product-property tree growth + breadcrumb
- `docs/manim/numbers.py` — benchmark table build

Render with Manim Community Edition:

```bash
pip install manim
manim render -qh docs/manim/convergence.py EntroShopConvergence
manim render -qh docs/manim/tree.py EntroShopTree
manim render -qh docs/manim/numbers.py EntroShopNumbers
# -q h = 1080p; drop -qh to render fast previews
```

Timing notes: VO lines are counted at ~150 words/min; the [mm:ss] column
is the cumulative clock in the final cut, so a Manim clip may need a
speedup or a hold in the editor to land on its beat.

---

## Storyboard

### [0:00–0:20] Open — Manim clip: convergence

| # | Time | VO (one line per row) | Screen |
|---|------|------------------------|--------|
| 1 | 0:00 | So here's the setup. | Manim: 50,000 dim points fill the frame |
| 2 | 0:03 | Somewhere in a 50,000-item catalog there's one product we have to find. | Manim: one point brightens, others dim |
| 3 | 0:08 | A simulated customer answers our questions, and we get ten turns to do it. | Overlay: "1 target. 10 turns." |
| 4 | 0:12 | So we built a little agent that asks the right questions and converges. | Manim: points sweep inward in waves |
| 5 | 0:15 | 200 out of 200 on the public set, 1.59 turns average, zero tokens offline. | Text pops: "200/200 · 1.59 turns · 0 tokens" |
| 6 | 0:18 | Let's go ahead and walk through it. | Cut to screen recording |

### [0:20–0:55] Scene 1 — the simulator hands you the data (screen recording)

| # | Time | VO | Screen |
|---|------|----|--------|
| 7 | 0:20 | First, let's talk about what the simulator gives us. | Product card on screen |
| 8 | 0:23 | It doesn't paraphrase anything. | Highlight "features" field |
| 9 | 0:26 | The customer literally repeats the product's own metadata, word for word. | Highlight material value |
| 10 | 0:30 | You ask about material, you get "leather" back, exactly as written. | Callout: input → output "leather" |
| 11 | 0:34 | So what we're doing here is exact matching. | Fade to phrase-trie diagram |
| 12 | 0:38 | We built a phrase trie over the whole catalog, plus a few regexes for things like `color: x` and budget. | Trie nodes light up |
| 13 | 0:44 | Chinese works, English works. | "黑色皮带" → belt |
| 14 | 0:47 | There's an optional LLM rerank, but it only kicks in when the tree can't decide. | LLM tag grays out |
| 15 | 0:51 | Offline, we're at zero tokens. | Counter: "0 tokens" |

### [0:55–1:45] Scene 2 — let's watch the pool die (screen recording, the required multi-turn session)

| # | Time | VO | Screen |
|---|------|----|--------|
| 16 | 0:55 | Now this is the fun part. | Arena opens |
| 17 | 0:58 | We render the whole candidate pool as fish, so you can actually watch it converge. | Fish swarm |
| 18 | 1:03 | Each turn we ask the question that splits the pool the most, fish die, and the last one standing gets the crown. | Fish knocked out; crown appears |
| 19 | 1:12 | So the flow is: parse the message, update state, retrieve and rank, then decide. | Four-step callout |
| 20 | 1:18 | If the pool is small enough, we crown it. | Pool counter 28 → 3 |
| 21 | 1:22 | Otherwise we ask color, material, price, or category, with clickable options. | Chips row |
| 22 | 1:28 | So let's go ahead and run one. Black leather belt, under thirty dollars. | Type into chat |
| 23 | 1:34 | Watch it narrow. 50,000 down to a handful, then the champion. | Funnel 50k → 28 → 3 → 1 |
| 24 | 1:40 | That's a full multi-turn session, end to end, which is one of the deliverables. | Crown + cart add |

### [1:45–2:15] Scene 3 — Manim clip: the tree

| # | Time | VO | Screen |
|---|------|----|--------|
| 25 | 1:45 | Under the hood there's an n-ary tree of category properties, coarse to fine. | Manim: tree grows top-down |
| 26 | 1:51 | Every product maps to exactly one chain. | Manim: one leaf highlighted per branch |
| 27 | 1:56 | Category lookups are O(1), and once the tree pins the pool down to a small set, we skip the LLM entirely. | Manim: lookup path flashes |
| 28 | 2:03 | Zero tokens, and that's most turns. | Counter: "0 tokens" |
| 29 | 2:07 | You'll also notice the final pick shows its chain as a breadcrumb, so you can see exactly why we chose it. | Breadcrumb highlights root→leaf |

### [2:15–2:50] Scene 4 — MCP: plug it into anything (screen recording)

| # | Time | VO | Screen |
|---|------|----|--------|
| 30 | 2:15 | We also exposed the same core as an MCP server. | Terminal: claude mcp add |
| 31 | 2:20 | Four tools: search_products, product_details, clarify, tree_chain. | Tool list pops |
| 32 | 2:26 | JSON-RPC 2.0, stdlib only, no install. | Spec line |
| 33 | 2:30 | So you can plug it into Claude Desktop, Cursor, VS Code, anything that speaks MCP. | Host logos flash |
| 34 | 2:36 | Let's go ahead and do that: add the server, ask it to search for a black leather belt under thirty, and it comes back with ranked products. | Chat: search_products call |
| 35 | 2:44 | clarify asks the next question, tree_chain shows where the product sits. | Chat: clarify + tree_chain |
| 36 | 2:48 | Same deterministic core, so the MCP behavior is the scored behavior. | Core tag on all three |

### [2:50–3:00] Close — Manim clip: numbers

| # | Time | VO | Screen |
|---|------|----|--------|
| 37 | 2:50 | So, the numbers. | Manim: table builds row by row |
| 38 | 2:53 | Hit rate 100%. MRR 0.723. MTTC 1.59 versus 9.81 baseline. | Rows highlight |
| 39 | 2:57 | TechnicalScore 0.9053 versus 0.107. | Final row |
| 40 | 2:59 | Offline zero tokens, and if judging runs without network, the fallback just works. | "0 tokens" badge |
| 41 | 3:00 | Repo's up at Entropino-ai/EntroShop. Go ahead and try it. | Fade to repo URL |

---

## Manim scenes

### docs/manim/convergence.py

```python
"""Open clip: 50,000 catalog points collapse to a single target."""
from manim import *
import numpy as np

class EntroShopConvergence(Scene):
    def construct(self):
        # A pseudo-random cloud that stays visually dense (no clumping).
        rng = np.random.default_rng(20260827)
        pts = rng.uniform(-6.4, 6.4, size=(50000, 2))
        cloud = VGroup(*[Dot(p, radius=0.015, color=GREY_B) for p in pts])
        self.play(FadeIn(cloud, run_time=2.0))

        # "one product we have to find": brighten a single point.
        target = Dot(pts[271], radius=0.05, color=YELLOW)
        self.play(Transform(cloud[271], target), run_time=1.0)

        # Ten turns: 10 inward waves, each one "a question".
        turns = Text("10 turns", color=WHITE).to_edge(UP)
        self.play(Write(turns))
        for i in range(10):
            radius = 6.4 - i * 0.55
            ring = Circle(radius=radius, color=TEAL, stroke_width=1.5)
            self.play(Create(ring), run_time=0.25)
            self.play(FadeOut(ring), run_time=0.15)

        # Convergence: everything sweeps into the target.
        self.play(cloud.animate.move_to(target.get_center()), run_time=2.0)
        self.play(FadeOut(cloud), FadeOut(turns))

        # The score punchline.
        score = Text("200/200  ·  1.59 turns  ·  0 tokens",
                     color=GREEN).scale(0.8)
        self.play(Write(score))
        self.wait(1.5)
```

### docs/manim/tree.py

```python
"""Tree clip: category tree grows, a lookup path flashes, breadcrumb shows."""
from manim import *

class EntroShopTree(Scene):
    def construct(self):
        root = Text("Catalog").move_to(UP * 3)
        mid  = Text("Men").next_to(root, DOWN, buff=0.9)
        leaf = Text("Belts").next_to(mid, DOWN, buff=0.9)

        self.play(Write(root))
        self.play(Write(mid))
        self.play(Write(leaf))
        edges = VGroup(
            Line(root.get_bottom(), mid.get_top(), color=GREY_B),
            Line(mid.get_bottom(), leaf.get_top(), color=GREY_B),
        )
        self.play(Create(edges))

        # Breadcrumb: highlight root -> leaf in yellow.
        self.play(edges.animate.set_color(YELLOW))
        self.play(
            root.animate.set_color(YELLOW),
            mid.animate.set_color(YELLOW),
            leaf.animate.set_color(YELLOW),
        )
        self.wait(1.0)

        # O(1) lookup flash: a dot races down the path.
        dot = Dot(root.get_bottom(), color=TEAL)
        self.play(MoveAlongPath(dot, edges[0]), MoveAlongPath(dot, edges[1]),
                  run_time=1.2)
        self.wait(1.0)
```

### docs/manim/numbers.py

```python
"""Close clip: benchmark table builds row by row, winner highlighted."""
from manim import *

class EntroShopNumbers(Scene):
    def construct(self):
        rows = [
            ("Metric",      "BM25 baseline",  "EntroShop"),
            ("Hit rate@10", "0.125",          "1.000"),
            ("MRR",         "0.068",          "0.723"),
            ("MTTC",        "9.81",           "1.59"),
            ("TechnicalScore", "0.107",       "0.9053"),
        ]
        table = VGroup()
        for r, row in enumerate(rows):
            cells = VGroup()
            for c, text in enumerate(row):
                cell = Text(text, font_size=28).move_to(
                    RIGHT * (c - 1) * 2.6 + DOWN * r * 0.7)
                cells.add(cell)
            table.add(cells)
            self.play(FadeIn(cells), run_time=0.35)
        # Highlight the EntroShop column.
        for row in table:
            row[2].set_color(GREEN)
        self.wait(1.5)
```

---

## Cut order if over 3:00

1. Cut Scene 3 (tree) VO lines 27–28; keep the breadcrumb shot if the
   Manim clip is already rendered.
2. Shorten the open clip (lines 1–6) to two waves instead of ten.
3. Keep the multi-turn session (16–24) and the MCP beat (30–36) intact;
   both are required deliverables.
