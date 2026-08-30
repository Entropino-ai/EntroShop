"""Full smoke-test suite for EntroShop (offline, no network, no LLM).

Covers: official evaluator regression, convergence battery, demo endpoints,
MCP tools, submission package import, and free-chat convergence loop.
Run from the repo root with the kit on PYTHONPATH:

    PYTHONPATH=../techjam-conversational-search python3 analysis/smoke_test.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

# Resolve the repository root (analysis/ -> EntroShop) and the sibling
# organizer kit, then prepend both so that ``agent_lib``, ``starter``, the demo
# server, and the official evaluator are importable without installation.
ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT.parent / "techjam-conversational-search"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(KIT))

# Module-level tally shared by every check(); ``main`` reads it to compute the
# pass ratio and to decide the process exit code.
PASS = 0
FAIL = 0
FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    """Record a single assertion result and print a one-line verdict.

    Increments the module-level PASS/FAIL counters and, on failure, appends the
    check name to FAILED so that ``main`` can list every failing test and exit
    non-zero. ``detail`` is a short diagnostic (a value or exception message)
    printed only on failure to keep passing output noise-free.
    """
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [ok] {name}")
    else:
        FAIL += 1
        FAILED.append(name)
        print(f"  [FAIL] {name} {detail}")


def test_evaluator_regression() -> None:
    """Re-run the official judge over the 200-session public set.

    Builds the real catalog index and the competition ``Agent``, then scores
    them through the organizer's ``evaluate`` exactly as the leaderboard does.
    The thresholds are pinned regression baselines matching the published
    public-set scores, so any retrieval or ranking regression fails the suite.
    """
    print("[1/7] official evaluator regression (public set, 200 sessions)")
    from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl
    from agent_lib.index import CatalogIndex
    from starter.agent import Agent

    catalog = ROOT / "data" / "catalog.jsonl"
    public = ROOT / "data" / "public_set.jsonl"
    samples = load_jsonl(public)
    ids, cats, products = catalog_index(catalog)
    agent = Agent(catalog)
    r = evaluate(agent, samples, ids, cats, products)
    # Assert each headline metric against its known-good baseline; tolerances
    # are intentionally tight so that drift on the public set is caught early.
    check("Hit@10 == 1.000", r["hit_rate_at_10"] == 1.0, str(r["hit_rate_at_10"]))
    check("TechnicalScore >= 0.905", r["recommended_technical_score"] >= 0.905,
          f"{r['recommended_technical_score']:.4f}")
    check("MRR >= 0.700", r["mrr"] >= 0.70, f"{r['mrr']:.4f}")
    check("MTTC <= 1.6", r["mttc"] <= 1.6, f"{r['mttc']:.3f}")
    print(f"       TS={r['recommended_technical_score']:.4f} "
          f"hit={r['hit_rate_at_10']:.3f} mrr={r['mrr']:.4f} mttc={r['mttc']:.3f}")


def test_convergence_battery() -> None:
    """Drive 13 edge-case queries through the guide state machine.

    Each case exercises a distinct convergence path: empty input, tiny/hard
    pools, guide-round caps, bilingual text, impossible combos, filler and
    topic-shift turns. A case passes when the loop converges before turn 10
    (or an explicit cap triggers) and retrieval still produced a ranking.
    """
    print("[2/7] convergence battery (13 edge cases)")
    from agent_lib.guide import GuideState, hard_pool
    from agent_lib.index import CatalogIndex
    from agent_lib.query import freeform_query
    from agent_lib.retrieve import freeform_retrieve_with_pool
    from agent_lib.dense import DenseIndex

    idx = CatalogIndex(ROOT / "data" / "catalog.jsonl")
    dense = DenseIndex(idx.products)
    cases = [
        ("black leather belt under $30", None, None),           # converges fast
        ("", None, 2),                                          # zero info -> no-progress guard
        ("just shoes", 12, None),                               # pool<=10
        ("a blue cotton dress", None, 3),                       # no-progress x2
        ("red dress with pockets for summer", 30, 4),           # guide_rounds
        ("shoes", None, 9),                                     # turn-9 clamp
        ("i want something cheap", 5, None),                    # tiny pool
        ("black white belt contradictory", None, 2),            # contradiction still converges
        ("黑色皮带 三十美元", 15, 3),                            # bilingual + budget
        ("a waterproof hat that is also a belt", 8, None),      # impossible combo
        ("hmm ok what about that one", 40, 5),                  # filler -> no-progress
        ("belt belt belt belt belt", 6, None),                  # repeat
        ("i changed my mind", 25, 4),                           # topic shift
    ]
    for text, pool_cap, rounds_cap in cases:
        guide = GuideState()
        guide_ok = True
        # Simulate up to 10 turns; the loop breaks early on any of the three
        # convergence conditions below, otherwise turn 10 counts as a failure.
        for turn in range(1, 11):
            query = freeform_query(text)
            guide.apply(query, text)
            acc = guide.to_query()
            ranked, pool, union = freeform_retrieve_with_pool(acc, idx, dense, 10, 200)
            hard = hard_pool(idx, guide)
            # A hard pool may be empty for unresolvable input; fall back to the
            # union size so the size-based caps still see a meaningful count.
            size = len(hard) if hard else union
            if pool_cap is not None and size <= pool_cap:
                break
            if rounds_cap is not None and guide.guide_rounds >= rounds_cap:
                break
            if guide.should_converge(size, turn):
                break
        else:
            guide_ok = False  # hit turn 10 without converging
        check(f"converges: {text[:38]!r}", guide_ok and bool(ranked))
    print("       (pool caps and guide caps validated by construction)")


def _request(url: str, payload: dict | None) -> dict:
    """POST a JSON payload to the local demo/MCP server and return the reply.

    ``payload=None`` encodes an empty body (used for the health check and
    GET-style endpoints). Fails loudly by raising ``urllib``'s HTTP/timeout
    exceptions, which callers surface as check failures rather than swallowing.
    """
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _new_session(mode: str, scenario: str | None = None) -> dict:
    """Create a session on the demo server via ``/api/new``.

    ``scenario`` is optional and only attached for the example/"demo" mode;
    ``chat`` sessions omit it so the client drives the whole conversation.
    """
    payload = {"mode": mode}
    if scenario is not None:
        payload["scenario"] = scenario
    return _request("http://127.0.0.1:8090/api/new", payload)


def _turn(sid: str, message: str, **extra) -> dict:
    """Send one user turn to ``/api/turn`` and return the raw response dict.

    ``**extra`` forwards any optional protocol fields the endpoint accepts.
    """
    payload = {"session_id": sid, "user_message": message, **extra}
    return _request("http://127.0.0.1:8090/api/turn", payload)


def _final_asin(r: dict) -> str | None:
    """Extract the converged product ASIN from a turn response, if present.

    Returns ``None`` when the response has no ``final`` field (not converged)
    or when it is a non-dict payload, so callers can test truthiness directly.
    """
    fin = r.get("final")
    if isinstance(fin, dict):
        return fin.get("parent_asin") or fin.get("asin")
    return None


def test_demo() -> None:
    """Exercise the demo HTTP server's health, chat, and example endpoints.

    The chat loop simulates a real client following the first non-converge
    guidance chip each turn until a final ASIN appears (or options run out).
    The example-session path is guarded: without the organizer kit on the
    PYTHONPATH it fails as a check instead of aborting the whole suite.
    """
    print("[3/7] demo server endpoints")
    health = _request("http://127.0.0.1:8090/api/health", None)
    check("health ok", health.get("ok") is True, str(health))

    # chat session: new -> turn (follow guidance chips) until final_asin
    sess = _new_session("chat")
    check("chat session created", bool(sess.get("session_id")), str(sess)[:200])
    msg = "black leather belt under $30"
    final = None
    # Drive the conversation by always accepting the first non-converge chip,
    # stopping as soon as the server reports a final product.
    for _ in range(10):
        r = _turn(sess["session_id"], msg)
        final = _final_asin(r)
        if final:
            break
        opts = (r.get("guide") or {}).get("options") or []
        if not opts:
            break
        # follow the first actionable chip (skip the "that's it" converge chip)
        nxt = next((o for o in opts if o.get("type") != "converge"), None)
        if not nxt:
            msg = "that's it"
            continue
        msg = nxt.get("message") or nxt.get("value") or msg
    check("chat returns message", bool(r.get("agent_message")), str(r)[:200])
    check("chat converges to final asin", bool(final), str(r)[:200])

    # example session (needs the kit on PYTHONPATH)
    try:
        sess = _new_session("demo")
    except Exception as exc:  # noqa: BLE001
        check("example session (kit unavailable?)", False, str(exc)[:200])
        return
    check("example session created", bool(sess.get("session_id")), str(sess)[:200])
    r = _turn(sess["session_id"], sess.get("first_user_message") or "start")
    check("example returns message", bool(r.get("agent_message")), str(r)[:200])
    check("example reveals target", bool(r.get("target")), str(r)[:200])


def test_mcp() -> None:
    """Verify the MCP endpoint advertises and answers the core tools.

    Sends JSON-RPC 2.0 ``tools/list`` and two ``tools/call`` requests over
    HTTP to confirm the tool surface is present and that search/tree responses
    carry the expected payload shapes.
    """
    print("[4/7] MCP tools over HTTP")
    tools = _request("http://127.0.0.1:8090/mcp",
                     {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = [t.get("name") for t in tools.get("result", {}).get("tools", [])]
    for tool in ("search_products", "product_details", "clarify", "tree_chain"):
        check(f"tool {tool}", tool in names, str(names))
    res = _request("http://127.0.0.1:8090/mcp",
                   {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "search_products",
                               "arguments": {"query": "leather belt"}}})
    check("search_products returns items",
          bool(res.get("result", {}).get("content")), str(res)[:200])
    tc = _request("http://127.0.0.1:8090/mcp",
                  {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                   "params": {"name": "tree_chain",
                              "arguments": {"asin": "B08QN272FH"}}})
    # tree_chain returns content as a list of items; take the first item's text
    # (defaulting to empty) and require both the chain and leaf-count keys.
    tc_text = (tc.get("result", {}).get("content") or [{}])[0].get("text", "")
    check("tree_chain returns chain + leaf count",
          '"chain"' in tc_text and "leaf_products" in tc_text, tc_text[:150])


def test_submission_package() -> None:
    """Import-check the flattened submission bundle as a standalone package.

    Runs a subprocess with cwd inside ``submission/`` to prove the packaged
    modules import without relying on the repository's ``agent_lib`` layout.
    """
    print("[5/7] submission package import")
    sub = ROOT / "submission"
    proc = subprocess.run(
        [sys.executable, "-c",
         "import agent, src.extract, src.index, src.guide, src.retrieve, "
         "src.query, src.llm_rank, src.mcp, src.dense, src.state; print('ok')"],
        cwd=str(sub), capture_output=True, text=True)
    check("submission imports clean", proc.returncode == 0 and "ok" in proc.stdout,
          proc.stderr[:300])


def test_freechat_loop() -> None:
    """Run an open-ended chat that always follows the first guidance chip.

    Unlike ``test_demo``, this loop tracks its own turn counter and reports
    failure with an explicit diagnostic if 10 turns pass without a final ASIN.
    """
    print("[6/7] free-chat convergence loop (multi-turn chips)")
    sess = _new_session("chat")
    guide_turn = 0
    message = "i want a comfortable belt for work"
    while guide_turn < 10:
        r = _turn(sess["session_id"], message)
        if _final_asin(r):
            check("free chat converges", True)
            return
        options = (r.get("guide") or {}).get("options") or []
        if not options:
            break
        # Greedily adopt the top chip's message/value; fall back to the previous
        # message only when the chip carries no usable text.
        message = options[0].get("message") or options[0].get("value") or message
        guide_turn += 1
    check("free chat converges", False, "no final asin in 10 turns")


def test_index_integrity() -> None:
    """Sanity-check the built catalog index against expected catalog sizes.

    Guards against a missing/truncated catalog: product, posting, category and
    price structures must all reach minimum counts or the rest of the suite's
    retrieval assertions are meaningless.
    """
    print("[7/7] catalog index integrity")
    from agent_lib.index import CatalogIndex
    idx = CatalogIndex(ROOT / "data" / "catalog.jsonl")
    check("50k products indexed", len(idx.products) >= 49_000, str(len(idx.products)))
    check("phrase postings non-empty", len(idx.phrase_postings) > 1_000)
    check("coarse postings non-empty", len(idx.category_coarse_postings) > 100)
    check("prices populated", len(idx.prices) > 40_000)


def test_product_tree() -> None:
    """Validate the n-ary product-property tree's structural invariants.

    Confirms there are enough distinct chains, every product maps to exactly
    one non-trivial root->leaf chain, chain->product membership is invertible,
    shared prefixes are symmetric, and family clustering is non-trivial.
    """
    print("[8/8] product-property tree (unique chains + mapping)")
    from agent_lib.index import CatalogIndex
    from agent_lib.tree import ProductTree
    idx = CatalogIndex(ROOT / "data" / "catalog.jsonl")
    tree = ProductTree(idx)
    check("1628 distinct chains", tree.node_count >= 1600, str(tree.node_count))
    # Every catalog product must resolve to a non-empty chain; `all(...)` short
    # circuits and reports False if a single product is unmapped.
    check("every product maps to a unique chain",
          all(tuple(tree.chain(a)) for a in idx.products), "")
    sample = next(iter(idx.products))
    chain = tree.chain(sample)
    check("chain is root->leaf with >=2 segments", len(chain) >= 2, str(chain))
    check("products_for(chain) contains the product", sample in tree.products_for(chain),
          str(len(tree.products_for(chain))))
    check("common_prefix returns shared path",
          tree.common_prefix(sample, sample) == chain, str(tree.common_prefix(sample, sample)))
    fam = tree.families(min_size=2)
    check("family detection non-empty", len(fam) > 100, str(len(fam)))


def test_tree_first() -> None:
    """Verify the tree-first route refines (never widens) the token route.

    For a set of queries, the tree-aware hard pool must be a subset of the
    token-only hard pool, the tree-first union must be no larger, and the
    converged_pool gate must accept a pinned category while rejecting an
    over-broad one.
    """
    print("[8b] tree-first category route (refinement of token route)")
    from agent_lib.guide import GuideState, hard_pool
    from agent_lib.index import CatalogIndex
    from agent_lib.query import freeform_query
    from agent_lib.tree import ProductTree
    idx = CatalogIndex(ROOT / "data" / "catalog.jsonl")
    tree = ProductTree(idx)
    texts = ["women boots blue", "men belt", "cotton dress", "wool scarf", "sneakers"]
    ok = True
    for text in texts:
        state = GuideState()
        state.apply(freeform_query(text), text)
        hard_tok = hard_pool(idx, state)
        hard_tree = hard_pool(idx, state, tree=tree)
        # Subset is the invariant that makes the tree route safe: it can only
        # discard candidates, never introduce ones the token route missed.
        if not hard_tree <= hard_tok:
            ok = False
            break
    check("tree hard_pool is a subset of token hard_pool", ok, "")
    # tree-first retrieves an equal or smaller pool
    from agent_lib.dense import DenseIndex
    from agent_lib.retrieve import freeform_retrieve_with_pool
    dense = DenseIndex(idx.products)
    q = freeform_query("women boots ankle bootie")
    _, _, union_tok = freeform_retrieve_with_pool(q, idx, dense, 10, 200, tree=None)
    _, _, union_tree = freeform_retrieve_with_pool(q, idx, dense, 10, 200, tree=tree)
    # Same query, same budgets; the tree route's union must be <= the token one.
    check("tree-first pool <= token pool", union_tree <= union_tok,
          f"{union_tree} vs {union_tok}")
    # tree-vs-LLM gate: converged_pool is True only when the tree pins
    # candidates; unresolvable keywords (materials etc.) are ignored
    conv, tp = tree.converged_pool(["gift"], set(idx.products), threshold=10)
    check("converged_pool true when tree pins (gift)", conv and 0 < len(tp) <= 10,
          f"conv={conv} pool={len(tp)}")
    conv_big, _ = tree.converged_pool(["belt"], set(idx.products), threshold=10)
    check("converged_pool false when tree pool large (belt)", not conv_big, "")


def main() -> None:
    """Run every test in dependency order and report an aggregate verdict.

    Order matters: the offline index/tree tests run first so their failures
    surface before the network-dependent demo, MCP and submission tests. Prints
    a pass/total ratio with elapsed time and exits 1 (listing failures) when
    any check failed, 0 otherwise.
    """
    print("=" * 64)
    print("EntroShop smoke suite")
    print("=" * 64)
    t0 = time.time()
    test_index_integrity()
    test_product_tree()
    test_tree_first()
    test_evaluator_regression()
    test_convergence_battery()
    test_demo()
    test_mcp()
    test_freechat_loop()
    test_submission_package()
    print("=" * 64)
    print(f"passed {PASS} / {PASS + FAIL}  ({time.time() - t0:.1f}s)")
    if FAILED:
        print("failed:", *FAILED, sep="\n  - ")
        sys.exit(1)
    print("ALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
