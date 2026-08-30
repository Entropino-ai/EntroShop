# Demo Video — Line-by-line storyboard with Manim scenes

This is the shot-by-shot companion to
[`DEMO_VIDEO_SCRIPT.md`](DEMO_VIDEO_SCRIPT.md). Every VO line is on its
own row with the screen beat it lands on. Abstract beats (the 50k→1
convergence, the product tree, the score table) are rendered as Manim
animations instead of raw screen capture; the code for each scene is at
the bottom of this file.

The scenes are **modular**: each phase is its own Scene class and
renders to its own clip, so the editor can assemble the 3-minute video
from the exact shots it needs. 19 clips across 8 source files:

- `convergence.py` — 5 phases: Cloud, Target, Rings, Collapse, Score (+ ScoreTable)
- `tree.py` — 3 phases: Grow, Breadcrumb, Lookup (real multi-level tree)
- `numbers.py` — 2 phases: Build, Highlight
- `pipeline.py` — 2 phases: Build, Loop (docs/02)
- `convergence_policy.py` — 2 phases: Curve, Wall (docs/02)
- `mcp.py` — 2 phases: Build, Hosts (docs/03, README MCP)
- `scores.py` — 1 clip: BM25 vs EntroShop table (docs/05)
- `stress.py` — 2 phases: Grid, Banner (STRESS_TEST)

Rendered 1080p60 clips are collected in `docs/manim/media/final/` (19
files, ~3-5 s each). Render from scratch with
`docs/manim/render_all.sh`, or render individual scenes:

```bash
manim render -qh docs/manim/convergence.py EntroShopOpen_Cloud
manim render -qh docs/manim/tree.py EntroShopTree_Grow
# full list: docs/manim/render_all.sh
```

Note: scenes paint their own WHITE background and use dark foreground
elements. The default dark manim frame renders as pure black under the
cairo renderer on some macOS setups, so the scenes do not rely on it.

Timing notes: VO lines are counted at ~150 words/min; the [mm:ss] column
is the cumulative clock in the final cut, so a Manim clip may need a
speedup or a hold in the editor to land on its beat.

---

## Storyboard

### Recommended edit order (which clip goes with which line)

The 3-minute cut uses 12 of the 19 clips; the other 7 (pipeline, policy,
scores, stress) are extras for a longer version or the docs. Clips are
referenced by filename in `docs/manim/media/final/`; durations are the
rendered lengths, so a clip may need a speedup or a hold in the editor.

| VO line | Script beat | Clip file | Duration | Use |
|---------|-------------|-----------|----------|-----|
| 1 | "So here's the setup." | `EntroShopOpen_Cloud.mp4` | 2.5s | fade in the swarm |
| 2 | "...one product we have to find." | `EntroShopOpen_Target.mp4` | 2.0s | target lights red |
| 3 | "...we get ten turns to do it." | `EntroShopOpen_Rings.mp4` | 5.2s | ten inward rings |
| 4 | "...asks the right questions and converges." | `EntroShopOpen_Collapse.mp4` | 3.0s | swarm sweeps in |
| 5 | "200 out of 200 ... zero tokens offline." | `EntroShopOpen_ScoreTable.mp4` | 8.7s | three stats as a 2-column table, row by row |
| 25 | "...an n-ary tree of category properties." | `EntroShopTree_Grow.mp4` | 6.0s | tree grows level by level |
| 26–29 | "...one chain ... breadcrumb ... why." | `EntroShopTree_Breadcrumb.mp4` | 3.6s | breadcrumb chain turns yellow |
| 27 | "...Category lookups are O(1)..." | `EntroShopTree_Lookup.mp4` | 2.5s | (optional) lookup dot down the chain |
| 37–38 | "So, the numbers. Hit rate 100%..." | `EntroShopNumbers_Build.mp4` | 6.5s | table builds, holds for reading |
| 39–41 | "...TechnicalScore 0.9053... repo..." | `EntroShopNumbers_Highlight.mp4` | 6.0s | winner column + close, holds |

Extras (longer cut / docs):

