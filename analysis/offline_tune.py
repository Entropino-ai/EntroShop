"""Offline weight tuning: replay sessions, record per-turn retrieval states,
then grid-search scoring weights without re-running the evaluator.

The pool construction (phrase cascade + hard category intersection) is
scoring-independent, so we can replay once and evaluate many scoring
configurations offline.

Flow: ``record_turns`` replays every public-set session through the same
state machine the evaluator drives, snapshotting each turn's conversation
state and candidate pool into a ``TurnRecord``. ``evaluate_config`` then
re-ranks those frozen pools under arbitrary weight configurations, so tuning
is a pure, deterministic grid search with no LLM or network cost.

Run directly: ``python3 analysis/offline_tune.py`` from the repo root.
"""
from __future__ import annotations

import copy
import json
import math
import re
import sys
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

# Repo root (one level above analysis/) so the evaluator/ and agent_lib/
# packages are importable regardless of the current working directory.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluator.local_evaluator import (  # noqa: E402
    MAX_TURNS,
    TOP_K,
    catalog_index,
    coarse_category,
    customer_reply,
    initial_message,
    intent_card,
    load_jsonl,
    materialize_hidden_fields,
)
from agent_lib.extract import parse  # noqa: E402
from agent_lib.index import CatalogIndex  # noqa: E402
from agent_lib.state import ConversationState  # noqa: E402

CATALOG = ROOT / "data" / "catalog.jsonl"
PUBLIC = ROOT / "data" / "public_set.jsonl"

TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
CATEGORY_JUNK = {"clothing", "shoes", "jewelry", "women", "men", "girls", "boys", "baby"}


@dataclass
class TurnRecord:
    """Frozen snapshot of one conversation turn, ready for offline re-ranking.

    Attributes:
        turn: 1-based turn index within the session.
        state: Deep-copied ConversationState at this turn (copied so later turns
            cannot mutate this snapshot).
        pool: Candidate parent_asin set produced by ``build_pool`` for this turn.
        target: Ground-truth parent_asin for the session (the scoring target).
        override_applied: Whether the scripted intent override (if any) has been
            applied yet; only True turns are eligible for scoring in
            ``evaluate_config``.
    """
    turn: int
    state: ConversationState
    pool: set[str]
    target: str
    override_applied: bool


