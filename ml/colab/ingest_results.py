"""Bring the Colab results into the local project so `python -m iris_ml.run_phase2 report` includes them.

    python colab/ingest_results.py path/to/iris_colab_results.zip   (or the unzipped folder)

Checks before anything is copied: the run's data fingerprint equals this project's, every file is a registered experiment under its
exact cache key, arrays have the right shape and are valid probabilities. Existing files are never overwritten (use --force).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np

ML_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ML_ROOT))


class IngestError(Exception):
    pass


def check_and_collect(src: Path, expected_fp: dict[str, dict], registry: dict[tuple[str, str], str], n_users: dict[str, int]) -> list[Path]:
    """Validate a results folder and return the npz files to copy. `registry` maps (variant, name) -> spec key."""
    run = json.loads((src / "colab_run.json").read_text(encoding="utf-8"))
    for variant, fp in run["fingerprints"].items():
        if fp != expected_fp[variant]:
            raise IngestError(f"{variant}: the Colab run used different data, labels, split or folds than this project")
    keep = []
    for f in sorted((src / "phase2").glob("*.npz")):
        stem = f.stem
        audit = stem.startswith("audit_")
        variant, rest = (stem[6:] if audit else stem).split("_", 1)
        name, key = rest.rsplit("_", 1)
        if registry.get((variant, name)) != key:
            raise IngestError(f"{f.name}: not a registered experiment under its current specification (name or cache key differs)")
        z = np.load(f)
        if audit:
            p = z["probs"]
            ok = p.ndim == 2 and p.shape[1] == 3
        else:
            p = z["cal"]
            ok = p.ndim == 3 and p.shape[1] == n_users[variant] and p.shape[2] == 3 and z["raw"].shape == p.shape
        if not ok or not np.isfinite(p).all() or not np.allclose(p.sum(axis=-1), 1.0, atol=1e-3) or (p < -1e-6).any():
            raise IngestError(f"{f.name}: arrays have the wrong shape or are not valid probabilities")
        keep.append(f)
    if not keep:
        raise IngestError("no result files found")
    return keep


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="iris_colab_results.zip or the unzipped folder")
    ap.add_argument("--force", action="store_true", help="overwrite files that already exist")
    args = ap.parse_args(argv)

    from iris_ml import provenance
    from iris_ml.experiments import ART, prepare
    from iris_ml.run_phase2 import SPECS

    tmp = None
    src = Path(args.source)
    if src.suffix == ".zip":
        tmp = Path(tempfile.mkdtemp())
        zipfile.ZipFile(src).extractall(tmp)
        src = tmp
    try:
        preps = {v: prepare(v) for v in ("conservative", "lenient")}
        fps = {v: provenance.fingerprint(p) for v, p in preps.items()}
        registry = {(v, s.name): s.key() for v in preps for s in SPECS}
        files = check_and_collect(src, fps, registry, {v: len(p.y) for v, p in preps.items()})
        ART.mkdir(parents=True, exist_ok=True)
        copied = skipped = 0
        for f in files:
            dest = ART / f.name
            if dest.exists() and not args.force:
                skipped += 1
                continue
            shutil.copy(f, dest)
            copied += 1
        run = json.loads((src / "colab_run.json").read_text(encoding="utf-8"))
        shutil.copy(src / "colab_run.json", ART / "colab_run.json")
        print(f"verified against this project; copied {copied}, skipped {skipped} existing. GPU: {run['gpu']}, "
              f"torch {run['torch']}, finished {run['finished_utc']}")
    except IngestError as e:
        sys.exit(f"REFUSED: {e}")
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
