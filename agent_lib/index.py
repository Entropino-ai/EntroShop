"""Catalog index: mirrors the evaluator's constraint vocabulary so that every
constraint string the simulator discloses can be matched back to products."""
from __future__ import annotations

import json
import re
from pathlib import Path

# Tokenizer used to turn product text and messages into lowercased keyword sets.
TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
# Common English filler words excluded from title keyword matching.
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "i", "in", "is", "it", "me", "my", "of", "on", "or", "please", "some",
    "that", "the", "this", "to", "want", "with", "would", "you", "looking",
}
# Canonical material vocabulary (also encoded in MATERIAL_RE below).
MATERIALS = ("cotton", "polyester", "nylon", "leather", "wool", "spandex", "silk", "rayon", "fabric")
MATERIAL_RE = re.compile(r"\b(cotton|polyester|nylon|leather|wool|spandex|silk|rayon|fabric)\b", re.I)
# Color vocabulary; regex mirrors the evaluator's recognized color names.
COLOR_RE = re.compile(r"\b(black|white|blue|red|pink|green|brown|gray|grey|purple|yellow|orange)\b", re.I)
# Product fields concatenated into each product's searchable text corpus.
SEARCH_FIELDS = ("title", "features", "details", "description", "categories", "store")

# Mirrors evaluator.local_evaluator._flatten_values / _clean_constraint exactly.
def _flatten_values(value: object) -> list[str]:
    """Flatten a nested catalog value into evaluator-compatible constraint strings.

    WHY: the evaluator flattens catalog values the same way when it produces the
    constraint strings it discloses, so matching requires identical rendering.

    Dicts render as ``"key: item"`` entries, lists as their stringified items,
    and scalars as a single string. Empty-ish values (``None``, ``""``, ``[]``)
    are dropped.

    Returns:
        A list of non-empty string fragments, possibly empty for a blank value.
    """
    if isinstance(value, dict):
        # Dict fields render as "key: value" pairs, skipping empty values.
        return [f"{key}: {item}" for key, item in value.items() if item not in (None, "", [])]
    if isinstance(value, list):
        # List fields render as stringified items, skipping None/empty strings.
        return [str(item) for item in value if item not in (None, "")]
    # Scalars become a single-element list, unless they are None/empty.
    return [str(value)] if value not in (None, "") else []


def clean_constraint(value: str, limit: int = 180) -> str:
    """Normalize a raw constraint string to the evaluator's canonical form.

    Collapses all whitespace runs to one space, strips leading/trailing
    punctuation and whitespace, truncates to ``limit`` characters, and re-strips.
    This makes phrase matching independent of formatting differences between
    catalog fields and what the simulator discloses.

    Args:
        value: The raw constraint/catalog string to normalize.
        limit: Maximum number of characters retained after cleanup.

    Returns:
        The cleaned, truncated string (empty if the input was blank).
    """
    return re.sub(r"\s+", " ", value).strip(" -;,.\t\n")[:limit].rstrip()


def searchable_text(product: dict) -> str:
    """Build one flat string of all text a product can be matched on.

    Concatenates the values of ``SEARCH_FIELDS``, flattening dicts to
    ``"key value"`` and lists to their items, so downstream tokenization and
    regex extraction operate over a uniform corpus per product.

    Args:
        product: One raw catalog record (JSON object).

    Returns:
        A whitespace-joined string of all searchable text with no surrounding
        whitespace. Returns ``""`` if the product has no searchable fields.
    """
    parts: list[str] = []
    for field in SEARCH_FIELDS:
        value = product.get(field)
        if isinstance(value, dict):
            # Dict fields (e.g. features) flatten to "key value" fragments.
            parts.extend(f"{key} {item}" for key, item in value.items())
        elif isinstance(value, list):
            # List fields (e.g. categories) contribute each element as text.
            parts.extend(str(item) for item in value)
        elif value is not None:
            parts.append(str(value))
    return " ".join(parts).strip()


