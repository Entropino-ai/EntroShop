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
