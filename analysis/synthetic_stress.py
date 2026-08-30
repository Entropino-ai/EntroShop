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

# Repo root = one directory above `analysis/`; inserted on sys.path so the
# agent stack and organizer evaluator can be imported without installing them.
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
from agent_lib.state import ConversationState  # noqa: E402
from agent_lib.extract import parse  # noqa: E402
from starter.agent import Agent  # noqa: E402

# Offline data assets: the 50k-product catalog and the 200-session public set
# (the latter is only a reference metric here, never used for tuning).
CATALOG = ROOT / "data" / "catalog.jsonl"
PUBLIC = ROOT / "data" / "public_set.jsonl"
# Number of synthetic sessions per run — large enough for stable metrics but
# small enough to keep the full benchmark fast.
N_SYNTH = 300


def answerable_pool_size(idx: CatalogIndex, products: dict, asin: str) -> tuple[int, bool]:
    """Full-disclosure info bound for a target: build the conversation state
    as the agent would after every intent-card constraint is disclosed, then
    compute the tightest pool any agent can reach (phrase conjunction of the
    disclosed constraints, coarse-filtered). A session is *answerable* when
    that pool is small enough that the target is guaranteed into the top-10
    (pool <= 10) *and* the target survives the pool construction.

    Sessions whose info bound is larger are provably unanswerable: the
    simulator discloses constraints satisfied by many indistinguishable
    products, so no algorithm can rank the target into the top-10. The
    synthetic stress set only keeps answerable targets — it stresses the
    convergence pipeline, not luck.
    """
    # Reconstruct the intent card and category the simulator would disclose.
    card = intent_card(products[asin])
    constraints = [*card["hard_constraints"], *card["soft_preferences"]]
    category = coarse_category(products[asin].get("categories") or [])
    # Build the conversation state exactly as the agent would after every
    # constraint is disclosed, so the resulting pool mirrors a fully-informed run.
    state = ConversationState(session_id="probe", user_profile={})
    state.apply(parse(f"I'm looking for {category}, but I'm still exploring.", idx),
                is_opening=True)
    for constraint in constraints:
        state.apply(parse("For that, what matters is: " + constraint + ".", idx))
    state.category = category
    state.keywords = category.split()
    state.last_keywords = category.split()

    from itertools import combinations

    active = [phrase for phrase in state.active_phrases if phrase in idx.phrase_postings]
    pool = None
    # Sort by posting-list length so the most selective constraints are tried
    # first; tight conjunctions are discovered faster.
    ordered = sorted(active, key=lambda phrase: len(idx.phrase_postings[phrase]))
    for size in range(len(ordered), 0, -1):
        # Search the largest conjunctions first: the biggest combination that
        # still intersects non-empty is the tightest pool any agent can reach.
        for combo in combinations(ordered, size):
            intersection = None
            for phrase in combo:
                postings = idx.phrase_postings[phrase]
                intersection = set(postings) if intersection is None else (intersection & postings)
                if not intersection:
                    break
            if intersection:
                pool = intersection
                break
        if pool:
            break
    if pool is None:
        # No disclosed constraint combination is discriminative — fall back to
        # the full catalog (nothing restricts the search at all).
        pool = set(idx.products)
    # Coarse-category postings only help when the pool is still too large to
    # guarantee top-10; shrinking already-small pools would be needlessly wrong.
    coarse_key = " ".join(category.lower().split())
    coarse_set = idx.category_coarse_postings.get(coarse_key, set())
    if coarse_set and len(pool) > 10:
        filtered = pool & coarse_set
        if filtered:
            pool = filtered
    return len(pool), asin in pool


def product_genericness(asin: str, idx: CatalogIndex, products: dict) -> float:
    """Measure how "generic" a target's disclosed constraints are.

    Returns the largest posting-list size among the phrases the simulator would
    disclose for this product. A high value means the constraints are common
    boilerplate (e.g. "durable", "affordable") shared by many products, making
    the session hard to converge on; a low value means at least one
    discriminating, product-specific phrase exists. This is only used to bias
    the synthetic set toward hard cases, never as a scored signal.
    """
    card = intent_card(products[asin])
    phrases = [*card["hard_constraints"], *card["soft_preferences"]]
    sizes = [len(idx.phrase_postings.get(p, ())) for p in phrases]
    return max(sizes) if sizes else 0


