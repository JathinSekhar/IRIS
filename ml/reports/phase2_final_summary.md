# Phase 2 final summary

**Status: development evidence only. No safety or performance claim is made for IRIS.** Every number below is copied from
[`phase2_results.md`](phase2_results.md) (cross-validated, out-of-fold, on the 424 development users). The 76 held-out test users and
the gold set were not used. No final performance number exists, and none will until the gold-set evaluation is done (section 9).

## 1. The conclusion

1. **The 95%-of-High-cases-at-30%-review target was NOT achieved.** The best result anywhere is **55%** (an exploratory five-model
   ensemble); the pre-specified ensemble finds **50%**; the Phase 1 baseline finds **51%**. The gap to the target is about 40 points.
2. **No model is detectably better than the Phase 1 baseline.** Differences are within noise (about 100 High users).
3. **The models raise far too many false alarms on ordinary support chat**, and the one model that does not has a result that cannot be trusted
   (section 5).
4. Therefore **the AI model must not clear any case**. The system to ship is:

```
rules + check-in floor  ->  AI ranks the review queue  ->  a person reviews EVERY case  ->  the person decides
```

The model only changes the *order* in which people read cases. It can raise priority; it can never mark a case Low or safe.
This is implemented as `V1_POLICY` (`mandatory_review=True`) in `ml/iris_ml/decision.py` and pinned by tests.

## 2. What was built

| Part | Where |
| --- | --- |
| Experiment engine: one protocol for every model (same users, same repeated stratified 5-fold folds, out-of-fold predictions, cross-fitted temperature scaling, cached by exact specification) | `ml/iris_ml/experiments.py` |
| Models: TF-IDF baselines, chunk models, frozen sentence embeddings (MiniLM, MPNet) + logistic regression or softmax/ordinal head, attention multiple-instance model, DistilRoBERTa fine-tuning, five-label ("native5") training, ensembles | `neural.py`, `embeddings.py`, `chunks.py`, `experiments.py` |
| Rule layer (explicit self-harm language, recall-first), extended this phase | `ml/iris_ml/rules.py` |
| Cost-sensitive decision layer with fail-safe (a model failure goes to a human, never Low), check-in floor, prior-shift option (off by default), and the V1 mandatory-review policy | `decision.py`, `system.py`, `calibration.py` |
| Evaluation: recall at a review rate, AUROC, PR-AUC, paired bootstrap, McNemar, ordinary-chat false-alarm audit, challenge set, cost-matrix and prior sensitivity | `ranking.py`, `report2.py`, `challenge.py` |
| Template synthetic messages (train only, flagged) | `synth.py` |
| Colab package so no heavy compute runs on the laptop (verified bundle, GPU-only training, result import checks) | `ml/colab/` |
| Illustrative demo walkthrough | `walkthrough.py`, [`phase2_walkthrough.md`](phase2_walkthrough.md) |
| Integration contract for Phase 4 (draft, nothing applied) | `docs/TRIAGE_INTEGRATION_SPEC.md` |

## 3. Datasets used

| Data | Use | Terms |
| --- | --- | --- |
| Reddit C-SSRS (500 users; one long document each; four-psychiatrist labels) | Training and cross-validated evaluation on 424 development users. 76 users stay frozen as the test split | CC-BY-4.0; kept out of git |
| Template synthetic messages (1,084; no language-model API) | Added to **training folds only**, flagged | Written by the code author |
| ESConv (emotional-support chat; 6,000 seeker messages sampled) | **False-alarm audit only, never training** | Academic research use only; kept out of git |
| Challenge set (72 hand-written items: 41 benign, 31 that should escalate) | Regression and false-alarm check | Written by the code author. **Not gold, not independent** |
| Demo accounts (3 people) | Hand-testing the app and an illustrative walkthrough. **Never used for ML evaluation** | Fictional |

Labels come from a **mapping of the psychiatrists' five labels to IRIS urgency, which no clinician has reviewed** (two variants reported:
`conservative`, `lenient`). The text is long Reddit history, not chat.

## 4. Results

### 4.1 Ranking (conservative mapping, repeat 0)

"Review 30%" = share of High cases found when reviewers read the top 30% of users ranked by the model; reading at random finds 30%.

