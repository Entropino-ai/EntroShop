# Demo Video — Line-by-line storyboard with Manim scenes

This is the shot-by-shot companion to
[`DEMO_VIDEO_SCRIPT.md`](DEMO_VIDEO_SCRIPT.md). Every VO line is on its
own row with the screen beat it lands on. Abstract beats (the 50k→1
convergence, the product tree, the score table) are rendered as Manim
animations instead of raw screen capture; the code for each scene is at
the bottom of this file.

Eight scenes are produced (three for the video script, five covering
the non-demo docs — architecture pipeline, convergence policy, MCP
layer, score bars, stress battery):

- `docs/manim/convergence.py` — open: 50,000 points collapse to one
- `docs/manim/tree.py` — product-property tree growth + breadcrumb
- `docs/manim/numbers.py` — benchmark table build
- `docs/manim/pipeline.py` — four-stage turn loop (docs/02)
- `docs/manim/convergence_policy.py` — pool vs turn, 10-turn budget (docs/02)
- `docs/manim/mcp.py` — core → four tools → hosts (docs/03, README MCP)
- `docs/manim/scores.py` — BM25 vs EntroShop bars (docs/05)
- `docs/manim/stress.py` — 300 answerable sessions, 0 misses (STRESS_TEST)

Rendered 1080p clips are collected in `docs/manim/media/final/`. Render
from scratch with Manim Community Edition:

```bash
pip install manim          # plus system deps: pkg-config, cairo, pango, ffmpeg
manim render -qh docs/manim/convergence.py EntroShopConvergence
manim render -qh docs/manim/tree.py EntroShopTree
manim render -qh docs/manim/numbers.py EntroShopNumbers
# -q h = 1080p; drop -qh to render fast previews
```

Note: scenes paint their own WHITE background and use dark foreground
elements. The default dark manim frame renders as pure black under the
cairo renderer on some macOS setups, so the scenes do not rely on it.

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

Open clip: 50,000 catalog points collapse to a single target.

```python
"""Open clip: 50,000 catalog points collapse to a single target.

Render:
    manim render -qh convergence.py EntroShopConvergence
"""
from manim import *
import numpy as np


class EntroShopConvergence(Scene):
    """50k dots → one bright target → ten inward rings → all sweep in."""

    def construct(self):
        # Explicit light background: the cairo renderer on some macOS setups
        # paints the default dark frame as pure black, so scenes carry their
        # own background and use dark foreground elements.
        bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                       fill_opacity=1.0, stroke_width=0).set_z_index(-10)
        self.add(bg)

        rng = np.random.default_rng(20260827)
        # 8,000 dots is visually identical to 50k at this dot size and renders
        # in reasonable time; the VO still says "50,000".
        pts = rng.uniform(-6.4, 6.4, size=(8000, 2))
        cloud = VGroup(*[Dot([p[0], p[1], 0], radius=0.015, color=GREY_B)
                         for p in pts])
        self.play(FadeIn(cloud, run_time=2.0))

        # "one product we have to find": brighten a single point.
        idx = 271
        target = Dot([pts[idx][0], pts[idx][1], 0], radius=0.05, color=RED)
        self.play(Transform(cloud[idx], target), run_time=1.0)

        # Ten turns: 10 inward waves, each one "a question".
        turns = Text("10 turns", color=BLACK).to_edge(UP)
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

Category tree grows, breadcrumb highlights, O(1) lookup flash.

```python
"""Tree clip: category tree grows, a lookup path flashes, breadcrumb shows.

Render:
    manim render -qh tree.py EntroShopTree
"""
from manim import *


class EntroShopTree(Scene):
    """Coarse-to-fine tree growth plus the final breadcrumb highlight."""

    def construct(self):
        root = Text("Catalog").move_to(UP * 3)
        mid = Text("Men").next_to(root, DOWN, buff=0.9)
        leaf = Text("Belts").next_to(mid, DOWN, buff=0.9)

        # Explicit light background: the cairo renderer on some macOS setups
        # paints the default dark frame as pure black, so scenes carry their
        # own background and use dark foreground elements.
        bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                       fill_opacity=1.0, stroke_width=0).set_z_index(-10)
        self.add(bg)
        self.play(Write(root))
        self.play(Write(mid))
        self.play(Write(leaf))
        edges = VGroup(
            Line(root.get_bottom(), mid.get_top(), color=GREY),
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

        # O(1) lookup flash: a dot races down the path, one edge at a time.
        dot = Dot(root.get_bottom(), color=TEAL)
        self.play(MoveAlongPath(dot, edges[0]), run_time=0.6)
        self.play(MoveAlongPath(dot, edges[1]), run_time=0.6)
        self.wait(1.0)
```

### docs/manim/numbers.py

Benchmark table builds row by row, winner column highlighted.

```python
"""Close clip: benchmark table builds row by row, winner highlighted.

Render:
    manim render -qh numbers.py EntroShopNumbers
"""
from manim import *


class EntroShopNumbers(Scene):
    """Score table appears row by row; the EntroShop column goes green."""

    def construct(self):
        # Explicit light background: the cairo renderer on some macOS setups
        # paints the default dark frame as pure black, so scenes carry their
        # own background and use dark foreground elements.
        bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                       fill_opacity=1.0, stroke_width=0).set_z_index(-10)
        self.add(bg)
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
            row[2].set_color(GREEN_E)
        self.wait(1.5)
