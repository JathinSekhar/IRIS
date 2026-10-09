"""Phase 2 fine-tuning (DistilRoBERTa) on a Google Colab GPU.

Runs the SAME experiments as `python -m iris_ml.run_phase2 experiments` for the `finetune` family, with the same dataset, label
mapping, frozen split, repeated stratified folds, calibration and metrics. It only moves the compute to Colab. Nothing is invented:
every number in the outputs is computed from the model's own out-of-fold predictions.

    python colab/colab_finetune.py --out /content/drive/MyDrive/iris_phase2_colab [--dry-run]

Safety checks, in order:
  1. refuses to run without a CUDA GPU (there is no CPU fallback);
  2. recomputes the data fingerprint (raw file hash, development user ids, labels, chunks, synthetic set, fold assignment) and refuses
     to train if anything differs from the local project recorded in colab_manifest.json;
  3. only development users are loaded; the 76 held-out test users and the gold set are never present in the bundle.

Outputs (resumable: finished experiments are skipped when you run it again)
  <out>/phase2/<variant>_<name>_<key>.npz        out-of-fold probabilities, same format the report reads
  <out>/phase2/audit_<variant>_<name>_<key>.npz  final-model probabilities on ESConv + challenge messages (only if ESConv.json was uploaded)
  <out>/models/<variant>_<name>/                 the final fine-tuned model (encoder, tokenizer, head, config, meta)
  <out>/finetune_metrics.json, finetune_summary.md, colab_run.json, iris_colab_results.zip (everything except the model weights)
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ML_ROOT))

import numpy as np  # noqa: E402

from iris_ml import provenance  # noqa: E402
from iris_ml.experiments import SEED, fit_split, prepare, run_spec, summarise  # noqa: E402
from iris_ml.run_phase2 import LENIENT_SPECS, SPECS  # noqa: E402

FINAL_FIT = ("e3_distilroberta_ft", "e3s_distilroberta_ft_syn")      # the two fine-tuned models the report audits
FINAL_SEED = 2026                                                      # same seed as system.fit_final


def plan(variants: list[str]) -> list[tuple[str, object]]:
    """(variant, spec) for every fine-tuning experiment, exactly as run_phase2 registers them."""
    out = []
    for variant in variants:
        for spec in SPECS:
            if spec.family != "finetune":
                continue
            if variant == "lenient" and spec.name not in LENIENT_SPECS:
                continue
            out.append((variant, spec))
    return out


def verify_bundle(manifest: dict, variants: list[str]) -> dict[str, dict]:
    """Recompute fingerprints here and compare with the local project's. Returns the verified fingerprints; exits on any mismatch."""
    from iris_ml.datasets import reddit_cssrs as rc
    got = provenance.sha256_file(rc.RAW_PATH)
    if got != manifest["data"]["reddit_csv_sha256"]:
        sys.exit(f"STOP: the Reddit CSV differs from the local project (sha256 {got[:12]}... vs {manifest['data']['reddit_csv_sha256'][:12]}...).")
    out = {}
    for variant in variants:
        prep = prepare(variant)                 # also verifies the frozen split manifest and excludes the test users
        fp = provenance.fingerprint(prep)
        want = manifest["fingerprints"][variant]
        bad = {k: (fp[k], want[k]) for k in want if fp.get(k) != want[k]}
        if bad:
            sys.exit(f"STOP: {variant} does not match the local project: {sorted(bad)}")
        out[variant] = fp
        print(f"   verified {variant}: {fp['n_dev_users']} users, {fp['n_chunks']} chunks, folds {fp['folds_sha256'][:10]}", flush=True)
    return out


