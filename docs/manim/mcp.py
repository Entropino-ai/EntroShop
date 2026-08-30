"""MCP clip: four tools exposed over stdio/HTTP to any host.

Mirrors docs/03-modules.md (agent_lib/mcp.py) and the README MCP section.
Render:
    manim render -qh mcp.py EntroShopMCP
"""
from manim import *


class EntroShopMCP(Scene):
    """A core box feeds four tool cards; host logos connect from the side."""

    def construct(self):
        # Explicit light background: the cairo renderer on some macOS setups
        # paints the default dark frame as pure black, so scenes carry their
        # own background and use dark foreground elements.
        bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                       fill_opacity=1.0, stroke_width=0).set_z_index(-10)
        self.add(bg)
        core = RoundedRectangle(corner_radius=0.2, width=2.6, height=1.2,
                                color=BLUE_D)
        core_label = Text("deterministic core", font_size=24).move_to(core.get_center())
        self.play(Create(core), Write(core_label))

        tools = ["search_products", "product_details", "clarify", "tree_chain"]
        cards = VGroup()
        for i, name in enumerate(tools):
            card = RoundedRectangle(corner_radius=0.15, width=3.4, height=0.7,
                                    color=GREY_B).shift(
                DOWN * 1.1 + RIGHT * (i - 1.5) * 3.6)
            label = Text(name, font_size=22).move_to(card.get_center())
            cards.add(VGroup(card, label))
            self.play(Create(card), Write(label), run_time=0.35)

        # Wires from core to each tool.
        for card in cards:
            wire = Line(core.get_bottom(), card.get_top(), color=TEAL)
            self.play(Create(wire), run_time=0.25)

        # Hosts: Claude, Cursor, VS Code, anything.
        hosts = Text("Claude  ·  Cursor  ·  VS Code  ·  any MCP host",
                     font_size=26, color=YELLOW).to_edge(DOWN)
        self.play(Write(hosts))
        self.wait(1.5)
