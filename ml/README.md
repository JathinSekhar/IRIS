# IRIS ML

The intent, urgency and routing models, and the data and evaluation tooling around them. Plan and decisions:
[../docs/ML_PLAN.md](../docs/ML_PLAN.md). Labelling rules: [docs/LABELING_GUIDE.md](docs/LABELING_GUIDE.md). Data
sources and terms: [docs/DATA_REGISTRY.md](docs/DATA_REGISTRY.md).

## Status

| Phase | State |
| --- | --- |
| P0 Foundations | **Done** (rules, metrics, schema, splits, guide) |
| P1 Baselines | **Done**: Reddit C-SSRS loaded under CC-BY, split frozen, M0 and M1 evaluated, calibration, model card v0, gold pool and blind batches built. See `reports/phase1_baseline.md` |
| P2 Modelling | **Done as development evidence (2026-10-09).** 21 model configurations and 4 exploratory ensembles, DistilRoBERTa fine-tuned on Colab, decision layer with fail-safe, false-alarm audit. **The 95%-at-30%-review target was not achieved; no model is detectably better than the Phase 1 baseline; false alarms on ordinary chat are high.** Design decision: rules + check-in floor, the AI only ranks the review queue, a human reviews every case. See `reports/phase2_final_summary.md` and `docs/MODEL_CARD_v1.md` |
| Waiting on people | Clinician sign-off of the labelling guide and the label mapping; ethics approval + supervisor for UMD; two annotators and a counsellor for the gold set |

## Claims policy

Nothing in this folder is evidence that IRIS is safe or accurate. **The Phase 1 baseline is not sufficient for IRIS.** Safety or
performance claims wait for: clinician sign-off of the guide and label mapping, a gold set labelled by independent human
annotators with counsellor adjudication, and one final evaluation on the frozen gold set. See `../docs/ML_PLAN.md`.

## What exists

```
iris_ml/
  schema.py       one dataset schema + validation (leakage, synthetic-in-test, label consistency)
  splits.py       deterministic, group-aware train/val/test split
  metrics.py      High-recall with CIs, F1, quadratic kappa, calibration (ECE), cost, human-review tradeoff, slices
  rules.py        M0 rule-based safety net (explicit self-harm language, obfuscation-aware)
  agreement.py    inter-annotator kappa and the adjudication queue
  calibration.py  temperature scaling, cross-fitted so reported calibration is honest
  baselines.py    M1 (TF-IDF + logistic regression), repeated stratified CV, trivial baselines
  datasets/       reddit_cssrs.py: loader, privacy masking, label mapping, frozen split manifest
  segment.py      cuts documents into message-sized windows
  gold.py         gold set workflow: sample, blind batches, agreement, adjudication, freeze
  run_phase1.py   one command that reproduces the Phase 1 report
configs/          labels.yaml, costs.yaml (the cost matrix that encodes "miss urgent >> false alarm")
tests/            121 tests, including explicit must-flag / must-not-flag phrase lists for the rules
data/splits/      frozen split manifest (hashed ids + labels; committed)
data/gold/        gold workflow files (git-ignored: they contain third-party text); GOLD_FREEZE.json (hash) is committed
data/raw/         downloaded datasets (git-ignored)
reports/          Phase 1 and Phase 2 results (aggregates only); phase2_final_summary.md is the one to read first
docs/             labelling guide, data registry, gold workflow, UMD application prep, model cards (M1 v0, system v1)
colab/            Google Colab notebooks and scripts: fine-tuning and the full report run there, never on the laptop
docs/clinical_review/   every sentence the support module can show, with a safety checklist and scenarios, for a clinician to review.
                  **AI-assisted draft, clinical review pending: nothing there is approved.** Start with CLINICAL_REVIEW_STATUS.md
```

Phase 2 modules in `iris_ml/`: `experiments.py` (one protocol for every model), `neural.py`, `embeddings.py`, `chunks.py`, `synth.py`,
`decision.py` (cost-sensitive decision layer, fail-safe, the V1 mandatory-review policy), `system.py`, `ranking.py`, `challenge.py`, `report2.py`,
`run_phase2.py`, `provenance.py`, `walkthrough.py`.

## Run

```bash
cd ml
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
python -m iris_ml.run_phase1        # reproduce the Phase 1 report (needs data/raw/reddit_cssrs, see docs/DATA_REGISTRY.md)
python -m iris_ml.gold build        # rebuild the gold pool and blind batches
```

## Rules of this folder

- The **gold test set is frozen** before any model is tuned, and is never used for training or threshold selection.
- **Synthetic data is training-only.** `schema.validate` rejects it anywhere else.
- Split by `group_id` (user or conversation), never by row.
- Report High-urgency recall **with a confidence interval**. A single number is not a result.
- The cost matrix in `configs/costs.yaml` is agreed with a clinician and frozen before final evaluation.
