"""Multi-route retrieval and ranking.

Routes (all computed in-memory):
  R1 exact-phrase conjunction   -> the dominant signal (simulator discloses
                                   verbatim feature/detail strings)
  R2 category tokens            -> coarse category from the opening message
  R3 synthetic attributes       -> bare material words, "color: x", budget
  R4 title-token overlap        -> tie-breaking lexical signal
  R5 profile-tag affinity       -> anonymized user profile nudges ranking
Cascade relaxation: if the full conjunction is empty, drop the weakest
constraint(s) before falling back to category-only candidates.
"""
from __future__ import annotations

import math
import re
from itertools import combinations

from .index import CatalogIndex
from .state import ConversationState

W_PHRASE = 100.0   # exact-phrase hit: simulator discloses verbatim strings
W_SUPERSEDED = 30.0  # formerly active phrase still disclosed, weaker signal
W_MAT = 25.0       # per matching material word already disclosed by the user
W_COL = 25.0       # per matching color word already disclosed by the user
W_BUDGET = 40.0    # budget proximity (scaled by the closeness factor)
W_CAT = 60.0       # exact coarse-category match (tight, always-safe filter)
W_CAT_SUBSTR = 20.0  # category string appears as substring of item category
W_TITLE = 16.0     # disclosed constraint word appearing in the title
W_CORPUS = 8.0  # full-text overlap of disclosed constraint words (target
                # fingerprint; resolves near-ties inside info-bound pools)
W_CAT_TITLE = 3.0   # category token appears in the title (weak tiebreak)
W_TAG = 0.0         # profile preference-tag affinity (0 = effectively disabled)
W_RATING = 4.0      # small prior toward higher-rated items
W_POP = 8.0  # log popularity prior: purchase-record targets skew popular
W_TFIDF = 30.0  # dense-route cosine similarity (only applied when pool is large)
W_STYLE = 20.0  # rating_style consistency: "usually positive" users buy high-rated items
W_DEPTH = 0.25   # depth-weighted chain bonus scale (binary-search thinking: a
                # match at depth d pins ~catalog/2^d products, so deeper
                # matches carry exponentially more information)
DENSE_MIN_POOL = 200   # apply the dense route only above this pool size
DENSE_MIN_HISTORY = 1  # apply only once this many user messages arrived


def _style_consistency(rating: float | None, profile: dict) -> bool:
    """Return whether an item's rating matches the user's disclosed rating style.

    The user profile may reveal how the user typically rates items ("usually
    positive" vs "critical"). Consistency is a weak bonus (W_STYLE), never a
    hard filter: "mixed"/unknown styles and missing ratings always return True
    so nothing is wrongly penalized.
    """
    style = profile.get("rating_style", "")
    # Unknown style or no rating: no basis to judge, so treat as consistent.
    if style == "mixed" or rating is None:
        return True
    if style == "usually positive":
        return rating >= 4.0
    if style == "critical":
        return rating <= 3.5
    return True

# Near-universal category words that carry no discriminative power: they are
# dropped from category token sets so they can't drown out real signals.
CATEGORY_JUNK = {"clothing", "shoes", "jewelry", "women", "men", "girls", "boys", "baby"}
# Shared tokenizer: alphanumeric runs only, case-insensitive.
TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _query_category_tokens(category: str) -> set[str]:
    """Split the disclosed coarse category into meaningful lowercase tokens.

    Only alphanumeric tokens longer than one character are kept, and junk
    words (clothing, shoes, gender words, etc.) are dropped because they are
    near-universal and carry no discriminative power across categories.
    """
    tokens = {token.lower() for token in TOKEN_RE.findall(category) if len(token) > 1}
    return tokens - CATEGORY_JUNK


