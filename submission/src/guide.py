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

# Canonical facet vocabularies: only these color/material tokens are surfaced as
# clickable options, keeping the option list short and meaningful for the shopper.
COLOR_VALUES = ["black", "white", "blue", "red", "pink", "green", "brown",
                "grey", "purple", "yellow", "orange"]
MATERIAL_VALUES = ["cotton", "polyester", "nylon", "leather", "wool",
                   "spandex", "silk", "rayon", "denim", "down"]
# Price navigation bands: (low, high, display_label); None marks an open end.
PRICE_BANDS = [(None, 20.0, "$20 or less"), (20.0, 50.0, "$20–50"),
               (50.0, 100.0, "$50–100"), (100.0, None, "$100 or more")]

# Display names for facet keys (English values used verbatim for both languages).
FACET_ZH = {"color": "color", "material": "material", "price": "price", "category": "category"}
# Splits free-text category strings into lowercase alphanumeric tokens for counting.
TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

# explicit agreement / "enough" markers -> the shopper accepts the current pool
CONVERGE_RE = re.compile(r"就这些|就這些|就这样|就這样|可以了|不用了|就这些吧|开始推荐|開始推薦|that's it|that is it|stop|done|good enough|these are fine")
# explicit topic shift markers
SHIFT_RE = re.compile(r"算了|改找|不要了|換成|换成|重新找|不要这个|不要這個|换一个|換一個|never mind|forget it|switch to|instead|something different")
# rejection feedback reopens guidance on a converged session
NEGATIVE_RE = re.compile(r"不是|不对|不對|不喜欢|不喜歡|换一批|換一批|都不行|not this|not these|wrong|none of these|anything else")
# Low-information tokens excluded from category facets (generic/brand/size words).
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
    """Mutable per-session accumulation of shopper intent and convergence bookkeeping.

    This is the working memory of the guidance engine: it folds every parsed user
    message into running keyword/material/color/budget constraints, tracks which
    facets have already been asked so they are not repeated, and counts no-progress
    turns so the loop can force convergence within the session's turn budget.
    """
    keywords: list[str] = field(default_factory=list)  # all item-type keywords seen (union)
    last_keywords: list[str] = field(default_factory=list)  # latest item-type batch
    keyword_weights: dict[str, float] = field(default_factory=dict)  # recency decay
    materials: set[str] = field(default_factory=set)  # all materials mentioned (union)
    colors: set[str] = field(default_factory=set)  # all colors mentioned (union)
    last_materials: set[str] = field(default_factory=set)  # latest material mention
    last_colors: set[str] = field(default_factory=set)      # latest color mention
    budget: float | None = None  # shopper price point; None means unconstrained
    facet_keys: set[str] = field(default_factory=set)  # facets already offered (dedupe)
    no_progress: int = 0  # consecutive turns with no new constraint
    guide_rounds: int = 0  # number of guidance questions asked so far
    converged: bool = False  # shopper accepted the current pool

    def to_query(self) -> FreeformQuery:
        """Materialize the accumulated state as a FreeformQuery for retrieval.

        The text is intentionally empty because all signal lives in the structured
        fields; recent_materials/recent_colors are exposed separately so the
        retriever can prioritize the shopper's latest mention.
        """
        return FreeformQuery(text="", keywords=list(self.keywords),
                             materials=set(self.materials), colors=set(self.colors),
                             recent_materials=set(self.last_materials),
                             recent_colors=set(self.last_colors),
                             budget=self.budget, keyword_weights=dict(self.keyword_weights))

    def apply(self, query: FreeformQuery, text: str) -> bool:
        """Fold a new user message into the parsed state.

        Computes the delta between the incoming query and what is already known,
        then applies recency weighting, topic resets, and convergence bookkeeping.
        Returns True when new information arrived or the topic was reset (so the
        caller knows to re-run retrieval); False signals a no-progress turn.
        Side effect: mutates all accumulated fields in place.
        """
        # Early exit: the shopper explicitly accepted the current pool.
        if CONVERGE_RE.search(text):
            self.converged = True
            return True
        # Diff against current state so only genuinely new constraints count.
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
        if new_materials:
            self.last_materials = set(new_materials)  # latest mention becomes the focus
        if new_colors:
            self.last_colors = set(new_colors)  # latest mention becomes the focus
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
            # Rejection on a converged pool reopens guidance, but only once, so
            # the session cannot loop forever on repeated negative feedback.
            if NEGATIVE_RE.search(text) and self.no_progress < 2:
                self.converged = False  # rejected results -> offer new facets
        return has_new

    @property
    def is_empty(self) -> bool:
        """No usable constraints at all (nothing to retrieve with)."""
        return not (self.keywords or self.materials or self.colors
                    or self.budget is not None)

    def should_converge(self, pool_size: int, turn: int = 0) -> bool:
        """Decide whether to stop asking and commit to the current candidates.

        True when the shopper agreed, the pool is already small, two turns in a
        row added nothing, four guidance questions were asked, or the session is
        about to exhaust its turn budget. Pure function of state + inputs.
        """
        # natural convergence + a hard clamp: force the final answer by
        # turn 9 so every session finishes within the 10-turn budget
        return (self.converged or pool_size <= 10 or self.no_progress >= 2
                or self.guide_rounds >= 4 or turn >= 9)


