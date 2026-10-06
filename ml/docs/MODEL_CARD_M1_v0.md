# Model card: M1 v0 (TF-IDF + logistic regression urgency baseline)

**Status: research baseline. Not for use with real people. Not safe to deploy.**

## What it is
A reference model that predicts IRIS urgency (low / medium / high) from a long text. It exists so later models have something
to beat and so the evaluation code is exercised, nothing more.

- Features: TF-IDF, 1-2 grams, min_df 2, up to 50,000 terms. Classifier: multinomial logistic regression, balanced class weights.
- Calibration: temperature scaling (T averaged across folds, reported in the metrics file).
- Code: `iris_ml/baselines.py`; reproduce with `python -m iris_ml.run_phase1`; results in `reports/phase1_baseline.md`.

## Data
Reddit C-SSRS Suicide Dataset (Gaur et al., 2019; CC-BY-4.0; DOI 10.5281/zenodo.2667859): 500 users, one long document each,
labelled by four psychiatrists as Supportive, Indicator, Ideation, Behavior or Attempt. Trained and evaluated only on the
424 development users; the 76 held-out users are untouched.

## Results (development users, out-of-fold, 95% intervals)
| Mapping | High recall | Macro-F1 | Quadratic kappa | Calibration error |
| --- | --- | --- | --- | --- |
| conservative (Indicator = medium) | 0.22 (0.15-0.31) | 0.48 | 0.34 | 0.187 raw, 0.021 calibrated |
| lenient (Indicator = low) | 0.31 (0.23-0.41) | 0.54 | 0.43 | 0.186 raw, 0.055 calibrated |

For reference, random guessing at the class frequencies gets High recall 0.21 and kappa -0.08.
**Reaching 95% High recall would need a human to review 81% to 96% of cases**, far above the 30% project gate.

## What it does and does not do
- Separates low from medium urgency better than chance; calibration by temperature scaling works (large reduction in error).
- **Cannot separate High from Medium**: most true High users are predicted Medium. It must not be used to decide that anyone is safe.
- Says **nothing** about chat messages, everyday stress, emotional-support requests, logistics, other languages, or other
  platforms. The training data contains only suicide-forum content.

## Known problems and open questions
1. **Label mapping is a clinical hypothesis.** C-SSRS "Behavior" and "Attempt" are lifetime or recent history, while our own
   labelling guide reserves High for imminent or recent danger. Mapping them to High may overstate urgency in the data.
   A clinician must decide the mapping; the result is reported under two variants meanwhile.
2. Per-user labels on long histories cannot be pushed down to single messages.
3. 424 users, about 100 High: wide intervals, results will move a lot with a different split.
4. No test on the held-out users yet, by design (frozen until final evaluation).

## Intended use
Reference point for development inside this repository. Any use with real users requires: a clinician-approved labelling
guide, evaluation on the frozen gold set, the rule layer and baseline floor in front of it, human review of High and
uncertain cases, and ethics approval.

## Ethics
Third-party text is used under its licence for research, stays out of git, and is never quoted in reports. User ids are
hashed on load, links and mentions are masked.
