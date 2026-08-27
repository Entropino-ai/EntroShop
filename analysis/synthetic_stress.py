"""Synthetic stress data for EntroShop.

Part A — synthetic simulator sessions (mini private set):
    samples random catalog products as hidden targets (mix of random and
    deliberately "generic-feature" hard products), replays them through the
    official evaluator's simulator, and reports hit/MRR/MTTC. This estimates
    private-split generalization.

Part B — adversarial chat inputs:
    20 deliberately tricky free-chat queries (empty, single-char, numbers,
    contradictory colors, impossible combos, mixed language, negation,
    typos, repeats, long rambling, pronouns, emoji...) checked for crashes
    and sensible behavior.

Usage (from the repo root, with the organizer kit on PYTHONPATH):
    PYTHONPATH=../techjam-conversational-search python3 analysis/synthetic_stress.py
"""
from __future__ import annotations

import json
import random
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluator.local_evaluator import (  # noqa: E402
    catalog_index,
    coarse_category,
    evaluate,
    initial_message,
    intent_card,
    load_jsonl,
)
from agent_lib.index import CatalogIndex  # noqa: E402
from starter.agent import Agent  # noqa: E402

CATALOG = ROOT / "data" / "catalog.jsonl"
PUBLIC = ROOT / "data" / "public_set.jsonl"
N_SYNTH = 300


def product_genericness(asin: str, idx: CatalogIndex, products: dict) -> float:
    """Max posting size among the target's top-4 disclosed phrases; large
    value = the session is hard (constraints are common boilerplate)."""
    card = intent_card(products[asin])
    phrases = [*card["hard_constraints"], *card["soft_preferences"]]
    sizes = [len(idx.phrase_postings.get(p, ())) for p in phrases]
    return max(sizes) if sizes else 0


def synthesize_sessions(idx: CatalogIndex, products: dict, n: int, rng: random.Random) -> list[dict]:
    scenarios = ["buying", "browsing", "intent_override", "boundary"]
    weights = [40, 40, 15, 5]
    tags_pool = ["fit", "comfort", "style", "durability", "material", "color",
                 "size", "weather", "warmth", "price", "brand", "occasion"]
    samples: list[dict] = []
    # 40% deliberately generic-feature products (hard), 60% uniform random
    generic = sorted(products, key=lambda a: -product_genericness(a, idx, products))[:5000]
    for i in range(n):
        asin = rng.choice(generic) if i < n * 0.4 else rng.choice(list(products))
        scenario = rng.choices(scenarios, weights=weights)[0]
        rating = rng.choice([1.0, 2.0, 3.0, 4.0, 5.0])
        style = "usually positive" if rating >= 4 else "critical" if rating <= 2.5 else "mixed"
        profile = {
            "purchase_frequency": rng.choice(["first purchase", "1-2 prior purchases",
                                              "3-4 prior purchases", "5+ prior purchases"]),
            "average_prior_rating": rating,
            "rating_style": style,
            "preference_tags": rng.sample(tags_pool, k=rng.randint(2, 4)),
            "summary": f"Prior purchases emphasize {', '.join(rng.sample(tags_pool, k=3))}.",
        }
        samples.append({
            "sample_id": f"syn_{i:04d}",
            "scenario_type": scenario,
            "user_profile": profile,
            "ground_truth": {"parent_asin": asin},
        })
    return samples


def part_a() -> None:
    print("=" * 60)
    print("Part A — synthetic simulator sessions (mini private set)")
    print("=" * 60)
    idx = CatalogIndex(CATALOG)
    ids, cats, products = catalog_index(CATALOG)
    samples = synthesize_sessions(idx, products, N_SYNTH, random.Random(20260827))
    agent = Agent(CATALOG)
    result = evaluate(agent, samples, ids, cats, products)
    print(f"synthetic sessions: {len(samples)}  (40% generic-feature hard pool)")
    print(f"  Hit@10={result['hit_rate_at_10']:.4f}  MRR={result['mrr']:.4f}  "
          f"MTTC={result['mttc']:.2f}  TS={result['recommended_technical_score']:.4f}")
    for name, m in result["scenario_metrics"].items():
        print(f"    {name}: hit={m['hit_rate_at_10']:.3f} mrr={m['mrr']:.3f} mttc={m['mttc']:.2f}")
    missed = [s for s in result["sessions"] if not s["hit"]]
    print(f"  missed: {len(missed)}/{len(result['sessions'])}")
    for s in missed[:8]:
        print(f"    miss {s['sample_id']} [{s['scenario_type']}]")
    # public-set reference
    public = evaluate(agent, load_jsonl(PUBLIC), ids, cats, products)
    print(f"  public-set reference: Hit@10={public['hit_rate_at_10']:.4f} "
          f"MRR={public['mrr']:.4f} MTTC={public['mttc']:.2f}")


