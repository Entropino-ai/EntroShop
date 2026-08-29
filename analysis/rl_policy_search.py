"""Offline policy optimization (RL-style) for EntroShop.

Reward = simulator reward (hit / TechnicalScore). Each policy configuration
is rolled out against the environment and the argmax is reported — the
classic offline policy-search loop, with the official evaluator (or a
ground-truth chat simulator) as the environment.

Part A — competition ask policy (official evaluator as environment)
    policy space: per-scenario ask plans + ask caps; reward = TechnicalScore.

Part B — chat guidance policy (synthetic chat simulator as environment)
    the customer answers facet chips with the target's true values;
    policy space: convergence threshold, no-progress threshold, facet
    selection rule; reward = Hit@10 (target inside the final top-10),
    matching the official evaluator's metric.
"""
from __future__ import annotations

import itertools
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_lib import state as state_mod  # noqa: E402
from agent_lib.dense import DenseIndex  # noqa: E402
from agent_lib.guide import GuideState, choose_facet, hard_pool, option_labels  # noqa: E402
from agent_lib.query import FreeformQuery, freeform_query  # noqa: E402
from agent_lib.retrieve import freeform_retrieve_with_pool  # noqa: E402
from evaluator.local_evaluator import catalog_index, evaluate  # noqa: E402
from agent_lib.index import CatalogIndex  # noqa: E402
from starter.agent import Agent  # noqa: E402
from analysis.synthetic_stress import synthesize_sessions  # noqa: E402

CATALOG = ROOT / "data" / "catalog.jsonl"
PUBLIC = ROOT / "data" / "public_set.jsonl"


# ------------------------------------------------------------------ Part A
ASK_PLANS = {
    "other5": {k: ["other"] * 5 for k in ("buying", "browsing", "boundary", "intent_override")},
    "other3": {k: ["other"] * 3 for k in ("buying", "browsing", "boundary", "intent_override")},
    "feature_other": {"buying": ["feature", "other", "other"],
                      "browsing": ["feature", "other", "other"],
                      "boundary": ["feature", "other", "other"],
                      "intent_override": ["other"] * 5},
    "mat_color_other": {"buying": ["material", "color", "other", "other"],
                        "browsing": ["material", "color", "other", "other"],
                        "boundary": ["material", "color", "other", "other"],
                        "intent_override": ["other"] * 5},
}


def part_a() -> None:
    print("=" * 64)
    print("Part A — competition ask policy search (official evaluator, reward = TechnicalScore)")
    print("=" * 64)
    samples = __import__("evaluator.local_evaluator", fromlist=["load_jsonl"]).load_jsonl(PUBLIC)
    ids, cats, products = catalog_index(CATALOG)
    idx = CatalogIndex(CATALOG)
    agent = Agent(CATALOG)
    results = []
    for name, plans in ASK_PLANS.items():
        state_mod.PLANS.clear()
        state_mod.PLANS.update(plans)
        r = evaluate(agent, samples, ids, cats, products)
        results.append((r["recommended_technical_score"], r["hit_rate_at_10"], r["mrr"],
                        r["mttc"], name))
        print(f"  {name:16s} TS={r['recommended_technical_score']:.4f} "
              f"hit={r['hit_rate_at_10']:.3f} mrr={r['mrr']:.4f} mttc={r['mttc']:.3f}")
    results.sort(reverse=True)
    print(f"  -> best: {results[0][4]} (TS {results[0][0]:.4f})")
    state_mod.PLANS.clear()
    state_mod.PLANS.update(ASK_PLANS["other5"])
    return results[0]