def _budget_score(price: float | None, budget: float) -> float:
    """Score how close an item's price is to the user's budget.

    Returns W_BUDGET scaled by a linear closeness factor: 1.0 at an exact
    match, decaying to 0.0 once the gap reaches the budget magnitude. Missing
    prices score 0.0 (neutral) so unlisted items are never wrongly rewarded or
    penalized; ``max(abs(budget), 1.0)`` guards against divide-by-zero.
    """
    if price is None:
        return 0.0
    closeness = max(0.0, 1.0 - abs(price - budget) / max(abs(budget), 1.0))
    return W_BUDGET * closeness


def _constraint_tokens(state: ConversationState) -> set[str]:
    """Collect every disclosed constraint word into a single token set.

    Unions the alphanumeric tokens of active and superseded phrases with the
    material and color words. Used for fuzzy title/corpus/tree overlap signals
    (not exact matching), so coverage matters more than precision here.
    """
    tokens: set[str] = set()
    for phrase in state.active_phrases | state.superseded:
        tokens |= {token.lower() for token in TOKEN_RE.findall(phrase) if len(token) > 1}
    tokens |= state.materials | state.colors
    return tokens


def _category_candidates(index: CatalogIndex, tokens: set[str], limit: int = 3000) -> set[str]:
    """Compute the conjunctive candidate set for category tokens, with early exit.

    Intersects posting lists in order of increasing size (rarest token first)
    so the running intersection stays small. Stops once the candidate set is
    at or below ``limit`` — enough to rank without fully intersecting. Returns
    an empty set for empty ``tokens`` or any token with no postings (an
    impossible conjunction).
    """
    if not tokens:
        return set()
    candidates: set[str] | None = None
    # Rare-first ordering minimizes the size of the running intersection.
    for token in sorted(tokens, key=lambda token: len(index.category_token_postings.get(token, ()))):
        postings = index.category_token_postings.get(token)
        if not postings:
            return set()
        candidates = postings if candidates is None else (candidates & postings)
        if candidates is not None and len(candidates) <= limit:
            break
    return candidates or set()


def _category_intersection(index: CatalogIndex, tokens: set[str]) -> set[str]:
    """Full intersection over all category tokens (no early exit).

    Unlike ``_category_candidates`` this always intersects every token, so the
    result is the tightest category-conjunctive pool — used as a hard filter
    rather than a candidate generator. Returns an empty set when any token has
    no postings or ``tokens`` is empty.
    """
    if not tokens:
        return set()
    candidates: set[str] | None = None
    # Rare-first ordering keeps the running intersection small.
    for token in sorted(tokens, key=lambda token: len(index.category_token_postings.get(token, ()))):
        postings = index.category_token_postings.get(token)
        if not postings:
            return set()
        candidates = postings if candidates is None else (candidates & postings)
    return candidates or set()