def _entropy(counts: list[int]) -> float:
    """Shannon entropy (bits) of a discrete distribution given as raw counts.

    Higher entropy means the facet values are spread more evenly and therefore
    make a better disambiguating question; a degenerate distribution yields 0
    bits. Returns 0.0 for empty or zero-total input (no information).
    """
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
    """Count how many pool items fall into each facet value.

    Builds frequency distributions for color, material, price band, and free-text
    category tokens by scanning the current candidate pool through the catalog
    index. These counts drive facet-entropy selection in ``choose_facet`` and the
    "(N)" labels shown to the shopper. Zero-count values are retained for the
    fixed vocabularies (color/material/price) but not for the open category set.
    """
    # Fixed vocabularies start at zero so unmentioned values stay visible.
    color_counts = {value: 0 for value in COLOR_VALUES}
    material_counts = {value: 0 for value in MATERIAL_VALUES}
    band_counts = {band: 0 for band in PRICE_BANDS}
    category_counts: dict[str, int] = {}
    for asin in pool:
        # Intersect the item's attributes with the canonical vocab to ignore noise.
        for color in index.color_sets[asin] & set(COLOR_VALUES):
            color_counts[color] += 1
        for material in index.material_sets[asin] & set(MATERIAL_VALUES):
            material_counts[material] += 1
        price = index.prices[asin]
        if price is not None:
            # Bucket the price into exactly one band (bands are half-open).
            for low, high, _ in PRICE_BANDS:
                if (low is None or price >= low) and (high is None or price < high):
                    band_counts[(low, high, _)] += 1
                    break
        # Free-text category: tokenize and drop short or generic tokens.
        for token in TOKEN_RE.findall(index.category_specific_lower.get(asin, "")):
            if len(token) > 2 and token not in CATEGORY_JUNK:
                category_counts[token] = category_counts.get(token, 0) + 1
    return {
        "color": color_counts,
        "material": material_counts,
        "price": band_counts,
        "category": category_counts,
    }


def choose_facet(index, pool: list[str], state: GuideState, rule: str = "entropy"):
    """Pick the most informative facet not yet constrained by the shopper.

    Gathers per-facet value distributions over the current pool, filters out
    facets already asked (``state.facet_keys``) or already pinned by an existing
    constraint, and requires at least two viable values (each with >=3 items).
    With ``rule="entropy"`` (default) it returns the highest-entropy facet, i.e.
    the question that splits the pool most evenly; ``rule="first"`` is a cheap
    deterministic fallback. Returns ``(facet_key, [(value, count), ...])`` or
    ``(None, [])`` when nothing useful remains.
    """
    stats = facet_stats(index, pool)
    candidates = []
    # Color/material are useless once pinned: "black" makes further color
    # questions redundant, so an already-set value excludes the whole facet.
    for facet, counts in [("color", stats["color"]), ("material", stats["material"])]:
        if facet in state.facet_keys or (facet == "color" and state.colors) \
                or (facet == "material" and state.materials):
            continue
        # Keep only frequent values (>=3 items) and cap at the 5 most common.
        values = sorted(((value, count) for value, count in counts.items() if count >= 3),
                        key=lambda item: -item[1])[:5]
        if len(values) >= 2:
            candidates.append((facet, values))
    # Price facet: only when no budget is already set and it was not asked before.
    if "price" not in state.facet_keys and state.budget is None:
        values = [(band, count) for band, count in stats["price"].items() if count >= 3]
        if len(values) >= 2:
            candidates.append(("price", values))
    # Category facet: suggest tokens not already in the query, including the naive
    # plural form so "shirt" is not re-offered to the shopper as "shirts".
    if "category" not in state.facet_keys:
        constrained = set(state.keywords) | {kw + "s" for kw in state.keywords}
        values = sorted(stats["category"].items(), key=lambda item: -item[1])[:6]
        values = [(value, count) for value, count in values
                  if count >= 3 and value not in constrained]
        if len(values) >= 2:
            candidates.append(("category", values))
    if not candidates:
        return None, []
    if rule == "first":
        return candidates[0][0], candidates[0][1]

    # Default: maximize entropy so the chosen question maximizes information gain.
    best_facet, best_values = None, []
    best_entropy = -1.0
    for facet, values in candidates:
        entropy = _entropy([count for _, count in values])
        if entropy > best_entropy:
            best_entropy = entropy
            best_facet, best_values = facet, values
    return best_facet, best_values