| Model | AUROC | Review 30% | Macro-F1 | Kappa | AUROC difference vs Phase 1 baseline (95% interval) |
| --- | --- | --- | --- | --- | --- |
| **M1 Phase 1 baseline** (TF-IDF, whole documents) | 0.70 | 51% | 0.48 | 0.34 | n/a |
| MPNet embeddings + logistic regression | 0.69 | 49% | 0.50 | 0.39 | -0.00 [-0.07, +0.06] |
| **DistilRoBERTa fine-tuned (Colab T4)** | 0.71 | 49% | 0.51 | 0.41 | +0.02 [-0.04, +0.08] |
| **DistilRoBERTa fine-tuned + synthetic data** | 0.73 | 52% | 0.48 | 0.35 | +0.04 [-0.02, +0.10] |
| **DistilRoBERTa fine-tuned, ordinal head** | 0.71 | 50% | 0.34 | 0.39 | +0.01 [-0.06, +0.08] |
| Pre-specified ensemble | 0.72 | 50% | 0.41 | 0.29 | +0.02 [-0.04, +0.08] |
| Best exploratory ensemble (five models) | 0.74 | 55% | 0.53 | 0.43 | +0.05 [-0.00, +0.10] |

- Only one difference is flagged as distinguishable in the model's favour: an exploratory ensemble at +0.04 AUROC with a lower bound of +0.00. It is one of
  four ensembles tried after seeing results, so treat it as a lead, not a finding. The only clear difference overall is a loss: attention-MIL trained
  with synthetic data is -0.12 [-0.20, -0.03].
- Lenient mapping: fine-tuned DistilRoBERTa gets AUROC 0.70 and review-30% 49%, essentially the same.
- Fine-tuning used **one repeat** of 5-fold CV (cost); the cheap models used three.
- **The fine-tuned ordinal model's calibration is degenerate** (the calibration temperature reached its search limit of 20). Its calibrated ECE of 0.028
  comes from flattened probabilities and must not be read as good calibration. Calibration also did not help the plain fine-tuned model (ECE 0.048 -> 0.066).
- Every model family lands in the same 0.68 to 0.74 AUROC band, from TF-IDF to a fine-tuned transformer. That pattern suggests the labels and the data,
  not the model type, set the ceiling here. It is an inference from these results, not something this experiment tested directly.

### 4.2 Comparison with Phase 1

Phase 1 concluded the baseline was not sufficient (High recall 0.22 at the argmax decision on documents; no chat evaluation). Phase 2 tried 21 model
configurations and 4 exploratory ensembles. **None reaches the gate, and none is detectably better than M1.** What Phase 2 added is not a better number:
it is a decision layer with a fail-safe, an extended rule layer, evidence on false alarms, and the honest finding above.

## 5. The false-alarm problem (the main practical risk)

Document-trained models score single chat messages badly. On 6,000 ordinary support messages (ESConv), with the policy's minimum confidence at 0.6:

| System | Sent to a human | Final: Low / Medium / High |
| --- | --- | --- |
| M1 (Phase 1 baseline) | 58% | 0% / 74% / 26% |
| Fine-tuned DistilRoBERTa | 91% | 0% / 9% / 91% |
| Pre-specified ensemble | 100% | 0% / 0% / 100% |
| MPNet + logistic regression, with synthetic data | 65% | 17% / 21% / 62% |
| Fine-tuned DistilRoBERTa **with synthetic data** | 28% | 56% / 18% / 26% |

On the 41 benign challenge sentences, most systems keep **0 of 41** Low. The rule layer on its own keeps 41 of 41 Low but handles only 19 of 31
should-escalate items, so the rules and the model are complementary. With the current rules the rule layer flags 13 of the 6,000 ESConv messages (0.2%);
the report's "0%" is a rounded figure.

**Why the synthetic-data model looks better and why that cannot be trusted.** The fine-tuned model trained with synthetic data keeps 39 of 41 benign
challenge items Low and cuts ordinary-chat escalation to 28%, but:
- The synthetic data are template messages, and the challenge set is also hand-written by the same person. A test confirms the two share no literal
  fragments, but they share the author's idea of what an "ordinary" message sounds like. The challenge result is therefore optimistic.
- ESConv is independent of both, and even there a quarter of ordinary messages (26%) are still labelled High. Nobody has labelled those messages, so we
  cannot tell how many are false alarms.
- The same synthetic data hurt other models (attention-MIL: -0.12 AUROC) and lowered macro-F1 and kappa here. It also made one model miss 3 more
  should-escalate items on the model alone (27 of 31, where most models meet all 31), so the lower false-alarm rate is paid for in missed cases.
- No real chat messages with human urgency labels exist yet. Until they do, "does the synthetic data help?" cannot be answered.

Lowering the assumed High rate (prior shift) reduces false alarms but loses cases: for the pre-specified ensemble at an assumed 2% High rate, ordinary chat
sent to a human drops to 40%, but should-escalate items met fall to 26 of 31 and implicit High items caught to 1 of 4. The setting stays **off by default**; its
value is a safety decision for the project owner and a clinician.

## 6. What the V1 design does with these results

