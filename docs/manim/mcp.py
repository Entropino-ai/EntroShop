"""MCP clip, modular: core→tools build, then host logos.

Render:
    manim render -qh mcp.py EntroShopMCP_Build
    manim render -qh mcp.py EntroShopMCP_Hosts
"""
from manim import *

TOOLS = ["search_products", "product_details", "clarify", "tree_chain"]


def make_bg(scene: Scene) -> None:
    bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                   fill_opacity=1.0, stroke_width=0).set_z_index(-10)
    scene.add(bg)


def build_core() -> VGroup:
    core = RoundedRectangle(corner_radius=0.2, width=2.6, height=1.2,
                            color=BLUE_D)
    label = Text("deterministic core", font_size=24, color=BLACK).move_to(
        core.get_center())
    return VGroup(core, label)


def build_tools() -> VGroup:
    cards = VGroup()
    for i, name in enumerate(TOOLS):
        card = RoundedRectangle(corner_radius=0.15, width=3.4, height=0.7,
                                color=GREY).shift(
            DOWN * 1.1 + RIGHT * (i - 1.5) * 3.6)
        label = Text(name, font_size=22, color=BLACK).move_to(card.get_center())
        cards.add(VGroup(card, label))
    return cards


class EntroShopMCP_Build(Scene):
    """Phase 1: core box, four tool cards, wires between them."""

    def construct(self):
        make_bg(self)
        core, core_label = build_core()
        self.play(Create(core), Write(core_label))
        cards = build_tools()
        for card in cards:
            self.play(Create(card[0]), Write(card[1]), run_time=0.35)
        for card in cards:
            wire = Line(core.get_bottom(), card.get_top(), color=TEAL)
            self.play(Create(wire), run_time=0.25)
        self.wait(0.8)


class EntroShopMCP_Hosts(Scene):
    """Phase 2: any MCP host line appears under the wired tools."""

    def construct(self):
        make_bg(self)
        core, core_label = build_core()
        self.add(core, core_label)
        cards = build_tools()
        self.add(cards)
        for card in cards:
            wire = Line(core.get_bottom(), card.get_top(), color=TEAL)
            self.add(wire)
        hosts = Text("Claude  ·  Cursor  ·  VS Code  ·  any MCP host",
                     font_size=26, color=YELLOW).to_edge(DOWN)
        self.play(Write(hosts))
        self.wait(1.5)
