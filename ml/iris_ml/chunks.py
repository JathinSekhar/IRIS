"""Chunking user documents into message-sized pieces, and detecting near-duplicate text across users.

Chunks inherit their user's label. That is a WEAK label: a user labelled Attempt wrote many neutral sentences too. It is
used for training short-input models and always evaluated back at the user level, never as if chunk labels were true.
"""
from __future__ import annotations

import hashlib
import re

import numpy as np
import pandas as pd

from .segment import windows


def build_chunks(docs: pd.DataFrame, max_chunks_per_doc: int = 40, min_chars: int = 120, max_chars: int = 600,
                 max_sentences: int = 4) -> pd.DataFrame:
    """One row per chunk: chunk_id, doc_id, text, position, plus the doc's native_label and urgency.

    A very long history is down-sampled evenly (keeping order) so that it cannot dominate training."""
    rows = []
    for _, r in docs.iterrows():
        ws = windows(r["text"], min_chars=min_chars, max_chars=max_chars, max_sentences=max_sentences)
        if not ws:                                              # very short document: keep it whole, truncated
            ws = [r["text"][:max_chars]]
        if len(ws) > max_chunks_per_doc:
            keep = np.unique(np.linspace(0, len(ws) - 1, max_chunks_per_doc).round().astype(int))
            ws = [ws[i] for i in keep]
        for pos, w in enumerate(ws):
            rows.append({"chunk_id": f"{r['id']}#{pos}", "doc_id": r["id"], "text": w, "position": pos,
                         "native_label": r["native_label"], "urgency": r["urgency"]})
    return pd.DataFrame(rows)


# --- near-duplicate detection -------------------------------------------------------------------------------------

def _shingles(text: str, k: int = 8) -> set[int]:
    words = re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split()
    if len(words) < k:
        return {int(hashlib.md5(" ".join(words).encode()).hexdigest()[:12], 16)} if words else set()
    return {int(hashlib.md5(" ".join(words[i:i + k]).encode()).hexdigest()[:12], 16) for i in range(len(words) - k + 1)}


def near_duplicate_pairs(texts: list[str], threshold: float = 0.5, k: int = 8, sketch: int = 256) -> list[tuple[int, int, float]]:
    """Pairs of documents sharing a large fraction of their word 8-grams (cross-posts, copy-pasted passages).

    Uses a min-hash sketch so it is quick enough for a few thousand documents. Returns (i, j, estimated Jaccard)."""
    sketches = []
    for t in texts:
        s = sorted(_shingles(t, k))
        sketches.append(np.array(s[:sketch], dtype=np.uint64) if s else np.array([], dtype=np.uint64))
    sets = [set(x.tolist()) for x in sketches]
    out = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if not sets[i] or not sets[j]:
                continue
            inter = len(sets[i] & sets[j])
            jac = inter / len(sets[i] | sets[j])
            if jac >= threshold:
                out.append((i, j, float(jac)))
    return out


def duplicate_groups(n: int, pairs: list[tuple[int, int, float]]) -> np.ndarray:
    """Union-find over near-duplicate pairs: a group id for every document (documents without duplicates get their own)."""
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, j, _ in pairs:
        parent[find(i)] = find(j)
    roots = {}
    return np.array([roots.setdefault(find(i), len(roots)) for i in range(n)])


def pool_scores(values: np.ndarray, doc_index: np.ndarray, n_docs: int, how: str = "mean", k: int = 3) -> np.ndarray:
    """Pool chunk-level values (n_chunks, ...) to documents. how: mean | max | topk (mean of the k highest, per column)."""
    values = np.asarray(values, dtype=float)
    out_shape = (n_docs,) + values.shape[1:]
    out = np.zeros(out_shape)
    for d in range(n_docs):
        v = values[doc_index == d]
        if len(v) == 0:
            continue
        if how == "mean":
            out[d] = v.mean(axis=0)
        elif how == "max":
            out[d] = v.max(axis=0)
        elif how == "topk":
            out[d] = np.sort(v, axis=0)[-min(k, len(v)):].mean(axis=0)
        else:
            raise ValueError(f"unknown pooling {how!r}")
    return out
