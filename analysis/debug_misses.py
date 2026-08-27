"""Replay missed sessions with full logging to find failure causes."""
from __future__ import annotations

import json
import random
import sys
import uuid
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
from starter.agent import Agent  # noqa: E402

CATALOG = ROOT / "data" / "catalog.jsonl"
PUBLIC = ROOT / "data" / "public_set.jsonl"


def replay(agent: Agent, sample: dict, catalog_ids, categories, products, verbose: bool) -> dict:
    session_id = f"dbg_{uuid.uuid4().hex}"
    agent.reset(session_id, sample["user_profile"])
    target = str(sample["ground_truth"]["parent_asin"])
    card, behavior = materialize_hidden_fields(sample, products)
    effective_sample = {**sample, "intent_card": card, "behavior": behavior}
    disclosed: set[str] = set()
    boundary_used = False
    override_applied = sample["scenario_type"] != "intent_override"
    user_message = initial_message(effective_sample, coarse_category(categories.get(target, [])), disclosed)
    hit_turn = None
    if verbose:
        print(f"\n=== {sample['sample_id']} [{sample['scenario_type']}] target={target}")
        print(f"  title: {products[target]['title'][:120]}")
        print(f"  card: hard={card['hard_constraints']} soft={card['soft_preferences']}")
    for turn in range(1, MAX_TURNS + 1):
        response = agent.respond(session_id, user_message, turn, TOP_K)
        ranked = [item["parent_asin"] for item in response.get("recommendations", [])]
        if verbose:
            print(f"  T{turn} msg={user_message!r}")
            print(f"     ask={response.get('ask_attribute')!r} recs={ranked}")
        if override_applied and target in ranked[:10]:
            hit_turn = turn
            if verbose:
                print(f"     HIT rank={ranked.index(target)+1}")
            break
        if turn == MAX_TURNS:
            break
        override = effective_sample.get("behavior", {}).get("override") or {}
        if not override_applied and turn + 1 == int(override.get("turn", 3)):
            override_applied = True
            new_value = str(override.get("new_value", ""))
            if new_value:
                disclosed.add(new_value)
            user_message = str(override.get("message", "Actually, please ignore my earlier preference."))
        else:
            user_message, boundary_used = customer_reply(
                effective_sample, response.get("ask_attribute"), disclosed, boundary_used
            )
    if verbose:
        print(f"  RESULT: hit={hit_turn is not None} turn={hit_turn} | target phrases in index: "
              f"{[c for c in [*card['hard_constraints'], *card['soft_preferences']]]}")
    return {"hit": hit_turn is not None, "first_hit_turn": hit_turn}


def main() -> None:
    samples = load_jsonl(PUBLIC)
    catalog_ids, categories, products = catalog_index(CATALOG)
    agent = Agent(CATALOG)
    results = []
    for sample in samples:
        result = replay(agent, sample, catalog_ids, categories, products, verbose=False)
        results.append((sample, result))
    misses = [(sample, result) for sample, result in results if not result["hit"]]
    print(f"misses: {len(misses)}")
    by_scenario = {}
    for sample, result in misses:
        by_scenario.setdefault(sample["scenario_type"], []).append(sample["sample_id"])
    print("by scenario:", {key: len(value) for key, value in by_scenario.items()})
    for sample, result in misses:
        replay(agent, sample, catalog_ids, categories, products, verbose=True)


if __name__ == "__main__":
    main()
