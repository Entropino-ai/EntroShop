"""Probe v2: exact conjunction selectivity + why constraints miss exact match.

WHY THIS EXISTS
---------------
The public-set simulator discloses each session's ground-truth product, so we can
inspect what its constraints look like against the raw catalog. This probe answers
two diagnostics questions that drive retrieval tuning:

1. **Selectivity** — if we treat the disclosed constraints as verbatim catalog
   phrases and AND them together (exact conjunction), how many products survive?
   A low number means exact-phrase conjunction is a strong, precise retrieval
   signal; a high number means it under-constrains and needs more signals.

2. **Miss causes** — when a disclosed constraint does *not* match the target
   product's phrase set verbatim, *why*? (case mismatch, material wording, color
   tags, truncation, etc.) This tells us which normalizations would recover exact
   matches instead of silently dropping the constraint.

It is an offline, read-only analysis script: it imports the catalog index helpers,
loads the public set, and prints summary statistics to stdout. Nothing is written.
"""
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
    """Recursively flatten a catalog field into a list of display strings.

    Catalog JSON nests attributes in several shapes: flat lists, dicts of
    `key: value` pairs (e.g. features), and scalar leaves. This normalizes all
    of them into one flat list of non-empty strings so downstream code can treat
    every product uniformly as a bag of phrases.

    CONTRACT:
        * dict -> ["key: item", ...] (the key is kept because it often carries
          the attribute name, e.g. "material: cotton").
        * list -> ["item", ...] (elements stringified verbatim).
        * scalar -> ["value"] as a single-item list.
        * Falsy entries (None, "", []) are skipped at every level, so an empty
          input yields an empty list rather than a stray "None"/"" string.

    Side effects: none. Returns a new list; it never mutates the input.
    """
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in value.items() if item not in (None, "", [])]
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)] if value not in (None, "") else []


def clean_constraint(value: str, limit: int = 180) -> str:
    """Normalize a phrase for exact-match comparison.

    Catalog text can carry repeated whitespace, leading/trailing punctuation, and
    very long values. This collapses runs of whitespace to a single space, strips
    separator/punctuation characters from the ends, then truncates to ``limit``
    chars (rstripping so the cut never ends in whitespace).

    WHY: constraints must be compared against catalog phrases with the *same*
    normalization on both sides, otherwise near-identical strings fail exact
    matching. The 180-char cap mirrors the truncation the analysis later flags
    (see ``main``), keeping this helper's behavior aligned with that assumption.

    Returns the cleaned string (possibly empty if the value was blank). Pure
    function; no side effects.
    """
    return re.sub(r"\s+", " ", value).strip(" -;,.\t\n")[:limit].rstrip()


def main() -> None:
    """Run the probe: build exact-phrase indexes, measure conjunction
    selectivity, and classify why disclosed constraints miss exact matches.

    Pipeline:
      1. Load the public set (200 sessions) and the catalog index.
      2. Per product, flatten features+details into cleaned phrases.
      3. Build an inverted index phrase -> Counter of parent_asin occurrences.
      4. For each sample, take the target's disclosed hard+soft constraints,
         keep only those present verbatim in the target's phrase set, then AND
         the surviving phrases together to count how selective the exact
         conjunction is.
      5. For constraints that did NOT match verbatim, bucket the cause
         (case, material wording, color tag, truncation, other) for a few
         printed examples.

    Side effects: prints a human-readable summary to stdout. Returns None.
    """
    samples = load_jsonl(PUBLIC)
    _, _, products = catalog_index(CATALOG)

    phrase_sets: dict[str, set[str]] = {}
    for asin, product in products.items():
        # Merge feature and detail fields, then dedupe via a set of cleaned phrases.
        candidates = [*flatten_values(product.get("features")), *flatten_values(product.get("details"))]
        phrase_sets[asin] = {clean_constraint(item) for item in candidates if clean_constraint(item)}

    # inverted index: phrase -> how many times each product contains it
    inverted: dict[str, Counter[str]] = {}
    for asin, phrases in phrase_sets.items():
        for phrase in phrases:
            # setdefault creates the Counter lazily; counts keep ties/duplicates.
            inverted.setdefault(phrase, Counter())[asin] += 1

    hit_selectivity: list[int] = []
    missing_causes: Counter[str] = Counter()
    cases: list[tuple[str, str, str]] = []
    for sample in samples:
        target = str(sample["ground_truth"]["parent_asin"])
        card = intent_card(products[target])
        constraints = [*card["hard_constraints"], *card["soft_preferences"]]
        # Keep only constraints that exist verbatim in the target's own phrases.
        target_exact = [value for value in constraints if value in phrase_sets[target]]
        # conjunction over products containing ALL target-exact constraints
        if target_exact:
            # Start from the first phrase's posting list, then intersect the rest.
            matching = set(inverted[target_exact[0]].keys())
            for value in target_exact[1:]:
                matching &= set(inverted[value].keys())
            hit_selectivity.append(len(matching))
            if len(matching) <= 10:
                pass  # perfect conjunction — already narrow enough to score the target
        for value in constraints:
            if value not in phrase_sets[target]:
                # Diagnose WHY an exact match failed, to guide normalization.
                lowered = value.lower()
                target_lower = {p.lower() for p in phrase_sets[target]}
                if lowered in target_lower:
                    # Only case differs — a lowercased index would have matched.
                    missing_causes["case_mismatch"] += 1
                elif re.match(r"^(cotton|polyester|nylon|leather|wool|spandex|silk|rayon|fabric)$", lowered):
                    # A bare material word is not in the phrase set verbatim.
                    missing_causes["material_word"] += 1
                elif lowered.startswith("color:"):
                    # "color:"-prefixed tags are stored differently in the catalog.
                    missing_causes["color_tag"] += 1
                elif any(lowered.startswith(p[:60].lower()) and len(p) > 180 for p in target_lower):
                    # The phrase likely got cut by the 180-char truncation.
                    missing_causes["truncation"] += 1
                else:
                    # Unclassified miss — keep a sample for manual inspection.
                    missing_causes["other"] += 1
                    cases.append((target, value, sorted(phrase_sets[target])[:3]))

    sel = sorted(hit_selectivity)
    print(f"samples with >=1 exact constraint: {len(sel)}/200")
    if sel:
        # Percentiles are integer-indexed into the sorted list; median uses n//2.
        print("conjunction selectivity: median={} p25={} p75={} unique(=1)={}/{} "
              "<=10 candidates={}".format(
                  sel[len(sel) // 2], sel[len(sel) // 4], sel[3 * len(sel) // 4],
                  sum(1 for s in sel if s == 1), len(sel), sum(1 for s in sel if s <= 10)))
        print("distribution:", dict(Counter(sel).most_common(12)))
    print("non-exact constraint causes:", dict(missing_causes.most_common()))
    print("\nsample mismatches:")
    # Show only the first few unclassified cases to keep output readable.
    for target, value, phrases in cases[:5]:
        print(f"  target={target} constraint={value!r}")
        print(f"    sample target phrases: {phrases}")


if __name__ == "__main__":
    main()
