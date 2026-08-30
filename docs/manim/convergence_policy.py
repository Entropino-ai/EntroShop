"""Convergence policy clip, modular: draw the curve, then the budget wall.

Render:
    manim render -qh convergence_policy.py EntroShopPolicy_Curve
    manim render -qh convergence_policy.py EntroShopPolicy_Wall
"""
from manim import *


def make_bg(scene: Scene) -> None:
    bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                   fill_opacity=1.0, stroke_width=0).set_z_index(-10)
    scene.add(bg)


def make_axes() -> Axes:
    # Tick numbers are plain Text (no LaTeX) so the scene renders without TeX.
    return Axes(
        x_range=[0, 11, 1],
        y_range=[0, 5, 1],
        x_length=9,
        y_length=4,
        axis_config={"include_numbers": False},
    ).shift(DOWN * 0.5)


def add_ticks(scene: Scene, axes: Axes) -> None:
    for t in (0, 5, 10):
        tick = Text(str(t), font_size=20, color=GREY).next_to(
            axes.c2p(t, 0), DOWN * 0.35)
        scene.add(tick)


class EntroShopPolicy_Curve(Scene):
    """Phase 1: the log-pool curve drops turn by turn."""

    def construct(self):
        make_bg(self)
        axes = make_axes()
        self.play(Create(axes))
        add_ticks(self, axes)
        points = [(0, 4.7), (1, 4.0), (2, 3.2), (3, 2.4), (4, 1.8),
                  (5, 1.4), (6, 1.0), (7, 0.6), (8, 0.3), (9, 0.05)]
        line = axes.plot_line_graph(
            x_values=[p[0] for p in points],
            y_values=[p[1] for p in points],
            line_color=TEAL,
            vertex_dot_radius=0.04,
        )
        self.play(Create(line), run_time=2.0)
        self.wait(0.8)


class EntroShopPolicy_Wall(Scene):
    """Phase 2: the red 10-turn budget wall lands on the curve."""

    def construct(self):
        make_bg(self)
        axes = make_axes()
        self.add(axes)
        add_ticks(self, axes)
        points = [(0, 4.7), (1, 4.0), (2, 3.2), (3, 2.4), (4, 1.8),
                  (5, 1.4), (6, 1.0), (7, 0.6), (8, 0.3), (9, 0.05)]
        line = axes.plot_line_graph(
            x_values=[p[0] for p in points],
            y_values=[p[1] for p in points],
            line_color=TEAL,
            vertex_dot_radius=0.04,
        )
        self.add(line)
        wall = DashedLine(axes.c2p(10, 0), axes.c2p(10, 5), color=RED,
                          dash_length=0.1)
        budget = Text("10-turn budget", color=RED, font_size=26).next_to(wall, UP)
        self.play(Create(wall), Write(budget))
        self.wait(1.2)