def build_pool(state: ConversationState, idx: CatalogIndex) -> set[str]:
    """Replicate retrieve()'s scoring-independent pool construction.

    Builds the candidate-product set for one turn exactly the way the agent's
    ``retrieve()`` does, but WITHOUT any scoring-dependent ranking. That is the
    key enabler for offline tuning: the pool depends only on conversation state
    and the catalog index, so it can be recorded once and re-ranked under many
    weight configurations without re-running the evaluator.

    Strategy (in order):
      1. Phrase cascade — intersect the postings of the active phrases, trying
         the largest combinations of the rarest phrases first, so the most
         specific products are preferred.
      2. If that yields fewer than TOP_K products, broaden with a hard category
         intersection and union in material/color/budget matches.
      3. Fall back to the entire catalog if nothing matches.
      4. If the pool is still larger than TOP_K, narrow it back down by
         intersecting with the category-token candidates.

    Args:
        state: The current conversation state (active phrases, category,
            materials, colors, budget).
        idx: Prebuilt catalog index exposing phrase/category/material/color
            postings and priced/whole-catalog product sets.

    Returns:
        An unordered set of candidate ``parent_asin`` ids. Never empty in
        practice: the final fallback is the full catalog.
    """
    # Keep only active phrases that actually index any products.
    active = [p for p in state.active_phrases if p in idx.phrase_postings]
    # Tokenize the stated category and drop junk tokens (gender/apparel headings
    # that carry no discriminative signal between products).
    query_tokens = {t.lower() for t in TOKEN_RE.findall(state.category) if len(t) > 1} - CATEGORY_JUNK
    pool = None
    if active:
        # Rare (short-posting-list) phrases first: intersecting them earlier
        # shrinks the candidate set fastest.
        active_sorted = sorted(active, key=lambda p: len(idx.phrase_postings[p]))
        # Try the largest combinations first (most specific conjunction) down to
        # single phrases; the first non-empty intersection wins.
        for size in range(len(active_sorted), 0, -1):
            for combo in combinations(active_sorted, size):
                inter = None
                for p in combo:
                    postings = idx.phrase_postings[p]
                    inter = set(postings) if inter is None else (inter & postings)
                    if not inter:
                        break
                if inter:
                    pool = inter
                    break
            if pool:
                break
    # Broaden only when the phrase cascade produced nothing or too few products.
    if pool is None or len(pool) < TOP_K:
        cat_cand = set()
        if query_tokens:
            cat_cand = None
            # Intersect category-token postings, rarest token first; bail out of
            # the intersection as soon as a token matches nothing.
            for token in sorted(query_tokens, key=lambda t: len(idx.category_token_postings.get(t, ()))):
                postings = idx.category_token_postings.get(token)
                if not postings:
                    cat_cand = set()
                    break
                cat_cand = postings if cat_cand is None else (cat_cand & postings)
                if cat_cand is not None and len(cat_cand) <= 3000:  # mirror retrieve() early exit
                    break
        # Merge category candidates into the phrase pool (or seed the pool).
        if pool is None:
            pool = set(cat_cand or ())
        else:
            pool |= cat_cand
        # Union in products matching any requested material/color/budget so the
        # pool stays wide enough to rank later.
        for m in state.materials:
            pool |= idx.material_postings.get(m, set())
        for c in state.colors:
            pool |= idx.color_postings.get(c, set())
        if state.budget is not None:
            pool |= set(idx.priced_asins)
        # Last-resort fallback: the whole catalog.
        if not pool:
            pool = set(idx.products)
    # If broadening overshot, narrow the pool back down via category tokens.
    if pool and len(pool) > TOP_K and query_tokens:
        filtered = set()
        cands = None
        for token in sorted(query_tokens, key=lambda t: len(idx.category_token_postings.get(t, ()))):
            postings = idx.category_token_postings.get(token)
            if not postings:
                cands = set()
                break
            cands = postings if cands is None else (cands & postings)
        # ``cands or set()``: an empty intersection means "no filter", leaving
        # ``filtered`` empty so the original pool is kept as-is.
        filtered = pool & (cands or set())
        if filtered:
            pool = filtered
    return pool