| Clip file | Duration | Covers |
|-----------|----------|--------|
| `EntroShopPipeline_Build.mp4` | 3.1s | four-stage loop (docs/02) |
| `EntroShopPipeline_Loop.mp4` | 4.0s | one turn, 0 tokens (docs/02) |
| `EntroShopPolicy_Curve.mp4` | 3.8s | pool shrinks per turn (docs/02) |
| `EntroShopPolicy_Wall.mp4` | 2.2s | 10-turn budget wall (docs/02) |
| `EntroShopMCP_Build.mp4` | 5.2s | core → four tools (docs/03) |
| `EntroShopMCP_Hosts.mp4` | 3.5s | any MCP host line (docs/03) |
| `EntroShopScores.mp4` | 8.9s | BM25 vs EntroShop table (docs/05) |
| `EntroShopStress_Grid.mp4` | 2.3s | 300 sessions fill (STRESS_TEST) |
| `EntroShopStress_Banner.mp4` | 3.5s | 300/300 banner (STRESS_TEST) |

### [0:00–0:20] Open — Manim clip: convergence

| # | Time | VO (one line per row) | Screen |
|---|------|------------------------|--------|
| 1 | 0:00 | So here's the setup. | clip EntroShopOpen_Cloud: 50,000 dim points fill the frame |
| 2 | 0:03 | Somewhere in a 50,000-item catalog there's one product we have to find. | clip EntroShopOpen_Target: one point brightens red |
| 3 | 0:08 | A simulated customer answers our questions, and we get ten turns to do it. | clip EntroShopOpen_Rings: ten inward rings; overlay "1 target. 10 turns." |
| 4 | 0:12 | So we built a little agent that asks the right questions and converges. | clip EntroShopOpen_Collapse: swarm sweeps into the target |
| 5 | 0:15 | 200 out of 200 on the public set, 1.59 turns average, zero tokens offline. | clip EntroShopOpen_ScoreTable: rows build, hold after each |
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
| 25 | 1:45 | Under the hood there's an n-ary tree of category properties, coarse to fine. | clip EntroShopTree_Grow: tree grows top-down |
| 26 | 1:51 | Every product maps to exactly one chain. | clip EntroShopTree_Breadcrumb: root→leaf chain highlights |
| 27 | 1:56 | Category lookups are O(1), and once the tree pins the pool down to a small set, we skip the LLM entirely. | clip EntroShopTree_Lookup: lookup dot races the chain |
| 28 | 2:03 | Zero tokens, and that's most turns. | (optional) Counter: "0 tokens" |
| 29 | 2:07 | You'll also notice the final pick shows its chain as a breadcrumb, so you can see exactly why we chose it. | hold on EntroShopTree_Breadcrumb end frame |

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
| 37 | 2:50 | So, the numbers. | clip EntroShopNumbers_Build: table builds row by row |
| 38 | 2:53 | Hit rate 100%. MRR 0.723. MTTC 1.59 versus 9.81 baseline. | rows land as the table builds |
| 39 | 2:57 | TechnicalScore 0.9053 versus 0.107. | clip EntroShopNumbers_Highlight: winner column turns green |
| 40 | 2:59 | Offline zero tokens, and if judging runs without network, the fallback just works. | "0 tokens" badge (text overlay) |
| 41 | 3:00 | Repo's up at Entropino-ai/EntroShop. Go ahead and try it. | fade to repo URL |

---

## Manim scenes

### docs/manim/convergence.py

Open clip, phases: Cloud, Target, Rings, Collapse, Score (ScoreTable = 3-row stats table).

