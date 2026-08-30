"""Convergence policy clip: pool size vs turn, with the clamp at 10.

Mirrors docs/02-architecture.md "Convergence policy". Render:
    manim render -qh convergence_policy.py EntroShopPolicy
"""
from manim import *


class EntroShopPolicy(Scene):
    """Pool shrinks turn by turn; the 10-turn budget is drawn as a wall."""

    def construct(self):
        # Explicit light background: the cairo renderer on some macOS setups
        # paints the default dark frame as pure black, so scenes carry their
        # own background and use dark foreground elements.
        bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                       fill_opacity=1.0, stroke_width=0).set_z_index(-10)
        self.add(bg)
        # Axes: turns (x) vs log pool size (y). Tick numbers are added as
        # plain Text so the scene renders without a TeX install.
        axes = Axes(
            x_range=[0, 11, 1],
            y_range=[0, 5, 1],
            x_length=9,
            y_length=4,
            axis_config={"include_numbers": False},
        ).shift(DOWN * 0.5)
        self.play(Create(axes))
        for t in (0, 5, 10):
            tick = Text(str(t), font_size=20, color=GREY_B).next_to(
                axes.c2p(t, 0), DOWN * 0.35)
            self.play(FadeIn(tick), run_time=0.15)

        # Pool halves-ish each turn: 50k -> 28 -> 3 -> 1 on a log scale.
        points = [(0, 4.7), (1, 4.0), (2, 3.2), (3, 2.4), (4, 1.8),
                  (5, 1.4), (6, 1.0), (7, 0.6), (8, 0.3), (9, 0.05)]
        line = axes.plot_line_graph(
            x_values=[p[0] for p in points],
            y_values=[p[1] for p in points],
            line_color=TEAL,
            vertex_dot_radius=0.04,
        )
        self.play(Create(line), run_time=2.0)

        # The 10-turn budget wall.
        wall = DashedLine(
            axes.c2p(10, 0), axes.c2p(10, 5), color=RED, dash_length=0.1
        )
        budget = Text("10-turn budget", color=RED, font_size=26).next_to(wall, UP)
        self.play(Create(wall), Write(budget))
        self.wait(1.5)
