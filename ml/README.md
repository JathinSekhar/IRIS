# IRIS ML

The intent, urgency and routing models, and the data and evaluation tooling around them. Plan and decisions:
[../docs/ML_PLAN.md](../docs/ML_PLAN.md). Labelling rules: [docs/LABELING_GUIDE.md](docs/LABELING_GUIDE.md). Data
sources and terms: [docs/DATA_REGISTRY.md](docs/DATA_REGISTRY.md).

## Status

| Phase | State |
| --- | --- |
| P0 Foundations | **Done** (rules, metrics, schema, splits, guide) |
| P1 Baselines | **Done**: Reddit C-SSRS loaded under CC-BY, split frozen, M0 and M1 evaluated, calibration, model card v0, gold pool and blind batches built. See `reports/phase1_baseline.md` |
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
reports/          Phase 1 results (aggregates only)
docs/             labelling guide, data registry, gold workflow, UMD application prep, model card
```

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