```python
"""Open clip, modular: each phase is its own Scene and renders to its own mp4.

Render all (or just the ones you need):
    manim render -qh convergence.py EntroShopOpen_Cloud
    manim render -qh convergence.py EntroShopOpen_Target
    manim render -qh convergence.py EntroShopOpen_Rings
    manim render -qh convergence.py EntroShopOpen_Collapse
    manim render -qh convergence.py EntroShopOpen_Score        # combined line
    manim render -qh convergence.py EntroShopOpen_ScoreTable   # 3-row table
"""
from manim import *
import numpy as np

RNG = np.random.default_rng(20260827)
# 8,000 dots reads as a dense 50k swarm at this dot size and renders fast.
PTS = RNG.uniform(-6.4, 6.4, size=(8000, 2))
TARGET_IDX = 271


def make_bg(scene: Scene) -> None:
    """White background. The cairo renderer paints manim's default dark
    frame as pure black on some macOS setups, so every scene adds its own."""
    bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                   fill_opacity=1.0, stroke_width=0).set_z_index(-10)
    scene.add(bg)


def make_cloud() -> VGroup:
    return VGroup(*[Dot([p[0], p[1], 0], radius=0.015, color=GREY_B)
                    for p in PTS])


class EntroShopOpen_Cloud(Scene):
    """Phase 1: the 50,000-item swarm fades in and holds."""

    def construct(self):
        make_bg(self)
        self.play(FadeIn(make_cloud(), run_time=1.5))
        self.wait(1.0)


class EntroShopOpen_Target(Scene):
    """Phase 2: one hidden target brightens red among the swarm."""

    def construct(self):
        make_bg(self)
        cloud = make_cloud()
        self.add(cloud)
        t = PTS[TARGET_IDX]
        target = Dot([t[0], t[1], 0], radius=0.05, color=RED)
        self.play(Transform(cloud[TARGET_IDX], target), run_time=1.0)
        self.wait(1.0)


class EntroShopOpen_Rings(Scene):
    """Phase 3: ten inward rings, each one a question we get to ask."""

    def construct(self):
        make_bg(self)
        turns = Text("10 turns", color=BLACK).to_edge(UP)
        self.play(Write(turns))
        for i in range(10):
            radius = 6.4 - i * 0.55
            ring = Circle(radius=radius, color=TEAL, stroke_width=1.5)
            self.play(Create(ring), run_time=0.22)
            self.play(FadeOut(ring), run_time=0.13)
        self.wait(0.5)


class EntroShopOpen_Collapse(Scene):
    """Phase 4: the whole swarm sweeps into the single target."""

    def construct(self):
        make_bg(self)
        cloud = make_cloud()
        self.add(cloud)
        t = PTS[TARGET_IDX]
        target = Dot([t[0], t[1], 0], radius=0.05, color=RED)
        self.add(target)
        self.play(cloud.animate.move_to(target.get_center()), run_time=1.8)
        self.play(FadeOut(cloud), run_time=0.4)
        self.wait(0.8)


class EntroShopOpen_Score(Scene):
    """Phase 5 (combined): the score punchline fades in and holds."""

    def construct(self):
        make_bg(self)
        score = Text("200/200  ·  1.59 turns  ·  0 tokens",
                     color=GREEN_E).scale(0.8)
        self.play(Write(score), run_time=1.0)
        self.wait(1.5)


SCORE_ROWS = [
    ("Metric", "Value"),
    ("Hit rate@10", "200/200"),
    ("Avg. turns to conversion", "1.59"),
    ("Tokens (offline)", "0"),
]


class EntroShopOpen_ScoreTable(Scene):
    """Phase 5: the three headline stats as a two-column table, one row at a
    time with a hold so each number is readable."""

    def construct(self):
        make_bg(self)
        table = VGroup()
        for r, (metric, value) in enumerate(SCORE_ROWS):
            m = Text(metric, font_size=34, color=BLACK).move_to(
                LEFT * 2.6 + DOWN * r * 0.9)
            v = Text(value, font_size=34, color=GREEN_E).move_to(
                RIGHT * 2.6 + DOWN * r * 0.9)
            row = VGroup(m, v)
            table.add(row)
            self.play(FadeIn(row), run_time=0.4)
            self.wait(1.2 if r < len(SCORE_ROWS) - 1 else 2.5)
        self.wait(1.0)
```

### docs/manim/tree.py

Real multi-level tree, 3 phases: Grow, Breadcrumb, Lookup.

