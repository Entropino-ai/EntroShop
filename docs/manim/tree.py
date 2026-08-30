"""Tree clip, modular, covering the full 33s Scene-3 VO.

VO lines and their scenes:
  "Under the hood there's an n-ary tree of category properties, coarse to
   fine."                              -> EntroShopTree_Grow
  "Every product maps to exactly one chain." -> EntroShopTree_Chains
  "Category lookups are O(1), and once the tree pins the pool down to a
   small set, we skip the LLM entirely. Zero tokens, and that's most
   turns."                              -> EntroShopTree_Lookup + EntroShopTree_SkipLLM
  "You'll also notice the final pick shows its chain as a breadcrumb, so
   you can see exactly why we chose it." -> EntroShopTree_Breadcrumb

Render:
    manim render -qh tree.py EntroShopTree_Grow
    manim render -qh tree.py EntroShopTree_Chains
    manim render -qh tree.py EntroShopTree_Lookup
    manim render -qh tree.py EntroShopTree_SkipLLM
    manim render -qh tree.py EntroShopTree_Breadcrumb
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


def add_full_tree(scene: Scene) -> list:
    """Draw the complete tree statically and return the node boxes."""
    boxes = [node_box(i) for i in range(len(NODES))]
    scene.add(*[b for box in boxes for b in box])
    scene.add(*[edge_line(a, b) for a, b in EDGES])
    return boxes


def caption(scene: Scene, text: str, color=GREEN_E) -> Text:
    t = Text(text, font_size=28, color=color).to_edge(DOWN, buff=0.7)
    scene.play(Write(t), run_time=0.5)
    return t


class EntroShopTree_Grow(Scene):
    """VO: n-ary tree of category properties, coarse to fine."""

    def construct(self):
        make_bg(self)
        boxes = [node_box(i) for i in range(len(NODES))]
        self.play(Create(boxes[0][0]), Write(boxes[0][1]), run_time=0.6)
        for i in (1, 2, 3):
            self.play(Create(edge_line(0, i)), run_time=0.2)
            self.play(Create(boxes[i][0]), Write(boxes[i][1]), run_time=0.35)
        for i in (4, 5, 6):
            self.play(Create(edge_line(2, i)), run_time=0.2)
            self.play(Create(boxes[i][0]), Write(boxes[i][1]), run_time=0.35)
        for i in (7, 8):
            self.play(Create(edge_line(5, i)), run_time=0.2)
            self.play(Create(boxes[i][0]), Write(boxes[i][1]), run_time=0.35)

        # Coarse -> fine label along the Men branch.
        arrow = Arrow(boxes[0].get_bottom(), boxes[7].get_top(), color=GREY)
        lbl = Text("coarse  →  fine", font_size=26, color=GREY).next_to(
            arrow, LEFT, buff=0.3)
        self.play(Create(arrow), Write(lbl), run_time=0.6)
        self.wait(1.5)


class EntroShopTree_Chains(Scene):
    """VO: every product maps to exactly one chain."""

    def construct(self):
        make_bg(self)
        boxes = add_full_tree(self)

        # Pick three leaf products; each gets its own chain path flashing.
        leaves = [7, 8, 4]  # Belts, Hats, Apparel
        labels = ["belt", "hat", "top"]
        for leaf, name in zip(leaves, labels):
            chain = []
            # Reconstruct path from root to leaf via parents (index-based).
            # Parents: 1,2,3 -> 0 ; 4,5,6 -> 2 ; 7,8 -> 5.
            parents = {1: 0, 2: 0, 3: 0, 4: 2, 5: 2, 6: 2, 7: 5, 8: 5}
            node = leaf
            while node != 0:
                chain.append(node)
                node = parents[node]
            chain.append(0)
            chain = chain[::-1]

            # Flash the chain blue, then label the product below.
            flash = VGroup()
            for a, b in zip(chain, chain[1:]):
                e = edge_line(a, b)
                flash.add(e)
                self.play(e.animate.set_color(BLUE), run_time=0.2)
            for idx in chain:
                self.play(boxes[idx].animate.set_color(BLUE), run_time=0.15)
            tag = Text(f'"{name}" → one chain', font_size=24, color=BLUE).move_to(
                boxes[leaf].get_bottom() + DOWN * 0.6)
            self.play(Write(tag), run_time=0.3)
            self.wait(0.6)
            # Reset colors for the next product.
            for a, b in EDGES:
                edge_line(a, b).set_color(GREY_B)
            for i in range(len(NODES)):
                boxes[i][0].set_color(GREY_B)
                boxes[i][1].set_color(BLACK)
            self.play(FadeOut(tag))

        self.wait(1.0)


class EntroShopTree_Lookup(Scene):
    """VO: category lookups are O(1)."""

    def construct(self):
        make_bg(self)
        boxes = add_full_tree(self)
        for a, b in zip(CHAIN, CHAIN[1:]):
            edge_line(a, b).set_color(YELLOW)
            for idx in (a, b):
                boxes[idx][0].set_color(YELLOW)
                boxes[idx][1].set_color(YELLOW)

        dot = Dot(node_box(CHAIN[0]).get_bottom(), color=TEAL)
        self.add(dot)
        for a, b in zip(CHAIN, CHAIN[1:]):
            self.play(MoveAlongPath(dot, edge_line(a, b)), run_time=0.5)
        cap = caption(self, "O(1) per step")
        self.wait(1.5)
        self.play(FadeOut(cap))


class EntroShopTree_SkipLLM(Scene):
    """VO: once the tree pins the pool small, skip the LLM. 0 tokens."""

    def construct(self):
        make_bg(self)
        boxes = add_full_tree(self)

        # The pool shrinks to the Belts subtree.
        pool = Text("pool", font_size=26, color=BLACK).move_to(
            boxes[0].get_top() + UP * 0.8)
        self.play(Write(pool))
        for idx in CHAIN[1:]:
            self.play(boxes[idx][0].animate.set_color(TEAL),
                      boxes[idx][1].animate.set_color(TEAL), run_time=0.2)
        small = Text("pinned: 1 subtree", font_size=24, color=TEAL).next_to(
            pool, RIGHT, buff=0.5)
        self.play(Write(small), run_time=0.4)

        # LLM box gets crossed out.
        llm = RoundedRectangle(corner_radius=0.15, width=2.2, height=0.8,
                               color=GREY).shift(RIGHT * 4.4 + DOWN * 1.6)
        llm_txt = Text("LLM", font_size=26, color=BLACK).move_to(llm.get_center())
        self.play(Create(llm), Write(llm_txt), run_time=0.4)
        cross = Line(llm.get_corner(UL), llm.get_corner(DR), color=RED,
                     stroke_width=6)
        self.play(Create(cross), run_time=0.3)

        zero = Text("0 tokens · most turns", font_size=30, color=GREEN_E).to_edge(
            DOWN, buff=0.7)
        self.play(Write(zero), run_time=0.5)
        self.wait(2.0)


class EntroShopTree_Breadcrumb(Scene):
    """VO: the final pick shows its chain as a breadcrumb."""

    def construct(self):
        make_bg(self)
        boxes = add_full_tree(self)
        for a, b in zip(CHAIN, CHAIN[1:]):
            self.play(edge_line(a, b).animate.set_color(YELLOW), run_time=0.3)
            for idx in (a, b):
                self.play(boxes[idx][0].animate.set_color(YELLOW),
                          boxes[idx][1].animate.set_color(YELLOW), run_time=0.2)

        # Breadcrumb strip at the bottom: Catalog > Men > Accessories > Belts.
        crumb = Text("Catalog  >  Men  >  Accessories  >  Belts",
                     font_size=30, color=BLACK).to_edge(DOWN, buff=0.7)
        self.play(Write(crumb), run_time=0.8)
        self.wait(2.0)
