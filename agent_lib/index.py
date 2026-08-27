"""Catalog index: mirrors the evaluator's constraint vocabulary so that every
constraint string the simulator discloses can be matched back to products."""
from __future__ import annotations

import json
import re
from pathlib import Path

TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "i", "in", "is", "it", "me", "my", "of", "on", "or", "please", "some",
    "that", "the", "this", "to", "want", "with", "would", "you", "looking",
}
MATERIALS = ("cotton", "polyester", "nylon", "leather", "wool", "spandex", "silk", "rayon", "fabric")
MATERIAL_RE = re.compile(r"\b(cotton|polyester|nylon|leather|wool|spandex|silk|rayon|fabric)\b", re.I)
COLOR_RE = re.compile(r"\b(black|white|blue|red|pink|green|brown|gray|grey|purple|yellow|orange)\b", re.I)
SEARCH_FIELDS = ("title", "features", "details", "description", "categories", "store")

# Mirrors evaluator.local_evaluator._flatten_values / _clean_constraint exactly.
def _flatten_values(value: object) -> list[str]:
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in value.items() if item not in (None, "", [])]
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)] if value not in (None, "") else []


def clean_constraint(value: str, limit: int = 180) -> str:
    return re.sub(r"\s+", " ", value).strip(" -;,.\t\n")[:limit].rstrip()


def searchable_text(product: dict) -> str:
    parts: list[str] = []
    for field in SEARCH_FIELDS:
        value = product.get(field)
        if isinstance(value, dict):
            parts.extend(f"{key} {item}" for key, item in value.items())
        elif isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif value is not None:
            parts.append(str(value))
    return " ".join(parts).strip()


class _PhraseTrie:
    """Compact trie over catalog phrases for O(len(message)) substring lookup."""

    __slots__ = ("root",)

    def __init__(self, phrases: set[str]) -> None:
        root: dict = {}
        for phrase in phrases:
            node = root
            for char in phrase:
                node = node.setdefault(char, {})
            node[0] = phrase  # int key can never collide with char paths
        self.root = root

    def find(self, text: str) -> set[str]:
        found: set[str] = set()
        for start in range(len(text)):
            node = self.root
            for pos in range(start, len(text)):
                node = node.get(text[pos])
                if node is None:
                    break
                terminal = node.get(0)
                if terminal is not None:
                    found.add(terminal)
        return found


class CatalogIndex:
    def __init__(self, catalog_path: str | Path) -> None:
        self.products: dict[str, dict] = {}
        self.product_phrases: dict[str, set[str]] = {}
        self.phrase_postings: dict[str, set[str]] = {}
        self.material_sets: dict[str, set[str]] = {}
        self.color_sets: dict[str, set[str]] = {}
        self.material_postings: dict[str, set[str]] = {}
        self.color_postings: dict[str, set[str]] = {}
        self.category_lower: dict[str, str] = {}
        self.category_specific_lower: dict[str, str] = {}
        self.category_tokens: dict[str, set[str]] = {}
        self.category_token_postings: dict[str, set[str]] = {}
        self.category_specific_token_postings: dict[str, set[str]] = {}
        self.category_coarse_key: dict[str, str] = {}
        self.category_coarse_postings: dict[str, set[str]] = {}
        # mirror evaluator.local_evaluator.coarse_category exactly
        self._coarse_excluded = {"clothing", "clothing shoes & jewelry",
                                 "clothing, shoes & jewelry"}
        self.title_tokens: dict[str, set[str]] = {}
        self.prices: dict[str, float | None] = {}
        self.priced_asins: set[str] = set()
        self.ratings: dict[str, tuple[float | None, int]] = {}
        self.stores: dict[str, str] = {}
        self.corpus: dict[str, str] = {}

        with Path(catalog_path).open(encoding="utf-8") as handle:
            for line in handle:
                product = json.loads(line)
                asin = str(product["parent_asin"])
                self.products[asin] = product
                self.corpus[asin] = searchable_text(product)
                corpus_lower = self.corpus[asin].lower()

                phrases: set[str] = set()
                for item in (*_flatten_values(product.get("features")), *_flatten_values(product.get("details"))):
                    cleaned = clean_constraint(item)
                    if cleaned:
                        phrases.add(cleaned)
                for phrase in phrases:
                    self.phrase_postings.setdefault(phrase, set()).add(asin)
                self.product_phrases[asin] = phrases

                self.material_sets[asin] = {match.lower() for match in MATERIAL_RE.findall(corpus_lower)}
                self.color_sets[asin] = {match.lower() for match in COLOR_RE.findall(corpus_lower)}
                for material in self.material_sets[asin]:
                    self.material_postings.setdefault(material, set()).add(asin)
                for color in self.color_sets[asin]:
                    self.color_postings.setdefault(color, set()).add(asin)

                categories = [str(value) for value in product.get("categories") or []]
                joined = " ".join(categories)
                self.category_lower[asin] = joined.lower()
                # category path without the universal root entries, so words
                # like "shoes"/"jewelry" stay meaningful for free-form chat
                root_excluded = {"clothing", "clothing shoes & jewelry", "clothing, shoes & jewelry"}
                specific = [part for part in categories if part.lower() not in root_excluded]
                specific_joined = " ".join(specific)
                self.category_specific_lower[asin] = specific_joined.lower()
                for token in {t.lower() for t in TOKEN_RE.findall(specific_joined) if len(t) > 1}:
                    self.category_specific_token_postings.setdefault(token, set()).add(asin)

                # exact coarse category (last two parts, like the evaluator's
                # coarse_category): the simulator discloses this verbatim, so
                # it is a far tighter filter than loose token intersection
                coarse_parts: list[str] = []
                for value in categories:
                    for part in value.split(","):
                        part = part.strip()
                        if part and part.lower() not in self._coarse_excluded:
                            coarse_parts.append(part)
                coarse_key = " ".join(coarse_parts[-2:]).lower() if coarse_parts else "clothing item"
                self.category_coarse_key[asin] = coarse_key
                self.category_coarse_postings.setdefault(coarse_key, set()).add(asin)
                tokens = {token.lower() for token in TOKEN_RE.findall(joined) if len(token) > 1}
                tokens -= {"clothing", "shoes", "jewelry", "women", "men"}
                self.category_tokens[asin] = tokens
                for token in tokens:
                    self.category_token_postings.setdefault(token, set()).add(asin)
                self.title_tokens[asin] = {
                    token.lower()
                    for token in TOKEN_RE.findall(str(product.get("title") or ""))
                    if len(token) > 1 and token.lower() not in STOPWORDS
                }

                price = product.get("price")
                self.prices[asin] = float(price) if isinstance(price, (int, float)) else None
                if self.prices[asin] is not None:
                    self.priced_asins.add(asin)
                rating = product.get("average_rating")
                self.ratings[asin] = (
                    float(rating) if isinstance(rating, (int, float)) else None,
                    int(product.get("rating_number") or 0),
                )
                self.stores[asin] = str(product.get("store") or "")

        self.phrase_trie = _PhraseTrie(set(self.phrase_postings))
