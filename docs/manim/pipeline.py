"""Architecture clip: message -> parse -> state -> retrieve -> decide.

Mirrors docs/02-architecture.md "Pipeline". Render:
    manim render -qh pipeline.py EntroShopPipeline
"""
from manim import *


class EntroShopPipeline(Scene):
    """The four-stage turn loop, shown as boxes with a token counter."""

    def construct(self):
        # Explicit light background: the cairo renderer on some macOS setups
        # paints the default dark frame as pure black, so scenes carry their
        # own background and use dark foreground elements.
        bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                       fill_opacity=1.0, stroke_width=0).set_z_index(-10)
        self.add(bg)
        stages = ["parse", "state", "retrieve", "decide"]
        boxes = VGroup()
        for i, name in enumerate(stages):
            box = Rectangle(width=2.2, height=1.0, color=BLUE_D).shift(RIGHT * (i - 1.5) * 2.6)
            label = Text(name, font_size=30).move_to(box.get_center())
            boxes.add(VGroup(box, label))
            self.play(Create(box), Write(label), run_time=0.4)

        # Arrows between stages.
        arrows = VGroup()
        for i in range(3):
            a = Arrow(boxes[i].get_right(), boxes[i + 1].get_left(), color=GREY_B)
            arrows.add(a)
            self.play(Create(a), run_time=0.25)

        # Token counter stays zero through the loop.
        counter = Text("tokens: 0", color=GREEN).to_edge(DOWN)
        self.play(Write(counter))

        # One full loop flash: highlight each box in turn.
        for i in range(4):
            self.play(boxes[i].animate.set_color(YELLOW), run_time=0.25)
            self.play(boxes[i].animate.set_color(BLUE), run_time=0.25)
        self.wait(1.0)
