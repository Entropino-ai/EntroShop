"""Grid-search ask policies against the real evaluator (shared index)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_lib import state  # noqa: E402
from agent_lib.index import CatalogIndex  # noqa: E402
from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl  # noqa: E402
from starter.agent import Agent  # noqa: E402

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
    print("building shared index...")
    shared_index = CatalogIndex("data/catalog.jsonl")
    samples = load_jsonl("data/public_set.jsonl")
    ids, cats, products = catalog_index("data/catalog.jsonl")
    print(f"catalog ok: {len(ids)} products, {len(samples)} sessions")

    for name, plans in POLICIES.items():
        state.PLANS.clear()
        state.PLANS.update(plans)
        agent = Agent.__new__(Agent)
        agent.catalog_path = Path("data/catalog.jsonl")
        agent.index = shared_index
        agent._sessions = {}
        result = evaluate(agent, samples, ids, cats, products)
        scen = {k: (v["hit_rate_at_10"], round(v["mrr"], 4), v["mttc"])
                for k, v in result["scenario_metrics"].items()}
        print(f"{name:18s} hit={result['hit_rate_at_10']:.3f} mrr={result['mrr']:.4f} "
              f"mttc={result['mttc']:.3f} TS={result['recommended_technical_score']:.4f}")
        print(f"    {json.dumps(scen)}")


if __name__ == "__main__":
    main()
