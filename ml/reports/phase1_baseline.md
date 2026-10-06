# Phase 1 baseline results (M0 and M1)

_Generated 2026-10-06 08:51 UTC by `python -m iris_ml.run_phase1`. Aggregates only; no text from the dataset appears here._

## Read this first

- The data is the **Reddit C-SSRS** set: 500 users, **one long document per user**, labels from psychiatrists on the C-SSRS scale. It is **not chat messages**, it contains **only suicide-risk content** (nothing on everyday stress, logistics or greetings), and it has **500 people**.
- Mapping C-SSRS labels to IRIS urgency is a **clinical hypothesis not yet reviewed by a clinician**. Both mappings are reported; the conclusions should hold under both.
- Everything below uses development users only (train + val). The held-out **test users were not touched**.
- Intervals are 95% Wilson intervals. With this few High cases they are wide: **these numbers are a reference point for later models, not evidence that IRIS is safe.**

## Setup

- Dev users: 424 (test users held out: 76); split manifest sha256 `6d2df798d1c59d62...`
- Data file md5 verified against Zenodo: `be0addddd2bb64129d866ac41b625d04`
- M1: TF-IDF (1-2 grams, min_df=2, 50000 features) + logistic regression (C=1.0, balanced); 5-fold x 3 repeats, out-of-fold; temperature scaling fitted on the other folds; seed 2026
- Cost matrix (`configs/costs.yaml`): miss High = 10, false escalation Low->High = 1, human review = 1

## Urgency mapping: `conservative`

Dev class counts: low 92, medium 229, high 103 (n = 424)

| Model | High recall (95% CI) | Macro-F1 | Quadratic kappa | Mean cost / message | ECE |
| --- | --- | --- | --- | --- | --- |
| Majority class | 0.00 (0.00-0.04), 0/103 | 0.23 | 0.00 | 1.08 | n/a |
| Random (class frequencies) | 0.21 (0.15-0.30), 22/103 | 0.31 | -0.08 | 1.62 | n/a |
| M0 rules on documents | 0.12 (0.07-0.19), 12/103 | 0.35 | 0.16 | 1.71 | n/a |
| M1 TF-IDF + logistic regression (calibrated) | 0.22 (0.15-0.31), 23/103 | 0.48 | 0.34 | 1.07 | 0.187 raw / 0.021 calibrated |

M1 confusion matrix (rows = true, columns = predicted):

| true \ predicted | low | medium | high |
| --- | --- | --- | --- |
| low | 31 | 60 | 1 |
| medium | 25 | 194 | 10 |
| high | 4 | 76 | 23 |

**Human-review tradeoff** (cases below a confidence threshold go to a human who resolves them correctly):

| threshold | cases sent to a human | High cases caught | mean cost |
| --- | --- | --- | --- |
| 0.40 | 0% | 22% | 1.08 |
| 0.50 | 21% | 37% | 1.02 |
| 0.60 | 61% | 70% | 0.98 |
| 0.70 | 88% | 90% | 1.01 |
| 0.80 | 99% | 99% | 1.00 |
| 0.90 | 100% | 100% | 1.00 |

To reach High recall >= 95%, M1 would have to send **96%** of messages to a human (threshold 0.76).
(The project gate is a human-review rate of at most 30%.)

## Urgency mapping: `lenient`

Dev class counts: low 176, medium 145, high 103 (n = 424)

| Model | High recall (95% CI) | Macro-F1 | Quadratic kappa | Mean cost / message | ECE |
| --- | --- | --- | --- | --- | --- |
| Majority class | 0.00 (0.00-0.04), 0/103 | 0.20 | 0.00 | 3.46 | n/a |
| Random (class frequencies) | 0.21 (0.15-0.30), 22/103 | 0.30 | -0.08 | 2.10 | n/a |
| M0 rules on documents | 0.12 (0.07-0.19), 12/103 | 0.36 | 0.19 | 1.53 | n/a |
| M1 TF-IDF + logistic regression (calibrated) | 0.31 (0.23-0.41), 32/103 | 0.54 | 0.43 | 1.55 | 0.186 raw / 0.055 calibrated |

M1 confusion matrix (rows = true, columns = predicted):

| true \ predicted | low | medium | high |
| --- | --- | --- | --- |
| low | 140 | 31 | 5 |
| medium | 53 | 73 | 19 |
| high | 31 | 40 | 32 |

**Human-review tradeoff** (cases below a confidence threshold go to a human who resolves them correctly):

| threshold | cases sent to a human | High cases caught | mean cost |
| --- | --- | --- | --- |
| 0.40 | 8% | 39% | 1.43 |
| 0.50 | 35% | 64% | 1.22 |
| 0.60 | 62% | 81% | 1.13 |
| 0.70 | 84% | 97% | 1.00 |
| 0.80 | 96% | 100% | 0.96 |
| 0.90 | 100% | 100% | 1.00 |

To reach High recall >= 95%, M1 would have to send **81%** of messages to a human (threshold 0.68).
(The project gate is a human-review rate of at most 30%.)

## What the model relies on (primary mapping, fit on all dev users)

- **low**: if you, your, you are, yourself, you were, you do, your life, kill himself, you will, if, that you, are
- **medium**: mental, mental depression, my, me, thank you, thank, depression, myself, with, hate, therapy, me feel
- **high**: my, hospital, was, kill myself, tried to, it was, on my, ive, tried, ive been, pills, myself

## Limitations

1. **Domain gap.** Long forum histories are very different from short chat messages. M1 here says nothing about chat performance; the team-labelled gold set (and later, consented pilot data) must measure that.
2. **Narrow label space.** No everyday-stress, emotional-support or logistics examples, so intent classification cannot be learned from this data. A model trained on it would see "supportive" forum replies as the only Low class.
3. **Tiny sample.** About 100 High cases at most; intervals above are wide, and per-class numbers vary a lot between splits.
4. **Per-user labels.** A user labelled Attempt wrote many neutral sentences too; document-level labels cannot be pushed down to messages.
5. **Label mapping is unreviewed.** See the two variants above.
6. **The rule layer on documents** is not what it will do on a single message: long histories contain explicit phrases even for supportive users, so its precision here is not meaningful.

## Citation

Gaur, M., Alambo, A., Sain, J. P., Kursuncu, U., Thirunarayan, K., Kavuluru, R., Sheth, A., Welton, R., Pathak, J. (2019). *Knowledge-aware Assessment of Severity of Suicide Risk for Early Intervention.* The Web Conference (WWW). Dataset: Zenodo, DOI 10.5281/zenodo.2667859, CC-BY-4.0.

_Environment: Python 3.10.11, scikit-learn 1.7.2, numpy 2.2.6, pandas 2.3.3._
