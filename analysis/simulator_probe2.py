"""Probe v2: exact conjunction selectivity + why constraints miss exact match."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluator.local_evaluator import catalog_index, intent_card, load_jsonl  # noqa: E402

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

    phrase_sets: dict[str, set[str]] = {}
    for asin, product in products.items():
        candidates = [*flatten_values(product.get("features")), *flatten_values(product.get("details"))]
        phrase_sets[asin] = {clean_constraint(item) for item in candidates if clean_constraint(item)}

    # inverted index
    inverted: dict[str, Counter[str]] = {}
    for asin, phrases in phrase_sets.items():
        for phrase in phrases:
            inverted.setdefault(phrase, Counter())[asin] += 1

    hit_selectivity: list[int] = []
    missing_causes: Counter[str] = Counter()
    cases: list[tuple[str, str, str]] = []
    for sample in samples:
        target = str(sample["ground_truth"]["parent_asin"])
        card = intent_card(products[target])
        constraints = [*card["hard_constraints"], *card["soft_preferences"]]
        target_exact = [value for value in constraints if value in phrase_sets[target]]
        # conjunction over products containing ALL target-exact constraints
        if target_exact:
            matching = set(inverted[target_exact[0]].keys())
            for value in target_exact[1:]:
                matching &= set(inverted[value].keys())
            hit_selectivity.append(len(matching))
            if len(matching) <= 10:
                pass  # perfect conjunction
        for value in constraints:
            if value not in phrase_sets[target]:
                lowered = value.lower()
                target_lower = {p.lower() for p in phrase_sets[target]}
                if lowered in target_lower:
                    missing_causes["case_mismatch"] += 1
                elif re.match(r"^(cotton|polyester|nylon|leather|wool|spandex|silk|rayon|fabric)$", lowered):
                    missing_causes["material_word"] += 1
                elif lowered.startswith("color:"):
                    missing_causes["color_tag"] += 1
                elif any(lowered.startswith(p[:60].lower()) and len(p) > 180 for p in target_lower):
                    missing_causes["truncation"] += 1
                else:
                    missing_causes["other"] += 1
                    cases.append((target, value, sorted(phrase_sets[target])[:3]))

    sel = sorted(hit_selectivity)
    print(f"samples with >=1 exact constraint: {len(sel)}/200")
    if sel:
        print("conjunction selectivity: median={} p25={} p75={} unique(=1)={}/{} "
              "<=10 candidates={}".format(
                  sel[len(sel) // 2], sel[len(sel) // 4], sel[3 * len(sel) // 4],
                  sum(1 for s in sel if s == 1), len(sel), sum(1 for s in sel if s <= 10)))
        print("distribution:", dict(Counter(sel).most_common(12)))
    print("non-exact constraint causes:", dict(missing_causes.most_common()))
    print("\nsample mismatches:")
    for target, value, phrases in cases[:5]:
        print(f"  target={target} constraint={value!r}")
        print(f"    sample target phrases: {phrases}")


if __name__ == "__main__":
    main()