```

### docs/manim/pipeline.py

Four-stage turn loop: parse, state, retrieve, decide (docs/02).

```python
"""Architecture clip: message -> parse -> state -> retrieve -> decide.

Mirrors docs/02-architecture.md "Pipeline". Render:
    manim render -qh pipeline.py EntroShopPipeline
"""
from manim import *


class EntroShopPipeline(Scene):
    """The four-stage turn loop, shown as boxes with a token counter."""

    def construct(self):
        # Explicit light background: the cairo renderer on some macOS setups
        # paints the default dark frame as pure black, so scenes carry their
        # own background and use dark foreground elements.
        bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                       fill_opacity=1.0, stroke_width=0).set_z_index(-10)
        self.add(bg)
        stages = ["parse", "state", "retrieve", "decide"]
        boxes = VGroup()
        for i, name in enumerate(stages):
            box = Rectangle(width=2.2, height=1.0, color=BLUE_D).shift(RIGHT * (i - 1.5) * 2.6)
            label = Text(name, font_size=30).move_to(box.get_center())
            boxes.add(VGroup(box, label))
            self.play(Create(box), Write(label), run_time=0.4)

        # Arrows between stages.
        arrows = VGroup()
        for i in range(3):
            a = Arrow(boxes[i].get_right(), boxes[i + 1].get_left(), color=GREY_B)
            arrows.add(a)
            self.play(Create(a), run_time=0.25)

        # Token counter stays zero through the loop.
        counter = Text("tokens: 0", color=GREEN).to_edge(DOWN)
        self.play(Write(counter))

        # One full loop flash: highlight each box in turn.
        for i in range(4):
            self.play(boxes[i].animate.set_color(YELLOW), run_time=0.25)
            self.play(boxes[i].animate.set_color(BLUE), run_time=0.25)
        self.wait(1.0)
```

### docs/manim/convergence_policy.py

Pool vs turn with the 10-turn budget wall (docs/02).

```python
"""Convergence policy clip: pool size vs turn, with the clamp at 10.

Mirrors docs/02-architecture.md "Convergence policy". Render:
    manim render -qh convergence_policy.py EntroShopPolicy
"""
from manim import *


class EntroShopPolicy(Scene):
    """Pool shrinks turn by turn; the 10-turn budget is drawn as a wall."""

    def construct(self):
        # Explicit light background: the cairo renderer on some macOS setups
        # paints the default dark frame as pure black, so scenes carry their
        # own background and use dark foreground elements.
        bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                       fill_opacity=1.0, stroke_width=0).set_z_index(-10)
        self.add(bg)
        # Axes: turns (x) vs log pool size (y). Tick numbers are added as
        # plain Text so the scene renders without a TeX install.
        axes = Axes(
            x_range=[0, 11, 1],
            y_range=[0, 5, 1],
            x_length=9,
            y_length=4,
            axis_config={"include_numbers": False},
        ).shift(DOWN * 0.5)
        self.play(Create(axes))
        for t in (0, 5, 10):
            tick = Text(str(t), font_size=20, color=GREY_B).next_to(
                axes.c2p(t, 0), DOWN * 0.35)
            self.play(FadeIn(tick), run_time=0.15)

        # Pool halves-ish each turn: 50k -> 28 -> 3 -> 1 on a log scale.
        points = [(0, 4.7), (1, 4.0), (2, 3.2), (3, 2.4), (4, 1.8),
                  (5, 1.4), (6, 1.0), (7, 0.6), (8, 0.3), (9, 0.05)]
        line = axes.plot_line_graph(
            x_values=[p[0] for p in points],
            y_values=[p[1] for p in points],
            line_color=TEAL,
            vertex_dot_radius=0.04,
        )
        self.play(Create(line), run_time=2.0)

        # The 10-turn budget wall.
        wall = DashedLine(
            axes.c2p(10, 0), axes.c2p(10, 5), color=RED, dash_length=0.1
        )
        budget = Text("10-turn budget", color=RED, font_size=26).next_to(wall, UP)
        self.play(Create(wall), Write(budget))
        self.wait(1.5)
```

### docs/manim/mcp.py

Deterministic core feeding four tools, any MCP host (docs/03).

```python
"""MCP clip: four tools exposed over stdio/HTTP to any host.

Mirrors docs/03-modules.md (agent_lib/mcp.py) and the README MCP section.
Render:
    manim render -qh mcp.py EntroShopMCP
"""
from manim import *


