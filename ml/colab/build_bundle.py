"""Pack everything the Colab run needs into one zip: `ml/artifacts/colab/iris_colab_bundle.zip` (git-ignored).

    python colab/build_bundle.py [--include-esconv]

Contents: the model code, configs, the frozen split manifest, the Reddit C-SSRS CSV (CC-BY-4.0, needed for training), the Colab
script, and `colab_manifest.json` with the fingerprints that the Colab run must reproduce. NOT included: the held-out test users'
labels are in the CSV like any other row but are excluded by the loader (as locally); the gold set, tests, cached artifacts and the
demo pages are never packed. ESConv (academic-research-only licence) is packed only with --include-esconv, and is used only for the
false-alarm audit, never for training.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ML_ROOT))

SKIP_PARTS = {"__pycache__"}
REQUIREMENTS = """# Colab already has torch, transformers, numpy, pandas and scikit-learn; these are the extras (versions are recorded in colab_run.json)
sentence-transformers
PyYAML
joblib
"""


def package_files(root: Path) -> list[Path]:
    files = [p for p in (root / "iris_ml").rglob("*.py") if not SKIP_PARTS & set(p.parts)]
    files += list((root / "configs").glob("*.yaml"))
    files += list((root / "data" / "splits").glob("*.csv"))
    files.append(root / "colab" / "colab_finetune.py")
    return sorted(files)


def write_bundle(root: Path, dest: Path, manifest: dict, include_esconv: bool, include_results: bool = False) -> Path:
    """Write the zip. Everything lives under `ml/` so iris_ml.ROOT resolves exactly as it does locally.

    `include_results` adds the cached out-of-fold results (probabilities only, no text) so the Colab run can build the full report."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    extra = [(root / "data" / "raw" / "reddit_cssrs" / "500_Reddit_users_posts_labels.csv")]
    if include_esconv:
        extra.append(root / "data" / "raw" / "esconv" / "ESConv.json")
    if include_results:
        extra += sorted((root / "artifacts" / "phase2").glob("*.npz"))
        extra.append(root / "colab" / "colab_report.py")
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in package_files(root) + extra:
            z.write(p, "ml/" + p.relative_to(root).as_posix())
        z.writestr("ml/requirements-colab.txt", REQUIREMENTS)
        z.writestr("ml/colab_manifest.json", json.dumps(manifest, indent=1))
    return dest


def make_manifest(root: Path, include_esconv: bool) -> dict:
    from iris_ml import provenance
    from iris_ml.datasets import reddit_cssrs as rc
    from iris_ml.experiments import prepare
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=root, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=root, check=True).stdout.strip())
    except Exception:
        commit, dirty = None, None
    return {
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": commit, "git_working_tree_dirty": dirty,
        "code_sha256": provenance.code_sha256(root),
        "data": {"reddit_csv_sha256": provenance.sha256_file(rc.RAW_PATH), "esconv_included": include_esconv,
                 "split_manifest_sha256": provenance.sha256_file(rc.MANIFEST_PATH)},
        "fingerprints": {v: provenance.fingerprint(prepare(v)) for v in ("conservative", "lenient")},
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--include-esconv", action="store_true", help="also pack ESConv.json for the false-alarm audit")
    ap.add_argument("--with-results", action="store_true",
                    help="also pack the cached Phase 2 results and the report script, so Colab can build the full report")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    default = "iris_colab_report_bundle.zip" if args.with_results else "iris_colab_bundle.zip"
    out = args.out or str(ML_ROOT / "artifacts" / "colab" / default)
    manifest = make_manifest(ML_ROOT, args.include_esconv)
    dest = write_bundle(ML_ROOT, Path(out), manifest, args.include_esconv, args.with_results)
    print(f"wrote {dest} ({dest.stat().st_size / 1e6:.1f} MB); ESConv included: {args.include_esconv}; "
          f"git dirty: {manifest['git_working_tree_dirty']}; code {manifest['code_sha256'][:12]}")


if __name__ == "__main__":
    main()
