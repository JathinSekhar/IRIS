"""Build the full Phase 2 report on a Colab GPU (the laptop does no computing).

    python colab/colab_report.py --out /content/drive/MyDrive/iris_phase2_colab

Uses the cached out-of-fold results packed in the bundle (including the Colab fine-tuning results), refits the cheap models once on all
development users to score the ESConv + challenge messages, and runs `iris_ml.report2.build_report()` unchanged. The same bundle
verification as the training run applies: it stops if the data, labels, split or folds differ from the local project.

Outputs: <out>/phase2_results.md, phase2_metrics.json, audit_*.npz (message-level probabilities; no text) and iris_report_results.zip.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ML_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from colab_finetune import verify_bundle  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true", help="verify the bundle and list the cached results; build nothing")
    args = ap.parse_args(argv)
    out = Path(args.out)

    from iris_ml import system
    from iris_ml.experiments import ART
    manifest = json.loads((ML_ROOT / "colab_manifest.json").read_text(encoding="utf-8"))
    verify_bundle(manifest, ["conservative", "lenient"])
    cached = sorted(p.name for p in ART.glob("*.npz"))
    print(f"== {len(cached)} cached result files in the bundle; ESConv present: {system.ESCONV_PATH.exists()}", flush=True)
    if not system.ESCONV_PATH.exists():
        sys.exit("STOP: ESConv.json is missing, so the ordinary-chat audit cannot be built. Upload it or rebuild the bundle with --include-esconv.")
    if not any(n.startswith("conservative_e3_") for n in cached):
        sys.exit("STOP: the fine-tuning results are not in this bundle; rebuild it with --with-results after importing them.")
    if args.dry_run:
        print("== dry run OK", flush=True)
        return

    import torch
    if not torch.cuda.is_available():
        sys.exit("STOP: no GPU. Runtime > Change runtime type > T4 GPU. There is deliberately no CPU fallback.")
    print(f"== GPU: {torch.cuda.get_device_name(0)}", flush=True)
    from iris_ml.report2 import REPORTS, build_report
    from iris_ml.run_phase2 import run_experiments
    # The lenient-mapping sensitivity table needs its cheap experiments; finished ones are loaded from the cache, missing ones run here.
    run_experiments(["lenient"], None, skip_finetune=True)
    build_report()

    out.mkdir(parents=True, exist_ok=True)
    stage = out / "_report_stage"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir()
    for f in ("phase2_results.md", "phase2_metrics.json"):
        shutil.copy(REPORTS / f, stage / f)
        shutil.copy(REPORTS / f, out / f)
    for a in list(ART.glob("audit_*.npz")) + list(ART.glob("lenient_*.npz")):     # new audit caches and any newly run experiments
        shutil.copy(a, stage / a.name)
    zip_path = shutil.make_archive(str(out / "iris_report_results"), "zip", root_dir=stage)
    shutil.rmtree(stage)
    print(f"== finished. Download {zip_path}", flush=True)


if __name__ == "__main__":
    main()
