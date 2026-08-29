"""Dense retrieval route: TF-IDF vector space over product text.

Complements the exact-phrase route when constraints are paraphrased, vague,
or the lexical pool is large. Fully offline (fitted on the frozen catalog at
load time) — no model downloads, no network.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sklearn.feature_extraction.text import TfidfVectorizer

if TYPE_CHECKING:
    import numpy as np

TEXT_FIELDS = ("title", "features", "categories", "store")


def product_text(product: dict) -> str:
    parts: list[str] = []
    for field in TEXT_FIELDS:
        value = product.get(field)
        if isinstance(value, dict):
            parts.extend(f"{key} {item}" for key, item in value.items())
        elif isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif value is not None:
            parts.append(str(value))
    return " ".join(parts).strip()


class DenseIndex:
    """TF-IDF matrix over the catalog plus query-side transform."""

    def __init__(self, products: dict[str, dict]) -> None:
        self.asins = list(products)
        self._row = {asin: index for index, asin in enumerate(self.asins)}
        texts = [product_text(products[asin]) for asin in self.asins]
        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            token_pattern=r"[a-z0-9]{2,}",
            sublinear_tf=True,
        )
        self.matrix = self.vectorizer.fit_transform(texts)

    def query_scores(self, query_text: str, asins: list[str]) -> list[tuple[str, float]]:
        """Cosine similarity between the query and the given products."""
        import numpy as np

        if not asins or not query_text.strip():
            return [(asin, 0.0) for asin in asins]
        query_vec = self.vectorizer.transform([query_text])
        rows = [self._row[asin] for asin in asins if asin in self._row]
        if not rows:
            return [(asin, 0.0) for asin in asins]
        sims = np.asarray(query_vec.dot(self.matrix[rows].T).toarray())[0]
        row_sim = {row: float(sim) for row, sim in zip(rows, sims)}
        return [(asin, row_sim.get(self._row[asin], 0.0)) for asin in asins]