def _score(
    asin: str,
    index: CatalogIndex,
    state: ConversationState,
    query_tokens: set[str],
    constraint_tokens: set[str],
    dense_map: dict[str, float] | None = None,
    tree=None,
) -> float:
    """Compute the hybrid heuristic score for one product (ASIN).

    Aggregates weighted, independent signals into a single number (higher is
    better): exact-phrase hits (the dominant signal), category, material/
    color, budget, title/corpus token overlap, profile-tag affinity, rating
    and popularity priors, dense-route similarity, and the tree depth bonus.
    ``query_tokens`` are category tokens; ``constraint_tokens`` are the wider
    disclosed words. Optional routes (``dense_map``, ``tree``) simply
    contribute nothing when absent, so the core path stays deterministic.
    """
    score = 0.0
    product_phrases = index.product_phrases[asin]
    # Active phrases are the strongest signal: the simulator discloses them
    # verbatim, so an exact phrase match is near-conclusive.
    for phrase in state.active_phrases:
        if phrase in product_phrases:
            score += W_PHRASE
    # Superseded phrases are still disclosed but were superseded by later
    # constraints, so they earn a smaller reward.
    for phrase in state.superseded:
        if phrase in product_phrases:
            score += W_SUPERSEDED
    # Material/color matches reward each shared slot word (disclosed earlier).
    if state.materials & index.material_sets[asin]:
        score += W_MAT * len(state.materials & index.material_sets[asin])
    if state.colors & index.color_sets[asin]:
        score += W_COL * len(state.colors & index.color_sets[asin])
    if state.budget is not None:
        score += _budget_score(index.prices[asin], state.budget)
    if state.category:
        # Normalize whitespace so "men  belt" == "men belt" for exact matching.
        coarse_key = " ".join(state.category.lower().split())
        if index.category_coarse_key.get(asin) == coarse_key:
            score += W_CAT
        else:
            # Fallback: reward partial category-token overlap proportionally,
            # and a raw substring hit as a weaker secondary signal.
            if query_tokens:
                matched = query_tokens & index.category_tokens[asin]
                score += W_CAT * 0.5 * (len(matched) / len(query_tokens))
            if state.category.lower() in index.category_lower[asin]:
                score += W_CAT_SUBSTR
    # Title overlap of disclosed constraint words, capped to avoid one
    # keyword-spam title dominating the score.
    overlap = constraint_tokens & index.title_tokens[asin]
    score += W_TITLE * min(len(overlap), 8)
    cat_overlap = query_tokens & index.title_tokens[asin]
    score += W_CAT_TITLE * min(len(cat_overlap), 8)
    # full-corpus overlap of disclosed constraint words: the target's own
    # features/details are its fingerprint, so corpus-level matches resolve
    # near-ties inside info-bound pools (smaller weight than title — corpus
    # includes the boilerplate the whole pool shares)
    corpus_overlap = constraint_tokens & index.corpus_tokens.get(asin, frozenset())
    score += W_CORPUS * min(len(corpus_overlap), 16)
    for tag in state.user_profile.get("preference_tags", []):
        if tag and tag.lower() in index.corpus[asin].lower():
            score += W_TAG
    rating, rating_number = index.ratings[asin]
    # Rating prior is capped at 5.0 so it cannot overpower the constraint
    # signals; popularity uses log1p so a few mega-popular items don't drown
    # everything else, and is capped at 9.5 for the same reason.
    if rating is not None:
        score += W_RATING * min(rating, 5.0)
    if rating_number:
        score += W_POP * min(9.5, math.log1p(rating_number))
    # Style consistency is a full-or-nothing bonus: matches the user's rating
    # tendency if one is disclosed, otherwise it stays off.
    if _style_consistency(rating, state.user_profile):
        score += W_STYLE
    # Dense-route cosine similarity, applied only when a dense_map was built.
    if dense_map is not None:
        score += W_TFIDF * dense_map.get(asin, 0.0)
    # Binary-search thinking: deeper chain matches pin down exponentially
    # smaller subsets, so they contribute more (see ProductTree docstring).
    if tree is not None and (constraint_tokens or query_tokens):
        tokens = constraint_tokens | query_tokens
        score += W_DEPTH * tree.depth_weighted_bonus(asin, tokens)
    return score


