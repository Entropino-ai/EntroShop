"""Probe the simulator: how intent cards are derived, how constraints
map to catalog text, and how selective exact-phrase conjunctions are."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluator.local_evaluator import (  # noqa: E402
    catalog_index,
    classify_constraint,
    intent_card,
    load_jsonl,
)

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog.jsonl"
PUBLIC = ROOT / "data" / "public_set.jsonl"


def flatten_values(value: object) -> list[str]:
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in value.items() if item not in (None, "", [])]
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)] if value not in (None, "") else []


def clean_constraint(value: str, limit: int = 180) -> str:
    return re.sub(r"\s+", " ", value).strip(" -;,.\t\n")[:limit].rstrip()


def main() -> None:
    samples = load_jsonl(PUBLIC)
    _, _, products = catalog_index(CATALOG)

    # Per-product exact phrase sets (as the intent_card producer sees them)
    phrase_sets: dict[str, set[str]] = {}
    for asin, product in products.items():
        candidates = [*flatten_values(product.get("features")), *flatten_values(product.get("details"))]
        phrases = {clean_constraint(item) for item in candidates if clean_constraint(item)}
        phrase_sets[asin] = phrases

    attr_counts: Counter[str] = Counter()
    exact_in_target: list[bool] = []
    conjunction_selectivity: list[int] = []
    constraint_overlap_stats: list[tuple[int, int]] = []  # (shared by others, total phrases)
    budgets = 0
    title_as_category = 0
    for sample in samples:
        target = str(sample["ground_truth"]["parent_asin"])
        product = products[target]
        card = intent_card(product)
        constraints = [*card["hard_constraints"], *card["soft_preferences"]]
        for value in constraints:
            attr = classify_constraint(value)
            attr_counts[attr] += 1
            exact_in_target.append(value in phrase_sets[target])
            if "budget around $" in value:
                budgets += 1
        # selectivity: how many products contain ALL exact constraints
        if constraints:
            matching = [asin for asin, phrases in phrase_sets.items()
                        if all(value in phrases for value in constraints if value in phrases)]
            conjunction_selectivity.append(len(matching))
        # how many other products share each individual exact phrase
        for value in constraints:
            if value in phrase_sets[target]:
                shared = sum(1 for phrases in phrase_sets.values() if value in phrases)
                constraint_overlap_stats.append((shared, len(phrase_sets[target])))

    print("attribute distribution of constraints:", dict(attr_counts.most_common()))
    print(f"constraints that exactly match a raw feature/detail string of the target: "
          f"{sum(exact_in_target)}/{len(exact_in_target)} = {sum(exact_in_target)/len(exact_in_target):.4f}")
    print(f"budget constraints: {budgets}/{len(samples)} sessions")
    sel = conjunction_selectivity
    print("conjunction selectivity (products matching ALL exact constraints): "
          f"median={sorted(sel)[len(sel)//2]} mean={sum(sel)/len(sel):.2f} "
          f"unique(=1)={sum(1 for s in sel if s == 1)}/{len(sel)}")
    print("single-phrase sharing (products sharing the exact string, incl target): "
          f"median={sorted(s for s, _ in constraint_overlap_stats)[len(constraint_overlap_stats)//2]} "
          f"max={max(s for s, _ in constraint_overlap_stats)}")
    # phrase length distribution
    lens = [len(v) for asin in phrase_sets for v in phrase_sets[asin]]
    print(f"phrase count total={len(lens)}, median len={sorted(lens)[len(lens)//2]}, "
          f"max len={max(lens)}")
    print("sample card:", json.dumps(intent_card(products[str(samples[0]['ground_truth']['parent_asin'])]), indent=2)[:900])


if __name__ == "__main__":
    main()
