"""Convergent guidance for free-form chat (anti-divergence engine).

Design grounded in:
- EAR, Estimation-Action-Reflection (arXiv:2002.09102): estimate when to
  ask vs recommend, reflect after each action.
- Mixed-initiative conversational search (arXiv:2204.08046): the system
  proposes concrete facet options; the user picks instead of typing.
- Personalized interactive faceted search (WWW 2008): show facet values
  with counts from the CURRENT candidate pool (dynamic faceted navigation).
- ReAct (arXiv:2210.03629): act -> observe -> terminate; here the "observe"
  step detects no-progress turns and forces convergence.

Like progressive rendering, every turn re-renders a refined result set and
the session terminates once further refinement stops helping.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .query import FreeformQuery

COLOR_VALUES = ["black", "white", "blue", "red", "pink", "green", "brown",
                "grey", "purple", "yellow", "orange"]
MATERIAL_VALUES = ["cotton", "polyester", "nylon", "leather", "wool",
                   "spandex", "silk", "rayon", "denim", "down"]
PRICE_BANDS = [(None, 20.0, "$20 or less"), (20.0, 50.0, "$20–50"),
               (50.0, 100.0, "$50–100"), (100.0, None, "$100 or more")]

FACET_ZH = {"color": "color", "material": "material", "price": "price", "category": "category"}
TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

CONVERGE_RE = re.compile(r"就这些|就這些|就这样|就這样|可以了|不用了|就这些吧|开始推荐|開始推薦|that's it|that is it|stop|done|good enough|these are fine")
# explicit topic shift markers
SHIFT_RE = re.compile(r"算了|改找|不要了|換成|换成|重新找|不要这个|不要這個|换一个|換一個|never mind|forget it|switch to|instead|something different")
# rejection feedback reopens guidance on a converged session
NEGATIVE_RE = re.compile(r"不是|不对|不對|不喜欢|不喜歡|换一批|換一批|都不行|not this|not these|wrong|none of these|anything else")
CATEGORY_JUNK = {"clothing", "shoes", "jewelry", "women", "men", "girls", "boys",
                 "baby", "kids", "accessories", "fashion", "casual", "novelty", "apparel",
                 "more", "specific", "one", "two", "best", "new", "set", "size", "de", "la",
                 "sets", "yoga", "sport", "sports", "outdoor", "active", "lounge", "sleep"}

# Curated starting categories for zero-information queries
STARTER_CATEGORIES = [
    ("Shirts", "shirts"), ("Pants", "pants"), ("Jackets", "jacket"),
    ("Dresses", "dress"), ("Sweaters", "sweater"), ("T-Shirts", "t-shirts"),
    ("Sneakers", "sneakers"), ("Boots", "boots"), ("Hats", "hat"),
    ("Scarves", "scarf"), ("Bags", "bag"), ("Watches", "watch"),
    ("Belts", "belt"), ("Jewelry", "jewelry"),
]


@dataclass
class GuideState:
    """Accumulated chat query + convergence bookkeeping."""
    keywords: list[str] = field(default_factory=list)
    last_keywords: list[str] = field(default_factory=list)  # latest item-type batch
    keyword_weights: dict[str, float] = field(default_factory=dict)  # recency decay
    materials: set[str] = field(default_factory=set)
    colors: set[str] = field(default_factory=set)
    budget: float | None = None
    facet_keys: set[str] = field(default_factory=set)
    no_progress: int = 0
    guide_rounds: int = 0
    converged: bool = False

    def to_query(self) -> FreeformQuery:
        return FreeformQuery(text="", keywords=list(self.keywords),
                             materials=set(self.materials), colors=set(self.colors),
                             budget=self.budget, keyword_weights=dict(self.keyword_weights))

    def apply(self, query: FreeformQuery, text: str) -> bool:
        """Fold a new user message into the state. Returns True if new
        information arrived (or a topic reset happened)."""
        if CONVERGE_RE.search(text):
            self.converged = True
            return True
        new_keywords = [kw for kw in query.keywords if kw not in self.keywords]
        new_materials = query.materials - self.materials
        new_colors = query.colors - self.colors
        new_budget = query.budget is not None and query.budget != self.budget
        # explicit topic shift -> reset to a fresh intent
        if SHIFT_RE.search(text):
            self.keywords = list(new_keywords)
            self.last_keywords = list(new_keywords)
            self.keyword_weights = {kw: 1.0 for kw in new_keywords}
            self.materials = set(query.materials)
            self.colors = set(query.colors)
            self.budget = query.budget
            self.facet_keys = set()
            self.no_progress = 0
            self.converged = False
            return True
        self.keywords.extend(new_keywords)
        if new_keywords:
            # the user's latest item-type mention is the current focus:
            # decay older keywords so they stop dominating the ranking
            for keyword in self.keyword_weights:
                self.keyword_weights[keyword] = min(self.keyword_weights[keyword], 0.3)
            for keyword in new_keywords:
                self.keyword_weights[keyword] = 1.0
            self.last_keywords = list(new_keywords)
        self.materials |= new_materials
        self.colors |= new_colors
        if new_budget:
            self.budget = query.budget
        has_new = bool(new_keywords or new_materials or new_colors or new_budget)
        if has_new:
            self.no_progress = 0
            self.converged = False  # new info reopens a converged session
        else:
            self.no_progress += 1
            if NEGATIVE_RE.search(text) and self.no_progress < 2:
                self.converged = False  # rejected results -> offer new facets
        return has_new

    @property
    def is_empty(self) -> bool:
        """No usable constraints at all (nothing to retrieve with)."""
        return not (self.keywords or self.materials or self.colors
                    or self.budget is not None)

    def should_converge(self, pool_size: int, turn: int = 0) -> bool:
        # natural convergence + a hard clamp: force the final answer by
        # turn 9 so every session finishes within the 10-turn budget
        return (self.converged or pool_size <= 5 or self.no_progress >= 2
                or self.guide_rounds >= 4 or turn >= 9)


def _entropy(counts: list[int]) -> float:
    total = sum(counts)
    if total <= 0:
        return 0.0
    entropy = 0.0
    for count in counts:
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    return entropy


def facet_stats(index, pool: list[str]) -> dict:
    """Value distributions of each facet over the current candidate pool."""
    color_counts = {value: 0 for value in COLOR_VALUES}
    material_counts = {value: 0 for value in MATERIAL_VALUES}
    band_counts = {band: 0 for band in PRICE_BANDS}
    category_counts: dict[str, int] = {}
    for asin in pool:
        for color in index.color_sets[asin] & set(COLOR_VALUES):
            color_counts[color] += 1
        for material in index.material_sets[asin] & set(MATERIAL_VALUES):
            material_counts[material] += 1
        price = index.prices[asin]
        if price is not None:
            for low, high, _ in PRICE_BANDS:
                if (low is None or price >= low) and (high is None or price < high):
                    band_counts[(low, high, _)] += 1
                    break
        for token in TOKEN_RE.findall(index.category_specific_lower.get(asin, "")):
            if len(token) > 2 and token not in CATEGORY_JUNK:
                category_counts[token] = category_counts.get(token, 0) + 1
    return {
        "color": color_counts,
        "material": material_counts,
        "price": band_counts,
        "category": category_counts,
    }


def choose_facet(index, pool: list[str], state: GuideState):
    """Pick the most informative unconstrained facet; returns
    (facet_key, [(value, count, label), ...]) or (None, []) when nothing
    useful remains."""
    stats = facet_stats(index, pool)
    candidates = []
    for facet, counts in [("color", stats["color"]), ("material", stats["material"])]:
        if facet in state.facet_keys or (facet == "color" and state.colors) \
                or (facet == "material" and state.materials):
            continue
        values = sorted(((value, count) for value, count in counts.items() if count >= 3),
                        key=lambda item: -item[1])[:5]
        if len(values) >= 2:
            candidates.append((facet, values))
    if "price" not in state.facet_keys and state.budget is None:
        values = [(band, count) for band, count in stats["price"].items() if count >= 3]
        if len(values) >= 2:
            candidates.append(("price", values))
    if "category" not in state.facet_keys:
        constrained = set(state.keywords) | {kw + "s" for kw in state.keywords}
        values = sorted(stats["category"].items(), key=lambda item: -item[1])[:6]
        values = [(value, count) for value, count in values
                  if count >= 3 and value not in constrained]
        if len(values) >= 2:
            candidates.append(("category", values))
    if not candidates:
        return None, []

    best_facet, best_values = None, []
    best_entropy = -1.0
    for facet, values in candidates:
        entropy = _entropy([count for _, count in values])
        if entropy > best_entropy:
            best_entropy = entropy
            best_facet, best_values = facet, values
    return best_facet, best_values


def hard_pool(index, state: GuideState) -> set:
    """Conjunctive candidate set implied by the accumulated hard constraints
    (category keywords ∩ materials ∩ colors, price-aware). This is the set
    that genuinely shrinks turn by turn."""
    from .retrieve import _plural_variants

    sets: list[set] = []
    hard_keywords = state.last_keywords or state.keywords
    for keyword in hard_keywords:
        variant_postings: set = set()
        for variant in _plural_variants(keyword):
            postings = index.category_specific_token_postings.get(variant)
            if postings is None:
                postings = index.category_token_postings.get(variant)
            if postings:
                variant_postings |= postings
        if variant_postings:
            sets.append(variant_postings)
    for material in state.materials:
        postings = index.material_postings.get(material)
        if postings:
            sets.append(postings)
    for color in state.colors:
        postings = index.color_postings.get(color)
        if postings:
            sets.append(postings)
    if not sets:
        return set()
    # tiny posting sets (<=5) are token coincidences ("ski" as a stray token),
    # not real constraints — drop them so they don't kill the intersection
    sets = [postings for postings in sets if len(postings) > 5]
    if not sets:
        return set()
    intersection = set(sets[0])
    for postings in sets[1:]:
        intersection &= postings
    if state.budget is not None and intersection:
        low, high = state.budget * 0.7, state.budget * 1.5
        intersection = {asin for asin in intersection
                        if index.prices[asin] is None or low <= index.prices[asin] <= high}
    return intersection


def hard_pool_size(index, state: GuideState) -> int:
    """Size of hard_pool(); 300 is the dense-only baseline for display."""
    return len(hard_pool(index, state)) or 300


def option_labels(facet: str, values) -> list[dict]:
    """Human labels + the message a click will send (parser-friendly English)."""
    labels = []
    for value, count in values:
        if facet == "color":
            label = f"{value.capitalize()} ({count})"
            message = value
        elif facet == "material":
            label = f"{value.capitalize()} ({count})"
            message = value
        elif facet == "price":
            low, high, label_text = value
            label = f"{label_text} ({count})"
            if low is None:
                message = f"budget under {int(high)} dollars"
            elif high is None:
                message = f"budget {int((low + high) * 1.5)} dollars"
            else:
                message = f"budget {int((low + high) / 2)} dollars"
        else:  # category token
            label = f"{value} ({count})"
            message = value
        labels.append({"value": str(value if not isinstance(value, tuple) else value[2]),
                       "label": label, "message": message, "count": count})
    return labels


def guide_message(pool_size: int, facet: str, values) -> str:
    if facet is None:
        return f"Converged to {pool_size} exact matches; here are the best candidates."
    options = ", ".join(option_labels(facet, values)[:4][i]["label"] for i in range(min(4, len(values))))
    return f"Narrowed to {pool_size} exact matches. Fastest to converge by {FACET_ZH.get(facet, facet)}: {options}"
