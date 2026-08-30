"""Mini-transformer dense route: sentence-transformers/all-MiniLM-L6-v2.

A 22M-parameter distilled BERT ("MiniLM") encodes catalog texts into 384-dim
vectors; queries are encoded at runtime and ranked by cosine similarity.
Falls back gracefully (the caller should keep the TF-IDF route) when
torch/transformers or the model cache is unavailable.

Requires the vendored transformers install (see README):
    pip install --target vendor transformers
and PYTHONPATH=vendor when running.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

# HuggingFace identifier for the distilled MiniLM sentence encoder used here.
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class TransformerDense:
    def __init__(
        self,
        products: dict[str, dict],
        texts: dict[str, str],
        cache_dir: str | Path = "data/models/hf",
        cache_path: str | Path = "data/models/minilm_embeddings.npz",
    ) -> None:
        """Build the dense retriever: load the MiniLM model/tokenizer and the
        catalog embedding matrix (rebuilt from scratch or restored from cache).

        Args:
            products: Mapping of product ID (ASIN) -> product record dict.
            texts: Mapping of product ID -> searchable text used for encoding.
            cache_dir: Where HuggingFace downloads/serves the model weights.
            cache_path: Where the precomputed document-embedding matrix is
                stored, with a sibling ``.asins.json`` recording row order.

        Side effects:
            * Initializes torch and caps its thread count (MiniLM batches are
              small; extra threads add contention without more throughput).
            * Writes the NPZ cache + ASIN manifest on the first build.
            * Prints progress to stdout (flush=True so logs survive buffering).

        Raises:
            ImportError if torch/transformers are unavailable, or OSError if the
            model weights cannot be fetched. The caller must fall back to the
            TF-IDF route in either case.
        """
        import numpy as np  # noqa: F401 (checked below)
        import torch
        from transformers import AutoModel, AutoTokenizer

        self.torch = torch
        # Halve the thread pool so dense encoding doesn't starve the TF-IDF
        # route or other in-process work when both run concurrently.
        torch.set_num_threads(max(4, torch.get_num_threads() // 2))
        self.cache_dir = Path(cache_dir)
        self.cache_path = Path(cache_path)
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, cache_dir=str(self.cache_dir))
        self.model = AutoModel.from_pretrained(MODEL_NAME, cache_dir=str(self.cache_dir))
        # Inference only: disables dropout and keeps BN/weight stats frozen.
        self.model.eval()
        self.asins = list(products)
        # Row-index lookup: each ASIN -> its fixed row in the embedding matrix,
        # so query scoring can gather rows without repeated list scans.
        self._row = {asin: index for index, asin in enumerate(self.asins)}
        self._embeddings = self._load_or_build(products, texts)

    # ------------------------------------------------------------- encoding
    def _mean_pool(self, hidden, mask) -> "object":
        """Average token hidden states over real tokens only (mean pooling).

        The attention mask zeroes out padding tokens, so this collapses each
        sequence into a single document-level vector. A tiny epsilon avoids
        division-by-zero for a fully-masked (all-pad) sequence.

        Args:
            hidden: Last hidden state, shape (batch, seq_len, hidden_dim).
            mask: Attention mask, shape (batch, seq_len), 1 = real token.

        Returns:
            Mean-pooled tensor of shape (batch, hidden_dim).
        """
        # Broadcast the (batch, seq) mask to (batch, seq, hidden) so padding
        # positions contribute zero before summing.
        expanded = mask.unsqueeze(-1).expand(hidden.size()).float()
        # Sum real-token states, then divide by the real-token count per row.
        return (hidden * expanded).sum(1) / expanded.sum(1).clamp(min=1e-9)

    def encode(self, texts: list[str], batch_size: int = 128) -> "object":
        """Encode a list of texts into L2-normalized 384-dim vectors.

        Batching bounds peak memory while amortizing tokenizer/model overhead.
        Output rows are L2-normalized so cosine similarity collapses to a dot
        product (see ``query_scores``).

        Args:
            texts: Raw strings to encode.
            batch_size: Number of texts per forward pass.

        Returns:
            A torch tensor of shape (len(texts), 384) with unit-norm rows, on
            the model's default device and dtype.
        """
        import torch

        vectors = []
        # Slice the input into fixed-size batches to bound peak memory and keep
        # tokenizer padding overhead low.
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            # Pad/truncate to 96 tokens: enough for short catalog descriptions,
            # while longer text rarely adds retrieval signal.
            tokens = self.tokenizer(
                batch, padding=True, truncation=True, max_length=96, return_tensors="pt"
            )
            # Disable autograd: inference only, saving memory and time.
            with torch.no_grad():
                hidden = self.model(**tokens).last_hidden_state
            pooled = self._mean_pool(hidden, tokens["attention_mask"])
            # L2-normalize each row; clamp avoids NaN on zero-length vectors.
            vectors.append(pooled / pooled.norm(dim=1, keepdim=True).clamp(min=1e-9))
        # Stack all batches back into a single (N, D) matrix in input order.
        return torch.cat(vectors, dim=0)

    def _load_or_build(self, products: dict[str, dict], texts: dict[str, str]) -> "object":
        """Return the catalog embedding matrix, reusing a disk cache when valid.

        The cache is valid only if the stored ASIN list exactly matches the
        current ``self.asins``; any ordering or product change forces a rebuild
        so row indices stay aligned with ``self._row``.

        Args:
            products: Mapping of ASIN -> product dict (unused here; kept for
                symmetry with the constructor contract).
            texts: Mapping of ASIN -> searchable text.

        Returns:
            Torch tensor of shape (num_products, 384), aligned with the order
            of ``self.asins``.

        Side effects:
            * Loads or writes ``self.cache_path`` and its sibling ASIN manifest.
            * Prints one-time progress (flush=True so logs aren't lost).
        """
        import numpy as np
        import torch

        asin_file = Path(str(self.cache_path) + ".asins.json")
        # Reuse the cache only when both files exist AND the stored ordering
        # still matches; a mismatch would silently corrupt row->product mapping.
        if self.cache_path.exists() and asin_file.exists():
            stored = json.loads(asin_file.read_text())
            if stored == self.asins:
                print(f"[dense] loading cached MiniLM embeddings ({len(self.asins)} docs)", flush=True)
                return torch.from_numpy(np.load(self.cache_path)["emb"])

        print(f"[dense] encoding {len(self.asins)} catalog docs with MiniLM (one-time)...", flush=True)
        started = time.time()
        embeddings = []
        chunk = 1024
        # Encode in large chunks so encode()'s internal batching stays efficient
        # and progress is reported per chunk rather than per tiny batch.
        for start in range(0, len(self.asins), chunk):
            batch_asins = self.asins[start:start + chunk]
            embeddings.append(self.encode([texts[asin] for asin in batch_asins]))
            elapsed = time.time() - started
            done = min(start + chunk, len(self.asins))
            print(f"[dense]   {done}/{len(self.asins)} docs ({elapsed:.0f}s)", flush=True)
        matrix = torch.cat(embeddings, dim=0)
        # Persist for next run: create the parent directory, then store the
        # matrix plus its row order as a sidecar JSON manifest.
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(self.cache_path, emb=matrix.numpy())
        asin_file.write_text(json.dumps(self.asins))
        print(f"[dense] embeddings cached at {self.cache_path} ({time.time() - started:.0f}s)", flush=True)
        return matrix

    # ------------------------------------------------------------- querying
    def query_scores(self, query_text: str, asins: list[str]) -> list[tuple[str, float]]:
        """Rank the given products by cosine similarity to the query.

        Because ``encode`` L2-normalizes vectors, cosine similarity reduces to
        a plain dot product ``query_vec @ rows.T``. Unknown ASINs and an empty/
        whitespace query fall back to a 0.0 score, which the caller treats as
        "no dense signal" and resolves via the TF-IDF route.

        Args:
            query_text: Free-text query string.
            asins: Product IDs to score, in caller-desired output order.

        Returns:
            A list of ``(asin, score)`` tuples, one per input ASIN in the same
            order; scores are Python floats in ``[-1, 1]``.
        """
        # Nothing to score: return neutral scores so downstream logic can fall
        # back to other routes without special-casing the empty query.
        if not asins or not query_text.strip():
            return [(asin, 0.0) for asin in asins]
        query_vec = self.encode([query_text])[0]
        # Map ASINs to matrix rows, skipping any unknown IDs (defensive).
        rows = [self._row[asin] for asin in asins if asin in self._row]
        if not rows:
            return [(asin, 0.0) for asin in asins]
        # Cosine == dot product because both sides are L2-normalized.
        sims = query_vec @ self._embeddings[rows].T
        # Pair each gathered row back to its score for a stable lookup below.
        row_sim = {row: float(sim) for row, sim in zip(rows, sims.tolist())}
        # Emit in the caller's ASIN order, defaulting unknown ASINs to 0.0.
        return [(asin, row_sim.get(self._row[asin], 0.0)) for asin in asins]