def hard_pool(index, state: GuideState, tree=None) -> set:
    """Compute the conjunctive candidate set from accumulated hard constraints.

    Intersects the posting sets of category keywords, materials, and colors, then
    applies a soft price window around the shopper's budget. This is the "exact
    matches" pool that genuinely shrinks turn by turn. Keyword postings too tiny
    to be real constraints are dropped, and items with no price data are treated
    as passing the budget filter rather than being eliminated.

    When ``tree`` (a ProductTree) is provided, category keywords resolve
    tree-first (subtree products via the value index); keywords the tree
    does not match fall back to token postings. Returns a set of ASINs.
    """
    from .retrieve import _plural_variants

    sets: list[set] = []
    # Latest item-type batch is the shopper's current focus when present.
    hard_keywords = state.last_keywords or state.keywords
    for keyword in hard_keywords:
        keyword_set: set = set()
        if tree is not None:
            keyword_set = tree.subtree_for_keyword(keyword)
        if not keyword_set:
            # Fall back to token postings across plural variants ("shirt"/"shirts").
            variant_postings: set = set()
            for variant in _plural_variants(keyword):
                postings = index.category_specific_token_postings.get(variant)
                if postings is None:
                    postings = index.category_token_postings.get(variant)
                if postings:
                    variant_postings |= postings
            keyword_set = variant_postings
        if keyword_set:
            sets.append(keyword_set)
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
    # Soft price window: items within +/-50% of budget survive; unpriced items pass.
    if state.budget is not None and intersection:
        low, high = state.budget * 0.7, state.budget * 1.5
        intersection = {asin for asin in intersection
                        if index.prices[asin] is None or low <= index.prices[asin] <= high}
    return intersection


def hard_pool_size(index, state: GuideState, tree=None) -> int:
    """Return the hard_pool size for display, with a dense-only baseline.

    When the conjunctive pool is empty (no hard constraints yet), 300 is shown as
    a representative "unconstrained" figure so the UI never displays zero.
    """
    return len(hard_pool(index, state, tree=tree)) or 300


def option_labels(facet: str, values) -> list[dict]:
    """Render facet values as clickable options for the UI.

    Each entry carries a display ``label`` (value + count), a stable ``value``, a
    ``message`` string that a click will send back as the user's next utterance,
    and the ``count``. Price bands are converted into a natural-language budget
    message the query parser can round-trip back into a numeric budget.
    """
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
            # Turn a price band into a parser-friendly budget utterance.
            if low is None:
                message = f"budget under {int(high)} dollars"
            elif high is None:
                message = f"budget {int(low * 1.6)} dollars"
            else:
                message = f"budget {int((low + high) / 2)} dollars"
        else:  # category token
            label = f"{value} ({count})"
            message = value
        # For price bands, `value` is a tuple; expose its label text as the value.
        labels.append({"value": str(value if not isinstance(value, tuple) else value[2]),
                       "label": label, "message": message, "count": count})
    return labels


def guide_message(pool_size: int, facet: str, values) -> str:
    """Build the assistant's guidance utterance for a turn.

    When no facet remains (``facet is None``) it announces convergence and lists
    how the shopper can still narrow manually. Otherwise it names the chosen facet,
    shows up to four of its option labels, and appends a facet-specific hint so the
    shopper always knows what to say next. Pure string construction.
    """
    if facet is None:
        return (f"Converged to {pool_size} exact matches — here are the best "
                f"candidates. To narrow further, tell me a color, material, "
                f"or budget (e.g. \"black\", \"leather\", \"under $30\"), or "
                f"say \"that's it\" to keep this pick.")
    # Join at most 4 option labels as a compact suggestion list.
    options = ", ".join(option_labels(facet, values)[:4][i]["label"] for i in range(min(4, len(values))))
    return (f"Narrowed to {pool_size} exact matches. Fastest to converge by "
            f"{FACET_ZH.get(facet, facet)}: {options}. "
            + {
                "color": "Pick one above or type a color, e.g. \"black\" or \"navy\".",
                "material": "Pick one above or type a material, e.g. \"cotton\" or \"leather\".",
                "price": "Pick a band above or type a budget, e.g. \"under $40\" or \"$20 to $50\".",
                "category": "Pick a category above or type an item, e.g. \"boots\" or \"dress\".",
            }.get(facet, "Pick an option above or describe what you want."))