```python
"""Tree clip, modular: growth, breadcrumb, lookup are separate Scenes.

A real coarse-to-fine tree: Catalog root, then Women/Men/Kids, then Men's
subtree with Accessories -> Belts as the highlighted chain.

Render:
    manim render -qh tree.py EntroShopTree_Grow
    manim render -qh tree.py EntroShopTree_Breadcrumb
    manim render -qh tree.py EntroShopTree_Lookup
"""
from manim import *

# Node coordinates: (label, x, y). Levels top (root) to bottom (leaf).
NODES = [
    ("Catalog", 0.0, 3.4),
    ("Women", -5.4, 1.6),
    ("Men", 0.0, 1.6),
    ("Kids", 5.4, 1.6),
    ("Apparel", -2.6, -0.2),
    ("Accessories", 2.6, -0.2),
    ("Shoes", 5.0, -0.2),
    ("Belts", 1.0, -2.0),
    ("Hats", 4.2, -2.0),
]

# Edges as (parent index, child index) into NODES.
EDGES = [
    (0, 1), (0, 2), (0, 3),
    (2, 4), (2, 5), (2, 6),
    (5, 7), (5, 8),
]

# The chain highlighted as the final breadcrumb: Catalog -> Men -> Accessories -> Belts.
CHAIN = [0, 2, 5, 7]


def node_box(i: int) -> VGroup:
    label, x, y = NODES[i]
    box = RoundedRectangle(corner_radius=0.18, width=2.3, height=0.8,
                           color=GREY_B, fill_color=WHITE, fill_opacity=1.0)
    text = Text(label, font_size=24, color=BLACK)
    group = VGroup(box, text).move_to(np.array([x, y, 0]))
    return group


def edge_line(a: int, b: int) -> Line:
    xa, ya = NODES[a][1], NODES[a][2]
    xb, yb = NODES[b][1], NODES[b][2]
    return Line(np.array([xa, ya, 0]), np.array([xb, yb, 0]), color=GREY_B)


def make_bg(scene: Scene) -> None:
    bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                   fill_opacity=1.0, stroke_width=0).set_z_index(-10)
    scene.add(bg)


class EntroShopTree_Grow(Scene):
    """Phase 1: the tree grows level by level, root first."""

    def construct(self):
        make_bg(self)
        boxes = [node_box(i) for i in range(len(NODES))]
        # Root.
        self.play(Create(boxes[0][0]), Write(boxes[0][1]), run_time=0.6)
        # Level 2: Women / Men / Kids with edges from root.
        for i in (1, 2, 3):
            self.play(Create(edge_line(0, i)), run_time=0.2)
            self.play(Create(boxes[i][0]), Write(boxes[i][1]), run_time=0.35)
        # Level 3: Men's subtree.
        for i in (4, 5, 6):
            self.play(Create(edge_line(2, i)), run_time=0.2)
            self.play(Create(boxes[i][0]), Write(boxes[i][1]), run_time=0.35)
        # Level 4: Accessories' children.
        for i in (7, 8):
            self.play(Create(edge_line(5, i)), run_time=0.2)
            self.play(Create(boxes[i][0]), Write(boxes[i][1]), run_time=0.35)
        self.wait(1.0)


class EntroShopTree_Breadcrumb(Scene):
    """Phase 2: the Catalog -> Men -> Accessories -> Belts chain turns yellow."""

    def construct(self):
        make_bg(self)
        boxes = [node_box(i) for i in range(len(NODES))]
        self.add(*[b for box in boxes for b in box])
        self.add(*[edge_line(a, b) for a, b in EDGES])
        for a, b in zip(CHAIN, CHAIN[1:]):
            self.play(edge_line(a, b).animate.set_color(YELLOW), run_time=0.3)
            for idx in (a, b):
                box, text = boxes[idx]
                self.play(box.animate.set_color(YELLOW),
                          text.animate.set_color(YELLOW), run_time=0.25)
        self.wait(1.2)


class EntroShopTree_Lookup(Scene):
    """Phase 3: an O(1) lookup dot races down the highlighted chain."""

    def construct(self):
        make_bg(self)
        boxes = [node_box(i) for i in range(len(NODES))]
        self.add(*[b for box in boxes for b in box])
        lines = [edge_line(a, b) for a, b in EDGES]
        self.add(*lines)
        for a, b in zip(CHAIN, CHAIN[1:]):
            edge_line(a, b).set_color(YELLOW)
            for idx in (a, b):
                boxes[idx][0].set_color(YELLOW)
                boxes[idx][1].set_color(YELLOW)
        # Dot starts at the root box bottom and follows the chain edges.
        dot = Dot(node_box(CHAIN[0]).get_bottom(), color=TEAL)
        self.add(dot)
        for a, b in zip(CHAIN, CHAIN[1:]):
            line = edge_line(a, b)
            self.play(MoveAlongPath(dot, line), run_time=0.5)
        self.wait(1.0)
```

### docs/manim/numbers.py

Score table, 2 phases: Build (holds per row), Highlight (holds after green).

