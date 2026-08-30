"""Score comparison clip: BM25 baseline vs EntroShop bars.

Mirrors docs/05-benchmarks.md headline table. Render:
    manim render -qh scores.py EntroShopScores
"""
from manim import *


class EntroShopScores(Scene):
    """Four metrics, two bars each; EntroShop wins every pair."""

    def construct(self):
        metrics = [
            ("Hit rate@10", 0.125, 1.000),
            ("MRR",         0.068, 0.723),
            ("MTTC (lower is better)", 0.119, 0.941),  # normalized efficiency proxy
            ("TechnicalScore", 0.107, 0.905),
        ]
        # Explicit light background: the cairo renderer on some macOS setups
        # paints the default dark frame as pure black, so scenes carry their
        # own background and use dark foreground elements.
        bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                       fill_opacity=1.0, stroke_width=0).set_z_index(-10)
        self.add(bg)
        group = VGroup()
        for r, (name, base, ours) in enumerate(metrics):
            label = Text(name, font_size=24).move_to(LEFT * 4.2 + DOWN * r * 1.1)
            group.add(label)
            base_bar = Rectangle(width=base * 5, height=0.3, color=GREY).move_to(
                LEFT * 2.0 + DOWN * r * 1.1, aligned_edge=LEFT)
            ours_bar = Rectangle(width=ours * 5, height=0.3, color=TEAL).move_to(
                LEFT * 2.0 + DOWN * r * 1.1, aligned_edge=LEFT)
            group.add(base_bar, ours_bar)
            self.play(FadeIn(label), GrowFromEdge(base_bar, LEFT), run_time=0.4)
            self.play(GrowFromEdge(ours_bar, LEFT), run_time=0.4)
        legend = Text("grey: BM25 baseline   teal: EntroShop",
                      font_size=22, color=GREY_B).to_edge(DOWN)
        self.play(Write(legend))
        self.wait(1.5)
