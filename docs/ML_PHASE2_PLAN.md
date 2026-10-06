# ML Phase 2 plan (DRAFT for the project owner's approval)

> Planning only. Nothing in this document has been built, and nothing here is a safety or performance claim.
> Standing rules (see `ML_PLAN.md`): labels come only from independent human annotators; the UMD application stays a draft;
> **the Claude API is not used** until the owner provides a key and approves; no claims until the gold set and clinical review exist.

## 1. What Phase 1 taught us

| Finding | Evidence |
| --- | --- |
| The TF-IDF baseline is weak at the thing that matters | High recall 0.22 to 0.31 (random 0.21); most true High users are predicted Medium |
| Calibration is solvable | Temperature scaling cut calibration error from about 0.19 to between 0.02 and 0.06 (depending on the mapping) |
| Ranking by risk helps a little | Exploratory, dev users only: AUROC (High vs rest) 0.72. If reviewers read the top 30% ranked by the model, they would see about **50% to 55%** of High cases (reading 30% at random finds 30%). Reading the top 50% finds about 70% to 75% |
| The 95%-at-30%-review gate is far away | The gap is about 40 points of recall |
| The data is the bottleneck, not the algorithm | 500 users, long histories, suicide-only content, no everyday-stress or logistics negatives, labels per user, unreviewed label mapping |

These are development numbers with wide intervals (about 100 High cases). They show direction, not a result.

## 2. Reframe Phase 2

The original Phase 2 was "fine-tune a transformer and beat the baseline". Given the findings, a better classifier alone will not
close the gap in the time and data we have, and we must not let the product depend on it doing so. Phase 2 therefore has two goals:

1. **Make the system safe even when the classifier is imperfect** (decision layer, ranking, floors, human review).
2. **Improve the classifier where the data allows**, and be honest about what it still cannot do.

Product stance proposed for v1 (needs your confirmation): the model is a **risk ranker that prioritises the human queue**, not a
gatekeeper that clears messages. Layers, in order:

```
rules (recall-first) -> baseline floor (check-in) -> model: risk score + calibrated confidence
   -> cost-sensitive decision (abstain when unsure or out of scope) -> human review queue ordered by risk -> feedback
```

Implications: early review rates will be high and are bounded by real reviewer capacity; "Low" is never shown to a user as "safe";
very short, non-English or unfamiliar messages go to a human by default.

## 3. Workstreams

### A. Data readiness (the real blocker)

| Item | What | Status / action |
| --- | --- | --- |
| A1 Licence survey | Check terms of candidate sources before any download | See table below |
| A2 Team-written message set | Volunteers write **fictional** chat-style messages for every class, including everyday stress, emotional support, logistics and idioms ("this exam is killing me"), under a writing guide with no real personal details. About 600 messages. A second person audits a sample. Flagged `source=team_written`, train only, kept separate from gold | **Needs the owner's decision** (who writes, wellbeing note) |
| A3 Hard-negative augmentation | Template and paraphrase variants for idioms, negation, third person, typos. Small, flagged, train only | Can start without approval |
| A4 Weak segment labels | Cut Reddit documents into short windows that inherit the user's label; **audit a sample with annotators to measure the noise rate before trusting it** | Uses the gold workflow's annotators |
| A5 LLM-generated data | Only after API approval and a written protocol (no real user data is ever sent) | **Blocked** |

Licence survey (read-only; nothing downloaded):