def record_turns(idx: CatalogIndex, products: dict, samples: list[dict]) -> list[TurnRecord]:
    """Replay every sample session and snapshot one TurnRecord per turn.

    Drives the same ConversationState state machine the evaluator drives, so the
    recorded pools match exactly what the agent would retrieve at each turn. The
    result is a frozen replay of the whole public set: each TurnRecord holds a
    deep-copied state, the candidate pool, the ground-truth target, and whether
    the intent override (if any) has been applied yet.

    The conversation is advanced through ALL MAX_TURNS turns regardless of hits;
    hit/mrr/mttc are computed later by ``evaluate_config``, so early termination
    here would silently drop scoring-relevant turns.

    Args:
        idx: Prebuilt catalog index used by ``parse`` and ``build_pool``.
        products: Mapping from parent_asin to product dicts (used to materialize
            hidden fields and read ground-truth categories).
        samples: Loaded public-set sessions; each must have ``sample_id``,
            ``user_profile``, ``ground_truth``, and ``scenario_type``.

    Returns:
        A flat list of TurnRecords in (session, turn) replay order. Session
        boundaries are recoverable via ``state.session_id``.
    """
    records: list[TurnRecord] = []
    for sample in samples:
        session_id = f"offline_{sample['sample_id']}"
        state = ConversationState(session_id=session_id, user_profile=sample["user_profile"])
        target = str(sample["ground_truth"]["parent_asin"])
        # Materialize the hidden intent card and scripted behavior that the
        # simulator normally keeps out of the customer's visible messages.
        card, behavior = materialize_hidden_fields(sample, products)
        effective = {**sample, "intent_card": card, "behavior": behavior}
        disclosed: set[str] = set()
        boundary_used = False
        # Non-override scenarios are scorable from turn 1; an intent_override
        # scenario starts "unapplied" until its scripted override turn arrives.
        override_applied = sample["scenario_type"] != "intent_override"
        user_message = initial_message(effective, coarse_category(products[target].get("categories") or []), disclosed)
        for turn in range(1, MAX_TURNS + 1):
            parsed = parse(user_message, idx)
            if turn == 1:
                # First turn seeds the opening phrases and applies them as the
                # opening move (mirroring the agent's reset/respond flow).
                state.opening_phrases = set(parsed.phrases)
                state.apply(parsed, is_opening=True)
            else:
                state.apply(parsed)
            # Mirror the evaluator's last-ask bookkeeping used by downstream
            # retrieval/guidance decisions.
            state.last_ask = state.plan[-1] if state.plan else None
            pool = build_pool(state, idx)
            # Deep-copy the state because the same object is mutated on the next
            # turn; each TurnRecord must remain a frozen snapshot.
            records.append(TurnRecord(turn=turn, state=copy.deepcopy(state), pool=pool,
                                      target=target, override_applied=override_applied))
            # advance the conversation exactly like the evaluator (never stop
            # early: scoring-dependent hit checks happen in evaluate_config)
            if turn == MAX_TURNS:
                break
            override = effective.get("behavior", {}).get("override") or {}
            # At the scripted override turn, flip the override flag and swap in
            # the customer's corrected message plus the newly disclosed value.
            if not override_applied and turn + 1 == int(override.get("turn", 3)):
                override_applied = True
                new_value = str(override.get("new_value", ""))
                if new_value:
                    disclosed.add(new_value)
                user_message = str(override.get("message", "Actually, please ignore my earlier preference."))
            else:
                # Normal turn: advance via the simulated customer reply.
                user_message, boundary_used = customer_reply(
                    effective, "other", disclosed, boundary_used
                )
    return records


def score_config(rec: TurnRecord, idx: CatalogIndex, cfg: dict) -> float:
    """Score one TurnRecord against its own ground-truth target.

    Legacy fast-path scorer: it evaluates ``rec.state`` against ``rec.target``
    (the record's fixed target) rather than against an arbitrary candidate. It
    is superseded by ``_score_for``, which scores any candidate ``asin`` and is
    what ``evaluate_config`` actually uses; this function survives only for the
    abandoned "cheap trick" block in ``evaluate_config`` and as reference.

    The feature terms mirror ``_score_for`` exactly except that the target is
    taken from ``rec.target`` and there is no style-consistency bonus.

    Args:
        rec: A turn snapshot whose ``state`` is scored against ``rec.target``.
        idx: Catalog index with per-product phrase/material/color/title/rating
            sets.
        cfg: Weight configuration (keys ``w_phrase``, ``w_sup``, ``w_mat``,
            ``w_col``, ``w_budget``, ``w_cat``, ``w_cat_substr``, ``w_title``,
            ``w_cat_title``, ``w_tag``, ``w_rating``, ``w_pop``).

    Returns:
        A non-negative float; higher means a better match. Deterministic and
        side-effect free.
    """
    state = rec.state
    # Category query tokens (same junk filtering as build_pool).
    qt = {t.lower() for t in TOKEN_RE.findall(state.category) if len(t) > 1} - CATEGORY_JUNK
    # All constraint tokens: phrase words + explicit material/color values.
    ctokens = set()
    for p in state.active_phrases | state.superseded:
        ctokens |= {t.lower() for t in TOKEN_RE.findall(p) if len(t) > 1}
    ctokens |= state.materials | state.colors
    s = 0.0
    # Exact active-phrase match against the target's phrase set.
    for p in state.active_phrases:
        if p in idx.product_phrases[rec.target]:
            s += cfg["w_phrase"]
    # Superseded phrases still score, at a lower weight.
    for p in state.superseded:
        if p in idx.product_phrases[rec.target]:
            s += cfg["w_sup"]
    # Material / color overlap counts.
    s += cfg["w_mat"] * len(state.materials & idx.material_sets[rec.target])
    s += cfg["w_col"] * len(state.colors & idx.color_sets[rec.target])
    # Budget proximity decays linearly from 1.0 down to 0.0 as price drifts.
    if state.budget is not None and idx.prices[rec.target] is not None:
        s += cfg["w_budget"] * max(0.0, 1.0 - abs(idx.prices[rec.target] - state.budget) / max(abs(state.budget), 1.0))
    # Category overlap is the fraction of query tokens present in the target.
    if qt:
        s += cfg["w_cat"] * len(qt & idx.category_tokens[rec.target]) / len(qt)
    # Whole category string appears verbatim in the target's categories.
    if state.category and state.category.lower() in idx.category_lower[rec.target]:
        s += cfg["w_cat_substr"]
    # Title-token overlap, capped at 8 to stop long titles dominating.
    s += cfg["w_title"] * min(len(ctokens & idx.title_tokens[rec.target]), 8)
    s += cfg["w_cat_title"] * min(len(qt & idx.title_tokens[rec.target]), 8)
    # Preference-tag substring bonus against the full product corpus text.
    for tag in state.user_profile.get("preference_tags", []):
        if tag and tag.lower() in idx.corpus[rec.target].lower():
            s += cfg["w_tag"]
    # Rating and popularity (log-scaled review count) bonuses.
    rating, rn = idx.ratings[rec.target]
    if rating is not None:
        s += cfg["w_rating"] * min(rating, 5.0)
    if rn:
        s += cfg["w_pop"] * min(9.5, math.log1p(rn))
    return s


