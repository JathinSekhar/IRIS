# Model card: IRIS triage system v1 (design and research models)

**Status: research. Not for use with real people. Not safe to deploy. No performance claim is made.**
Supersedes [MODEL_CARD_M1_v0.md](MODEL_CARD_M1_v0.md) as the description of the system; M1 remains the Phase 1 reference baseline.
Full evidence: [`../reports/phase2_final_summary.md`](../reports/phase2_final_summary.md) and [`../reports/phase2_results.md`](../reports/phase2_results.md).

## What the system is

```
message -> rule layer -> check-in floor -> AI ranking -> mandatory human review -> the human decides
```

| Part | Behaviour |
| --- | --- |
| Rule layer (`rules.py`) | Explicit self-harm language (intent, plan, means, timing, ideation, euphemisms, third-party risk, obfuscation) raises urgency to Review or High. Cannot be lowered by anything |
| Check-in floor | The self-harm (C-SSRS) answers from the user's check-in set a minimum urgency (none, medium, high) |
| AI ranking | A model scores each message; the score orders the human review queue. **It can raise priority. It can never clear a case or mark it Low or safe** |
| Human review | **Every** case is read by a person, who makes the final decision |
| Fail-safe | If the model is unavailable, slow or returns invalid output, the case still goes to a human; rules and the floor still apply |

Highest urgency wins: the final provisional priority is the maximum of the model, the rules and the floor. The shipped policy is `V1_POLICY`
(`mandatory_review=True`, `ml/iris_ml/decision.py`). The urgency it returns is a **provisional priority for the reviewer**, not a decision.

## Support wording (the part the person reads)

What a person sees comes from a fixed, deterministic list of 66 messages (`iris_ml/support.py`), not from a model. **All of it is an AI-assisted draft: clinical
review is pending and nothing is approved.** The full list, with each message's intended situation, safety considerations, limitations, a five-question draft
self-check, 49 safety-critical scenarios, and a checklist for a clinician, is in [`clinical_review/`](clinical_review/CLINICAL_REVIEW_STATUS.md). The scenario
table lists 3 situations the system handles worse than desired today (non-English text such as Hinglish, and two ambiguous phrases, "I can't take it anymore"
and "I'm so done with everything", that are not flagged on purpose to avoid flooding reviewers) and 11 judgement calls that need a clinician. Four other gaps
found by the first review were closed with new rule patterns and tests.

## The AI model(s)

No model has been selected as a deployable artefact, and none has been saved for deployment. Models evaluated: TF-IDF baselines, sentence
embeddings (all-MiniLM-L6-v2, all-mpnet-base-v2; Apache-2.0) with logistic regression or small heads, an attention multiple-instance model, and
DistilRoBERTa fine-tuned on a Colab GPU. The named v1 ranker is the **pre-specified ensemble** (MiniLM and MPNet embeddings + logistic regression
trained on the psychiatrists' five labels and mapped to urgency, plus chunk-level TF-IDF), chosen before any ensemble result was seen. This is a
default, not a finding: no candidate is detectably better than the Phase 1 baseline, and the choice is to be revisited on the gold set.

## Data

- **Reddit C-SSRS** (Gaur et al., 2019; CC-BY-4.0; DOI 10.5281/zenodo.2667859): 500 users, one long document each, labelled by four psychiatrists
  as Supportive, Indicator, Ideation, Behavior or Attempt. Training and evaluation use only the 424 development users; 76 users are frozen.
- **Label mapping to IRIS urgency is an unreviewed clinical hypothesis** (two variants reported).
- **Template synthetic messages** (1,084, no language-model API): training folds only, flagged. Written by the code author.
- **ESConv** (emotional-support chat): false-alarm audit only, never training. Academic research use only.
- **Challenge set** (72 hand-written items): regression and false-alarm check. Not gold, not independent.
- Third-party text stays out of git and is not quoted in reports.

## Results (development users, out-of-fold; see the report for intervals)

| | AUROC | High cases found when reading the top 30% |
| --- | --- | --- |
| Phase 1 baseline (M1) | 0.70 | 51% |
| Pre-specified ensemble | 0.72 | 50% |
| DistilRoBERTa fine-tuned (Colab) | 0.71 | 49% |
| DistilRoBERTa fine-tuned + synthetic data | 0.73 | 52% |
| Best exploratory ensemble | 0.74 | 55% |

- **The target (95% of High cases found at 30% review) was not achieved.** The gap is about 40 points.
- No model is detectably different from the baseline (differences within the 95% intervals), apart from one clear loss.
- Random reading finds 30%. These models are better than chance at ranking and far from good enough to decide anything alone.

## False alarms on ordinary chat (ESConv, 6,000 messages, evaluation policy)

| System | Sent to a human | Final: Low / Medium / High |
| --- | --- | --- |
| Phase 1 baseline (M1) | 58% | 0% / 74% / 26% |
| DistilRoBERTa fine-tuned | 91% | 0% / 9% / 91% |
| Pre-specified ensemble | 100% | 0% / 0% / 100% |
| DistilRoBERTa fine-tuned + synthetic data | 28% | 56% / 18% / 26% |

Most models treat ordinary support messages as High. The one model with a low rate learned that from template data written by the same person who wrote
the challenge set, so its improvement cannot be verified, and it missed more should-escalate items on its own. **This is why the model is not allowed to clear
cases.**

## What it does and does not do

- Does: flags explicit self-harm language; applies the check-in floor; orders the review queue; sends everything to a person.
- Does not: diagnose, decide that anyone is safe, replace a clinician, handle languages other than English, or work on text unlike its training data without re-evaluation.
- **Reviewer capacity is a hard requirement.** With mandatory review every message needs a reader; ranking only changes who is read first.
- A "Low" provisional priority must never be shown to the user as "you are safe". The user-facing response contains no scores or urgency labels.

## Known problems and open questions

1. The label mapping, labelling guide and cost matrix have not been reviewed by a clinician.
2. The training data are long forum histories; message-level behaviour and calibration are unverified.
3. 424 users, 103 High: wide uncertainty.
4. No real chat messages with human urgency labels exist yet; the synthetic-data question cannot be answered without them.
5. The ordinal fine-tuned model's calibration is degenerate (temperature at the search limit).
6. A *medium* baseline from PHQ-9 and GAD-7 scores does not currently raise the floor used for message triage (only the self-harm answers do). Open design decision.
7. Prior shift (assumed High rate), minimum confidence and the cost matrix are unapproved safety settings. Prior shift is off by default.

## Intended use

Development reference and design basis inside this repository. Any use with real people requires, at minimum: clinician sign-off of the guide and mapping;
evaluation on a frozen gold set labelled by two independent annotators with counsellor adjudication; the rule layer and check-in floor in front of the model;
mandatory human review (as designed); staffed reviewers; and ethics approval.

## Ethics

Third-party text is used under its licences for research, stays out of git and is not quoted. User ids are hashed on load; links and mentions are masked.
No real user data has been used or sent to any external service. The Claude API is not used.

## Reproducibility

Code hash and library versions of the Colab fine-tuning run are in `colab_run.json` (Colab T4; torch 2.11.0, transformers 5.18.0, scikit-learn 1.6.1);
the dataset, labels, split and fold assignment were verified identical to the local project. One repeat of 5-fold CV for fine-tuning. See `ml/colab/README.md`.