| Source | Use | What I found | Next step |
| --- | --- | --- | --- |
| Dreaddit | stress intent | Licence unconfirmed | Read the repository terms |
| GoEmotions | emotion signal | Its documentation states [no known licence](https://www.huggingface.co/datasets/google-research-datasets/go_emotions/blob/add492243ff905527e67aeb8b80c082af02207c3/README.md?code=true) | **Treat as unusable** unless the owners clarify |
| ESConv (emotional-support dialogues) | support-style language | [Research-use licence](https://github.com/thu-coai/Emotiona1-Support-Conversation); exact terms to read | Read terms, then ask permission |
| MentalBERT / MentalRoBERTa | domain-pretrained encoder | [Gated on Hugging Face](https://huggingface.co/mental/mental-roberta-base): you must accept terms and share contact details | **Owner action** if you want it |
| UMD v2 | severity labels at scale | Ethics approval + supervisor + data management plan required | **Draft only, not submitted** |
| IRIS pilot messages | in-domain data | Needs user consent and ethics approval | Not used |

### B. Modelling experiments (development users only; the frozen test users and gold set are not touched)

| ID | Experiment | Why |
| --- | --- | --- |
| E1 | Short-segment TF-IDF + logistic regression (weak labels), pooled per user | A fair short-input baseline against M1 |
| E2 | Frozen sentence embeddings + logistic regression | Usually beats fine-tuning at a few hundred examples, cheap, runs on CPU |
| E3 | Fine-tune DistilRoBERTa / RoBERTa-base on segments with an **ordinal** urgency head | The planned M2 |
| E4 | Same with MentalRoBERTa | Only if you accept its terms |
| E5 | Multiple-instance learning: encode chunks, attention-pool to a user label | Respects that labels are per user |
| E6 | Late fusion of the check-in baseline and conversation context | Matches the product |

Ablations: ordinal vs cross-entropy loss, class weights, temperature scaling vs isotonic, maximum length.

**Protocol:** repeated stratified cross-validation on the development users, **identical folds for every model**, five seeds for
neural models, paired bootstrap against M1, McNemar for High-recall differences. With 103 High cases, differences smaller than about
12 points cannot be detected, so I will say "not distinguishable" instead of declaring winners.

**Development targets** (not safety claims): AUROC for High vs rest at least 0.80 (M1: 0.72) with the paired interval excluding zero;
High cases found in the top 30% of the ranking at least 70% (M1: about 50% to 55%); calibration error at most 0.05.

### C. Decision layer (model-agnostic; first thing to build once approved)

- Cost-sensitive policy: choose the action with the lowest expected cost given calibrated probabilities and `configs/costs.yaml`.
- Review ranking by risk score; abstention for low confidence and for out-of-scope input (very short, non-English, empty).
- Combination rule: final urgency is the **maximum** of the model decision, the rule layer, and the baseline floor from the check-in.
- A `TriageResult` structure for the backend: urgency, intent, confidence, route, reasons (rule hits, floor, top terms), model version.
- A simulation harness: operating-point curves under the policy, and a **sweep over cost matrices**, because the cost matrix is awaiting
  clinical review and results should not hinge on one guess.

### D. Evaluation additions

Recall at a fixed review rate (ranking), AUROC and PR-AUC, paired comparisons, slice reports (negation, third person, short text),
a **red-team set** of about 100 adversarial messages written by the team and frozen before any tuning, and a **false-alarm audit on
everyday chat** (needs the negatives from A2, since the Reddit data has none).

### E. Integration contract (prepares Phase 4)

Message API; tables `messages`, `predictions` (model version, probabilities, rule hits, floor, decision) and `reviews` (reviewer label,
time); Row Level Security and the audit log as for the rest of the system; a model registry that records the artefact hash and the
data version; a feature flag so the model can be switched off without redeploying.

## 4. Gates and dependencies

| Gate | Unlocks |
| --- | --- |
| Now | A2/A3 (with your decision), C, D tooling, E1 and E2 |
| Clinician signs off the guide **and label mapping** | Gold labelling; any change to the mapping |
| Gold set labelled, adjudicated and frozen | The final evaluation and any performance claim |
| Ethics approval + supervisor | UMD application |
| Your API approval and key | A5 and any Claude-based comparison |

Phase 2 outputs are labelled **development only** until the second and third gates are passed.

## 5. Risks

Overfitting at 424 users (mitigated by cross-validation, simple models first); noisy weak labels (audit before use); near-duplicate
text across users (cross-posts) leaking between folds (add a near-duplicate check); sensitive text memorised by model weights (never
publish weights trained on third-party text); premature claims (claims policy); a decision layer tuned to an unreviewed cost matrix
(sweep and report sensitivity); false reassurance from "Low" (wording rules in the product).

## 6. Decisions I need from you

Only the ethical, clinical, data-usage and project-level ones:
1. **Confirm the v1 stance:** the model ranks and prioritises for human review; it does not clear messages on its own.
2. **Team-written messages (A2):** are you able to find volunteers, and are you comfortable with the writing guide approach?
3. **Permission to read and, if suitable, download** ESConv and Dreaddit (I will check terms first and tell you exact files and sizes).
4. **MentalRoBERTa:** do you want to accept Hugging Face's terms for it? (Your account, your decision.)
5. **Model weights:** permission to download open sentence-embedding and RoBERTa-family models (I will state names, sizes and licences first).
6. **GPU access:** do you have a GPU, or should I plan around free Colab/Kaggle?
7. Your **deadline**, so I can size what fits.

I will not start building Phase 2 until you approve this plan.
