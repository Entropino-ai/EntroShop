"""Score table clip, modular: build rows, then highlight the winner column.

Render:
    manim render -qh numbers.py EntroShopNumbers_Build
    manim render -qh numbers.py EntroShopNumbers_Highlight
"""
from manim import *

ROWS = [
    ("Metric", "BM25 baseline", "EntroShop"),
    ("Hit rate@10", "0.125", "1.000"),
    ("MRR", "0.068", "0.723"),
    ("MTTC", "9.81", "1.59"),
    ("TechnicalScore", "0.107", "0.9053"),
]


def make_bg(scene: Scene) -> None:
    bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                   fill_opacity=1.0, stroke_width=0).set_z_index(-10)
    scene.add(bg)


def build_table() -> VGroup:
    table = VGroup()
    for r, row in enumerate(ROWS):
        cells = VGroup()
        for c, text in enumerate(row):
            cell = Text(text, font_size=28, color=BLACK).move_to(
                RIGHT * (c - 1) * 2.6 + DOWN * r * 0.7)
            cells.add(cell)
        table.add(cells)
    return table


class EntroShopNumbers_Build(Scene):
    """Phase 1: the benchmark table builds row by row."""

    def construct(self):
        make_bg(self)
        table = build_table()
        for cells in table:
            self.play(FadeIn(cells), run_time=0.35)
        self.wait(0.8)


class EntroShopNumbers_Highlight(Scene):
    """Phase 2: the EntroShop column turns green and holds."""

    def construct(self):
        make_bg(self)
        table = build_table()
        self.add(table)
        for row in table:
            row[2].set_color(GREEN_E)
        self.wait(1.5)
