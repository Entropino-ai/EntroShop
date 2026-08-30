"""Open clip, modular: each phase is its own Scene and renders to its own mp4.

Render all (or just the ones you need):
    manim render -qh convergence.py EntroShopOpen_Cloud
    manim render -qh convergence.py EntroShopOpen_Target
    manim render -qh convergence.py EntroShopOpen_Rings
    manim render -qh convergence.py EntroShopOpen_Collapse
    manim render -qh convergence.py EntroShopOpen_Score
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
    """Phase 5: the score punchline fades in and holds."""

    def construct(self):
        make_bg(self)
        score = Text("200/200  ·  1.59 turns  ·  0 tokens",
                     color=GREEN_E).scale(0.8)
        self.play(Write(score), run_time=1.0)
        self.wait(1.5)
