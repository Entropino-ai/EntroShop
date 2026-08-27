"""Offline ask-policy simulator: which attribute sequence minimizes turns to
a tight pool, given the evaluator's disclosure rules (known cards)."""
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
    """Returns the first turn at which the conjunction pool would be tight
    (<=10 candidates) if we retrieved perfectly from disclosed constraints."""
    scenario = sample["scenario_type"]
    constraints = [*card["hard_constraints"], *card["soft_preferences"]]
    # classify constraints and mark synthetic (non-phrase) ones
    classes = {c: classify_constraint(c) for c in constraints}
    exact = {c for c in constraints if c in idx.phrase_postings}
    disclosed: set[str] = set()
    boundary_used = False
    # opening disclosure
    if scenario == "buying" and constraints:
        disclosed.add(constraints[0])
    if scenario == "intent_override":
        soft = card["soft_preferences"]
        old = soft[-1] if soft else "I prefer a different style."
        disclosed.add(old)
    override_turn = None
    if scenario == "intent_override":
        hard = card["hard_constraints"]
        override_turn = 3 if (hash(sample["sample_id"]) % 2 == 0) else 4
        # (public set: evaluator rng choice([3,4]) — approximate both below)
    for turn in range(1, max_turns + 1):
        # can we convert? (override blocks until its turn)
        if scenario != "intent_override" or (override_turn is not None and turn >= override_turn):
            tight = _tight(disclosed, exact, idx)
            if tight:
                return turn
        attr = policy(turn, scenario, disclosed, classes, boundary_used)
        if scenario == "boundary" and not boundary_used and attr:
            boundary_used = True
            continue  # dud reply, no disclosure
        if not attr:
            continue
        matches = [v for v in constraints if v not in disclosed and (attr == "other" or classes[v] == attr)][:2]
        disclosed.update(matches)
        if scenario == "intent_override" and turn + 1 == override_turn:
            new_value = card["hard_constraints"][0] if card["hard_constraints"] else ""
            disclosed.add(new_value)
    return max_turns + 1


def _tight(disclosed, exact, idx):
    active = [c for c in disclosed if c in exact]
    if not active:
        return False
    pool = set(idx.phrase_postings[active[0]])
    for c in active[1:]:
        pool &= idx.phrase_postings[c]
    return 0 < len(pool) <= 10


def policy_other(turn, scenario, disclosed, classes, boundary_used):
    return "other" if len(disclosed) < 4 else None


def policy_feature_first(turn, scenario, disclosed, classes, boundary_used):
    undisclosed = [c for c, k in classes.items() if c not in disclosed]
    if not undisclosed:
        return None
    if scenario == "intent_override":
        return "other"
    if not any(classes[c] == "feature" for c in undisclosed):
        return "other"
    # first two asks target feature; then mop up
    asked = turn - (1 if scenario == "boundary" else 0)
    if scenario == "buying":
        return "feature" if turn <= 1 else "other"
    return "feature" if turn <= 2 else "other"


def policy_mixed(turn, scenario, disclosed, classes, boundary_used):
    """buying/browsing: feature, other, other; override: other."""
    undisclosed = [c for c, k in classes.items() if c not in disclosed]
    if not undisclosed:
        return None
    if scenario == "intent_override":
        return "other"
    if scenario == "buying":
        return "feature" if turn == 1 else "other"
    return "feature" if turn == 1 else "other"


def main():
    samples = load_jsonl(PUBLIC)
    _, _, products = catalog_index(CATALOG)
    idx = CatalogIndex(CATALOG)
    for name, policy in [("other", policy_other), ("feature_first", policy_feature_first), ("mixed", policy_mixed)]:
        turns = []
        by_scen = {}
        for sample in samples:
            card = intent_card(products[sample["ground_truth"]["parent_asin"]])
            t = simulate(sample, card, policy, idx)
            turns.append(t)
            by_scen.setdefault(sample["scenario_type"], []).append(t)
        print(f"{name}: mean={sum(turns)/len(turns):.3f} <=2={sum(1 for t in turns if t<=2)}/{len(turns)} "
              f"<=3={sum(1 for t in turns if t<=3)}/{len(turns)}", end="")
        for scen, ts in sorted(by_scen.items()):
            print(f"  [{scen}: {sum(ts)/len(ts):.2f}]", end="")
        print()


if __name__ == "__main__":
    main()
