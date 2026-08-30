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
