"""Probe the simulator to understand how intent cards are derived and how
the disclosed constraints map onto raw catalog text.

This is a read-only analysis script (it never mutates data or writes files)
that answers three questions driving the retrieval design:

1. How are intent-card constraints derived?  Each session's ground-truth
   product is fed through :func:`intent_card`, and the resulting hard/soft
   constraints are classified via :func:`classify_constraint` to see which
   attributes the copilot actually reasons over.
2. How faithfully do constraints map to catalog text?  Constraints are checked
   against per-product sets of cleaned feature/detail strings, measuring how
   often a constraint is an exact substring of the target product's raw text.
3. How selective are exact-phrase conjunctions?  For each session it counts how
   many catalog products satisfy *all* exact constraints, which reveals how much
   of the retrieval signal comes from exact-phrase matching vs. other routes.

Results are printed to stdout as a compact summary: attribute distribution,
exact-match rate, budget-constraint frequency, conjunction selectivity,
phrase-sharing overlap, phrase-length stats, and one sample intent card.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

# Make the repo root importable so the sibling ``evaluator`` package resolves
# regardless of which directory this script is launched from.
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
    """Flatten a heterogeneous product-attribute value into display strings.

    Product fields in the catalog are inconsistently shaped: they can be a dict
    (key/value pairs), a list of items, or a single scalar. This normalizes all
    three shapes into a flat list of strings so they can be treated uniformly
    when building the exact-phrase inventory.

    Contract:
        * Dict values become ``"key: item"`` strings (one per key).
        * List items are stringified individually.
        * Scalars are stringified as-is.
        * Falsy placeholders (``None``, empty string, empty list) are skipped so
          they do not pollute the phrase inventory.

    Returns:
        A list of non-empty strings; may be empty if the value held no content.
    """
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in value.items() if item not in (None, "", [])]
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)] if value not in (None, "") else []


def clean_constraint(value: str, limit: int = 180) -> str:
    """Normalize a candidate phrase into a canonical, bounded string.

    Catalog text is noisy (irregular whitespace, trailing punctuation), so before
    it can be compared against constraints it must be normalized the same way
    the intent-card producer normalizes its constraints, so both sides share one
    canonical form for exact-phrase matching.

    Contract:
        * Collapses any whitespace run to a single space.
        * Strips leading/trailing spaces and the punctuation set ``" -;,."``
          plus tabs/newlines.
        * Truncates to ``limit`` characters (default 180) and re-strips, since
          long feature blurbs are unlikely to appear verbatim in a short
          constraint.

    Returns:
        The cleaned string; empty if the input held only whitespace/punctuation.
    """
    return re.sub(r"\s+", " ", value).strip(" -;,.\t\n")[:limit].rstrip()


def main() -> None:
    """Run the simulator probe and print a summary report.

    Loads the public sessions and the catalog index, builds per-product
    exact-phrase sets from ``features`` and ``details`` (mirroring the strings
    the intent-card producer sees), then iterates every session to accumulate:

        * the attribute distribution of constraints,
        * the rate at which constraints exactly match a raw catalog string of
          the target product,
        * how many products satisfy the conjunction of ALL exact constraints
          (selectivity), and
        * how many products share each individual exact phrase.

    Side effects: prints several formatted summary lines to stdout only; no
    files are written and no model/LLM calls are made.
    """
    samples = load_jsonl(PUBLIC)
    _, _, products = catalog_index(CATALOG)

    # Per-product exact phrase sets (as the intent_card producer sees them)
    phrase_sets: dict[str, set[str]] = {}
    for asin, product in products.items():
        # Only features/details can surface as verbatim constraints; pool both.
        candidates = [*flatten_values(product.get("features")), *flatten_values(product.get("details"))]
        # Clean each string, drop empties, and dedupe via the set comprehension.
        phrases = {clean_constraint(item) for item in candidates if clean_constraint(item)}
        phrase_sets[asin] = phrases

    attr_counts: Counter[str] = Counter()
    exact_in_target: list[bool] = []
    conjunction_selectivity: list[int] = []
    constraint_overlap_stats: list[tuple[int, int]] = []  # (shared by others, total phrases)
    budgets = 0
    title_as_category = 0  # reserved counter (currently unused in the report)
    for sample in samples:
        target = str(sample["ground_truth"]["parent_asin"])
        product = products[target]
        # Rebuild the card exactly as the agent would, to observe real output.
        card = intent_card(product)
        constraints = [*card["hard_constraints"], *card["soft_preferences"]]
        for value in constraints:
            attr = classify_constraint(value)
            attr_counts[attr] += 1
            # A constraint is "exact" if it appears verbatim in the target's text.
            exact_in_target.append(value in phrase_sets[target])
            if "budget around $" in value:  # budget constraints use this template
                budgets += 1
        # Selectivity: how many products contain ALL exact constraints.
        if constraints:
            # The inner ``if value in phrases`` drops constraints that are not
            # themselves exact phrases, so selectivity measures only the
            # exact-phrase part of the signal (never a vacuous empty match).
            matching = [asin for asin, phrases in phrase_sets.items()
                        if all(value in phrases for value in constraints if value in phrases)]
            conjunction_selectivity.append(len(matching))
        # How many other products share each individual exact phrase.
        for value in constraints:
            if value in phrase_sets[target]:
                # ``shared`` counts the target itself too (it always contains the phrase).
                shared = sum(1 for phrases in phrase_sets.values() if value in phrases)
                constraint_overlap_stats.append((shared, len(phrase_sets[target])))

    print("attribute distribution of constraints:", dict(attr_counts.most_common()))
    print(f"constraints that exactly match a raw feature/detail string of the target: "
          f"{sum(exact_in_target)}/{len(exact_in_target)} = {sum(exact_in_target)/len(exact_in_target):.4f}")
    print(f"budget constraints: {budgets}/{len(samples)} sessions")
    sel = conjunction_selectivity
    # Naive median via the sorted middle element; "unique(=1)" = sessions where
    # the conjunction already isolates a single product (the ideal signal).
    print("conjunction selectivity (products matching ALL exact constraints): "
          f"median={sorted(sel)[len(sel)//2]} mean={sum(sel)/len(sel):.2f} "
          f"unique(=1)={sum(1 for s in sel if s == 1)}/{len(sel)}")
    print("single-phrase sharing (products sharing the exact string, incl target): "
          f"median={sorted(s for s, _ in constraint_overlap_stats)[len(constraint_overlap_stats)//2]} "
          f"max={max(s for s, _ in constraint_overlap_stats)}")
    # Phrase length distribution: how long exact-phrase tokens tend to be.
    lens = [len(v) for asin in phrase_sets for v in phrase_sets[asin]]
    print(f"phrase count total={len(lens)}, median len={sorted(lens)[len(lens)//2]}, "
          f"max len={max(lens)}")
    # Print the first session's card (truncated) so a human can eyeball the shape.
    print("sample card:", json.dumps(intent_card(products[str(samples[0]['ground_truth']['parent_asin'])]), indent=2)[:900])


if __name__ == "__main__":
    main()
