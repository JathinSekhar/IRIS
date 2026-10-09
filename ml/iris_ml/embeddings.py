"""Sentence embeddings with an on-disk cache, so experiments re-use work instead of re-computing it.

Models are open-licensed (checked 2026-10-06 via the Hugging Face API): all-MiniLM-L6-v2 and all-mpnet-base-v2 are Apache-2.0.
Weights are cached under `artifacts/` (git-ignored). Texts are never written to the cache, only their hashes and vectors.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np

from . import ROOT

ARTIFACTS = ROOT / "artifacts"
os.environ.setdefault("HF_HOME", str(ARTIFACTS / "hf_cache"))      # keep downloaded weights inside the git-ignored folder

MINILM = "sentence-transformers/all-MiniLM-L6-v2"
MPNET = "sentence-transformers/all-mpnet-base-v2"
_loaded: dict[str, object] = {}


def _device() -> str:
    import torch
    return "cuda" if torch.cuda.is_available() else "cpu"


def _model(name: str):
    if name not in _loaded:
        from sentence_transformers import SentenceTransformer
        _loaded[name] = SentenceTransformer(name, device=_device())
    return _loaded[name]


def _key(name: str, texts: list[str]) -> str:
    h = hashlib.sha256(name.encode())
    for t in texts:
        h.update(hashlib.sha256(t.encode()).digest())
    return h.hexdigest()[:24]


def embed(texts: list[str], name: str = MINILM, batch_size: int = 64, cache_dir: Path | None = None,
          encoder=None) -> np.ndarray:
    """L2-normalised float32 embeddings, shape (n, dim). `encoder` lets tests inject a fake model."""
    texts = [str(t) for t in texts]
    cache_dir = Path(cache_dir) if cache_dir is not None else ARTIFACTS / "emb"
    path = cache_dir / f"{name.split('/')[-1]}_{_key(name, texts)}.npy"
    if path.exists():
        return np.load(path)
    enc = encoder or _model(name)
    vecs = enc.encode(texts, batch_size=batch_size, convert_to_numpy=True, normalize_embeddings=True,
                      show_progress_bar=False).astype(np.float32)
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.save(path, vecs)
    return vecs