| Layer | Role | Evidence it works |
| --- | --- | --- |
| Rule layer | Explicit self-harm language raises urgency; cannot be lowered | Explicit-phrase gate enforced by tests; handles 19 of 31 challenge should-escalate items alone |
| Check-in floor | The C-SSRS safety answers set a minimum urgency | Backend tests; demo walkthrough |
| AI ranking | Orders the review queue by risk score. **Cannot clear a case** | Ranking is the one thing measured: AUROC about 0.70 to 0.73. Modest and uncertain |
| Human review | **Every** case is reviewed; the human decides | Required by `V1_POLICY`; no model failure can turn into Low |

**Consequence to decide:** with mandatory review, reviewer capacity must cover all messages. The AI ranking only helps with who is read first. If that
is not staffable, the options (reviewing only flagged cases, or a supportive default reply with crisis resources for the rest) change the safety
case and need the project owner and a clinician.

The ranker named for v1 is the pre-specified ensemble (set before any ensemble result was seen). It is a default, not a finding: no candidate is
detectably better than M1, and it is to be re-decided on the gold set. **No deployable model artefact has been produced** (only audit-time fits).

The evaluation tables in this report use the *evaluation* policy, in which a confident model may clear a case. They measure what a model could do on its
own, and the answer is: not enough. They are not the behaviour of the shipped design.

## 7. Limitations

- **No clinician has reviewed the label mapping, the labelling guide or the cost matrix.** "Behavior" and "Attempt" are lifetime or recent history,
  while the guide reserves High for imminent danger.
- **Domain shift:** training text is long suicide-forum history; the product handles chat messages. Message-level calibration is unverified.
- **Small data:** 424 users and 103 High. Intervals are wide: differences under about 0.05 AUROC or 12 points of recall cannot be detected.
- **Fine-tuning:** one repeat; GPU results are not bit-reproducible across hardware and library versions (Colab T4, torch 2.11.0, transformers 5.18.0,
  scikit-learn 1.6.1; the fold assignment was verified identical to the local project).
- **Multiple comparisons:** many models were compared. Only the pre-specified ensemble was planned; the other ensembles are exploratory.
- **English only; no Hinglish or other languages.**
- **Rules changed after the report was built.** "Ending my life" is now recognised (found by the demo walkthrough) and "nobody would notice if I was gone"
  is now flagged at review level (found while probing the support-text matcher). Four more phrasings found by the support-message review are now flagged at
  review level too ("I don't see the point in anything", "I can't face another day", "everyone would be happier if I wasn't around", and "hurting/harming
  himself/herself" for another person). I re-checked after these changes that the rule-dependent numbers in the report are unchanged (challenge 41/41
  and 19/31; ESConv rule flags 13 of 6,000). Both gaps were found by trying to break the system by hand, which
  is a reminder that more gaps certainly exist: the rule layer is a hand-written pattern list and cannot be shown to catch every urgent phrasing.
- **Not verified in this session:** the heavy tests (model reload, fine-tune end-to-end) were not re-run, to keep compute off the laptop. The decision,
  rules, walkthrough and demo-account tests pass.
- Prior-shift, cost matrix and minimum confidence are tunable settings whose values are safety decisions; none has been approved.

## 8. Illustrative walkthrough

[`phase2_walkthrough.md`](phase2_walkthrough.md) shows the three demo patients (Ananya, Rohit, Arjun) through the V1 design: check-in floor, rule layer,
provisional priority, mandatory human review. **Illustrative only: not used for any ML evaluation, and no model was run.** It surfaced two real issues:
a rule gap (now fixed and tested) and an open design question: a *medium* check-in baseline from PHQ-9 and GAD-7 scores does not currently raise the floor that
message triage receives; only the self-harm answers do.

## 9. What is needed before any performance number

1. A clinician reviews and signs off the labelling guide, the label mapping and the cost matrix.
2. A gold set of real chat-like messages labelled by **two independent annotators**, with a **counsellor or clinician** adjudicating disagreements
   (`ml/docs/GOLD_SET_WORKFLOW.md`). The code assistant does not label gold data.
3. One final evaluation on the frozen gold set, with confidence intervals. Only then can a performance number be stated.
4. Ethics approval and a supervisor before the UMD application (it stays a draft).
5. Decisions: reviewer capacity under mandatory review, the prior-shift setting, and whether a medium check-in baseline should raise the floor.

## 10. Reproducing

- Everything except fine-tuning: `python -m iris_ml.run_phase2 experiments --skip-finetune` then `report`. These use compute; the Phase 2 report
  here was built on Colab using `ml/colab/`.
- Fine-tuning: `ml/colab/README.md` (Colab T4 only; the laptop never trains).
- The walkthrough: `python -m iris_ml.walkthrough`.