```python
"""Score table clip, modular: build rows, then highlight the winner column.

Render:
    manim render -qh numbers.py EntroShopNumbers_Build
    manim render -qh numbers.py EntroShopNumbers_Highlight
"""
from manim import *

ROWS = [
    ("Metric", "BM25 baseline", "EntroShop"),
    ("Hit rate@10", "0.125", "1.000"),
    ("MRR", "0.068", "0.723"),
    ("MTTC", "9.81", "1.59"),
    ("TechnicalScore", "0.107", "0.9053"),
]


def make_bg(scene: Scene) -> None:
    bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                   fill_opacity=1.0, stroke_width=0).set_z_index(-10)
    scene.add(bg)


def build_table() -> VGroup:
    table = VGroup()
    for r, row in enumerate(ROWS):
        cells = VGroup()
        for c, text in enumerate(row):
            cell = Text(text, font_size=28, color=BLACK).move_to(
                RIGHT * (c - 1) * 2.6 + DOWN * r * 0.7)
            cells.add(cell)
        table.add(cells)
    return table


class EntroShopNumbers_Build(Scene):
    """Phase 1: the benchmark table builds row by row, then holds so the
    full table is readable before the winner column highlights."""

    def construct(self):
        make_bg(self)
        table = build_table()
        for i, cells in enumerate(table):
            self.play(FadeIn(cells), run_time=0.35)
            # Hold briefly after each row so a viewer can read it; a longer
            # hold after the header and after the last row.
            hold = 1.2 if i in (0, len(table) - 1) else 0.3
            self.wait(hold)
        self.wait(1.5)


class EntroShopNumbers_Highlight(Scene):
    """Phase 2: the EntroShop column turns green row by row, then holds
    long enough to read every winner stat."""

    def construct(self):
        make_bg(self)
        table = build_table()
        self.add(table)
        for row in table:
            row[2].set_color(GREEN_E)
            self.wait(0.6)
        self.wait(3.0)
```

### docs/manim/pipeline.py

Architecture loop, 2 phases: Build, Loop.

```python
"""Architecture clip, modular: build the loop, then flash one turn.

Render:
    manim render -qh pipeline.py EntroShopPipeline_Build
    manim render -qh pipeline.py EntroShopPipeline_Loop
"""
from manim import *


def make_bg(scene: Scene) -> None:
    bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                   fill_opacity=1.0, stroke_width=0).set_z_index(-10)
    scene.add(bg)


def build_stages() -> VGroup:
    stages = ["parse", "state", "retrieve", "decide"]
    boxes = VGroup()
    for i, name in enumerate(stages):
        box = Rectangle(width=2.2, height=1.0, color=BLUE_D).shift(
            RIGHT * (i - 1.5) * 2.6)
        label = Text(name, font_size=30, color=BLACK).move_to(box.get_center())
        boxes.add(VGroup(box, label))
    return boxes


class EntroShopPipeline_Build(Scene):
    """Phase 1: the four stages appear with arrows between them."""

    def construct(self):
        make_bg(self)
        boxes = build_stages()
        for group in boxes:
            box, label = group
            self.play(Create(box), Write(label), run_time=0.4)
        arrows = VGroup()
        for i in range(3):
            a = Arrow(boxes[i].get_right(), boxes[i + 1].get_left(), color=GREY)
            arrows.add(a)
            self.play(Create(a), run_time=0.25)
        self.wait(0.8)


class EntroShopPipeline_Loop(Scene):
    """Phase 2: one turn flashes stage by stage, token counter stays 0."""

    def construct(self):
        make_bg(self)
        boxes = build_stages()
        self.add(boxes)
        arrows = VGroup(*[
            Arrow(boxes[i].get_right(), boxes[i + 1].get_left(), color=GREY)
            for i in range(3)
        ])
        self.add(arrows)
        counter = Text("tokens: 0", color=GREEN_E).to_edge(DOWN)
        self.play(Write(counter))
        for group in boxes:
            box, label = group
            self.play(box.animate.set_color(YELLOW), run_time=0.25)
            self.play(box.animate.set_color(BLUE_D), run_time=0.25)
        self.wait(1.0)
```

### docs/manim/convergence_policy.py

Convergence policy, 2 phases: Curve, Wall.

