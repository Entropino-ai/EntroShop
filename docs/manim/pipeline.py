"""Architecture clip, modular: build the loop, then flash one turn.

Render:
    manim render -qh pipeline.py EntroShopPipeline_Build
    manim render -qh pipeline.py EntroShopPipeline_Loop
"""
from manim import *


def make_bg(scene: Scene) -> None:
    bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                   fill_opacity=1.0, stroke_width=0).set_z_index(-10)
    scene.add(bg)


def build_stages() -> VGroup:
    stages = ["parse", "state", "retrieve", "decide"]
    boxes = VGroup()
    for i, name in enumerate(stages):
        box = Rectangle(width=2.2, height=1.0, color=BLUE_D).shift(
            RIGHT * (i - 1.5) * 2.6)
        label = Text(name, font_size=30, color=BLACK).move_to(box.get_center())
        boxes.add(VGroup(box, label))
    return boxes


class EntroShopPipeline_Build(Scene):
    """Phase 1: the four stages appear with arrows between them."""

    def construct(self):
        make_bg(self)
        boxes = build_stages()
        for group in boxes:
            box, label = group
            self.play(Create(box), Write(label), run_time=0.4)
        arrows = VGroup()
        for i in range(3):
            a = Arrow(boxes[i].get_right(), boxes[i + 1].get_left(), color=GREY)
            arrows.add(a)
            self.play(Create(a), run_time=0.25)
        self.wait(0.8)


class EntroShopPipeline_Loop(Scene):
    """Phase 2: one turn flashes stage by stage, token counter stays 0."""

    def construct(self):
        make_bg(self)
        boxes = build_stages()
        self.add(boxes)
        arrows = VGroup(*[
            Arrow(boxes[i].get_right(), boxes[i + 1].get_left(), color=GREY)
            for i in range(3)
        ])
        self.add(arrows)
        counter = Text("tokens: 0", color=GREEN_E).to_edge(DOWN)
        self.play(Write(counter))
        for group in boxes:
            box, label = group
            self.play(box.animate.set_color(YELLOW), run_time=0.25)
            self.play(box.animate.set_color(BLUE_D), run_time=0.25)
        self.wait(1.0)
