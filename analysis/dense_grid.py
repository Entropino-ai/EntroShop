"""Grid-search dense-route gating against the live evaluator (shared index)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import agent_lib.retrieve as R  # noqa: E402
from agent_lib.dense import DenseIndex  # noqa: E402
from agent_lib.index import CatalogIndex  # noqa: E402
from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl  # noqa: E402
from starter.agent import Agent  # noqa: E402


def main() -> None:
    idx = CatalogIndex("data/catalog.jsonl")
    dense = DenseIndex(idx.products)
    samples = load_jsonl("data/public_set.jsonl")
    ids, cats, products = catalog_index("data/catalog.jsonl")

    variants = [
        ("none", 0.0, 10**9, 99),
        ("w30_p200_h1", 30.0, 200, 1),
        ("w30_p200_h2", 30.0, 200, 2),
        ("w15_p200_h1", 15.0, 200, 1),
        ("w30_p500_h1", 30.0, 500, 1),
        ("w30_p500_h2", 30.0, 500, 2),
        ("w15_p500_h2", 15.0, 500, 2),
        ("w50_p500_h2", 50.0, 500, 2),
    ]
    for name, w, min_pool, min_hist in variants:
        R.W_TFIDF = w
        R.DENSE_MIN_POOL = min_pool
        R.DENSE_MIN_HISTORY = min_hist
        agent = Agent.__new__(Agent)
        agent.catalog_path = Path("data/catalog.jsonl")
        agent.index = idx
        agent.dense = dense
        agent._sessions = {}
        result = evaluate(agent, samples, ids, cats, products)
        scen = {k: (v["hit_rate_at_10"], round(v["mrr"], 4), v["mttc"])
                for k, v in result["scenario_metrics"].items()}
        print(f"{name:16s} hit={result['hit_rate_at_10']:.3f} mrr={result['mrr']:.4f} "
              f"mttc={result['mttc']:.3f} TS={result['recommended_technical_score']:.4f} "
              f"boundary_mrr={scen['boundary'][1]} browsing_mrr={scen['browsing'][1]}")


if __name__ == "__main__":
    main()
