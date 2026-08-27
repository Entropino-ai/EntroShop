"""Offline weight tuning: replay sessions, record per-turn retrieval states,
then grid-search scoring weights without re-running the evaluator.

The pool construction (phrase cascade + hard category intersection) is
scoring-independent, so we can replay once and evaluate many scoring
configurations offline.
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
    turn: int
    state: ConversationState
    pool: set[str]
    target: str
    override_applied: bool


def build_pool(state: ConversationState, idx: CatalogIndex) -> set[str]:
    """Replicate retrieve()'s scoring-independent pool construction."""
    active = [p for p in state.active_phrases if p in idx.phrase_postings]
    query_tokens = {t.lower() for t in TOKEN_RE.findall(state.category) if len(t) > 1} - CATEGORY_JUNK
    pool = None
    if active:
        active_sorted = sorted(active, key=lambda p: len(idx.phrase_postings[p]))
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
    if pool is None or len(pool) < TOP_K:
        cat_cand = set()
        if query_tokens:
            cat_cand = None
            for token in sorted(query_tokens, key=lambda t: len(idx.category_token_postings.get(t, ()))):
                postings = idx.category_token_postings.get(token)
                if not postings:
                    cat_cand = set()
                    break
                cat_cand = postings if cat_cand is None else (cat_cand & postings)
                if cat_cand is not None and len(cat_cand) <= 3000:  # mirror retrieve() early exit
                    break
        if pool is None:
            pool = set(cat_cand or ())
        else:
            pool |= cat_cand
        for m in state.materials:
            pool |= idx.material_postings.get(m, set())
        for c in state.colors:
            pool |= idx.color_postings.get(c, set())
        if state.budget is not None:
            pool |= set(idx.priced_asins)
        if not pool:
            pool = set(idx.products)
    if pool and len(pool) > TOP_K and query_tokens:
        filtered = set()
        cands = None
        for token in sorted(query_tokens, key=lambda t: len(idx.category_token_postings.get(t, ()))):
            postings = idx.category_token_postings.get(token)
            if not postings:
                cands = set()
                break
            cands = postings if cands is None else (cands & postings)
        filtered = pool & (cands or set())
        if filtered:
            pool = filtered
    return pool


def record_turns(idx: CatalogIndex, products: dict, samples: list[dict]) -> list[TurnRecord]:
    records: list[TurnRecord] = []
    for sample in samples:
        session_id = f"offline_{sample['sample_id']}"
        state = ConversationState(session_id=session_id, user_profile=sample["user_profile"])
        target = str(sample["ground_truth"]["parent_asin"])
        card, behavior = materialize_hidden_fields(sample, products)
        effective = {**sample, "intent_card": card, "behavior": behavior}
        disclosed: set[str] = set()
        boundary_used = False
        override_applied = sample["scenario_type"] != "intent_override"
        user_message = initial_message(effective, coarse_category(products[target].get("categories") or []), disclosed)
        for turn in range(1, MAX_TURNS + 1):
            parsed = parse(user_message, idx)
            if turn == 1:
                state.opening_phrases = set(parsed.phrases)
                state.apply(parsed, is_opening=True)
            else:
                state.apply(parsed)
            state.last_ask = state.plan[-1] if state.plan else None
            pool = build_pool(state, idx)
            records.append(TurnRecord(turn=turn, state=copy.deepcopy(state), pool=pool,
                                      target=target, override_applied=override_applied))
            # advance the conversation exactly like the evaluator (never stop
            # early: scoring-dependent hit checks happen in evaluate_config)
            if turn == MAX_TURNS:
                break
            override = effective.get("behavior", {}).get("override") or {}
            if not override_applied and turn + 1 == int(override.get("turn", 3)):
                override_applied = True
                new_value = str(override.get("new_value", ""))
                if new_value:
                    disclosed.add(new_value)
                user_message = str(override.get("message", "Actually, please ignore my earlier preference."))
            else:
                user_message, boundary_used = customer_reply(
                    effective, "other", disclosed, boundary_used
                )
    return records


def score_config(rec: TurnRecord, idx: CatalogIndex, cfg: dict) -> float:
    state = rec.state
    qt = {t.lower() for t in TOKEN_RE.findall(state.category) if len(t) > 1} - CATEGORY_JUNK
    ctokens = set()
    for p in state.active_phrases | state.superseded:
        ctokens |= {t.lower() for t in TOKEN_RE.findall(p) if len(t) > 1}
    ctokens |= state.materials | state.colors
    s = 0.0
    for p in state.active_phrases:
        if p in idx.product_phrases[rec.target]:
            s += cfg["w_phrase"]
    for p in state.superseded:
        if p in idx.product_phrases[rec.target]:
            s += cfg["w_sup"]
    s += cfg["w_mat"] * len(state.materials & idx.material_sets[rec.target])
    s += cfg["w_col"] * len(state.colors & idx.color_sets[rec.target])
    if state.budget is not None and idx.prices[rec.target] is not None:
        s += cfg["w_budget"] * max(0.0, 1.0 - abs(idx.prices[rec.target] - state.budget) / max(abs(state.budget), 1.0))
    if qt:
        s += cfg["w_cat"] * len(qt & idx.category_tokens[rec.target]) / len(qt)
    if state.category and state.category.lower() in idx.category_lower[rec.target]:
        s += cfg["w_cat_substr"]
    s += cfg["w_title"] * min(len(ctokens & idx.title_tokens[rec.target]), 8)
    s += cfg["w_cat_title"] * min(len(qt & idx.title_tokens[rec.target]), 8)
    for tag in state.user_profile.get("preference_tags", []):
        if tag and tag.lower() in idx.corpus[rec.target].lower():
            s += cfg["w_tag"]
    rating, rn = idx.ratings[rec.target]
    if rating is not None:
        s += cfg["w_rating"] * min(rating, 5.0)
    if rn:
        s += cfg["w_pop"] * min(9.5, math.log1p(rn))
    return s


