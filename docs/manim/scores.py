"""Score comparison clip: BM25 baseline vs EntroShop as a table.

Mirrors docs/05-benchmarks.md headline table. Same style as the
Numbers scene (two-column value table), but comparing against the
baseline, row by row with a hold, and the EntroShop column turns green.

Render:
    manim render -qh scores.py EntroShopScores
"""
from manim import *

# (metric, BM25 baseline, EntroShop) — exact values from docs/05.
SCORE_ROWS = [
    ("Metric", "BM25 baseline", "EntroShop"),
    ("Hit rate@10", "0.125", "1.000"),
    ("MRR", "0.068", "0.723"),
    ("MTTC", "9.81", "1.59"),
    ("TechnicalScore", "0.107", "0.9053"),
]


class EntroShopScores(Scene):
    """Benchmark table: one row at a time, then the EntroShop column turns
    green so the winner reads clearly."""

    def construct(self):
        # Explicit light background: the cairo renderer on some macOS setups
        # paints the default dark frame as pure black, so scenes carry their
        # own background and use dark foreground elements.
        bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                       fill_opacity=1.0, stroke_width=0).set_z_index(-10)
        self.add(bg)

        table = VGroup()
        for r, (metric, base, ours) in enumerate(SCORE_ROWS):
            m = Text(metric, font_size=28, color=BLACK).move_to(
                LEFT * 3.4 + DOWN * r * 0.85)
            b = Text(base, font_size=28, color=GREY).move_to(
                DOWN * r * 0.85)
            v = Text(ours, font_size=28, color=BLACK).move_to(
                RIGHT * 3.4 + DOWN * r * 0.85)
            row = VGroup(m, b, v)
            table.add(row)
            self.play(FadeIn(row), run_time=0.35)
            # Hold after the header and after the last row so it can be read.
            self.wait(1.0 if r in (0, len(SCORE_ROWS) - 1) else 0.4)

        # Winner column: EntroShop turns green row by row, then holds.
        for row in table[1:]:
            row[2].set_color(GREEN_E)
            self.wait(0.5)
        self.wait(2.0)
