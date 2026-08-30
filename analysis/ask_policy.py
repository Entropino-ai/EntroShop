"""Offline ask-policy simulator: which attribute sequence minimizes turns to
a tight pool, given the evaluator's disclosure rules (known cards).

This module exists to TUNE the agent's question-asking order without running the
full evaluator: for each public-set session it replays the deterministic
disclosure rules against a candidate ask-policy and reports, per scenario type,
how many turns that policy needs to narrow the exact-phrase conjunction pool to
<=10 candidates. A policy is a plain function over ``(turn, scenario, disclosed,
classes, boundary_used)``, so new strategies can be added as one function and
compared in ``main()`` for free."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluator.local_evaluator import (  # noqa: E402
    catalog_index,
    classify_constraint,
    intent_card,
    load_jsonl,
)
from agent_lib.index import CatalogIndex  # noqa: E402

CATALOG = ROOT / "data" / "catalog.jsonl"
PUBLIC = ROOT / "data" / "public_set.jsonl"

ALLOWED = {"category", "material", "color", "size", "style", "brand", "budget", "feature", "use_case", "other"}


def simulate(sample, card, policy, idx, max_turns=10):
    """Simulate one session under a candidate ask-policy and report its convergence turn.

    Replays the evaluator's deterministic disclosure rules for a single sample:
    at each turn it asks ``policy`` for an attribute, models what the evaluator
    would disclose from the known intent card, and checks whether the disclosed
    constraints (intersected via exact-phrase postings) already form a "tight"
    pool of 1..10 candidates. This is an OFFLINE approximation — it uses the
    known card rather than real user messages, and discloses verbatim strings.

    Args:
        sample: A session record with ``scenario_type``, ``sample_id``, and
            ``ground_truth`` keys (public_set.jsonl / private-set schema).
        card: The intent card for the ground-truth product, with
            ``hard_constraints`` and ``soft_preferences`` (verbatim phrases).
        policy: ``(turn, scenario, disclosed, classes, boundary_used) -> attr``
            returning the next attribute to ask, or ``None`` to stop asking.
        idx: A ``CatalogIndex`` exposing ``phrase_postings`` (phrase -> doc ids).
        max_turns: Turn budget; the loop runs turns ``1..max_turns``.

    Returns:
        The first 1-based turn at which the pool becomes tight, or
        ``max_turns + 1`` if it never tightens within the budget (a sentinel
        meaning "too slow").

    Notes:
        - ``intent_override`` blocks conversion until a deterministic override
          turn (3 or 4, hashed from ``sample_id``) mirrors the evaluator's rng.
        - ``boundary`` scenarios inject one "dud" reply that discloses nothing.
    """
    scenario = sample["scenario_type"]
    # Hards first, then softs: the evaluator discloses in this priority order.
    constraints = [*card["hard_constraints"], *card["soft_preferences"]]
    # classes maps each phrase to its coarse attribute; exact keeps only the
    # phrases that index verbatim in the catalog postings (the conjunction keys).
    classes = {c: classify_constraint(c) for c in constraints}
    exact = {c for c in constraints if c in idx.phrase_postings}
    disclosed: set[str] = set()
    boundary_used = False
    # Opening disclosure: each scenario starts with one constraint already known.
    if scenario == "buying" and constraints:
        disclosed.add(constraints[0])
    if scenario == "intent_override":
        soft = card["soft_preferences"]
        # Fallback matches the evaluator's canned phrasing when no softs exist.
        old = soft[-1] if soft else "I prefer a different style."
        disclosed.add(old)
    override_turn = None
    if scenario == "intent_override":
        hard = card["hard_constraints"]
        # Deterministically pick 3 or 4 from the sample id to mirror the
        # evaluator's rng choice([3,4]); both cases are approximated below.
        override_turn = 3 if (hash(sample["sample_id"]) % 2 == 0) else 4
    for turn in range(1, max_turns + 1):
        # Can we convert already? intent_override blocks until its override turn.
        if scenario != "intent_override" or (override_turn is not None and turn >= override_turn):
            tight = _tight(disclosed, exact, idx)
            if tight:
                return turn
        # Ask the policy which attribute to probe next.
        attr = policy(turn, scenario, disclosed, classes, boundary_used)
        # First boundary ask is a dud: the evaluator replies without disclosing.
        if scenario == "boundary" and not boundary_used and attr:
            boundary_used = True
            continue  # dud reply, no disclosure
        if not attr:
            continue
        # Disclose up to 2 unseen constraints matching the asked attribute
        # ("other" matches anything); [:2] mirrors the evaluator's reveal cap.
        matches = [v for v in constraints if v not in disclosed and (attr == "other" or classes[v] == attr)][:2]
        disclosed.update(matches)
        # At the override turn the user injects a brand-new hard constraint.
        if scenario == "intent_override" and turn + 1 == override_turn:
            new_value = card["hard_constraints"][0] if card["hard_constraints"] else ""
            disclosed.add(new_value)
    return max_turns + 1


def _tight(disclosed, exact, idx):
    """Return True if the disclosed exact phrases intersect to a tight pool (1..10).

    Only phrases that index verbatim in the catalog participate (``exact``); the
    pool is the intersection of their posting lists. An empty intersection (0
    docs) is NOT tight — it means the disclosed constraints conflict — so the
    simulator keeps asking rather than declaring a false success.
    """
    active = [c for c in disclosed if c in exact]
    if not active:
        return False
    # Seed the pool with the first phrase's postings, then intersect the rest.
    pool = set(idx.phrase_postings[active[0]])
    for c in active[1:]:
        pool &= idx.phrase_postings[c]
    return 0 < len(pool) <= 10


def policy_other(turn, scenario, disclosed, classes, boundary_used):
    """Baseline policy: always ask ``"other"`` for the first four disclosures.

    ``"other"`` matches any remaining constraint, so this maximizes disclosure
    per turn but learns nothing about attribute structure. Returns ``None`` once
    four constraints are disclosed to stop probing further.
    """
    return "other" if len(disclosed) < 4 else None


def policy_feature_first(turn, scenario, disclosed, classes, boundary_used):
    """Ask ``"feature"`` first (to disambiguate product function), then mop up.

    Rationale: ``feature`` is usually the highest-information coarse attribute,
    so spending the earliest turns on it should shrink the pool fastest. Falls
    back to ``"other"`` when no undisclosed ``feature`` constraint remains, or
    for ``intent_override`` (whose schedule is dictated by the override turn).
    """
    undisclosed = [c for c, k in classes.items() if c not in disclosed]
    if not undisclosed:
        return None
    if scenario == "intent_override":
        return "other"
    if not any(classes[c] == "feature" for c in undisclosed):
        return "other"
    # first two asks target feature; then mop up
    # (asked = turn offset by the boundary dud, kept for per-turn tuning)
    asked = turn - (1 if scenario == "boundary" else 0)
    if scenario == "buying":
        return "feature" if turn <= 1 else "other"
    return "feature" if turn <= 2 else "other"


def policy_mixed(turn, scenario, disclosed, classes, boundary_used):
    """Ask ``"feature"`` on turn 1, then ``"other"`` for the remaining turns.

    A middle-ground heuristic: lead with the informative ``feature`` attribute,
    then let ``"other"`` harvest whatever remains (``other`` matches any
    constraint). For ``intent_override`` sessions it just asks ``"other"``, since
    the override schedule already injects a hard constraint on its own.
    """
    undisclosed = [c for c, k in classes.items() if c not in disclosed]
    if not undisclosed:
        return None
    if scenario == "intent_override":
        return "other"
    if scenario == "buying":
        return "feature" if turn == 1 else "other"
    return "feature" if turn == 1 else "other"


def main():
    """Evaluate all three ask-policies on the public set and print summary stats.

    Loads the catalog and public sessions, then for each policy simulates every
    sample and reports mean turns-to-tight plus how many sessions tighten within
    2 and 3 turns, broken down per scenario type. This is the offline tuning
    loop: add a new policy function and list it here to compare strategies.
    """
    samples = load_jsonl(PUBLIC)
    _, _, products = catalog_index(CATALOG)
    idx = CatalogIndex(CATALOG)
    for name, policy in [("other", policy_other), ("feature_first", policy_feature_first), ("mixed", policy_mixed)]:
        turns = []
        by_scen = {}
        for sample in samples:
            # Resolve the ground-truth product's intent card for this session.
            card = intent_card(products[sample["ground_truth"]["parent_asin"]])
            t = simulate(sample, card, policy, idx)
            turns.append(t)
            # Bucket each result by scenario so per-scenario behavior is visible.
            by_scen.setdefault(sample["scenario_type"], []).append(t)
        print(f"{name}: mean={sum(turns)/len(turns):.3f} <=2={sum(1 for t in turns if t<=2)}/{len(turns)} "
              f"<=3={sum(1 for t in turns if t<=3)}/{len(turns)}", end="")
        for scen, ts in sorted(by_scen.items()):
            print(f"  [{scen}: {sum(ts)/len(ts):.2f}]", end="")
        print()


if __name__ == "__main__":
    main()