def evaluate_config(records: list[TurnRecord], idx: CatalogIndex, cfg: dict) -> dict:
    # group records by session in order
    sessions: list[list[TurnRecord]] = []
    current = []
    last_id = None
    for rec in records:
        sid = rec.state.session_id
        if sid != last_id and current:
            sessions.append(current)
            current = []
        current.append(rec)
        last_id = sid
    if current:
        sessions.append(current)
    hits = 0
    mrr = 0.0
    mttc = 0.0
    for session in sessions:
        first = None
        best = None
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
                ranked = sorted(rec.pool, key=lambda a: _score_for(a, rec, idx, cfg), reverse=True)
                if rec.target in ranked[:TOP_K]:
                    best = ranked.index(rec.target) + 1
                    first = rec.turn
                    break
        if first is not None:
            hits += 1
            mrr += 1.0 / best
            mttc += first
        else:
            mttc += MAX_TURNS + 1
    n = len(sessions)
    mrr /= n
    mttc /= n
    eff = max(0.0, min(1.0, (11.0 - mttc) / 10.0))
    return {"hit": hits / n, "mrr": round(mrr, 4), "mttc": round(mttc, 3),
            "ts": round(0.5 * hits / n + 0.3 * mrr + 0.2 * eff, 4)}


def _style_consistency(rating: float | None, profile: dict) -> bool:
    style = profile.get("rating_style", "")
    if style == "mixed" or rating is None:
        return True
    if style == "usually positive":
        return rating >= 4.0
    if style == "critical":
        return rating <= 3.5
    return True


def _score_for(asin: str, rec: TurnRecord, idx: CatalogIndex, cfg: dict) -> float:
    state = rec.state
    qt = {t.lower() for t in TOKEN_RE.findall(state.category) if len(t) > 1} - CATEGORY_JUNK
    ctokens = set()
    for p in state.active_phrases | state.superseded:
        ctokens |= {t.lower() for t in TOKEN_RE.findall(p) if len(t) > 1}
    ctokens |= state.materials | state.colors
    s = 0.0
    for p in state.active_phrases:
        if p in idx.product_phrases[asin]:
            s += cfg["w_phrase"]
    for p in state.superseded:
        if p in idx.product_phrases[asin]:
            s += cfg["w_sup"]
    s += cfg["w_mat"] * len(state.materials & idx.material_sets[asin])
    s += cfg["w_col"] * len(state.colors & idx.color_sets[asin])
    if state.budget is not None and idx.prices[asin] is not None:
        s += cfg["w_budget"] * max(0.0, 1.0 - abs(idx.prices[asin] - state.budget) / max(abs(state.budget), 1.0))
    if qt:
        s += cfg["w_cat"] * len(qt & idx.category_tokens[asin]) / len(qt)
    if state.category and state.category.lower() in idx.category_lower[asin]:
        s += cfg["w_cat_substr"]
    s += cfg["w_title"] * min(len(ctokens & idx.title_tokens[asin]), 8)
    s += cfg["w_cat_title"] * min(len(qt & idx.title_tokens[asin]), 8)
    for tag in state.user_profile.get("preference_tags", []):
        if tag and tag.lower() in idx.corpus[asin].lower():
            s += cfg["w_tag"]
    rating, rn = idx.ratings[asin]
    if rating is not None:
        s += cfg["w_rating"] * min(rating, 5.0)
    if rn:
        s += cfg["w_pop"] * min(9.5, math.log1p(rn))
    if _style_consistency(rating, state.user_profile):
        s += cfg["w_style"]
    return s


def main() -> None:
    idx = CatalogIndex(CATALOG)
    samples = load_jsonl(PUBLIC)
    _, _, products = catalog_index(CATALOG)
    print("recording turns...")
    records = record_turns(idx, products, samples)
    print(f"recorded {len(records)} turn-records across {len(set(r.state.session_id for r in records))} sessions")

    base = dict(w_phrase=100.0, w_sup=30.0, w_mat=25.0, w_col=25.0, w_budget=40.0,
                w_cat=60.0, w_cat_substr=20.0, w_title=16.0, w_cat_title=3.0,
                w_tag=0.0, w_rating=4.0, w_pop=8.0, w_style=0.0)
    print("baseline config:", evaluate_config(records, idx, base))

    variants = []
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
        results.append((r["ts"], r["hit"], r["mrr"], r["mttc"], name, cfg))
    results.sort(reverse=True)
    print("\ntop 10 configs (TS, hit, mrr, mttc, name):")
    for row in results[:10]:
        print("  ", row[:5])
    print("\nbest cfg:", results[0][5])


if __name__ == "__main__":
    main()