def evaluate_config(records: list[TurnRecord], idx: CatalogIndex, cfg: dict) -> dict:
    """Evaluate a weight configuration over the recorded sessions.

    Groups the flat TurnRecord stream back into sessions, then for each session
    finds the FIRST post-override turn where the ground-truth target ranks within
    TOP_K of the re-ranked pool. From those results it derives Hit@K, MRR, MTTC,
    an efficiency score, and the combined TechnicalScore (ts).

    Contract: pools are reused verbatim (never rebuilt), so this is a pure
    re-ranking of frozen candidate sets — the whole point of offline tuning. Only
    turns with ``override_applied`` are scored, because before an intent override
    lands the customer's stated preferences may not reflect the true target.

    Args:
        records: TurnRecords produced by ``record_turns``, in replay order.
        idx: Catalog index used by ``_score_for``.
        cfg: Weight configuration dict.

    Returns:
        Dict with ``hit`` (fraction of sessions where the target is in TOP_K),
        ``mrr`` (mean reciprocal rank, rounded), ``mttc`` (mean turns to correct,
        rounded), and ``ts`` (TechnicalScore = 0.5*hit + 0.3*mrr +
        0.2*efficiency).
    """
    # group records by session in order
    sessions: list[list[TurnRecord]] = []
    current = []
    last_id = None
    for rec in records:
        sid = rec.state.session_id
        # A session-id change (with a non-empty current list) closes the session.
        if sid != last_id and current:
            sessions.append(current)
            current = []
        current.append(rec)
        last_id = sid
    # Flush the final in-progress session.
    if current:
        sessions.append(current)
    hits = 0
    mrr = 0.0
    mttc = 0.0
    for session in sessions:
        first = None
        best = None
        # NOTE: this first loop is an abandoned fast path — it re-ranks with
        # score_config, which scores each candidate against itself (the target is
        # overwritten with the candidate asin), so the result is meaningless and
        # immediately discarded via ``break``. Kept only to avoid changing code;
        # the real evaluation is the loop below.
        for rec in session:
            if rec.override_applied:
                pool = rec.pool
                scored = sorted(pool, key=lambda a: score_config(
                    TurnRecord(rec.turn, rec.state, pool, a, rec.override_applied), idx, cfg), reverse=True)
                # note: cheap trick above scores the target only; do it properly:
                break
        # proper evaluation per record
        for rec in session:
            if rec.override_applied:
                # Re-rank the frozen pool by score and check whether the target
                # lands in the top TOP_K; record its 1-based rank and the turn.
                ranked = sorted(rec.pool, key=lambda a: _score_for(a, rec, idx, cfg), reverse=True)
                if rec.target in ranked[:TOP_K]:
                    best = ranked.index(rec.target) + 1
                    first = rec.turn
                    break
        if first is not None:
            hits += 1
            # Reciprocal rank: 1/1 for rank 1, 1/2 for rank 2, etc.
            mrr += 1.0 / best
            mttc += first
        else:
            # Misses are penalized as one turn past the maximum.
            mttc += MAX_TURNS + 1
    n = len(sessions)
    mrr /= n
    mttc /= n
    # Efficiency maps MTTC in [1, 11] linearly to [1, 0], clamped to [0, 1].
    eff = max(0.0, min(1.0, (11.0 - mttc) / 10.0))
    return {"hit": hits / n, "mrr": round(mrr, 4), "mttc": round(mttc, 3),
            "ts": round(0.5 * hits / n + 0.3 * mrr + 0.2 * eff, 4)}