```python
"""Convergence policy clip, modular: draw the curve, then the budget wall.

Render:
    manim render -qh convergence_policy.py EntroShopPolicy_Curve
    manim render -qh convergence_policy.py EntroShopPolicy_Wall
"""
from manim import *


def make_bg(scene: Scene) -> None:
    bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                   fill_opacity=1.0, stroke_width=0).set_z_index(-10)
    scene.add(bg)


def make_axes() -> Axes:
    # Tick numbers are plain Text (no LaTeX) so the scene renders without TeX.
    return Axes(
        x_range=[0, 11, 1],
        y_range=[0, 5, 1],
        x_length=9,
        y_length=4,
        axis_config={"include_numbers": False},
    ).shift(DOWN * 0.5)


def add_ticks(scene: Scene, axes: Axes) -> None:
    for t in (0, 5, 10):
        tick = Text(str(t), font_size=20, color=GREY).next_to(
            axes.c2p(t, 0), DOWN * 0.35)
        scene.add(tick)


class EntroShopPolicy_Curve(Scene):
    """Phase 1: the log-pool curve drops turn by turn."""

    def construct(self):
        make_bg(self)
        axes = make_axes()
        self.play(Create(axes))
        add_ticks(self, axes)
        points = [(0, 4.7), (1, 4.0), (2, 3.2), (3, 2.4), (4, 1.8),
                  (5, 1.4), (6, 1.0), (7, 0.6), (8, 0.3), (9, 0.05)]
        line = axes.plot_line_graph(
            x_values=[p[0] for p in points],
            y_values=[p[1] for p in points],
            line_color=TEAL,
            vertex_dot_radius=0.04,
        )
        self.play(Create(line), run_time=2.0)
        self.wait(0.8)


class EntroShopPolicy_Wall(Scene):
    """Phase 2: the red 10-turn budget wall lands on the curve."""

    def construct(self):
        make_bg(self)
        axes = make_axes()
        self.add(axes)
        add_ticks(self, axes)
        points = [(0, 4.7), (1, 4.0), (2, 3.2), (3, 2.4), (4, 1.8),
                  (5, 1.4), (6, 1.0), (7, 0.6), (8, 0.3), (9, 0.05)]
        line = axes.plot_line_graph(
            x_values=[p[0] for p in points],
            y_values=[p[1] for p in points],
            line_color=TEAL,
            vertex_dot_radius=0.04,
        )
        self.add(line)
        wall = DashedLine(axes.c2p(10, 0), axes.c2p(10, 5), color=RED,
                          dash_length=0.1)
        budget = Text("10-turn budget", color=RED, font_size=26).next_to(wall, UP)
        self.play(Create(wall), Write(budget))
        self.wait(1.2)
```

### docs/manim/mcp.py

MCP layer, 2 phases: Build, Hosts.

```python
"""MCP clip, modular: core→tools build, then host logos.

Render:
    manim render -qh mcp.py EntroShopMCP_Build
    manim render -qh mcp.py EntroShopMCP_Hosts
"""
from manim import *

TOOLS = ["search_products", "product_details", "clarify", "tree_chain"]


def make_bg(scene: Scene) -> None:
    bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                   fill_opacity=1.0, stroke_width=0).set_z_index(-10)
    scene.add(bg)


def build_core() -> VGroup:
    core = RoundedRectangle(corner_radius=0.2, width=2.6, height=1.2,
                            color=BLUE_D)
    label = Text("deterministic core", font_size=24, color=BLACK).move_to(
        core.get_center())
    return VGroup(core, label)


def build_tools() -> VGroup:
    cards = VGroup()
    for i, name in enumerate(TOOLS):
        card = RoundedRectangle(corner_radius=0.15, width=3.4, height=0.7,
                                color=GREY).shift(
            DOWN * 1.1 + RIGHT * (i - 1.5) * 3.6)
        label = Text(name, font_size=22, color=BLACK).move_to(card.get_center())
        cards.add(VGroup(card, label))
    return cards


class EntroShopMCP_Build(Scene):
    """Phase 1: core box, four tool cards, wires between them."""

    def construct(self):
        make_bg(self)
        core, core_label = build_core()
        self.play(Create(core), Write(core_label))
        cards = build_tools()
        for card in cards:
            self.play(Create(card[0]), Write(card[1]), run_time=0.35)
        for card in cards:
            wire = Line(core.get_bottom(), card.get_top(), color=TEAL)
            self.play(Create(wire), run_time=0.25)
        self.wait(0.8)


class EntroShopMCP_Hosts(Scene):
    """Phase 2: any MCP host line appears under the wired tools."""

    def construct(self):
        make_bg(self)
        core, core_label = build_core()
        self.add(core, core_label)
        cards = build_tools()
        self.add(cards)
        for card in cards:
            wire = Line(core.get_bottom(), card.get_top(), color=TEAL)
            self.add(wire)
        hosts = Text("Claude  ·  Cursor  ·  VS Code  ·  any MCP host",
                     font_size=26, color=YELLOW).to_edge(DOWN)
        self.play(Write(hosts))
        self.wait(1.5)
```

