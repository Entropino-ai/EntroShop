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
    """Phase 1: the benchmark table builds row by row, then holds so the
    full table is readable before the winner column highlights."""

    def construct(self):
        make_bg(self)
        table = build_table()
        for i, cells in enumerate(table):
            self.play(FadeIn(cells), run_time=0.35)
            # Hold briefly after each row so a viewer can read it; a longer
            # hold after the header and after the last row.
            hold = 1.2 if i in (0, len(table) - 1) else 0.3
            self.wait(hold)
        self.wait(1.5)


class EntroShopNumbers_Highlight(Scene):
    """Phase 2: the EntroShop column turns green row by row, then holds
    long enough to read every winner stat."""

    def construct(self):
        make_bg(self)
        table = build_table()
        self.add(table)
        for row in table:
            row[2].set_color(GREEN_E)
            self.wait(0.6)
        self.wait(3.0)