def retrieve(
    state: ConversationState,
    index: CatalogIndex,
    top_k: int,
    dense=None,
    llm=None,
    tree=None,
) -> tuple[list[str], dict, int]:
    """Rank candidate products and return (ranked asins, usage, pool size).

    Builds the candidate pool in route order — exact-phrase conjunction with
    cascade relaxation (R1), category/material/color/budget candidates (R2/R3),
    then a hard coarse-category filter — and ranks with the heuristic scorer.

    The optional LLM reranks only the top-20 and only when the tree-first
    route is NOT converged: if the product-property tree alone pins the pool
    to a small set, the deterministic ranking is kept and zero tokens are
    spent ("tree when possible, LLM only when the tree is not enough").
    Failures (dense/LLM exceptions) fall back to heuristic order."""
    active = [phrase for phrase in state.active_phrases if phrase in index.phrase_postings]
    query_tokens = _query_category_tokens(state.category)
    constraint_tokens = _constraint_tokens(state)

    # ---- R1: exact-phrase conjunction with cascade relaxation ----
    pool: set[str] | None = None
    if active:
        # Intersect the rarest phrases first so the running set stays small.
        active_sorted = sorted(active, key=lambda phrase: len(index.phrase_postings[phrase]))
        # Cascade: try the full conjunction first, then drop constraints from
        # the end (weakest/rarest) until a non-empty intersection is found.
        for size in range(len(active_sorted), 0, -1):
            for combo in combinations(active_sorted, size):
                intersection: set[str] | None = None
                for phrase in combo:
                    postings = index.phrase_postings[phrase]
                    intersection = set(postings) if intersection is None else (intersection & postings)
                    # Short-circuit: an empty intersection can never recover.
                    if not intersection:
                        break
                if intersection:
                    pool = intersection
                    break
            if pool:
                break

    # ---- R2/R3: extend with category and synthetic-signal candidates ----
    if pool is None or len(pool) < top_k:
        # Union (not intersect) the synthetic signals here: the phrase
        # conjunction is too strict alone, so any material/color/budget hit
        # widens the pool before the hard category filter tightens it again.
        category_candidates = _category_candidates(index, query_tokens)
        if pool is None:
            pool = set(category_candidates)
        else:
            pool |= category_candidates
        if state.materials:
            for material in state.materials:
                pool |= index.material_postings.get(material, set())
        if state.colors:
            for color in state.colors:
                pool |= index.color_postings.get(color, set())
        if state.budget is not None:
            # Every priced item is a budget candidate; closeness is scored later.
            pool |= set(index.priced_asins)
        # Last-resort fallback: the entire catalog, ranked heuristically.
        if not pool:
            pool = set(index.products)

    # ---- hard category intersection: the disclosed coarse category is the
    # target's own last-two category parts verbatim, so exact-coarse matching
    # is a tight and always-safe filter; token intersection is the fallback.
    if pool and len(pool) > top_k:
        # Normalize whitespace again so the coarse key matches the index.
        coarse_key = " ".join(state.category.lower().split()) if state.category else ""
        coarse_set = index.category_coarse_postings.get(coarse_key, set())
        if coarse_set:
            # Apply the exact coarse filter only when it leaves a non-empty
            # pool; an empty intersection means the constraint is too strict.
            filtered = pool & coarse_set
            if filtered:
                pool = filtered
        elif query_tokens:
            # Fallback: tighten by full category-token intersection instead.
            filtered = pool & _category_intersection(index, query_tokens)
            if filtered:
                pool = filtered

    # ---- dense route: TF-IDF similarity when the pool stays large ----
    dense_map: dict[str, float] | None = None
    # Dense only helps break ties in large pools; skip it for small pools or
    # when there is too little history, and never let an exception abort the
    # deterministic fallback.
    if dense is not None and len(pool) > DENSE_MIN_POOL and len(state.history) >= DENSE_MIN_HISTORY:
        try:
            dense_map = dict(dense.query_scores(" ".join(state.history), list(pool)))
        except Exception:
            dense_map = None

    # Sort by score, then by rating_number as a deterministic tiebreak, both
    # descending (higher is better).
    ranked = sorted(
        pool,
        key=lambda asin: (
            _score(asin, index, state, query_tokens, constraint_tokens, dense_map, tree),
            index.ratings[asin][1],  # rating_number tiebreak
        ),
        reverse=True,
    )

    # ---- optional LLM reranking of the top candidates ----
    # Gate: use the LLM only when the tree-first route did NOT converge
    # ("tree when possible, LLM when the tree is not enough"). The tree is
    # converged when every category keyword resolves to a subtree and the
    # conjunctive subtree ∩ pool is small — then the deterministic ranking
    # is already decisive and tokens are saved.
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    tree_converged = False
    if llm is not None and tree is not None and state.history:
        # competition path: the disclosed coarse category is the tree keyword
        # source (last-two category parts, e.g. "men belt"); phrase/other
        # constraints are handled by the deterministic route already
        tree_keywords = (state.category.split() if state.category else [])
        if tree_keywords:
            tree_converged, _ = tree.converged_pool(tree_keywords, pool, threshold=top_k * 2)
    if (llm is not None and top_k < len(pool) <= 60 and state.history
            and not tree_converged):
        top_n = ranked[:20]
        candidates = []
        for asin in top_n:
            product = index.products[asin]
            # Normalize the heterogeneous "features" field (dict, list, or
            # absent) into a short, string-only list for the LLM prompt.
            features = product.get("features")
            if isinstance(features, dict):
                feature_list = [f"{key}: {item}" for key, item in features.items()][:3]
            elif isinstance(features, list):
                feature_list = [str(item) for item in features][:3]
            else:
                feature_list = []
            candidates.append({
                "parent_asin": asin,
                "title": product.get("title") or "",
                "categories": [str(item) for item in (product.get("categories") or [])],
                "features": feature_list,
            })
        ordered, usage = llm.rerank("\n".join(state.history), candidates)
        if ordered:
            # Put LLM-preferred items first, then append the remaining ranked
            # items (deduplicated) so the final list stays stable in length.
            ranked = ordered + [asin for asin in ranked if asin not in ordered]
    return ranked[:top_k], usage, len(pool)