### docs/manim/scores.py

BM25 baseline vs EntroShop as a table, EntroShop column turns green.

```python
"""Score comparison clip: BM25 baseline vs EntroShop as a table.

Mirrors docs/05-benchmarks.md headline table. Same style as the
Numbers scene (two-column value table), but comparing against the
baseline, row by row with a hold, and the EntroShop column turns green.

Render:
    manim render -qh scores.py EntroShopScores
"""
from manim import *

# (metric, BM25 baseline, EntroShop) — exact values from docs/05.
SCORE_ROWS = [
    ("Metric", "BM25 baseline", "EntroShop"),
    ("Hit rate@10", "0.125", "1.000"),
    ("MRR", "0.068", "0.723"),
    ("MTTC", "9.81", "1.59"),
    ("TechnicalScore", "0.107", "0.9053"),
]


class EntroShopScores(Scene):
    """Benchmark table: one row at a time, then the EntroShop column turns
    green so the winner reads clearly."""

    def construct(self):
        # Explicit light background: the cairo renderer on some macOS setups
        # paints the default dark frame as pure black, so scenes carry their
        # own background and use dark foreground elements.
        bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                       fill_opacity=1.0, stroke_width=0).set_z_index(-10)
        self.add(bg)

        table = VGroup()
        for r, (metric, base, ours) in enumerate(SCORE_ROWS):
            m = Text(metric, font_size=28, color=BLACK).move_to(
                LEFT * 3.4 + DOWN * r * 0.85)
            b = Text(base, font_size=28, color=GREY).move_to(
                DOWN * r * 0.85)
            v = Text(ours, font_size=28, color=BLACK).move_to(
                RIGHT * 3.4 + DOWN * r * 0.85)
            row = VGroup(m, b, v)
            table.add(row)
            self.play(FadeIn(row), run_time=0.35)
            # Hold after the header and after the last row so it can be read.
            self.wait(1.0 if r in (0, len(SCORE_ROWS) - 1) else 0.4)

        # Winner column: EntroShop turns green row by row, then holds.
        for row in table[1:]:
            row[2].set_color(GREEN_E)
            self.wait(0.5)
        self.wait(2.0)
```

### docs/manim/stress.py

Stress battery, 2 phases: Grid, Banner.

```python
"""Stress-test clip, modular: the 300-dot grid, then the banner.

Render:
    manim render -qh stress.py EntroShopStress_Grid
    manim render -qh stress.py EntroShopStress_Banner
"""
from manim import *


def make_bg(scene: Scene) -> None:
    bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                   fill_opacity=1.0, stroke_width=0).set_z_index(-10)
    scene.add(bg)


def build_grid() -> VGroup:
    dots = VGroup()
    for i in range(300):
        x = (i % 30) - 14.5
        y = 4.0 - (i // 30) * 0.55
        dots.add(Dot(np.array([x, y, 0]), radius=0.06, color=GREEN_E))
    return dots


class EntroShopStress_Grid(Scene):
    """Phase 1: the 300-session grid fills in chunk by chunk."""

    def construct(self):
        make_bg(self)
        dots = build_grid()
        for start in range(0, 300, 30):
            self.play(FadeIn(dots[start:start + 30]), run_time=0.15)
        self.wait(0.8)


class EntroShopStress_Banner(Scene):
    """Phase 2: the 300/300 banner appears under the filled grid."""

    def construct(self):
        make_bg(self)
        dots = build_grid()
        self.add(dots)
        banner = Text("300 / 300  Hit@10 = 1.000", color=GREEN_E,
                      font_size=34).to_edge(DOWN)
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