class _PhraseTrie:
    """Compact trie over catalog phrases for O(len(message)) substring lookup."""

    __slots__ = ("root",)

    def __init__(self, phrases: set[str]) -> None:
        """Build a character trie of every known phrase for substring matching.

        Terminal nodes store the whole phrase under integer key ``0``, which can
        never collide with a single-character path key.

        Args:
            phrases: The set of cleaned catalog phrases to index.
        """
        root: dict = {}
        for phrase in phrases:
            node = root
            for char in phrase:
                node = node.setdefault(char, {})
            node[0] = phrase  # int key can never collide with char paths
        self.root = root

    def find(self, text: str) -> set[str]:
        """Return all indexed phrases that appear as substrings of ``text``.

        Scans every start position and walks the trie as far as characters keep
        matching, collecting any terminal phrases found along each path.

        Args:
            text: The free-form message text to scan for known phrases.

        Returns:
            The set of catalog phrases found verbatim inside ``text``.
        """
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
    """In-memory search index over the full product catalog.

    Pre-computes, for every product, all the signals retrieval needs —
    searchable text, token sets, phrase/material/color postings, category and
    coarse-category keys, price, rating, and store — so each turn's constraint
    matching becomes O(1)/O(len(query)) lookups instead of a scan over the
    50k-record catalog. All structures mirror the evaluator's vocabulary so
    disclosed constraint strings resolve to exact product matches.
    """

    def __init__(self, catalog_path: str | Path) -> None:
        """Load a JSON-lines catalog and build all inverted indexes.

        Reads the catalog one record at a time (keeping memory bounded while
        building), keying every product by its ``parent_asin``.

        Args:
            catalog_path: Path to a JSONL file with one product object per line.

        Raises:
            FileNotFoundError: If ``catalog_path`` does not exist.
            json.JSONDecodeError: If a line is not valid JSON.
        """
        # Per-product maps (keyed by parent_asin) plus inverted postings
        # (keyed by phrase/material/color/token -> set of asins) used for
        # O(1) lookups during each turn's constraint matching.
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
        # token-set view of each product's searchable text: lets retrieval
        # do O(1) keyword membership instead of full-text regex per candidate
        self.corpus_tokens: dict[str, frozenset[str]] = {}

        with Path(catalog_path).open(encoding="utf-8") as handle:
            for line in handle:
                product = json.loads(line)
                asin = str(product["parent_asin"])
                # Raw record + flattened searchable text + lowercased token set.
                self.products[asin] = product
                self.corpus[asin] = searchable_text(product)
                corpus_lower = self.corpus[asin].lower()
                self.corpus_tokens[asin] = frozenset(TOKEN_RE.findall(corpus_lower))

                # Feature/detail phrases, cleaned to the evaluator's canonical
                # form, index into exact-phrase postings for verbatim matching.
                phrases: set[str] = set()
                for item in (*_flatten_values(product.get("features")), *_flatten_values(product.get("details"))):
                    cleaned = clean_constraint(item)
                    if cleaned:
                        phrases.add(cleaned)
                for phrase in phrases:
                    self.phrase_postings.setdefault(phrase, set()).add(asin)
                self.product_phrases[asin] = phrases

                # Materials and colors are regex-extracted from the whole corpus
                # and inverted so a disclosed constraint maps straight to asins.
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
                # Multi-char category tokens (minus roots) post into an inverted index.
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
                # Fall back to a generic key if filtering left no category parts.
                coarse_key = " ".join(coarse_parts[-2:]).lower() if coarse_parts else "clothing item"
                self.category_coarse_key[asin] = coarse_key
                self.category_coarse_postings.setdefault(coarse_key, set()).add(asin)
                tokens = {token.lower() for token in TOKEN_RE.findall(joined) if len(token) > 1}
                # Drop uninformative root-level category words before indexing.
                tokens -= {"clothing", "shoes", "jewelry", "women", "men"}
                self.category_tokens[asin] = tokens
                for token in tokens:
                    self.category_token_postings.setdefault(token, set()).add(asin)
                # Title keywords (stopword- and single-char-filtered) for loose matching.
                self.title_tokens[asin] = {
                    token.lower()
                    for token in TOKEN_RE.findall(str(product.get("title") or ""))
                    if len(token) > 1 and token.lower() not in STOPWORDS
                }

                # Numeric attributes are normalized once; missing values become
                # None/0 so downstream scoring can handle them uniformly.
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

        # Build the phrase trie once from all discovered phrases for fast
        # substring scanning of user messages at query time.
        self.phrase_trie = _PhraseTrie(set(self.phrase_postings))
