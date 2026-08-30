"""Open clip: 50,000 catalog points collapse to a single target.

Render:
    manim render -qh convergence.py EntroShopConvergence
"""
from manim import *
import numpy as np


class EntroShopConvergence(Scene):
    """50k dots → one bright target → ten inward rings → all sweep in."""

    def construct(self):
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
