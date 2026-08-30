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
