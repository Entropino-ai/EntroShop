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
) -> tuple[list[str], dict, int]:
    """Returns (ranked asins, usage, pool size). The optional LLM reranks the
    top-20 when the pool is medium-sized; failures fall back to heuristic
    order."""
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
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    if llm is not None and top_k < len(pool) <= 60 and state.history:
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


def _freeform_rank(query, index: CatalogIndex, dense):
    """Build the candidate pool and a scoring closure (shared by the
    public freeform entry points)."""
    pool: set[str] = set()
    dense_map: dict[str, float] = {}
    if dense is not None:
        # include materials/colors in the dense query so semantic models
        # can enforce them ("wool scarf black" -> black wool scarves)
        query_text = " ".join(
            [query.text, *query.keywords, *sorted(query.materials), *sorted(query.colors)]
        ).strip()
        if query_text:
            sims = dense.query_scores(query_text, dense.asins)
            top = sorted(sims, key=lambda item: -item[1])[:300]
            dense_map = dict(top)
            pool |= dense_map.keys()
    for material in query.materials:
        pool |= index.material_postings.get(material, set())
    for color in query.colors:
        pool |= index.color_postings.get(color, set())
    category_variants: dict[str, set[str]] = {}
    for keyword in query.keywords:
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
    if not pool:
        pool = set(index.products)

    patterns = {keyword: re.compile(rf"\b{re.escape(keyword)}\b") for keyword in query.keywords}
    weights = query.keyword_weights or {}
    budget = query.budget

    def score(asin: str) -> float:
        value = 35.0 * dense_map.get(asin, 0.0)
        corpus = index.corpus[asin].lower()
        title_tokens = index.title_tokens[asin]
        for keyword, pattern in patterns.items():
            weight = weights.get(keyword, 1.0)
            if pattern.search(corpus):
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

    return pool, score


def freeform_retrieve(query, index: CatalogIndex, dense, top_k: int = 10) -> list[str]:
    """Demo chat-mode retrieval for free-form human input.

    Builds candidates from three routes — TF-IDF/MiniLM dense top-N over the
    whole catalog, synthetic material/color postings, and category-token
    matches — then ranks with a hybrid score. Not used by the submission
    agent (the simulator always speaks fixed templates).
    """
    pool, score = _freeform_rank(query, index, dense)
    ranked = sorted(pool, key=score, reverse=True)
    return ranked[:top_k]


def freeform_retrieve_with_pool(query, index: CatalogIndex, dense, top_k: int = 10,
                                pool_limit: int = 200):
    """freeform_retrieve + (top-scored pool sample, real pool size) for
    facet guidance."""
    pool, score = _freeform_rank(query, index, dense)
    ranked = sorted(pool, key=score, reverse=True)
    return ranked[:top_k], ranked[:pool_limit], len(pool)
