# IRIS ML plan (approved)

Core system: **message -> safety rules -> intent + urgency model -> calibration -> cost-sensitive decision (+ baseline
floor from the check-in) -> route or human review -> feedback**. Code lives in [`ml/`](../ml/README.md).

## Principles

1. The model assists; **a human reviews every case and decides**. The model only ranks the review queue. It never clears a case as Low
   (decided 2026-10-09 after the Phase 2 results; `V1_POLICY` in `ml/iris_ml/decision.py`).
2. The model can only raise urgency, never go below the baseline floor from the check-in (see ARCHITECTURE.md).
3. The rule layer for explicit self-harm language runs first and cannot be overridden by the model.
4. Recall over precision: missing an urgent case costs far more than an unnecessary escalation.

## Decisions (defaults accepted unless changed)

| Topic | Decision |
| --- | --- |
| Languages in v1 | English only. Hinglish is a stretch goal after Phase 3; other languages are stated as unsupported |
| Compute | **Heavy compute (training, embedding, reports) runs on Colab only; the development laptop's CPU and GPU are not used for it** (owner's decision, 2026-10-09). See `ml/colab/` |
| Claude API | **Not used** until the owner provides a key and explicitly agrees. No real user data is ever sent to a third party |
| Datasets (2026-10-06; see `ml/docs/DATA_REGISTRY.md`) | Reddit C-SSRS downloaded and in use (CC-BY-4.0). UMD requires ethics approval first (prep drafted). Gold pool built; labelling needs two humans and a clinician-approved guide |

## Claims policy (decided 2026-10-06)

**No statement that IRIS, or any model in this repository, is safe, accurate or clinically valid may be made in the app,
a report, a demo or slides until all three of these are true:**
1. a clinician has signed off the labelling guide **and the label mapping**;
2. the frozen gold set has been labelled by **independent human annotators** (agreement kappa >= 0.6) and a **counsellor
   has adjudicated** every disagreement;
3. a final evaluation on the frozen gold set has been run, with confidence intervals.

Until then every number is a development reference point. **Phase 2 did not change this:** its best result finds 55% (exploratory) of High cases at
30% review against a 95% target, and its models raise many false alarms on ordinary chat. **The Phase 1 baseline (M1 v0) is not sufficient for IRIS**: it
catches only 22% to 31% of High cases on long forum documents, it was never evaluated on chat messages, and its labels
rest on an unreviewed mapping. Its limitations are stated in `ml/docs/MODEL_CARD_M1_v0.md` and `ml/reports/phase1_baseline.md`.

## Standing decisions from the project owner

| Date | Decision |
| --- | --- |
| 2026-10-06 | Gold labels come **only from independent human annotators**; a counsellor or clinical professional reviews the label mapping and adjudicates disagreements. The code assistant organises the workflow but never labels |
| 2026-10-06 | The **UMD application stays a draft** until institutional ethics approval and supervisor details are confirmed. It is not submitted by the code assistant |
| 2026-10-06 | **Claude API is not approved.** It may be used only after the owner provides a key and explicitly approves it |
| 2026-10-06 | Phase 2 planning may proceed; Phase 2 results are not safety or performance claims until the gold set and clinical review exist |
| 2026-10-09 | **Honest Phase 2 conclusion accepted.** The real DistilRoBERTa (Colab) results stay in the report unchanged. Final design: rules + check-in floor -> AI ranks the queue -> mandatory human review -> human decides; the model never clears a case. The 95%-at-30%-review target was not achieved and this is documented, with the false-alarm problem and the limits of the synthetic-data evaluation |
| 2026-10-09 | No more heavy experiments on the laptop. The demo patients get an illustrative walkthrough only, never ML evaluation. **No final performance number is claimed until the gold-set evaluation** (two independent annotators + counsellor/clinician) is done |

## Phases and gates

| Phase | Deliverable | Gate |
| --- | --- | --- |
| **P0 Foundations** | Labelling guide, schema and leakage checks, evaluation harness, rule layer (M0), repo skeleton | Tests pass; guide awaits clinician sign-off; data requests raised |
| **P1 Baselines** | M0 + M1 (TF-IDF + calibrated logistic regression), first numbers on a validation set, model card v0 | Reproducible from one command (Objective 2). **Done 2026-10-06**: M1 High recall 0.22-0.31 on documents; fails the human-review gate, as expected |
| **P2 Transformer** | M2 fine-tuned DistilBERT/RoBERTa, two heads, calibration, cost-sensitive decision, ablations (context, baseline features) | Beats M1 on cost at equal High recall, or is dropped. **Done 2026-10-09: DistilRoBERTa does not detectably beat M1 (AUROC 0.71 to 0.73 vs 0.70; 49% to 52% of High cases found at 30% review vs 51%).** Kept as a research result; the system design changed to mandatory human review. See `ml/reports/phase2_final_summary.md` |
| **P3 Robustness** | Error analysis, slices, red-team set, threshold selection | Ship or no-ship decision recorded |
| **P4 Integration** | Triage service, message API, reviewer actions, feedback tables, end-to-end demo | Every prediction stored with model version |
| **P5 Report** | Model card, datasheet, evaluation, limitations | |

## Proposed acceptance gates (to agree with the project owner and a clinician)

- High-urgency recall >= 0.95 on the gold set at a human-review rate <= 30%
- Expected calibration error <= 0.05
- No slice with High recall below 0.85
- The rule layer catches 100% of the explicit-phrase list (already enforced by `ml/tests/test_rules.py`)

With a few hundred gold items the confidence intervals are wide. All claims are stated with intervals, never as bare
point estimates.

## Risks

Reddit-to-chat domain shift; label noise from mapped external labels; a small gold set; synthetic-data bias;
users reading "Low" as "safe"; over-claiming clinical validity. Mitigations: synthetic data is train-only and flagged,
mapped labels are clinician-sampled, the gold set is frozen before any model is tuned, and all product wording keeps
"supports, does not diagnose".
