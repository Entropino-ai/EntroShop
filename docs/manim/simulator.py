"""Simulator-disclosure clip: verbatim metadata, exact match, phrase trie.

Covers the 33-second Scene 1 VO:
  "First, let's talk about what the simulator gives us. It doesn't
   paraphrase anything. The customer literally repeats the product's own
   metadata, word for word. You ask about material, you get 'leather'
   back, exactly as written. So what we're doing here is exact matching.
   We built a phrase trie over the whole catalog, plus a few regexes for
   things like `color: x` and budget."

Modular scenes (one clip each):
    manim render -qh simulator.py EntroShopSim_Reveal     # product card fields
    manim render -qh simulator.py EntroShopSim_ExactMatch # input -> 'leather'
    manim render -qh simulator.py EntroShopSim_Trie       # colorful phrase trie
    manim render -qh simulator.py EntroShopSim_Regex      # color: x, budget
"""
from manim import *


def make_bg(scene: Scene) -> None:
    bg = Rectangle(width=14.22, height=8.0, fill_color=WHITE,
                   fill_opacity=1.0, stroke_width=0).set_z_index(-10)
    scene.add(bg)


def title(scene: Scene, text: str) -> Text:
    t = Text(text, font_size=30, color=BLACK).to_edge(UP, buff=0.4)
    scene.play(Write(t), run_time=0.5)
    return t


class EntroShopSim_Reveal(Scene):
    """A product card appears; its metadata fields highlight one by one,
    then the 'verbatim' stamp lands."""

    def construct(self):
        make_bg(self)
        ttl = title(self, "the simulator hands you the data")

        # Product card: title box plus three field rows. The card is placed
        # high enough that the stamp below it never collides with fields.
        card = RoundedRectangle(corner_radius=0.15, width=6.6, height=4.6,
                                color=GREY_B).shift(LEFT * 0.6 + UP * 0.5)
        card_title = Text("Product", font_size=26, color=BLACK).move_to(
            card.get_top() + DOWN * 0.6)
        fields = [
            ("material:", "leather"),
            ("color:", "black"),
            ("features:", "Ribbon Inlay, Harness Buckle"),
        ]
        rows = VGroup()
        for i, (k, v) in enumerate(fields):
            # Anchor each key to the card center with a fixed downward step;
            # the value sits to the right via next_to so it never overlaps.
            key = Text(k, font_size=24, color=BLACK).move_to(
                card.get_center() + UP * 0.9 + DOWN * (i * 0.9))
            val = Text(v, font_size=24, color=DARK_BLUE).next_to(
                key, RIGHT, buff=0.35)
            rows.add(VGroup(key, val))

        self.play(Create(card), Write(card_title), run_time=0.7)
        for row in rows:
            self.play(Write(row), run_time=0.4)
            self.wait(0.6)

        # Verbatim stamp: well below the card bottom, clear of the fields.
        stamp = Text("repeated verbatim, word for word", font_size=26,
                     color=GREEN_E).move_to(card.get_bottom() + DOWN * 1.0)
        self.play(Write(stamp))
        self.wait(1.2)
        self.play(FadeOut(card_title), *[FadeOut(r) for r in rows],
                  FadeOut(stamp), FadeOut(card))
        self.wait(0.3)


class EntroShopSim_ExactMatch(Scene):
    """Ask material -> get 'leather' back exactly as written."""

    def construct(self):
        make_bg(self)
        ttl = title(self, "exact matching")

        # Question bubble on the left, answer bubble on the right.
        q = RoundedRectangle(corner_radius=0.3, width=4.4, height=1.1,
                             fill_color=LIGHT_GREY, fill_opacity=1.0,
                             color=GREY_B).shift(LEFT * 3.4 + UP * 0.8)
        q_text = Text("you ask: material?", font_size=28, color=BLACK).move_to(
            q.get_center())
        self.play(Create(q), Write(q_text))

        a = RoundedRectangle(corner_radius=0.3, width=4.4, height=1.1,
                             fill_color=GREEN_A, fill_opacity=1.0,
                             color=GREEN_E).shift(RIGHT * 3.4 + UP * 0.8)
        a_text = Text('customer: "leather"', font_size=28, color=BLACK).move_to(
            a.get_center())
        self.play(Create(a), Write(a_text))

        # Equality: both strings are byte-identical.
        eq = Text("leather == leather", font_size=30, color=GREEN_E).to_edge(
            DOWN, buff=1.0)
        self.play(Write(eq))
        self.wait(1.5)
        self.play(FadeOut(q), FadeOut(q_text), FadeOut(a), FadeOut(a_text),
                  FadeOut(eq))
        self.wait(0.3)


