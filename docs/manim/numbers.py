"""Close clip: benchmark table builds row by row, winner highlighted.

Render:
    manim render -qh numbers.py EntroShopNumbers
"""
from manim import *


class EntroShopNumbers(Scene):
    """Score table appears row by row; the EntroShop column goes green."""

    def construct(self):
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
            row[2].set_color(GREEN)
        self.wait(1.5)
