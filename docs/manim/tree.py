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

        # O(1) lookup flash: a dot races down the path, one edge at a time.
        dot = Dot(root.get_bottom(), color=TEAL)
        self.play(MoveAlongPath(dot, edges[0]), run_time=0.6)
        self.play(MoveAlongPath(dot, edges[1]), run_time=0.6)
        self.wait(1.0)
