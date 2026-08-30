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

W_PHRASE = 100.0
W_SUPERSEDED = 30.0
W_MAT = 25.0
W_COL = 25.0
W_BUDGET = 40.0
W_CAT = 60.0
W_CAT_SUBSTR = 20.0
W_TITLE = 16.0
W_CAT_TITLE = 3.0
W_TAG = 0.0
W_RATING = 4.0
W_POP = 8.0  # log popularity prior: purchase-record targets skew popular
W_TFIDF = 30.0  # dense-route cosine similarity (only applied when pool is large)
W_STYLE = 20.0  # rating_style consistency: "usually positive" users buy high-rated items
DENSE_MIN_POOL = 200   # apply the dense route only above this pool size
DENSE_MIN_HISTORY = 1  # apply only once this many user messages arrived


def _style_consistency(rating: float | None, profile: dict) -> bool:
    style = profile.get("rating_style", "")
    if style == "mixed" or rating is None:
        return True
    if style == "usually positive":
        return rating >= 4.0
    if style == "critical":
        return rating <= 3.5
    return True

CATEGORY_JUNK = {"clothing", "shoes", "jewelry", "women", "men", "girls", "boys", "baby"}
TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _query_category_tokens(category: str) -> set[str]:
    tokens = {token.lower() for token in TOKEN_RE.findall(category) if len(token) > 1}
    return tokens - CATEGORY_JUNK


def _budget_score(price: float | None, budget: float) -> float:
    if price is None:
        return 0.0
    closeness = max(0.0, 1.0 - abs(price - budget) / max(abs(budget), 1.0))
    return W_BUDGET * closeness


def _constraint_tokens(state: ConversationState) -> set[str]:
    tokens: set[str] = set()
    for phrase in state.active_phrases | state.superseded:
        tokens |= {token.lower() for token in TOKEN_RE.findall(phrase) if len(token) > 1}
    tokens |= state.materials | state.colors
    return tokens


def _category_candidates(index: CatalogIndex, tokens: set[str], limit: int = 3000) -> set[str]:
    if not tokens:
        return set()
    candidates: set[str] | None = None
    for token in sorted(tokens, key=lambda token: len(index.category_token_postings.get(token, ()))):
        postings = index.category_token_postings.get(token)
        if not postings:
            return set()
        candidates = postings if candidates is None else (candidates & postings)
        if candidates is not None and len(candidates) <= limit:
            break
    return candidates or set()


def _category_intersection(index: CatalogIndex, tokens: set[str]) -> set[str]:
    """Full intersection over all category tokens (no early exit)."""
    if not tokens:
        return set()
    candidates: set[str] | None = None
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
) -> float:
    score = 0.0
    product_phrases = index.product_phrases[asin]
    for phrase in state.active_phrases:
        if phrase in product_phrases:
            score += W_PHRASE
    for phrase in state.superseded:
        if phrase in product_phrases:
            score += W_SUPERSEDED
    if state.materials & index.material_sets[asin]:
        score += W_MAT * len(state.materials & index.material_sets[asin])
    if state.colors & index.color_sets[asin]:
        score += W_COL * len(state.colors & index.color_sets[asin])
    if state.budget is not None:
        score += _budget_score(index.prices[asin], state.budget)
    if state.category:
        coarse_key = " ".join(state.category.lower().split())
        if index.category_coarse_key.get(asin) == coarse_key:
            score += W_CAT
        else:
            if query_tokens:
                matched = query_tokens & index.category_tokens[asin]
                score += W_CAT * 0.5 * (len(matched) / len(query_tokens))
            if state.category.lower() in index.category_lower[asin]:
                score += W_CAT_SUBSTR
    overlap = constraint_tokens & index.title_tokens[asin]
    score += W_TITLE * min(len(overlap), 8)
    cat_overlap = query_tokens & index.title_tokens[asin]
    score += W_CAT_TITLE * min(len(cat_overlap), 8)
    for tag in state.user_profile.get("preference_tags", []):
        if tag and tag.lower() in index.corpus[asin].lower():
            score += W_TAG
    rating, rating_number = index.ratings[asin]
    if rating is not None:
        score += W_RATING * min(rating, 5.0)
    if rating_number:
        score += W_POP * min(9.5, math.log1p(rating_number))
    if _style_consistency(rating, state.user_profile):
        score += W_STYLE
    if dense_map is not None:
        score += W_TFIDF * dense_map.get(asin, 0.0)
    return score


