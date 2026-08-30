"""Grid-search ``ask_attribute`` policies against the official local evaluator.

WHY THIS EXISTS
    This is an offline development probe (see ``analysis/`` in the repo guide).
    It sweeps a small set of hand-crafted ask-policies — deterministic schedules
    that map conversation phases to the ``ask_attribute`` the agent emits each
    turn — and prints the official metrics for every policy in a single run.
    It answers, cheaply and reproducibly: *which question schedule maximizes
    Hit@10 / MRR / MTTC / TechnicalScore on the disclosed public set?*

HOW IT WORKS
    Rather than driving the full state machine's own decisions, it wires a bare
    ``Agent`` whose per-turn ``ask_attribute`` is looked up from a fixed plan
    (``POLICIES`` below) and then reuses the *exact* judge
    (``evaluator.local_evaluator.evaluate``) used for the official score. Because
    evaluation shares the parsed ``CatalogIndex`` and the real judge, numbers
    here are directly comparable to an official run.

CONTRACT / SIDE EFFECTS
    - Prints a per-policy metric table to stdout; writes no files.
    - Mutates ``agent_lib.state.PLANS`` in place per policy (clear + repopulate),
      which is why this is meant to run as a standalone script, not to be imported.

NOTES
    ``analysis/`` exists for tuning, but any schedule found here must still be
    validated for robustness on the 800 unseen private sessions — not overfit to
    the disclosed templates alone (see repo guide's hard rules).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Repo root sits one level above this file (analysis/ -> EntroShop/); prepend it
# so the app's own packages import without a package install.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Imports happen *after* the sys.path bootstrap above, hence the noqa: E402
# (module-level import not at top of file) suppressions.
from agent_lib import state  # noqa: E402
from agent_lib.index import CatalogIndex  # noqa: E402
from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl  # noqa: E402
from starter.agent import Agent  # noqa: E402

# Grid of ask-attribute schedules to sweep. Each plan maps a conversation
# phase/intent key ("buying", "browsing", "boundary", "intent_override") to an
# ordered list of ``ask_attribute`` tokens emitted one per turn while in that
# phase. Tokens are real attribute questions ("feature", "color") or the generic
# fallthrough "other"; the list length caps how many questions a phase asks
# before its schedule is exhausted.
#
# The knob being swept is which phases lead with a discriminating attribute
# question (feature/color) vs. the generic "other", to find the schedule that
# maximizes the official metrics on the public set.
POLICIES = {
    "other5": {
        "buying": ["other"] * 5,
        "browsing": ["other"] * 5,
        "boundary": ["other"] * 5,
        "intent_override": ["other"] * 5,
    },
    "buying_ftr": {
        "buying": ["feature", "other", "other", "other"],
        "browsing": ["other"] * 5,
        "boundary": ["other"] * 5,
        "intent_override": ["other"] * 5,
    },
    "browsing_ftr": {
        "buying": ["other"] * 5,
        "browsing": ["feature", "other", "other", "other"],
        "boundary": ["other"] * 5,
        "intent_override": ["other"] * 5,
    },
    "mixed_ftr": {
        "buying": ["feature", "other", "other"],
        "browsing": ["feature", "feature", "other", "other"],
        "boundary": ["feature", "feature", "other", "other"],
        "intent_override": ["other"] * 4,
    },
    "browsing_ftr2": {
        "buying": ["other"] * 5,
        "browsing": ["feature", "feature", "other", "other"],
        "boundary": ["feature", "feature", "other", "other"],
        "intent_override": ["other"] * 5,
    },
    "buying_color_ftr": {
        "buying": ["color", "feature", "other", "other"],
        "browsing": ["other"] * 5,
        "boundary": ["other"] * 5,
        "intent_override": ["other"] * 5,
    },
    "boundary_ftr": {
        "buying": ["other"] * 5,
        "browsing": ["other"] * 5,
        "boundary": ["feature", "feature", "other", "other"],
        "intent_override": ["other"] * 5,
    },
}


def main() -> None:
    """Run every policy in ``POLICIES`` through the official evaluator and print metrics.

    Builds the shared catalog index once (so each policy reuses the same parsed
    50k-product catalog instead of re-parsing it), loads the public sessions,
    then for each policy constructs a minimal ``Agent`` whose per-turn
    ``ask_attribute`` is driven by the policy schedule (via ``state.PLANS``) and
    calls the real ``evaluate``. Prints one summary line per policy plus a JSON
    dump of the per-scenario breakdown.

    Side effects: none persistent (stdout only). Mutates ``state.PLANS`` between
    iterations, so this is only safe as the script entry point, not as a
    reusable library call.
    """
    print("building shared index...")
    # Parse the catalog once and share it across all policies — 50k products are
    # expensive to re-parse, and only per-policy agent state varies between runs.
    shared_index = CatalogIndex("data/catalog.jsonl")
    samples = load_jsonl("data/public_set.jsonl")
    # Re-derive ids/cats/products with the same helper the official run uses,
    # guaranteeing the judge sees identical inputs (metric parity).
    ids, cats, products = catalog_index("data/catalog.jsonl")
    print(f"catalog ok: {len(ids)} products, {len(samples)} sessions")

    for name, plans in POLICIES.items():
        # Install this policy's schedule into the global plan table the agent reads.
        state.PLANS.clear()
        state.PLANS.update(plans)
        # Build a bare Agent by hand: skip __init__ (which would re-index the
        # catalog) and inject the shared index plus a clean session cache so each
        # policy starts from a blank slate instead of leaking prior turns.
        agent = Agent.__new__(Agent)
        agent.catalog_path = Path("data/catalog.jsonl")
        agent.index = shared_index
        agent._sessions = {}
        result = evaluate(agent, samples, ids, cats, products)
        # Collapse scenario_metrics into a compact (hit@10, mrr, mttc) tuple per
        # scenario so the whole per-scenario breakdown fits on one JSON line.
        scen = {k: (v["hit_rate_at_10"], round(v["mrr"], 4), v["mttc"])
                for k, v in result["scenario_metrics"].items()}
        print(f"{name:18s} hit={result['hit_rate_at_10']:.3f} mrr={result['mrr']:.4f} "
              f"mttc={result['mttc']:.3f} TS={result['recommended_technical_score']:.4f}")
        print(f"    {json.dumps(scen)}")


if __name__ == "__main__":
    main()