def _plural_variants(keyword: str) -> set[str]:
    """Generate a small set of likely plural forms for a keyword.

    Covers the common English rules (default -s/-es, -y→-ies, -f→-ves,
    -fe→-ves) while always keeping the singular form so singular matches
    still succeed. Variants are used for substring matching over the category
    path, so a broad but cheap approximation is preferable to exactness.
    """
    variants = {keyword, keyword + "s", keyword + "es"}
    if keyword.endswith("y"):
        variants.add(keyword[:-1] + "ies")
    if keyword.endswith("f"):
        variants.add(keyword[:-1] + "ves")
    if keyword.endswith("fe"):
        variants.add(keyword[:-2] + "ves")
    return variants


def _freeform_rank(query, index: CatalogIndex, dense, tree=None):
    """Build the candidate pool and a scoring closure (shared by the
    public freeform entry points).

    Tree-first, dense embedded:
      1. Tree (or token) category route + material/color slots build the pool.
      2. If the tree alone pinned the pool small (<= TREE_DENSE_SKIP),
         dense is skipped entirely — heuristic ranking is already decisive.
      3. Otherwise dense scores *within the pool* (never the 50k catalog),
         and its top-300 join the pool when the pool is still huge.
    """
    TREE_DENSE_SKIP = 60  # pool this small: skip dense entirely
    pool: set[str] = set()
    category_variants: dict[str, set[str]] = {}
    tree_hits: set[str] = set()
    if tree is not None:
        # Tree-first: each keyword that maps to a subtree contributes that
        # subtree's products directly; unmatched keywords fall through to the
        # token-posting fallback below.
        for keyword in query.keywords:
            products = tree.subtree_for_keyword(keyword)
            if products:
                pool |= products
                tree_hits.add(keyword)
                category_variants[keyword] = tree.variants(keyword)
        leftover = [kw for kw in query.keywords if kw not in tree_hits]
    else:
        leftover = list(query.keywords)
    for keyword in leftover:
        variants = _plural_variants(keyword)
        variant_postings: set[str] = set()
        for variant in variants:
            # Prefer the specific-token postings (category path) and fall back
            # to the general token postings when the specific map lacks the key.
            postings = index.category_specific_token_postings.get(variant)
            if postings is None:
                postings = index.category_token_postings.get(variant)
            if postings:
                variant_postings |= postings
        if variant_postings:
            pool |= variant_postings
            category_variants[keyword] = variants
    for material in query.materials:
        pool |= index.material_postings.get(material, set())
    for color in query.colors:
        pool |= index.color_postings.get(color, set())

    # ---- dense only when the tree did NOT pin the pool ----
    dense_map: dict[str, float] = {}
    query_text = " ".join(
        [query.text, *query.keywords, *sorted(query.materials), *sorted(query.colors)]
    ).strip()
    if dense is not None and query_text and pool and len(pool) > TREE_DENSE_SKIP:
        if len(pool) > 300:
            # Huge pool: keep only the top-300 dense hits and union them in.
            sims = dense.query_scores(query_text, list(pool))
            top = sorted(sims, key=lambda item: -item[1])[:300]
            dense_map = dict(top)
            pool |= dense_map.keys()
        else:
            # Moderate pool: score every candidate but keep the pool intact.
            sims = dense.query_scores(query_text, list(pool))
            dense_map = dict(sims)
    if not pool:
        pool = set(index.products)

    # Whole-word regexes (escaped) for exact keyword matching in free text.
    patterns = {keyword: re.compile(rf"\b{re.escape(keyword)}\b") for keyword in query.keywords}
    # Precompute plural variants once, but only if the index exposes corpus
    # tokens (older indexes may not, in which case full-text regex is used).
    keyword_variants = {
        kw: _plural_variants(kw) for kw in query.keywords
    } if hasattr(index, "corpus_tokens") else {}
    weights = query.keyword_weights or {}
    budget = query.budget

    def score(asin: str) -> float:
        """Hybrid free-form score for one product (higher is better)."""
        value = 35.0 * dense_map.get(asin, 0.0)
        corpus_tokens = index.corpus_tokens.get(asin) if hasattr(index, "corpus_tokens") else None
        title_tokens = index.title_tokens[asin]
        for keyword, pattern in patterns.items():
            weight = weights.get(keyword, 1.0)
            # fast: token-set membership instead of full-text regex
            kw_variants = keyword_variants.get(keyword) or (keyword,)
            if corpus_tokens is not None:
                if kw_variants & corpus_tokens:
                    value += 18.0 * weight
            elif pattern.search(index.corpus[asin].lower()):
                value += 18.0 * weight
            if keyword in title_tokens:
                # title mention = strong intent match (helps with
                # role reversal like "gift for dad" vs dad-themed girly items)
                value += 25.0 * weight
        recent_mats = query.recent_materials or query.materials
        recent_cols = query.recent_colors or query.colors
        value += 50.0 * len(recent_mats & index.material_sets[asin])
        value += 50.0 * len(recent_cols & index.color_sets[asin])
        value += 20.0 * len((query.materials - recent_mats) & index.material_sets[asin])
        value += 20.0 * len((query.colors - recent_cols) & index.color_sets[asin])
        # category keywords via variant substrings on the root-stripped
        # category path (belt->belts, scarf->scarves, shoes stays meaningful)
        category_lower = index.category_specific_lower[asin]
        for keyword, variants in category_variants.items():
            if any(variant in category_lower for variant in variants):
                value += 60.0 * weights.get(keyword, 1.0)
        if budget is not None:
            price = index.prices[asin]
            if price is not None:
                # Over-budget by more than 35% is actively penalized; within
                # range, closeness to the budget earns a proportional bonus.
                if price > budget * 1.35:
                    value -= 30.0
                else:
                    value += 30.0 * max(0.0, 1.0 - abs(price - budget) / max(budget, 1.0))
        rating, rating_number = index.ratings[asin]
        if rating is not None:
            value += 3.0 * min(rating, 5.0)
        if rating_number:
            value += 3.0 * min(9.5, math.log1p(rating_number))
        # Binary-search thinking: a free-chat keyword matching a DEEP chain
        # segment ("leather" in "Leather Belts") pins down a far smaller
        # subset than a shallow one ("belt" in "Belts"), so it contributes
        # more. Applied only when the tree is available (tree-first mode).
        if tree is not None:
            tokens = set(query.keywords) | set(query.materials) | set(query.colors)
            if tokens:
                value += W_DEPTH * tree.depth_weighted_bonus(asin, tokens)
        return value

    # cheap pre-filter for huge pools: skip the expensive regex scorer for
    # candidates with no dense hit, no material/color, and no category
    # variant — their score would be near zero anyway.
    def _cheap_candidates(asin: str) -> bool:
        if dense_map.get(asin, 0.0) > 0.0:
            return True
        if query.materials & index.material_sets[asin]:
            return True
        if query.colors & index.color_sets[asin]:
            return True
        if category_variants:
            cat = index.category_specific_lower[asin]
            for variants in category_variants.values():
                if any(v in cat for v in variants):
                    return True
        if patterns:
            title = index.products[asin].get("title") or ""
            if any(pat.search(title) for pat in patterns.values()):
                return True
        return False

    score._cheap_candidates = _cheap_candidates  # type: ignore[attr-defined]
    return pool, score


