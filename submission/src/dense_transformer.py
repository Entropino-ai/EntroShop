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

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class TransformerDense:
    def __init__(
        self,
        products: dict[str, dict],
        texts: dict[str, str],
        cache_dir: str | Path = "data/models/hf",
        cache_path: str | Path = "data/models/minilm_embeddings.npz",
    ) -> None:
        import numpy as np  # noqa: F401 (checked below)
        import torch
        from transformers import AutoModel, AutoTokenizer

        self.torch = torch
        torch.set_num_threads(max(4, torch.get_num_threads() // 2))
        self.cache_dir = Path(cache_dir)
        self.cache_path = Path(cache_path)
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, cache_dir=str(self.cache_dir))
        self.model = AutoModel.from_pretrained(MODEL_NAME, cache_dir=str(self.cache_dir))
        self.model.eval()
        self.asins = list(products)
        self._row = {asin: index for index, asin in enumerate(self.asins)}
        self._embeddings = self._load_or_build(products, texts)

    # ------------------------------------------------------------- encoding
    def _mean_pool(self, hidden, mask) -> "object":
        expanded = mask.unsqueeze(-1).expand(hidden.size()).float()
        return (hidden * expanded).sum(1) / expanded.sum(1).clamp(min=1e-9)

    def encode(self, texts: list[str], batch_size: int = 128) -> "object":
        import torch

        vectors = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            tokens = self.tokenizer(
                batch, padding=True, truncation=True, max_length=96, return_tensors="pt"
            )
            with torch.no_grad():
                hidden = self.model(**tokens).last_hidden_state
            pooled = self._mean_pool(hidden, tokens["attention_mask"])
            vectors.append(pooled / pooled.norm(dim=1, keepdim=True).clamp(min=1e-9))
        return torch.cat(vectors, dim=0)

    def _load_or_build(self, products: dict[str, dict], texts: dict[str, str]) -> "object":
        import numpy as np
        import torch

        asin_file = Path(str(self.cache_path) + ".asins.json")
        if self.cache_path.exists() and asin_file.exists():
            stored = json.loads(asin_file.read_text())
            if stored == self.asins:
                print(f"[dense] loading cached MiniLM embeddings ({len(self.asins)} docs)", flush=True)
                return torch.from_numpy(np.load(self.cache_path)["emb"])

        print(f"[dense] encoding {len(self.asins)} catalog docs with MiniLM (one-time)...", flush=True)
        started = time.time()
        embeddings = []
        chunk = 1024
        for start in range(0, len(self.asins), chunk):
            batch_asins = self.asins[start:start + chunk]
            embeddings.append(self.encode([texts[asin] for asin in batch_asins]))
            elapsed = time.time() - started
            done = min(start + chunk, len(self.asins))
            print(f"[dense]   {done}/{len(self.asins)} docs ({elapsed:.0f}s)", flush=True)
        matrix = torch.cat(embeddings, dim=0)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(self.cache_path, emb=matrix.numpy())
        asin_file.write_text(json.dumps(self.asins))
        print(f"[dense] embeddings cached at {self.cache_path} ({time.time() - started:.0f}s)", flush=True)
        return matrix

    # ------------------------------------------------------------- querying
    def query_scores(self, query_text: str, asins: list[str]) -> list[tuple[str, float]]:
        """Cosine similarity between the query and the given products."""
        if not asins or not query_text.strip():
            return [(asin, 0.0) for asin in asins]
        query_vec = self.encode([query_text])[0]
        rows = [self._row[asin] for asin in asins if asin in self._row]
        if not rows:
            return [(asin, 0.0) for asin in asins]
        sims = query_vec @ self._embeddings[rows].T
        row_sim = {row: float(sim) for row, sim in zip(rows, sims.tolist())}
        return [(asin, row_sim.get(self._row[asin], 0.0)) for asin in asins]
