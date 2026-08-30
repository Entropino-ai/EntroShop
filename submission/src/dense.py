"""Dense retrieval route: TF-IDF vector space over product text.

Complements the exact-phrase route when constraints are paraphrased, vague,
or the lexical pool is large. Fully offline (fitted on the frozen catalog at
load time) — no model downloads, no network.

Despite the "dense" name, this is a *sparse* TF-IDF bag-of-words index (a fast,
deterministic fallback that behaves like a dense semantic matcher on lexical
paraphrases), not a learned neural embedding. The index is built once over the
frozen catalog and never mutated; queries only score, never retrain.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sklearn.feature_extraction.text import TfidfVectorizer

if TYPE_CHECKING:
    import numpy as np

# Ordered product keys flattened into one searchable document by product_text().
# Order matters: title (strongest signal) first, store (weakest) last.
TEXT_FIELDS = ("title", "features", "categories", "store")


def product_text(product: dict) -> str:
    """Flatten one product's textual fields into a single whitespace-joined string.

    Normalizes heterogeneous field shapes (dict, list, scalar) into flat text so
    the TF-IDF vectorizer sees one uniform document per product. Missing fields
    (``None``) are skipped, and the final string is stripped, so a product with
    no text yields ``""`` — which the vectorizer handles as an all-zero token set.

    Returns:
        str: The concatenated searchable text (possibly empty).
    """
    parts: list[str] = []
    for field in TEXT_FIELDS:
        value = product.get(field)
        if isinstance(value, dict):
            # Map-style fields (e.g. feature->value): emit "key value" so both
            # the attribute name and its value become searchable tokens.
            parts.extend(f"{key} {item}" for key, item in value.items())
        elif isinstance(value, list):
            # List fields (e.g. categories): emit each item verbatim.
            parts.extend(str(item) for item in value)
        elif value is not None:
            # Scalar fields (e.g. title/store): emit once; None means absent.
            parts.append(str(value))
    return " ".join(parts).strip()


class DenseIndex:
    """Offline TF-IDF index over the whole catalog plus a query-side transform.

    Holds the fitted vectorizer, the sparse document matrix (one row per
    product, ordered by ``asins``), and an ASIN->row lookup so a subset of
    products can be scored against a query without re-indexing. Built once in
    ``__init__``; fully deterministic and network-free.
    """

    def __init__(self, products: dict[str, dict]) -> None:
        """Build the TF-IDF matrix by fitting on every product once at load time.

        Args:
            products: Mapping of ASIN -> product dict. Iteration order defines
                the stable row order of ``self.matrix`` and ``self.asins``.

        Side effects:
            Fits ``self.vectorizer`` on the full catalog and materializes
            ``self.matrix``; thereafter the index is immutable.
        """
        self.asins = list(products)
        # Fast ASIN -> matrix-row lookup for scoring only a candidate subset.
        self._row = {asin: index for index, asin in enumerate(self.asins)}
        # One flattened document per product, aligned with self.asins order.
        texts = [product_text(products[asin]) for asin in self.asins]
        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            token_pattern=r"[a-z0-9]{2,}",  # 2+ alnum tokens; drops noise/singles
            sublinear_tf=True,  # log(1+tf): caps repeated-term dominance
        )
        self.matrix = self.vectorizer.fit_transform(texts)

    def query_scores(self, query_text: str, asins: list[str]) -> list[tuple[str, float]]:
        """Score a query against the given candidate products via cosine similarity.

        Returns one ``(asin, score)`` tuple per input ASIN, preserving input
        order. Scores come from the dot product of the L2-normalized TF-IDF
        query vector and product vectors, i.e. cosine similarity. A blank query
        or a fully unknown ASIN list yields all-zero scores, so callers can
        always downstream-rank the list without special-casing.

        Args:
            query_text: Free-text query (any language; tokenizer keeps alnum).
            asins: Candidate products to score, in the caller's preferred order.

        Returns:
            list[tuple[str, float]]: ``(asin, cosine_similarity)`` for every
            input ASIN, in the same order as ``asins``.
        """
        import numpy as np

        # Degenerate inputs: no candidates or an empty query -> uniform zeros.
        if not asins or not query_text.strip():
            return [(asin, 0.0) for asin in asins]
        query_vec = self.vectorizer.transform([query_text])
        # Restrict to known rows; unknown ASINs fall through to the 0.0 default.
        rows = [self._row[asin] for asin in asins if asin in self._row]
        if not rows:
            return [(asin, 0.0) for asin in asins]
        # Sparse dot product over only the candidate rows, densified once for
        # numpy indexing; [0] unwraps the single query's 1xN result.
        sims = np.asarray(query_vec.dot(self.matrix[rows].T).toarray())[0]
        row_sim = {row: float(sim) for row, sim in zip(rows, sims)}
        # Rebuild in input order; missing rows (unknown ASINs) default to 0.0.
        return [(asin, row_sim.get(self._row[asin], 0.0)) for asin in asins]
