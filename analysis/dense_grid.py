"""Grid-search dense-route gating against the live evaluator (shared index).

WHY: The agent's retrieval pipeline mixes a deterministic TF-IDF route with an
optional dense (MiniLM) route. The dense route is gated by three module-level
knobs in ``agent_lib.retrieve`` — a TF-IDF weight, a minimum candidate-pool
size, and a minimum conversation history. This script sweeps a small hand-picked
grid over those knobs and reports the official evaluator's metrics for each, so
the best gate thresholds can be chosen without changing agent code.

CONTRACT: Run as a script (``python3 analysis/dense_grid.py``). It mutates the
``agent_lib.retrieve`` module globals between variants and prints one summary
line per variant to stdout. It does not write any result file itself.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Resolve the repo root (parent of this file's ``analysis`` directory) and put it
# on ``sys.path`` so the package imports below resolve when run as a script.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Deliberately imported after the ``sys.path`` fix above; ``# noqa: E402`` silences
# flake8's "module level import not at top of file" rule.
import agent_lib.retrieve as R  # noqa: E402
from agent_lib.dense import DenseIndex  # noqa: E402
from agent_lib.index import CatalogIndex  # noqa: E402
from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl  # noqa: E402
from starter.agent import Agent  # noqa: E402


def main() -> None:
    """Sweep dense-route gating thresholds over the official public-set evaluator.

    For each variant it mutates the ``agent_lib.retrieve`` module-level knobs,
    wires a fresh ``Agent`` instance by hand (via ``__new__`` to skip any
    ``__init__`` side effects), runs the shared-index ``evaluate`` on the public
    sessions, and prints one summary line per variant.

    Contract:
        - Variant tuples are ``(name, W_TFIDF, DENSE_MIN_POOL, DENSE_MIN_HISTORY)``.
        - Side effects: mutates ``R`` module globals and prints to stdout.
        - Returns ``None``; the evaluator itself is responsible for any files.
    """
    # Build the shared indices/samples once so every variant reuses the same
    # objects — only the retrieval *gating* knobs change between variants.
    idx = CatalogIndex("data/catalog.jsonl")
    dense = DenseIndex(idx.products)
    samples = load_jsonl("data/public_set.jsonl")
    ids, cats, products = catalog_index("data/catalog.jsonl")

    # Each tuple: (name, W_TFIDF, DENSE_MIN_POOL, DENSE_MIN_HISTORY).
    # The ("none", ...) entry uses sentinel values that effectively disable the
    # dense route: a zero TF-IDF weight, an unreachably large min-pool, and a
    # 99-turn minimum history that the 10-turn sessions can never satisfy.
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
        # Mutate the module-level knobs consumed by agent_lib.retrieve so the
        # variant takes effect without rebuilding the agent or its constructor.
        R.W_TFIDF = w
        R.DENSE_MIN_POOL = min_pool
        R.DENSE_MIN_HISTORY = min_hist
        # Bypass Agent.__init__ (which may do expensive setup) and wire only the
        # attributes the evaluator actually reads during a session.
        agent = Agent.__new__(Agent)
        agent.catalog_path = Path("data/catalog.jsonl")
        agent.index = idx
        agent.dense = dense
        agent._sessions = {}
        # Run the official evaluator over the shared public-set sessions.
        result = evaluate(agent, samples, ids, cats, products)
        # Flatten per-scenario metrics into a name-keyed lookup so the summary
        # line can cherry-pick the boundary/browsing MRRs below.
        scen = {k: (v["hit_rate_at_10"], round(v["mrr"], 4), v["mttc"])
                for k, v in result["scenario_metrics"].items()}
        # One-line report per variant: overall hit/MRR/MTTC/technical score plus
        # the boundary and browsing scenario MRRs for a finer-grained comparison.
        print(f"{name:16s} hit={result['hit_rate_at_10']:.3f} mrr={result['mrr']:.4f} "
              f"mttc={result['mttc']:.3f} TS={result['recommended_technical_score']:.4f} "
              f"boundary_mrr={scen['boundary'][1]} browsing_mrr={scen['browsing'][1]}")


if __name__ == "__main__":
    main()
