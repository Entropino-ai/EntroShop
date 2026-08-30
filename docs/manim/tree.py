"""Tree clip, modular: growth, breadcrumb, lookup are separate Scenes.

Render:
    manim render -qh tree.py EntroShopTree_Grow
    manim render -qh tree.py EntroShopTree_Breadcrumb
    manim render -qh tree.py EntroShopTree_Lookup
"""
from manim import *


def make_tree():
    root = Text("Catalog", color=BLACK).move_to(UP * 3)
    mid = Text("Men", color=BLACK).next_to(root, DOWN, buff=0.9)
    leaf = Text("Belts", color=BLACK).next_to(mid, DOWN, buff=0.9)
    edges = VGroup(
        Line(root.get_bottom(), mid.get_top(), color=GREY),
        Line(mid.get_bottom(), leaf.get_top(), color=GREY),
    )
    return root, mid, leaf, edges


def make_bg(scene: Scene) -> None:
    bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                   fill_opacity=1.0, stroke_width=0).set_z_index(-10)
    scene.add(bg)


class EntroShopTree_Grow(Scene):
    """Phase 1: the coarse-to-fine tree grows top-down."""

    def construct(self):
        make_bg(self)
        root, mid, leaf, edges = make_tree()
        self.play(Write(root))
        self.play(Write(mid))
        self.play(Write(leaf))
        self.play(Create(edges))
        self.wait(1.0)


class EntroShopTree_Breadcrumb(Scene):
    """Phase 2: the final pick's root→leaf chain highlights yellow."""

    def construct(self):
        make_bg(self)
        root, mid, leaf, edges = make_tree()
        self.add(root, mid, leaf, edges)
        self.play(edges.animate.set_color(YELLOW))
        self.play(
            root.animate.set_color(YELLOW),
            mid.animate.set_color(YELLOW),
            leaf.animate.set_color(YELLOW),
        )
        self.wait(1.2)


class EntroShopTree_Lookup(Scene):
    """Phase 3: an O(1) lookup dot races down the chain, edge by edge."""

    def construct(self):
        make_bg(self)
        root, mid, leaf, edges = make_tree()
        self.add(root, mid, leaf, edges)
        dot = Dot(root.get_bottom(), color=TEAL)
        self.play(MoveAlongPath(dot, edges[0]), run_time=0.6)
        self.play(MoveAlongPath(dot, edges[1]), run_time=0.6)
        self.wait(1.0)