class EntroShopMCP(Scene):
    """A core box feeds four tool cards; host logos connect from the side."""

    def construct(self):
        # Explicit light background: the cairo renderer on some macOS setups
        # paints the default dark frame as pure black, so scenes carry their
        # own background and use dark foreground elements.
        bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                       fill_opacity=1.0, stroke_width=0).set_z_index(-10)
        self.add(bg)
        core = RoundedRectangle(corner_radius=0.2, width=2.6, height=1.2,
                                color=BLUE_D)
        core_label = Text("deterministic core", font_size=24).move_to(core.get_center())
        self.play(Create(core), Write(core_label))

        tools = ["search_products", "product_details", "clarify", "tree_chain"]
        cards = VGroup()
        for i, name in enumerate(tools):
            card = RoundedRectangle(corner_radius=0.15, width=3.4, height=0.7,
                                    color=GREY_B).shift(
                DOWN * 1.1 + RIGHT * (i - 1.5) * 3.6)
            label = Text(name, font_size=22).move_to(card.get_center())
            cards.add(VGroup(card, label))
            self.play(Create(card), Write(label), run_time=0.35)

        # Wires from core to each tool.
        for card in cards:
            wire = Line(core.get_bottom(), card.get_top(), color=TEAL)
            self.play(Create(wire), run_time=0.25)

        # Hosts: Claude, Cursor, VS Code, anything.
        hosts = Text("Claude  ·  Cursor  ·  VS Code  ·  any MCP host",
                     font_size=26, color=YELLOW).to_edge(DOWN)
        self.play(Write(hosts))
        self.wait(1.5)
```

### docs/manim/scores.py

BM25 baseline vs EntroShop bars (docs/05).

```python
"""Score comparison clip: BM25 baseline vs EntroShop bars.

Mirrors docs/05-benchmarks.md headline table. Render:
    manim render -qh scores.py EntroShopScores
"""
from manim import *


class EntroShopScores(Scene):
    """Four metrics, two bars each; EntroShop wins every pair."""

    def construct(self):
        metrics = [
            ("Hit rate@10", 0.125, 1.000),
            ("MRR",         0.068, 0.723),
            ("MTTC (lower is better)", 0.119, 0.941),  # normalized efficiency proxy
            ("TechnicalScore", 0.107, 0.905),
        ]
        # Explicit light background: the cairo renderer on some macOS setups
        # paints the default dark frame as pure black, so scenes carry their
        # own background and use dark foreground elements.
        bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                       fill_opacity=1.0, stroke_width=0).set_z_index(-10)
        self.add(bg)
        group = VGroup()
        for r, (name, base, ours) in enumerate(metrics):
            label = Text(name, font_size=24).move_to(LEFT * 4.2 + DOWN * r * 1.1)
            group.add(label)
            base_bar = Rectangle(width=base * 5, height=0.3, color=GREY).move_to(
                LEFT * 2.0 + DOWN * r * 1.1, aligned_edge=LEFT)
            ours_bar = Rectangle(width=ours * 5, height=0.3, color=TEAL).move_to(
                LEFT * 2.0 + DOWN * r * 1.1, aligned_edge=LEFT)
            group.add(base_bar, ours_bar)
            self.play(FadeIn(label), GrowFromEdge(base_bar, LEFT), run_time=0.4)
            self.play(GrowFromEdge(ours_bar, LEFT), run_time=0.4)
        legend = Text("grey: BM25 baseline   teal: EntroShop",
                      font_size=22, color=GREY_B).to_edge(DOWN)
        self.play(Write(legend))
        self.wait(1.5)
```

### docs/manim/stress.py

300 answerable sessions, 0 misses (STRESS_TEST).

```python
"""Stress-test clip: 300 answerable sessions, 0 misses.

Mirrors docs/STRESS_TEST.md. Render:
    manim render -qh stress.py EntroShopStress
"""
from manim import *


class EntroShopStress(Scene):
    """A 300-dot grid; every dot stays green (no miss)."""

    def construct(self):
        # Explicit light background: the cairo renderer on some macOS setups
        # paints the default dark frame as pure black, so scenes carry their
        # own background and use dark foreground elements.
        bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                       fill_opacity=1.0, stroke_width=0).set_z_index(-10)
        self.add(bg)
        dots = VGroup()
        for i in range(300):
            x = (i % 30) - 14.5
            y = 4.0 - (i // 30) * 0.55
            dots.add(Dot(np.array([x, y, 0]), radius=0.06, color=GREEN_E))
        # Reveal in chunks so the build reads as "sessions passing".
        for start in range(0, 300, 30):
            self.play(FadeIn(dots[start:start + 30]), run_time=0.15)
        banner = Text("300 / 300  Hit@10 = 1.000", color=GREEN, font_size=34).to_edge(DOWN)
        self.play(Write(banner))
        self.wait(1.5)
```

---

## Cut order if over 3:00

1. Cut Scene 3 (tree) VO lines 27–28; keep the breadcrumb shot if the
   Manim clip is already rendered.
2. Shorten the open clip (lines 1–6) to two waves instead of ten.
3. Keep the multi-turn session (16–24) and the MCP beat (30–36) intact;
   both are required deliverables.