def _json_default(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def final_fit(spec, prep, res, out: Path, texts: list[str] | None) -> dict:
    """Fit on ALL development users (never the test users), save the model, and score the audit messages."""
    name = f"{prep.variant}_{spec.name}"
    model_dir = out / "models" / name
    audit = out / "phase2" / f"audit_{prep.variant}_{spec.name}_{spec.key()}.npz"
    if (model_dir / "ft_config.json").exists() and (audit.exists() or texts is None):
        print(f"   final model {name}: already done, skipping", flush=True)
        return json.loads((model_dir / "meta.json").read_text(encoding="utf-8"))
    t0 = time.time()
    fitted = fit_split(spec, prep, np.arange(len(prep.y)), None, seed=FINAL_SEED)
    ft = fitted.scorer
    meta = {"name": spec.name, "variant": prep.variant, "spec_key": spec.key(), "family": spec.family, "head": spec.head,
            "synthetic_in_training": spec.syn, "base_model": ft.cfg.model_name, "epochs": ft.cfg.epochs, "lr": ft.cfg.lr,
            "batch_size": ft.cfg.batch_size, "max_len": ft.cfg.max_len, "seed": FINAL_SEED, "n_train_users": int(len(prep.y)),
            "classes": ["low", "medium", "high"], "temperature": float(res.temps.mean()),
            "trained_on": "development users only (424); held-out test users and gold set never used",
            "fit_seconds": None}
    ft.save(model_dir)
    if texts is not None:
        probs = fitted.predict_texts(texts)
        np.savez(audit, probs=probs)
        meta["audit_messages"] = len(texts)
    fitted.free()
    meta["fit_seconds"] = round(time.time() - t0, 1)
    (model_dir / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"   final model {name}: saved to {model_dir} ({meta['fit_seconds']}s)", flush=True)
    return meta


def audit_texts() -> list[str] | None:
    """ESConv seeker messages + the challenge set, in the order the report expects. None if ESConv.json was not uploaded."""
    from iris_ml import system
    from iris_ml.challenge import challenge_frame
    if not system.ESCONV_PATH.exists():
        print("   ESConv.json not uploaded: the ordinary-chat workload audit for these models is skipped", flush=True)
        return None
    return system.esconv_messages(6000) + list(challenge_frame()["text"])


def summary_markdown(rows: list[dict]) -> str:
    L = ["# DistilRoBERTa fine-tuning: results computed on Colab\n",
         "Out-of-fold, development users only, same folds and metrics as every other Phase 2 model. "
         "One repeat of 5-fold CV (fine-tuning is expensive). Not a safety or performance claim.\n",
         "| Variant | Model | Synthetic | Head | AUROC | Review 30% | Macro-F1 | Kappa | ECE raw -> cal | Mean temperature | Minutes |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        m = r["repeat0"]
        L.append(f"| {r['variant']} | {r['name']} | {'yes' if r['syn'] else 'no'} | {r['head']} | {m['auroc_high']:.2f} | "
                 f"{100 * m['recall_at']['30%']:.0f}% | {m['macro_f1']:.2f} | {m['qwk']:.2f} | "
                 f"{m['ece_raw']:.3f} -> {m['ece_cal']:.3f} | {r['mean_temperature']:.2f} | {r['seconds'] / 60:.1f} |")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="output folder (use a Google Drive folder so a disconnect loses nothing)")
    ap.add_argument("--variants", nargs="+", default=["conservative", "lenient"])
    ap.add_argument("--dry-run", action="store_true", help="verify the bundle and print the plan; train nothing")
    args = ap.parse_args(argv)
    out = Path(args.out)

    manifest = json.loads((ML_ROOT / "colab_manifest.json").read_text(encoding="utf-8"))
    print(f"== IRIS Phase 2 fine-tuning on Colab (bundle built {manifest['built_utc']}, code {manifest['code_sha256'][:12]})", flush=True)
    todo = plan(args.variants)
    print("== plan:", ", ".join(f"{v}/{s.name}" for v, s in todo), flush=True)
    fps = verify_bundle(manifest, args.variants)
    if args.dry_run:
        print("== dry run OK: data, labels, split and folds match the local project. Nothing was trained.", flush=True)
        return

    import torch
    if not torch.cuda.is_available():
        sys.exit("STOP: no GPU. In Colab choose Runtime > Change runtime type > T4 GPU. There is deliberately no CPU fallback.")
    gpu = torch.cuda.get_device_name(0)
    print(f"== GPU: {gpu}", flush=True)
    (out / "phase2").mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")

    rows, finals = [], {}
    texts = audit_texts()
    for variant in args.variants:
        prep = prepare(variant)
        print(f"== variant {variant}: {len(prep.y)} users, {len(prep.chunks)} chunks, {len(prep.synth)} synthetic messages", flush=True)
        for v, spec in todo:
            if v != variant:
                continue
            t = time.time()
            res = run_spec(spec, prep, cache_dir=out / "phase2")
            print(f"-- {variant}/{spec.name}: done in {time.time() - t:.0f}s (stored {res.seconds:.0f}s)", flush=True)
            rows.append({**summarise(res, prep.y), "variant": variant, "syn": spec.syn, "head": spec.head, "spec_key": spec.key()})
            if variant == "conservative" and spec.name in FINAL_FIT:
                finals[spec.name] = final_fit(spec, prep, res, out, texts)

    (out / "finetune_metrics.json").write_text(json.dumps(rows, indent=1, default=_json_default), encoding="utf-8")
    (out / "finetune_summary.md").write_text(summary_markdown(rows), encoding="utf-8")
    import sklearn
    import transformers
    run = {"started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "gpu": gpu,
           "python": platform.python_version(), "torch": torch.__version__, "transformers": transformers.__version__,
           "scikit_learn": sklearn.__version__, "numpy": np.__version__, "seed": SEED, "final_fit_seed": FINAL_SEED,
           "experiments": [{"variant": v, "name": s.name, "spec_key": s.key(), "repeats": s.repeats} for v, s in todo],
           "final_models": finals, "esconv_audit_done": texts is not None, "fingerprints": fps,
           "code_sha256": manifest["code_sha256"], "reddit_csv_sha256": manifest["data"]["reddit_csv_sha256"],
           "bundle_built_utc": manifest["built_utc"], "git_commit": manifest.get("git_commit")}
    (out / "colab_run.json").write_text(json.dumps(run, indent=1, default=_json_default), encoding="utf-8")

    stage = out / "_results_stage"
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(out / "phase2", stage / "phase2")
    for f in ("finetune_metrics.json", "finetune_summary.md", "colab_run.json"):
        shutil.copy(out / f, stage / f)
    for d in (out / "models").glob("*"):                      # model metadata only; the weights stay in the models folder
        (stage / "models" / d.name).mkdir(parents=True, exist_ok=True)
        for f in ("meta.json", "ft_config.json"):
            if (d / f).exists():
                shutil.copy(d / f, stage / "models" / d.name / f)
    zip_path = shutil.make_archive(str(out / "iris_colab_results"), "zip", root_dir=stage)
    shutil.rmtree(stage)
    print(f"== finished. Results: {zip_path}\n== models: {out / 'models'}\n\n" + (out / "finetune_summary.md").read_text(encoding="utf-8"),
          flush=True)


if __name__ == "__main__":
    main()