TRICKY_QUERIES = [
    "",                                        # empty
    "哦", "b",                                 # single char
    "30",                                      # number only
    "black white belt",                        # two conflicting colors
    "a belt that is also a waterproof hat",    # impossible combo
    "黑色belt 预算三十 dollars",                # mixed language
    "not black, no leather",                   # negation (unsupported)
    "BLACK LEATHER BELT!!!",                   # caps + punctuation
    "blck lthr blt",                           # typos
    "buy me something nice please",            # filler only
    "gift", "gift", "gift",                    # exact repeat x3
    "so I was thinking maybe something for winter that is warm and cozy "
    "and not too expensive and good for hiking and also looks nice and my "
    "friend said she liked the ones from that one store",   # long rambling
    "size 42 men",                             # size attribute
    "cheap but also luxury brand",             # contradictory adjectives
    "给我推荐一个礼物",                          # generic gift
    "a red dress for a wedding",               # occasion
    "birthday gift under 25 dollars for grandma who loves knitting",  # multi-constraint
    "🎁🛍️",                                    # emoji only
    "no budget limit",                         # budget negation
    "那条黑色皮带怎么样",                        # pronoun reference
]


def part_b() -> None:
    print("\n" + "=" * 60)
    print("Part B — adversarial chat inputs")
    print("=" * 60)
    base = "http://127.0.0.1:8090"

    def post(path: str, body: dict) -> dict:
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=60).read())

    post("/api/llm", {"clear": True})
    clean = 0
    for i, query in enumerate(TRICKY_QUERIES, 1):
        sid = post("/api/new", {"mode": "chat"})["session_id"]
        try:
            t = post("/api/turn", {"session_id": sid, "user_message": query})
            recs = len(t["recommendations"])
            chips = len(t["guide"]["options"])
            ok = recs > 0 or chips > 0
            clean += 1
            top = t["recommendations"][0]["title"][:30] if recs else "(no recs, guided)"
            print(f"  [{ok and 'ok' or '??'}] #{i:02d} {query[:44]!r:46} -> recs={recs} chips={chips} top={top}")
        except Exception as exc:
            print(f"  [FAIL] #{i:02d} {query[:40]!r} -> EXCEPTION {exc}")
    post("/api/llm", {"use_local_default": True})
    print(f"  queries without server errors: {clean}/{len(TRICKY_QUERIES)}")


def part_a_classify() -> None:
    """Classify misses: family-ambiguous (information bound) vs ranked-low vs
    not-in-pool (bug). Mirrors the agent's own pool construction."""
    from evaluator.local_evaluator import (  # noqa: E402
        classify_constraint,
        materialize_hidden_fields,
    )

    idx = CatalogIndex(CATALOG)
    ids, cats, products = catalog_index(CATALOG)
    samples = synthesize_sessions(idx, products, N_SYNTH, random.Random(20260827))
    agent = Agent(CATALOG)
    res = evaluate(agent, samples, ids, cats, products)
    by_sample = {s["sample_id"]: s for s in samples}

    def pool_for(exact, mats, cols, category):
        pool = set(idx.phrase_postings[exact[0]]) if exact else set()
        for p in exact[1:]:
            pool &= idx.phrase_postings[p]
        for m in mats:
            pool |= idx.material_postings.get(m, set())
        for c in cols:
            pool |= idx.color_postings.get(c, set())
        coarse_key = " ".join(category.lower().split())
        cs = idx.category_coarse_postings.get(coarse_key, set())
        if cs and len(pool) > 10:
            f = pool & cs
            if f:
                pool = f
        return pool

    counts = {"family-ambiguous": 0, "not-in-pool": 0, "ranked-low": 0}
    for sess in res["sessions"]:
        if sess["hit"]:
            continue
        sample = by_sample[sess["sample_id"]]
        target = sample["ground_truth"]["parent_asin"]
        card, _ = materialize_hidden_fields(sample, products)
        phrases = [*card["hard_constraints"], *card["soft_preferences"]]
        exact = [p for p in phrases if p in idx.phrase_postings]
        mats = {p for p in phrases if classify_constraint(p) == "material"}
        cols = {p for p in phrases if classify_constraint(p) == "color"}
        category = coarse_category(products[target].get("categories") or [])
        pool = pool_for(exact, mats, cols, category)
        if target not in pool:
            counts["not-in-pool"] += 1
        elif len(pool) > 10:
            counts["family-ambiguous"] += 1
        else:
            counts["ranked-low"] += 1
    print(f"  miss classification: {counts}")


if __name__ == "__main__":
    part_a()
    part_a_classify()
    part_b()