class EntroShopSim_Trie(Scene):
    """A colorful phrase trie over the catalog; searching 'leather' flashes
    the root -> l -> leather path."""

    def construct(self):
        make_bg(self)
        ttl = title(self, "phrase trie over the whole catalog")

        # Trie layout: root, then branches for b/l/c/w.
        root_pos = np.array([0.0, 2.8, 0])
        branch_pos = {
            "b": np.array([-5.4, 0.9, 0]),
            "l": np.array([-1.8, 0.9, 0]),
            "c": np.array([1.8, 0.9, 0]),
            "w": np.array([5.4, 0.9, 0]),
        }
        leaf_pos = {
            "belt": np.array([-6.2, -1.4, 0]),
            "leather": np.array([-2.6, -1.4, 0]),
            "cotton": np.array([1.0, -1.4, 0]),
            "wool": np.array([4.6, -1.4, 0]),
        }
        branch_colors = {"b": BLUE, "l": TEAL, "c": PURPLE, "w": ORANGE}

        def box(label: str, pos: np.ndarray, color) -> VGroup:
            r = RoundedRectangle(corner_radius=0.2, width=2.1, height=0.85,
                                 fill_color=LIGHT_GREY, fill_opacity=1.0,
                                 color=color)
            t = Text(label, font_size=22, color=BLACK)
            return VGroup(r, t).move_to(pos)

        def edge(a: np.ndarray, b: np.ndarray, color) -> Line:
            return Line(a, b, color=color)

        root = box("catalog phrases", root_pos, GOLD)
        self.play(Create(root[0]), Write(root[1]), run_time=0.6)

        # Branches: node + edge, each branch its own color.
        branch_boxes, leaf_boxes, edges = {}, {}, []
        for k, pos in branch_pos.items():
            b = box(k, pos, branch_colors[k])
            branch_boxes[k] = b
            edges.append(edge(root.get_bottom(), b.get_top(), branch_colors[k]))
            self.play(Create(b[0]), Write(b[1]), Create(edges[-1]),
                      run_time=0.35)
        for word, pos in leaf_pos.items():
            lb = box(word, pos, branch_colors[word[0]])
            leaf_boxes[word] = lb
            edges.append(edge(branch_boxes[word[0]].get_bottom(),
                              lb.get_top(), branch_colors[word[0]]))
            self.play(Create(lb[0]), Write(lb[1]), Create(edges[-1]),
                      run_time=0.35)
        self.wait(0.5)

        # Search 'leather': highlight root -> l -> leather, then pulse.
        chain = [root, branch_boxes["l"], leaf_boxes["leather"]]
        for i, node in enumerate(chain):
            node[0].set_fill(YELLOW, opacity=0.35)
            node[0].set_color(YELLOW)
            node[1].set_color(YELLOW)
            self.play(node.animate.scale(1.12), run_time=0.2)
            self.play(node.animate.scale(1.0 / 1.12), run_time=0.2)
        found = Text('"leather" found, O(1) per step', font_size=26,
                     color=GREEN_E).to_edge(DOWN, buff=1.0)
        self.play(Write(found))
        self.wait(1.5)
        self.play(FadeOut(found))
        self.wait(0.3)


class EntroShopSim_Regex(Scene):
    """Regexes catch synthetic constraints: color: x and budget.

    Two explicit columns: chat input on the left, the matching regex on the
    right, so nothing overlaps horizontally.
    """

    def construct(self):
        make_bg(self)
        ttl = title(self, "regexes for synthetic constraints")

        # Two chat lines, stacked in the left column.
        line1 = Text("customer: color is black", font_size=28, color=BLACK).move_to(
            LEFT * 4.2 + UP * 0.9)
        line2 = Text("customer: under 30 dollars", font_size=28,
                     color=BLACK).move_to(LEFT * 4.2 + DOWN * 0.9)
        self.play(Write(line1), run_time=0.4)
        self.play(Write(line2), run_time=0.4)

        # Regex patterns in the right column, aligned to each chat line.
        pat1 = Text(r"regex: color:\s*x", font_size=26, color=TEAL).move_to(
            RIGHT * 2.2 + UP * 0.9)
        pat2 = Text(r"regex: budget (\$\d+)", font_size=26, color=ORANGE).move_to(
            RIGHT * 2.2 + DOWN * 0.9)
        self.play(Write(pat1), Write(pat2), run_time=0.5)

        # Matched substrings, below each pattern.
        hit1 = Text("→ color: black", font_size=24, color=GREEN_E).next_to(
            pat1, DOWN, buff=0.55)
        hit2 = Text("→ $30", font_size=24, color=GREEN_E).next_to(
            pat2, DOWN, buff=0.55)
        self.play(Write(hit1), Write(hit2))
        self.wait(1.8)
        self.play(FadeOut(line1), FadeOut(line2), FadeOut(pat1), FadeOut(pat2),
                  FadeOut(hit1), FadeOut(hit2))
        self.wait(0.3)