def synthesize_sessions(idx: CatalogIndex, products: dict, n: int, rng: random.Random) -> list[dict]:
    """Build a synthetic session set shaped like the private split.

    Returns `n` session dicts in the evaluator's input format (sample_id,
    scenario_type, user_profile, ground_truth), each guaranteed answerable: the
    target is drawn from a pool biased toward deliberately generic-feature
    products (hard) for the first 40% and uniform-random across the catalog for
    the rest, and every target is verified via answerable_pool_size to be
    solvable in principle (info-bound pool <= 10 and the target survives pool
    construction).

    Raises RuntimeError if fewer than `n` answerable targets are found within
    the attempt budget (n * 200 tries), which indicates a broken index.
    """
    # Scenario mix mirrors the evaluator's taxonomy; "boundary" is rare on
    # purpose because it is the hardest and most artificial.
    scenarios = ["buying", "browsing", "intent_override", "boundary"]
    weights = [40, 40, 15, 5]
    tags_pool = ["fit", "comfort", "style", "durability", "material", "color",
                 "size", "weather", "warmth", "price", "brand", "occasion"]
    samples: list[dict] = []
    # 40% deliberately generic-feature products (hard), 60% uniform random —
    # but only targets whose full-disclosure pool is small enough to be
    # answerable (see answerable_pool_size). This keeps the set harsh while
    # guaranteeing every session is solvable in principle.
    # Descending sort (negated key) puts the most generic/hard products first;
    # the 5000 cap bounds the sort cost on the 50k-product catalog.
    generic = sorted(products, key=lambda a: -product_genericness(a, idx, products))[:5000]
    attempts = 0
    while len(samples) < n and attempts < n * 200:
        attempts += 1
        # First 40% of slots draw from the hard generic pool; the rest are
        # uniform-random across the whole catalog.
        asin = rng.choice(generic) if len(samples) < n * 0.4 else rng.choice(list(products))
        pool_size, target_in = answerable_pool_size(idx, products, asin)
        if not target_in or pool_size > 10:
            continue  # provably unanswerable or lost by pool construction — skip
        scenario = rng.choices(scenarios, weights=weights)[0]
        # Random prior rating drives the profile's sentiment style, which the
        # agent is expected to respect without over-indexing on.
        rating = rng.choice([1.0, 2.0, 3.0, 4.0, 5.0])
        style = "usually positive" if rating >= 4 else "critical" if rating <= 2.5 else "mixed"
        # Synthetic prior-purchase history shapes the user_profile the evaluator
        # feeds the agent; tags and summary are sampled for variety.
        profile = {
            "purchase_frequency": rng.choice(["first purchase", "1-2 prior purchases",
                                              "3-4 prior purchases", "5+ prior purchases"]),
            "average_prior_rating": rating,
            "rating_style": style,
            "preference_tags": rng.sample(tags_pool, k=rng.randint(2, 4)),
            "summary": f"Prior purchases emphasize {', '.join(rng.sample(tags_pool, k=3))}.",
        }
        samples.append({
            "sample_id": f"syn_{len(samples):04d}",
            "scenario_type": scenario,
            "user_profile": profile,
            "ground_truth": {"parent_asin": asin},
        })
    if len(samples) < n:
        raise RuntimeError(f"could only build {len(samples)}/{n} answerable sessions")
    return samples


def part_a() -> None:
    """Run the synthetic mini-private-set benchmark end to end.

    Builds 300 answerable sessions (deterministically seeded), runs them through
    the official evaluator against the starter agent, prints overall and
    per-scenario metrics plus a short sample of misses, then reports the
    public-set reference score for comparison. Side effect: prints to stdout
    only; no files are written.
    """
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
    # Surface a short sample of failed sessions so they can be eyeballed for
    # whether they are info-bound, ranked-low, or a pool-construction bug.
    missed = [s for s in result["sessions"] if not s["hit"]]
    print(f"  missed: {len(missed)}/{len(result['sessions'])}")
    for s in missed[:8]:
        print(f"    miss {s['sample_id']} [{s['scenario_type']}]")
    # public-set reference
    public = evaluate(agent, load_jsonl(PUBLIC), ids, cats, products)
    print(f"  public-set reference: Hit@10={public['hit_rate_at_10']:.4f} "
          f"MRR={public['mrr']:.4f} MTTC={public['mttc']:.2f}")


