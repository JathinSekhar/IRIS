"""Proof that two machines used the same data, labels, split and folds.

The Colab run recomputes this fingerprint from the files in its bundle and refuses to train if anything differs from the local
project; the import step checks it again before accepting results. Only hashes and counts are produced, never text.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from . import ROOT


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _sha(*parts: bytes) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p)
        h.update(b"|")
    return h.hexdigest()


def fingerprint(prep) -> dict:
    """Hashes of everything an experiment depends on, for one prepared label variant (`experiments.Prepared`)."""
    from .experiments import user_splits
    folds = _sha(*[np.asarray(te, dtype=np.int64).tobytes() for _, _, _, te in user_splits(prep.y, 1)])
    return {
        "variant": prep.variant,
        "n_dev_users": int(len(prep.y)),
        "class_counts": np.bincount(prep.y, minlength=3).tolist(),
        "dev_ids_sha256": _sha(*[str(i).encode() for i in prep.dev["id"]]),
        "labels_sha256": _sha(np.asarray(prep.y, dtype=np.int64).tobytes()),
        "native_labels_sha256": _sha(np.asarray(prep.y5, dtype=np.int64).tobytes()) if prep.y5 is not None else None,
        "n_chunks": int(len(prep.chunks)),
        "chunks_sha256": _sha(*[t.encode() for t in prep.chunks["text"]]),
        "n_synthetic": int(len(prep.synth)),
        "synthetic_sha256": _sha(*[t.encode() for t in prep.synth["text"]]),
        "folds_sha256": folds,
    }


def code_sha256(ml_root: Path | None = None) -> str:
    """One hash over the model code and configs, so a result can be traced to the exact code that produced it."""
    root = Path(ml_root) if ml_root is not None else ROOT
    files = sorted(list((root / "iris_ml").rglob("*.py")) + list((root / "configs").glob("*.yaml")))
    parts = []
    for f in files:
        parts += [str(f.relative_to(root)).replace("\\", "/").encode(), f.read_bytes().replace(b"\r\n", b"\n")]
    return _sha(*parts)
