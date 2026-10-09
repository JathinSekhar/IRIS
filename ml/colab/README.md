# Fine-tuning on Google Colab (DistilRoBERTa, Phase 2)

Fine-tuning never runs on the development laptop. This folder runs the **same experiments** (`e3`, `e3s`, `e3o`, and `e3` with the
lenient label mapping) on a free Colab GPU, with the same dataset, label mapping, frozen split, repeated stratified folds,
calibration and metrics as every other Phase 2 model. The numbers it produces are the model's own out-of-fold results; the report
reads them from the same cache format as the other models.

## Steps

1. **Build the bundle** on the laptop (a few seconds, no training; output is git-ignored):

   ```bash
   python colab/build_bundle.py
   ```

   Writes `artifacts/colab/iris_colab_bundle.zip` (about 1.4 MB: code, configs, frozen split, the Reddit CSV, a manifest of data
   fingerprints). Add `--include-esconv` to also pack `ESConv.json` for the false-alarm audit (academic-research-only licence;
   audit only, never training). You can also upload it from inside the notebook instead.
2. Open `colab/IRIS_finetune_colab.ipynb` in Colab (File > Upload notebook), set **Runtime > Change runtime type > T4 GPU**, and run
   the cells top to bottom. Put `iris_colab_bundle.zip` in the root of your Drive (or upload when asked).
3. Download `iris_colab_results.zip` from the last cell. Model weights stay in your Drive folder under `models/`.
4. **Bring the results in** (verifies first, never overwrites unless `--force`):

   ```bash
   python colab/ingest_results.py path/to/iris_colab_results.zip
   python -m iris_ml.run_phase2 report
   ```

## Safety checks built in

- The run **refuses to start without a GPU**; there is no CPU fallback.
- It recomputes a fingerprint (raw CSV hash, development user ids, labels, chunk texts, synthetic set, fold assignment) and
  **refuses to train** if anything differs from the local project. The import step checks it again, and rejects any file that is not a
  registered experiment under its exact cache key or whose arrays are not valid probabilities.
- Only the 424 development users are loaded. The 76 held-out test users and the gold set are never used.

## What you get

| File | Contents |
| --- | --- |
| `phase2/<variant>_<name>_<key>.npz` | out-of-fold probabilities (raw and calibrated) for every user |
| `phase2/audit_*.npz` | final-model probabilities on ESConv + challenge messages (only if ESConv was provided) |
| `models/<variant>_<name>/` | final fine-tuned model (encoder, tokenizer, head, config, `meta.json` with temperature and settings) |
| `finetune_metrics.json`, `finetune_summary.md` | metrics computed from the predictions |
| `colab_run.json` | GPU, library versions, seeds, fingerprints, code hash, timings |

## Honest notes

- One repeat of 5-fold CV for fine-tuning (cost), unlike the three repeats of the cheap models. The report says so.
- GPU training is not bit-for-bit reproducible across hardware or library versions; expect small run-to-run differences. Versions are
  recorded in `colab_run.json`.
- The fine-tuned model is a research artefact, not a deployable safety system: message-level calibration is unverified and the labels
  are unreviewed. The Phase 2 report says what the results do and do not show.
