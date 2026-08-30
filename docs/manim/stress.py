"""Stress-test clip, modular: the 300-dot grid, then the banner.

Render:
    manim render -qh stress.py EntroShopStress_Grid
    manim render -qh stress.py EntroShopStress_Banner
"""
from manim import *


def make_bg(scene: Scene) -> None:
    bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                   fill_opacity=1.0, stroke_width=0).set_z_index(-10)
    scene.add(bg)


def build_grid() -> VGroup:
    dots = VGroup()
    for i in range(300):
        x = (i % 30) - 14.5
        y = 4.0 - (i // 30) * 0.55
        dots.add(Dot(np.array([x, y, 0]), radius=0.06, color=GREEN_E))
    return dots


class EntroShopStress_Grid(Scene):
    """Phase 1: the 300-session grid fills in chunk by chunk."""

    def construct(self):
        make_bg(self)
        dots = build_grid()
        for start in range(0, 300, 30):
            self.play(FadeIn(dots[start:start + 30]), run_time=0.15)
        self.wait(0.8)


class EntroShopStress_Banner(Scene):
    """Phase 2: the 300/300 banner appears under the filled grid."""

    def construct(self):
        make_bg(self)
        dots = build_grid()
        self.add(dots)
        banner = Text("300 / 300  Hit@10 = 1.000", color=GREEN_E,
                      font_size=34).to_edge(DOWN)
        self.play(Write(banner))
        self.wait(1.5)