def retrieve(
    state: ConversationState,
    index: CatalogIndex,
    top_k: int,
    dense=None,
    llm=None,
    tree=None,
) -> tuple[list[str], dict, int]:
    """Returns (ranked asins, usage, pool size).

    The optional LLM reranks the top-20 only when the tree-first route is
    NOT converged: if the product-property tree alone pins the pool to a
    small set, the deterministic ranking is kept and zero tokens are spent
    ("tree when possible, LLM only when the tree is not enough"). Failures
    fall back to heuristic order."""
    active = [phrase for phrase in state.active_phrases if phrase in index.phrase_postings]
    query_tokens = _query_category_tokens(state.category)
    constraint_tokens = _constraint_tokens(state)

    # ---- R1: exact-phrase conjunction with cascade relaxation ----
    pool: set[str] | None = None
    if active:
        active_sorted = sorted(active, key=lambda phrase: len(index.phrase_postings[phrase]))
        for size in range(len(active_sorted), 0, -1):
            for combo in combinations(active_sorted, size):
                intersection: set[str] | None = None
                for phrase in combo:
                    postings = index.phrase_postings[phrase]
                    intersection = set(postings) if intersection is None else (intersection & postings)
                    if not intersection:
                        break
                if intersection:
                    pool = intersection
                    break
            if pool:
                break

    # ---- R2/R3: extend with category and synthetic-signal candidates ----
    if pool is None or len(pool) < top_k:
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
            pool |= set(index.priced_asins)
        if not pool:
            pool = set(index.products)

    # ---- hard category intersection: the disclosed coarse category is the
    # target's own last-two category parts verbatim, so exact-coarse matching
    # is a tight and always-safe filter; token intersection is the fallback.
    if pool and len(pool) > top_k:
        coarse_key = " ".join(state.category.lower().split()) if state.category else ""
        coarse_set = index.category_coarse_postings.get(coarse_key, set())
        if coarse_set:
            filtered = pool & coarse_set
            if filtered:
                pool = filtered
        elif query_tokens:
            filtered = pool & _category_intersection(index, query_tokens)
            if filtered:
                pool = filtered

    # ---- dense route: TF-IDF similarity when the pool stays large ----
    dense_map: dict[str, float] | None = None
    if dense is not None and len(pool) > DENSE_MIN_POOL and len(state.history) >= DENSE_MIN_HISTORY:
        try:
            dense_map = dict(dense.query_scores(" ".join(state.history), list(pool)))
        except Exception:
            dense_map = None

    ranked = sorted(
        pool,
        key=lambda asin: (
            _score(asin, index, state, query_tokens, constraint_tokens, dense_map),
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
            ranked = ordered + [asin for asin in ranked if asin not in ordered]
    return ranked[:top_k], usage, len(pool)


def _plural_variants(keyword: str) -> set[str]:
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
            sims = dense.query_scores(query_text, list(pool))
            top = sorted(sims, key=lambda item: -item[1])[:300]
            dense_map = dict(top)
            pool |= dense_map.keys()
        else:
            sims = dense.query_scores(query_text, list(pool))
            dense_map = dict(sims)
    if not pool:
        pool = set(index.products)

    patterns = {keyword: re.compile(rf"\b{re.escape(keyword)}\b") for keyword in query.keywords}
    keyword_variants = {
        kw: _plural_variants(kw) for kw in query.keywords
    } if hasattr(index, "corpus_tokens") else {}
    weights = query.keyword_weights or {}
    budget = query.budget

    def score(asin: str) -> float:
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
                if price > budget * 1.35:
                    value -= 30.0
                else:
                    value += 30.0 * max(0.0, 1.0 - abs(price - budget) / max(budget, 1.0))
        rating, rating_number = index.ratings[asin]
        if rating is not None:
            value += 3.0 * min(rating, 5.0)
        if rating_number:
            value += 3.0 * min(9.5, math.log1p(rating_number))
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
    if len(pool) <= pool_limit * 50:
        ranked = sorted(pool, key=score, reverse=True)
        return ranked[:top_k], ranked[:pool_limit], len(pool)
    try:
        cheap = getattr(score, "_cheap_candidates", None)
    except AttributeError:
        cheap = None
    cands = [a for a in pool if cheap(a)] if cheap is not None else list(pool)
    if not cands:
        cands = list(pool)
    import heapq

    ranked = heapq.nlargest(pool_limit, cands, key=score)
    return ranked[:top_k], ranked[:pool_limit], len(pool)