def _style_consistency(rating: float | None, profile: dict) -> bool:
    """Return whether a product rating is consistent with the user's rating style.

    This is a one-sided bonus gate: it returns True when the rating matches the
    user's stated taste (or when no strong preference is expressed), and False
    when it contradicts it. Callers only ADD a weight when this is True, so an
    inconsistent rating is simply not rewarded rather than actively penalized.

    Args:
        rating: The product's average rating, or None if unknown.
        profile: The session's user profile, possibly containing
            ``rating_style`` in {"mixed", "usually positive", "critical"}.

    Returns:
        True if the rating is consistent (or unconstrained); False only for a
        clear mismatch (e.g. a low rating for a "usually positive" user).
    """
    style = profile.get("rating_style", "")
    # No stated preference and unknown ratings are never penalized.
    if style == "mixed" or rating is None:
        return True
    if style == "usually positive":
        return rating >= 4.0
    if style == "critical":
        return rating <= 3.5
    return True


def _score_for(asin: str, rec: TurnRecord, idx: CatalogIndex, cfg: dict) -> float:
    """Score a single candidate ``asin`` against a turn's conversation state.

    This is the real ranking function used by ``evaluate_config``. It sums a
    weighted set of relevance features comparing the turn's constraints (active
    and superseded phrases, category, materials, colors, budget, preference tags)
    against the candidate product, plus quality signals (rating, popularity) and
    an optional style-consistency bonus.

    Args:
        asin: Candidate ``parent_asin`` being scored.
        rec: The turn snapshot supplying the conversation state.
        idx: Catalog index exposing per-product phrase/material/color/title sets,
            category tokens/lower, prices, ratings, and corpus text.
        cfg: Weight configuration; see ``score_config`` for the key set.

    Returns:
        A non-negative float; higher ranks first. Deterministic, no side effects,
        and cheap (pure set/string operations), so it can run over every
        candidate in every pool during a grid search.
    """
    state = rec.state
    # Category query tokens (same junk filtering as build_pool).
    qt = {t.lower() for t in TOKEN_RE.findall(state.category) if len(t) > 1} - CATEGORY_JUNK
    # All constraint tokens: phrase words + explicit material/color values.
    ctokens = set()
    for p in state.active_phrases | state.superseded:
        ctokens |= {t.lower() for t in TOKEN_RE.findall(p) if len(t) > 1}
    ctokens |= state.materials | state.colors
    s = 0.0
    # Exact active-phrase match against the candidate's phrase set.
    for p in state.active_phrases:
        if p in idx.product_phrases[asin]:
            s += cfg["w_phrase"]
    # Superseded phrases still score, at a lower weight.
    for p in state.superseded:
        if p in idx.product_phrases[asin]:
            s += cfg["w_sup"]
    # Material / color overlap counts.
    s += cfg["w_mat"] * len(state.materials & idx.material_sets[asin])
    s += cfg["w_col"] * len(state.colors & idx.color_sets[asin])
    # Budget proximity decays linearly from 1.0 down to 0.0 as price drifts.
    if state.budget is not None and idx.prices[asin] is not None:
        s += cfg["w_budget"] * max(0.0, 1.0 - abs(idx.prices[asin] - state.budget) / max(abs(state.budget), 1.0))
    # Category overlap is the fraction of query tokens present in the candidate.
    if qt:
        s += cfg["w_cat"] * len(qt & idx.category_tokens[asin]) / len(qt)
    # Whole category string appears verbatim in the candidate's categories.
    if state.category and state.category.lower() in idx.category_lower[asin]:
        s += cfg["w_cat_substr"]
    # Title-token overlap, capped at 8 to stop long titles dominating.
    s += cfg["w_title"] * min(len(ctokens & idx.title_tokens[asin]), 8)
    s += cfg["w_cat_title"] * min(len(qt & idx.title_tokens[asin]), 8)
    # Preference-tag substring bonus against the full product corpus text.
    for tag in state.user_profile.get("preference_tags", []):
        if tag and tag.lower() in idx.corpus[asin].lower():
            s += cfg["w_tag"]
    # Rating and popularity (log-scaled review count) bonuses.
    rating, rn = idx.ratings[asin]
    if rating is not None:
        s += cfg["w_rating"] * min(rating, 5.0)
    if rn:
        s += cfg["w_pop"] * min(9.5, math.log1p(rn))
    # Style-consistency bonus: only added when the rating matches the user's
    # stated rating style, so mismatches are never penalized, only unblessed.
    if _style_consistency(rating, state.user_profile):
        s += cfg["w_style"]
    return s


