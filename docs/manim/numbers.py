"""Close clip: benchmark table builds row by row, winner highlighted.

Render:
    manim render -qh numbers.py EntroShopNumbers
"""
from manim import *


class EntroShopNumbers(Scene):
    """Score table appears row by row; the EntroShop column goes green."""

    def construct(self):
        # Explicit light background: the cairo renderer on some macOS setups
        # paints the default dark frame as pure black, so scenes carry their
        # own background and use dark foreground elements.
        bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                       fill_opacity=1.0, stroke_width=0).set_z_index(-10)
        self.add(bg)
        rows = [
            ("Metric",      "BM25 baseline",  "EntroShop"),
            ("Hit rate@10", "0.125",          "1.000"),
            ("MRR",         "0.068",          "0.723"),
            ("MTTC",        "9.81",           "1.59"),
            ("TechnicalScore", "0.107",       "0.9053"),
        ]
        table = VGroup()
        for r, row in enumerate(rows):
            cells = VGroup()
            for c, text in enumerate(row):
                cell = Text(text, font_size=28).move_to(
                    RIGHT * (c - 1) * 2.6 + DOWN * r * 0.7)
                cells.add(cell)
            table.add(cells)
            self.play(FadeIn(cells), run_time=0.35)
        # Highlight the EntroShop column.
        for row in table:
            row[2].set_color(GREEN_E)
        self.wait(1.5)
