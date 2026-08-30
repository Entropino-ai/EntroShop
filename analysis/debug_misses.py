"""Replay missed sessions with full logging to find failure causes.

This development probe re-runs every public-set session through the agent using
the exact simulator logic from ``evaluator.local_evaluator``, records which
sessions fail to surface the ground-truth product inside the top-10
recommendations ("misses"), and then replays only those misses with verbose
per-turn logging. It exists because the official evaluator reports aggregate
metrics but does not show *why* a session missed; the per-turn trace here (user
message, asked attribute, ranked ASINs, hit turn) is the fastest way to inspect
a failure without touching the read-only evaluator or data artifacts.
"""
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
    """Run one sample through the agent and report whether the target was hit.

    Mirrors the official evaluator's turn loop (with ``intent_override`` handling)
    so failures can be reproduced deterministically and inspected turn by turn.
    The agent's mutable session state is isolated behind a fresh ``dbg_*``
    session id on every call, so replaying the same ``agent`` instance across
    samples never leaks state from a previous session.

    Contract / returns:
        A dict ``{"hit": bool, "first_hit_turn": int | None}`` where ``hit`` is
        True only when the ground-truth ``parent_asin`` appears in the top-10
        recommendations on a turn where an override has been applied, and
        ``first_hit_turn`` is the 1-based turn of that first hit (else ``None``).

    Side effects:
        Prints a per-turn trace when ``verbose`` is True. This is a debug probe,
        so output is intentional and unbuffered relative to stdout.

    Failure modes:
        ``products[target]`` raises ``KeyError`` if the sample's ground-truth
        ASIN is absent from the catalog index; the evaluator data is expected
        to guarantee this lookup.
    """
    session_id = f"dbg_{uuid.uuid4().hex}"
    agent.reset(session_id, sample["user_profile"])
    target = str(sample["ground_truth"]["parent_asin"])
    # Rebuild the same hidden state the evaluator injects so the simulator sees
    # an identical, fully-disclosed intent card plus the override behavior.
    card, behavior = materialize_hidden_fields(sample, products)
    effective_sample = {**sample, "intent_card": card, "behavior": behavior}
    disclosed: set[str] = set()
    boundary_used = False
    # intent_override scenarios start with the override already in effect; the
    # others apply it lazily on the configured turn below.
    override_applied = sample["scenario_type"] != "intent_override"
    user_message = initial_message(effective_sample, coarse_category(categories.get(target, [])), disclosed)
    hit_turn = None
    if verbose:
        print(f"\n=== {sample['sample_id']} [{sample['scenario_type']}] target={target}")
        print(f"  title: {products[target]['title'][:120]}")
        print(f"  card: hard={card['hard_constraints']} soft={card['soft_preferences']}")
    for turn in range(1, MAX_TURNS + 1):
        response = agent.respond(session_id, user_message, turn, TOP_K)
        # Keep only the ASINs so rank position can be checked and printed cleanly.
        ranked = [item["parent_asin"] for item in response.get("recommendations", [])]
        if verbose:
            print(f"  T{turn} msg={user_message!r}")
            print(f"     ask={response.get('ask_attribute')!r} recs={ranked}")
        # A hit counts only in the top 10 and only after any override is live,
        # matching the evaluator's scoring contract (exact ASIN equality).
        if override_applied and target in ranked[:10]:
            hit_turn = turn
            if verbose:
                print(f"     HIT rank={ranked.index(target)+1}")
            break
        if turn == MAX_TURNS:
            break
        override = effective_sample.get("behavior", {}).get("override") or {}
        # Inject the user's "ignore my earlier preference" override on the
        # simulator-specified turn; its new value is added to the disclosed set
        # so later replies can treat it as known customer feedback.
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
        # The trailing list dumps the exact constraint phrases so a miss can be
        # cross-checked against the catalog's indexable strings by hand.
        print(f"  RESULT: hit={hit_turn is not None} turn={hit_turn} | target phrases in index: "
              f"{[c for c in [*card['hard_constraints'], *card['soft_preferences']]]}")
    return {"hit": hit_turn is not None, "first_hit_turn": hit_turn}


def main() -> None:
    """Replay the whole public set, summarize misses, then dump miss traces.

    This is the entry point of the probe: it first runs every sample quietly to
    collect a hit/miss verdict, aggregates the misses by scenario type so the
    failure distribution is visible at a glance, and finally replays each miss
    with ``verbose=True`` to print the full per-turn trace for manual triage.
    Returns ``None``; all output goes to stdout.
    """
    samples = load_jsonl(PUBLIC)
    catalog_ids, categories, products = catalog_index(CATALOG)
    agent = Agent(CATALOG)
    results = []
    # First pass: score every session quietly to build the miss set.
    for sample in samples:
        result = replay(agent, sample, catalog_ids, categories, products, verbose=False)
        results.append((sample, result))
    misses = [(sample, result) for sample, result in results if not result["hit"]]
    print(f"misses: {len(misses)}")
    by_scenario = {}
    # Bucket misses by scenario type so failures cluster visibly per template.
    for sample, result in misses:
        by_scenario.setdefault(sample["scenario_type"], []).append(sample["sample_id"])
    print("by scenario:", {key: len(value) for key, value in by_scenario.items()})
    # Second pass: replay only the misses verbosely for step-by-step inspection.
    for sample, result in misses:
        replay(agent, sample, catalog_ids, categories, products, verbose=True)


if __name__ == "__main__":
    main()
