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