def main() -> None:
    """Record the public set once, then grid-search scoring weights offline.

    Builds the catalog index, replays all public sessions into TurnRecords,
    prints the baseline configuration's metrics, then evaluates every
    combination of four weight dimensions (w_style, w_pop, w_rating,
    w_cat_title) — 4*3*3*3 = 108 configs — and reports the top 10 by
    TechnicalScore.

    Side effects: prints progress and results to stdout only. Deterministic;
    no network or LLM access.
    """
    idx = CatalogIndex(CATALOG)
    samples = load_jsonl(PUBLIC)
    # catalog_index returns the product dict keyed by parent_asin (last element).
    _, _, products = catalog_index(CATALOG)
    print("recording turns...")
    records = record_turns(idx, products, samples)
    print(f"recorded {len(records)} turn-records across {len(set(r.state.session_id for r in records))} sessions")

    # Baseline weights; the grid below perturbs only the last four dimensions.
    base = dict(w_phrase=100.0, w_sup=30.0, w_mat=25.0, w_col=25.0, w_budget=40.0,
                w_cat=60.0, w_cat_substr=20.0, w_title=16.0, w_cat_title=3.0,
                w_tag=0.0, w_rating=4.0, w_pop=8.0, w_style=0.0)
    print("baseline config:", evaluate_config(records, idx, base))

    variants = []
    # Cartesian product over the four tunable weights; each name encodes its
    # settings so results are self-describing.
    for w_style in [0.0, 5.0, 10.0, 20.0]:
        for w_pop in [4.0, 8.0, 12.0]:
            for w_rating in [2.0, 4.0, 6.0]:
                for w_cat_title in [0.0, 3.0, 6.0]:
                    variants.append((f"s{w_style}_p{w_pop}_r{w_rating}_ct{w_cat_title}",
                                     {**base, "w_style": w_style, "w_pop": w_pop,
                                      "w_rating": w_rating, "w_cat_title": w_cat_title}))
    results = []
    for name, cfg in variants:
        r = evaluate_config(records, idx, cfg)
        # Tuple sorted by ts first (primary key), then the remaining fields.
        results.append((r["ts"], r["hit"], r["mrr"], r["mttc"], name, cfg))
    results.sort(reverse=True)
    print("\ntop 10 configs (TS, hit, mrr, mttc, name):")
    for row in results[:10]:
        print("  ", row[:5])
    print("\nbest cfg:", results[0][5])


if __name__ == "__main__":
    main()