def freeform_retrieve(query, index: CatalogIndex, dense, top_k: int = 10,
                      tree=None) -> list[str]:
    """Demo chat-mode retrieval for free-form human input.

    Builds candidates from three routes — TF-IDF/MiniLM dense top-N over the
    whole catalog, synthetic material/color postings, and category matches
    (tree-first when ``tree`` is given, token-posting fallback) — then ranks
    with a hybrid score. Not used by the submission agent (the simulator
    always speaks fixed templates).
    """
    pool, score = _freeform_rank(query, index, dense, tree=tree)
    ranked = _top_by_score(pool, score, top_k)
    return ranked


def _top_by_score(pool, score, limit: int) -> list[str]:
    """Top-``limit`` of the pool by score. When the pool is huge, cheaply
    pre-filter it (candidates with any strong signal) before scoring, so
    the expensive scorer never runs over the whole catalog."""
    if len(pool) <= limit * 50:
        return sorted(pool, key=score, reverse=True)[:limit]
    # cheap pre-filter: keep only candidates the scorer can plausibly rank
    # high (dense similarity present or any keyword/category hit). This
    # avoids calling score() on tens of thousands of irrelevant products.
    try:
        cheap = getattr(score, "_cheap_candidates", None)
    except AttributeError:
        cheap = None
    if cheap is not None:
        cands = [a for a in pool if cheap(a)]
        if cands:
            pool = cands
    import heapq

    return heapq.nlargest(limit, pool, key=score)


def freeform_retrieve_with_pool(query, index: CatalogIndex, dense, top_k: int = 10,
                                pool_limit: int = 200, tree=None):
    """freeform_retrieve + (top-scored pool sample, real pool size) for
    facet guidance."""
    pool, score = _freeform_rank(query, index, dense, tree=tree)
    # Small pool: sort directly and return both the top_k answers and a wider
    # facet-guidance sample, plus the true pool size.
    if len(pool) <= pool_limit * 50:
        ranked = sorted(pool, key=score, reverse=True)
        return ranked[:top_k], ranked[:pool_limit], len(pool)
    # Huge pool: cheaply pre-filter before scoring so we never score the
    # whole catalog with the expensive closure.
    try:
        cheap = getattr(score, "_cheap_candidates", None)
    except AttributeError:
        cheap = None
    cands = [a for a in pool if cheap(a)] if cheap is not None else list(pool)
    # Guard: if the pre-filter dropped everything (shouldn't happen), fall
    # back to the full pool rather than returning nothing.
    if not cands:
        cands = list(pool)
    import heapq

    ranked = heapq.nlargest(pool_limit, cands, key=score)
    return ranked[:top_k], ranked[:pool_limit], len(pool)
