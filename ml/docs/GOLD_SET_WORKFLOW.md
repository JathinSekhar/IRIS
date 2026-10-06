# Gold test set workflow

The gold set is the **only** thing that can tell us how a model behaves on message-sized text, so it has to be independent,
blind and frozen. This document is the step-by-step procedure. The code is `iris_ml/gold.py`.

## Status

| Step | State |
| --- | --- |
| Sampling pool (300 segments, 72 held-out users) and blind batches | **Built** (`data/gold/`, git-ignored) |
| Clinician sign-off of `LABELING_GUIDE.md` | **Pending** |
| Two annotators identified | **Pending** |
| Counsellor for adjudication identified | **Pending** |
| Labelling, agreement check, adjudication, freeze | Not started |

**Decision recorded 2026-10-06 (project owner):** labels come from independent human annotators. A counsellor or
clinical professional reviews the **label mapping** (`configs/label_maps.yaml`) and adjudicates disagreements. The code
assistant prepares and organises the workflow and does not label any item.

## Why the labels are not produced by the code assistant

A gold set is only evidence if the people labelling it are independent of the system being tested and are using a
clinician-approved guide. If the model's developer (or the assistant that wrote it) supplied labels, the evaluation would
be circular, and clinical safety claims would rest on non-clinical judgement. The tooling therefore does the organising
work and never suggests a label.

## Procedure

1. **Clinician review.** A counsellor or clinical psychologist reviews `LABELING_GUIDE.md` and the cost matrix and
   signs off (or edits). Record the date and name in the guide's change log. Do not start labelling before this.
2. **Annotators.** Two people, independent of each other, who have read the guide. Agree the wellbeing rules (45-minute
   sessions, breaks, a named support person, right to stop).
3. **Distribute.** Give annotator A only `data/gold/batches/annotator_A.csv` and annotator B only `annotator_B.csv`, with
   `README.txt`. **Never** share `pool_private.csv` (it contains the original labels and rule results, which would bias them).
   Files contain third-party text: transfer them securely, do not email or post them, and delete copies afterwards.
4. **Label.** Each annotator fills `intent`, `urgency`, `subject`, `uncertain`, `notes` for every row, alone. About 330 rows
   each (300 items plus 10% repeats). Plan roughly 5-7 hours per person in sessions of at most 45 minutes.
5. **Collect.** Save the returned files as `data/gold/annotations/annotator_A.csv` and `annotator_B.csv`.
6. **Check.** `python -m iris_ml.gold check` validates the files (no missing or invalid values, consistency rules),
   reports inter-annotator agreement (target kappa >= 0.6 for urgency and intent), each annotator's own consistency on
   the repeated items, and writes `annotations/adjudication_sheet.csv` (disagreements, High first).
   **If kappa is below 0.6, stop**: the guide is unclear. Fix the guide with the clinician and relabel; do not just adjudicate.
7. **Adjudicate.** The counsellor fills `final_intent`, `final_urgency`, `final_subject` for every row in the sheet.
8. **Finalise and freeze.** `python -m iris_ml.gold finalize` combines agreed and adjudicated labels, checks that every
   item comes from a held-out user, writes `gold_v1.csv` and records its SHA-256 in `GOLD_FREEZE.json`. After that the file
   cannot be rewritten without an explicit force, and `verify_frozen` detects any edit. Commit `GOLD_FREEZE.json` (hash and
   counts only); the CSV itself stays out of git.

## Rules after freezing

- Never train on the gold set, never tune thresholds on it, never look at its errors before the final evaluation round.
- Tune on a separate development set (the train and val users).
- Run `verify_frozen` at the start of every evaluation.

## What to expect (be honest about it)

Explicit imminent-intent phrases are rare in this text (about 3% of the pool), so **the number of true High items may
be small**. The pool over-samples attempt, method and imminence vocabulary to help, but the High count is only known after
labelling. If it is under about 60, the High-recall confidence interval will be wide (roughly +/- 10 points or more) and we
will say so rather than over-claim. Later additions (consented IRIS pilot data, UMD data if approved) can extend the gold set,
as a new frozen version, never by editing `gold_v1`.

## Known limits of this gold set

- Segments come from long Reddit histories, not chat. It measures whether the system reads distress in short text; it does
  not measure real chat behaviour.
- English only. Suicide-forum content, with no everyday-conversation examples (so it says nothing about false alarms on
  ordinary chat: that needs separate negative data).