# ------------------------------------------------------------------ Part B
def chat_rollout(target: str, scenario: str, products: dict, idx: CatalogIndex,
                 dense, cfg: dict, rng: random.Random) -> bool:
    """One chat session simulated against a ground-truth target.

    The customer opens with a *vague* scenario mention (real shoppers do not
    disclose half the constraints in their first sentence), then answers
    every facet chip with the target's true value when possible. Reward =
    Hit@10 (target inside the final top-10 list), matching the official
    evaluator's metric.
    """
    guide = GuideState()
    # vague, human-sounding opening: a category mention only (no material /
    # color / budget disclosure), so the guidance policy actually has to work
    opening = _vague_opening(target, products)
    target_colors = idx.color_sets[target]
    target_materials = idx.material_sets[target]
    target_price = idx.prices[target]
    target_cats = idx.category_specific_lower.get(target, "")
    for turn in range(1, 11):
        query = freeform_query(opening)
        guide.apply(query, opening)
        accumulated = guide.to_query()
        ranked, pool, union = freeform_retrieve_with_pool(accumulated, idx, dense, 20, 200)
        hard = hard_pool(idx, guide)
        pool_size = len(hard) if hard else union
        converged = guide.should_converge(pool_size, turn)
        if cfg["converge_at"] is not None:
            converged = converged or pool_size <= cfg["converge_at"]
        if cfg["no_progress_at"] is not None:
            converged = converged or guide.no_progress >= cfg["no_progress_at"]
        if converged:
            return bool(ranked) and target in ranked[:10]
        facet, values = choose_facet(idx, pool, guide, rule=cfg["facet_rule"])
        if facet is None or not values:
            return bool(ranked) and target in ranked[:10]
        options = option_labels(facet, values)
        # pick the chip matching the target's true value
        import re as _re
        picked = None
        if facet == "price" and target_price is not None:
            best_budget, picked = None, None
            for opt in options:
                nums = _re.findall(r"\d+", opt["message"])
                if not nums:
                    continue
                budget = float(nums[0])
                if best_budget is None or abs(target_price - budget) < abs(target_price - best_budget):
                    best_budget, picked = budget, opt
        else:
            for opt in options:
                v = str(opt["value"]).lower()
                if facet == "color" and v in target_colors:
                    picked = opt; break
                if facet == "material" and v in target_materials:
                    picked = opt; break
                if facet == "category" and v in target_cats:
                    picked = opt; break
        guide.guide_rounds += 1
        guide.facet_keys.add(facet)
        if picked is None:
            # the target has no value for this facet (e.g. no color listed):
            # answer "no preference" and move on to the next facet — this is
            # *not* a no-progress turn, so the agent keeps asking instead of
            # converging early on a huge pool
            opening = "no preference"
            continue
        opening = picked["message"]
    return False


def _vague_opening(target: str, products: dict) -> str:
    """A category-only, human-sounding first message for the simulated
    customer (no material/color/budget disclosure, so the guidance policy
    has real work to do)."""
    cats = [str(v) for v in products[target].get("categories") or []]
    # root entries are boilerplate ("Clothing, Shoes & Jewelry"); take the
    # last meaningful part as the shopper's vague intent
    root_excluded = {"clothing", "clothing shoes & jewelry", "clothing, shoes & jewelry"}
    specific = [c for c in cats if c.lower() not in root_excluded]
    last = specific[-1] if specific else "something"
    last = last.replace(" & ", " ").replace(",", " ")
    return f"I'm looking for {last}."


def part_b() -> None:
    print("=" * 64)
    print("Part B — chat guidance policy search (synthetic chat simulator, reward = Hit@10)")
    print("=" * 64)
    idx = CatalogIndex(CATALOG)
    dense = DenseIndex(idx.products)
    _, _, products = catalog_index(CATALOG)
    rng = random.Random(20260828)
    sessions = synthesize_sessions(idx, products, 120, rng)
    configs = list(itertools.product([5, 10], [2, 3], ["entropy", "first"]))
    results = []
    for converge_at, no_progress_at, facet_rule in configs:
        cfg = {"converge_at": converge_at, "no_progress_at": no_progress_at, "facet_rule": facet_rule}
        hits = 0
        for s in sessions:
            if chat_rollout(s["ground_truth"]["parent_asin"], s["scenario_type"],
                            products, idx, dense, cfg, rng):
                hits += 1
        results.append((hits / len(sessions), converge_at, no_progress_at, facet_rule))
        print(f"  converge<={converge_at:>2} no_progress>={no_progress_at} rule={facet_rule:8s} "
              f"hit={hits}/{len(sessions)} = {hits/len(sessions):.3f}")
    results.sort(reverse=True)
    print(f"  -> best: converge<={results[0][1]} no_progress>={results[0][2]} "
          f"rule={results[0][3]} (hit {results[0][0]:.3f})")
    return results[0]


if __name__ == "__main__":
    best_a = part_a()
    best_b = part_b()
    print(f"\n=== argmax policies ===\n  competition: {best_a}\n  chat: {best_b}")