# Adversarial free-chat inputs designed to probe crash-resistance and sane
# behavior under degenerate, contradictory, or noisy queries. Each entry carries
# an inline note naming the failure mode it targets.
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
    """Exercise the live demo server against adversarial free-chat inputs.

    Sends each TRICKY_QUERY through the local server's /api/new + /api/turn
    endpoints (http://127.0.0.1:8090) and reports, per query, whether it
    returned recommendations or guidance chips, or raised a server exception. A
    query is counted "clean" only when the server responds without error; the
    ok/chip flag is informational (a degraded but non-crashing answer is
    tolerated). Side effect: prints a per-query report to stdout.
    """
    print("\n" + "=" * 60)
    print("Part B — adversarial chat inputs")
    print("=" * 60)
    base = "http://127.0.0.1:8090"

    def post(path: str, body: dict) -> dict:
        """POST `body` as JSON to the local demo server and return the decoded
        JSON response. Raises on HTTP/network errors so the caller can count
        them as failures."""
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=60).read())

    # Reset the backend LLM so the run starts from a known configuration.
    post("/api/llm", {"clear": True})
    clean = 0
    for i, query in enumerate(TRICKY_QUERIES, 1):
        sid = post("/api/new", {"mode": "chat"})["session_id"]
        try:
            t = post("/api/turn", {"session_id": sid, "user_message": query})
            recs = len(t["recommendations"])
            chips = len(t["guide"]["options"])
            # A non-empty response (recs or guidance) counts as "ok"; a crash
            # would have raised instead.
            ok = recs > 0 or chips > 0
            clean += 1
            top = t["recommendations"][0]["title"][:30] if recs else "(no recs, guided)"
            print(f"  [{ok and 'ok' or '??'}] #{i:02d} {query[:44]!r:46} -> recs={recs} chips={chips} top={top}")
        except Exception as exc:
            print(f"  [FAIL] #{i:02d} {query[:40]!r} -> EXCEPTION {exc}")
    # Restore the default LLM configuration after the stress run.
    post("/api/llm", {"use_local_default": True})
    print(f"  queries without server errors: {clean}/{len(TRICKY_QUERIES)}")


def part_a_classify() -> None:
    """Categorize every missed synthetic session to separate bugs from noise.

    Rebuilds the retrieval pool for each miss using the agent's own pool
    construction (exact-phrase conjunction + material/color unions + coarse
    category), then buckets the miss into:
      * not-in-pool      — target never enters the pool (a genuine bug);
      * family-ambiguous — the info bound leaves too many candidates, so no
                           agent could rank the target into top-10;
      * ranked-low       — target was in a small enough pool but ranked outside
                           top-10 (a ranking failure).
    Prints the three-way counts; writes nothing.
    """
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
        """Reconstruct the retrieval pool for a target from its disclosed
        phrases: exact-phrase conjunction, then material/color unions, then the
        coarse-category filter (applied only when the pool is too large)."""
        pool = set(idx.phrase_postings[exact[0]]) if exact else set()
        for p in exact[1:]:
            pool &= idx.phrase_postings[p]
        # Material and color phrases are OR'd (unioned) rather than AND'd,
        # mirroring the agent's tolerant handling of alternative attributes.
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
            continue  # only misses need diagnosis
        sample = by_sample[sess["sample_id"]]
        target = sample["ground_truth"]["parent_asin"]
        # Recover the exact constraints the simulator would have disclosed.
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
    # Offline benchmark, miss diagnosis, then the live-server adversarial pass
    # (Part B requires demo/server.py to be running on :8090).
    part_a()
    part_a_classify()
    part_b()
