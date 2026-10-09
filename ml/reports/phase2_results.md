# Phase 2 results (development data only)

_Generated 2026-10-06 16:46 UTC by `python -m iris_ml.run_phase2 report`. Aggregates only; no dataset text appears here._

## Read this first

- Everything here is **development evidence on the 424 development users** (cross-validated, out-of-fold). The 76 held-out test users and the gold set were **not used**. No model was tuned against them.
- **These are not safety or performance claims about IRIS.** The label mapping is unreviewed, the data is long forum history rather than chat, and the gold set has not been labelled.
- Intervals are 95%. With about 100 High cases, differences smaller than roughly 0.05 AUROC or 12 points of recall cannot be detected, so results marked *not distinguishable* are ties, not small wins.

## 1. Every model (primary mapping `conservative`, repeat 0)

`Review x%` = share of High cases found when reviewers read the top x% of users ranked by the model (reading at random finds x%).

| Model | Family | Synthetic data | AUROC | Review 10% | 20% | **30%** | 40% | 50% | Macro-F1 | Kappa | ECE raw -> cal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| m1_doc_tfidf | doc_tfidf | no | 0.70 | 27% | 39% | **51%** | 61% | 69% | 0.48 | 0.34 | 0.186 -> 0.031 |
| e1_chunk_tfidf | chunk_tfidf | no | 0.68 | 17% | 32% | **45%** | 57% | 74% | 0.45 | 0.32 | 0.080 -> 0.050 |
| e1s_chunk_tfidf_syn | chunk_tfidf | yes | 0.68 | 20% | 33% | **45%** | 54% | 67% | 0.37 | 0.24 | 0.065 -> 0.051 |
| e2_minilm_lr | emb_lr | no | 0.70 | 21% | 39% | **50%** | 62% | 69% | 0.48 | 0.34 | 0.064 -> 0.044 |
| e2s_minilm_lr_syn | emb_lr | yes | 0.71 | 18% | 37% | **48%** | 60% | 69% | 0.45 | 0.29 | 0.096 -> 0.088 |
| e2_mpnet_lr | emb_lr | no | 0.69 | 16% | 35% | **49%** | 61% | 73% | 0.50 | 0.39 | 0.092 -> 0.056 |
| e2s_mpnet_lr_syn | emb_lr | yes | 0.70 | 17% | 35% | **51%** | 64% | 69% | 0.44 | 0.29 | 0.072 -> 0.058 |
| e2h_mpnet_head_ce | emb_head | no | 0.69 | 21% | 36% | **45%** | 60% | 70% | 0.49 | 0.37 | 0.062 -> 0.051 |
| e2o_mpnet_head_ordinal | emb_head | no | 0.68 | 18% | 34% | **46%** | 61% | 71% | 0.46 | 0.39 | 0.080 -> 0.102 |
| e5_minilm_mil | mil | no | 0.63 | 17% | 32% | **46%** | 55% | 63% | 0.42 | 0.19 | 0.069 -> 0.053 |
| e5_mpnet_mil | mil | no | 0.68 | 22% | 34% | **50%** | 60% | 68% | 0.42 | 0.21 | 0.125 -> 0.038 |
| e5s_mpnet_mil_syn | mil | yes | 0.58 | 19% | 28% | **40%** | 47% | 59% | 0.36 | 0.08 | 0.228 -> 0.064 |
| e5o_mpnet_mil_ordinal | mil | no | 0.65 | 20% | 38% | **47%** | 58% | 67% | 0.29 | 0.24 | 0.220 -> 0.053 |
| e3_distilroberta_ft | finetune | no | 0.71 | 23% | 33% | **49%** | 60% | 73% | 0.51 | 0.41 | 0.048 -> 0.066 |
| e3s_distilroberta_ft_syn | finetune | yes | 0.73 | 22% | 40% | **52%** | 62% | 76% | 0.48 | 0.35 | 0.060 -> 0.044 |
| e3o_distilroberta_ft_ordinal | finetune | no | 0.71 | 19% | 35% | **50%** | 59% | 74% | 0.34 | 0.39 | 0.192 -> 0.028 |
| n5_m1_doc_tfidf | doc_tfidf | no | 0.70 | 25% | 38% | **50%** | 61% | 71% | 0.32 | 0.12 | 0.126 -> 0.062 |
| n5_e1_chunk_tfidf | chunk_tfidf | no | 0.68 | 18% | 31% | **43%** | 60% | 74% | 0.35 | 0.21 | 0.059 -> 0.043 |
| n5_e2_minilm_lr | emb_lr | no | 0.71 | 23% | 42% | **50%** | 60% | 72% | 0.37 | 0.21 | 0.040 -> 0.027 |
| n5_e2_mpnet_lr | emb_lr | no | 0.69 | 17% | 34% | **49%** | 61% | 75% | 0.38 | 0.23 | 0.045 -> 0.062 |
| n5_e2o_mpnet_head_ordinal | emb_head | no | 0.67 | 16% | 28% | **46%** | 60% | 67% | 0.37 | 0.28 | 0.060 -> 0.075 |
| ens_prespecified | ensemble | no | 0.72 | 21% | 32% | **50%** | 64% | 73% | 0.41 | 0.29 | 0.048 -> 0.048 |
| ens_x1_m1_mpnet | ensemble | no | 0.72 | 23% | 36% | **50%** | 63% | 72% | 0.54 | 0.43 | 0.088 -> 0.088 |
| ens_x2_m1_minilm_mpnet | ensemble | no | 0.73 | 21% | 40% | **53%** | 61% | 74% | 0.55 | 0.44 | 0.097 -> 0.097 |
| ens_x3_m1_n5minilm_n5mpnet | ensemble | no | 0.74 | 22% | 41% | **53%** | 64% | 72% | 0.43 | 0.32 | 0.081 -> 0.081 |
| ens_x4_five | ensemble | no | 0.74 | 20% | 42% | **55%** | 65% | 75% | 0.53 | 0.43 | 0.096 -> 0.096 |

Split-to-split spread (3 repeats of 5-fold CV; models with one repeat are omitted):

| Model | AUROC mean (sd) | Review-30% mean (sd) | Macro-F1 mean (sd) |
| --- | --- | --- | --- |
| m1_doc_tfidf | 0.71 (0.013) | 51% (0.0 pts) | 0.48 (0.008) |
| e1_chunk_tfidf | 0.68 (0.007) | 45% (1.1 pts) | 0.44 (0.017) |
| e1s_chunk_tfidf_syn | 0.68 (0.008) | 45% (1.0 pts) | 0.37 (0.007) |
| e2_minilm_lr | 0.70 (0.006) | 48% (1.5 pts) | 0.48 (0.019) |
| e2s_minilm_lr_syn | 0.70 (0.011) | 48% (1.0 pts) | 0.44 (0.011) |
| e2_mpnet_lr | 0.70 (0.008) | 50% (2.6 pts) | 0.50 (0.007) |
| e2s_mpnet_lr_syn | 0.71 (0.008) | 51% (1.0 pts) | 0.44 (0.008) |
| e2h_mpnet_head_ce | 0.70 (0.005) | 47% (1.9 pts) | 0.49 (0.010) |
| e2o_mpnet_head_ordinal | 0.69 (0.006) | 47% (3.7 pts) | 0.47 (0.008) |
| e5_minilm_mil | 0.62 (0.018) | 43% (3.1 pts) | 0.41 (0.017) |
| e5_mpnet_mil | 0.67 (0.013) | 50% (1.9 pts) | 0.45 (0.026) |
| e5s_mpnet_mil_syn | 0.59 (0.017) | 40% (3.9 pts) | 0.37 (0.030) |
| e5o_mpnet_mil_ordinal | 0.66 (0.020) | 46% (3.4 pts) | 0.29 (0.001) |
| n5_m1_doc_tfidf | 0.71 (0.013) | 50% (1.0 pts) | 0.31 (0.008) |
| n5_e1_chunk_tfidf | 0.67 (0.008) | 44% (1.5 pts) | 0.35 (0.010) |
| n5_e2_minilm_lr | 0.69 (0.014) | 50% (1.1 pts) | 0.37 (0.008) |
| n5_e2_mpnet_lr | 0.70 (0.005) | 50% (2.6 pts) | 0.39 (0.002) |
| n5_e2o_mpnet_head_ordinal | 0.67 (0.007) | 46% (3.0 pts) | 0.36 (0.017) |
| ens_prespecified | 0.71 (0.006) | 50% (1.1 pts) | 0.40 (0.008) |
| ens_x1_m1_mpnet | 0.73 (0.016) | 50% (1.1 pts) | 0.53 (0.009) |
| ens_x2_m1_minilm_mpnet | 0.73 (0.007) | 54% (0.6 pts) | 0.54 (0.023) |
| ens_x3_m1_n5minilm_n5mpnet | 0.74 (0.005) | 54% (0.6 pts) | 0.44 (0.006) |
| ens_x4_five | 0.74 (0.007) | 54% (1.5 pts) | 0.54 (0.011) |

## 2. Compared with the Phase 1 baseline (M1, TF-IDF on whole documents)

Paired bootstrap on the same users and folds; difference = model minus M1. 'Review 30%' is High cases found when reading the top 30%.

| Model | AUROC difference | Review-30% difference | McNemar (High found in top 30%) |
| --- | --- | --- | --- |
| e1_chunk_tfidf | -0.02 [-0.07, +0.04] (not distinguishable) | -0.05 [-0.13, +0.05] (not distinguishable) | M1 only 17 / model only 12, p = 0.46 |
| e1s_chunk_tfidf_syn | -0.02 [-0.08, +0.03] (not distinguishable) | -0.03 [-0.13, +0.06] (not distinguishable) | M1 only 15 / model only 12, p = 0.70 |
| e2_minilm_lr | +0.01 [-0.05, +0.07] (not distinguishable) | +0.00 [-0.10, +0.11] (not distinguishable) | M1 only 17 / model only 17, p = 1.00 |
| e2s_minilm_lr_syn | +0.01 [-0.05, +0.08] (not distinguishable) | +0.03 [-0.07, +0.14] (not distinguishable) | M1 only 16 / model only 19, p = 0.74 |
| e2_mpnet_lr | -0.00 [-0.07, +0.06] (not distinguishable) | -0.01 [-0.12, +0.10] (not distinguishable) | M1 only 19 / model only 18, p = 1.00 |
| e2s_mpnet_lr_syn | +0.00 [-0.06, +0.07] (not distinguishable) | +0.03 [-0.08, +0.14] (not distinguishable) | M1 only 17 / model only 20, p = 0.74 |
| e2h_mpnet_head_ce | -0.01 [-0.07, +0.05] (not distinguishable) | +0.00 [-0.11, +0.12] (not distinguishable) | M1 only 18 / model only 18, p = 1.00 |
| e2o_mpnet_head_ordinal | -0.01 [-0.08, +0.05] (not distinguishable) | -0.03 [-0.14, +0.08] (not distinguishable) | M1 only 22 / model only 19, p = 0.76 |
| e5_minilm_mil | -0.06 [-0.14, +0.01] (not distinguishable) | -0.02 [-0.14, +0.11] (not distinguishable) | M1 only 23 / model only 21, p = 0.88 |
| e5_mpnet_mil | -0.02 [-0.09, +0.05] (not distinguishable) | -0.02 [-0.13, +0.09] (not distinguishable) | M1 only 22 / model only 20, p = 0.88 |
| e5s_mpnet_mil_syn | -0.12 [-0.20, -0.03] (distinguishable) | -0.08 [-0.20, +0.03] (not distinguishable) | M1 only 28 / model only 20, p = 0.31 |
| e5o_mpnet_mil_ordinal | -0.05 [-0.12, +0.03] (not distinguishable) | -0.04 [-0.13, +0.07] (not distinguishable) | M1 only 21 / model only 17, p = 0.63 |
| e3_distilroberta_ft | +0.02 [-0.04, +0.08] (not distinguishable) | -0.01 [-0.11, +0.10] (not distinguishable) | M1 only 22 / model only 21, p = 1.00 |
| e3s_distilroberta_ft_syn | +0.04 [-0.02, +0.10] (not distinguishable) | +0.04 [-0.05, +0.15] (not distinguishable) | M1 only 14 / model only 18, p = 0.60 |
| e3o_distilroberta_ft_ordinal | +0.01 [-0.06, +0.08] (not distinguishable) | +0.00 [-0.10, +0.11] (not distinguishable) | M1 only 20 / model only 20, p = 1.00 |
| n5_m1_doc_tfidf | +0.00 [-0.01, +0.01] (not distinguishable) | -0.02 [-0.06, +0.03] (not distinguishable) | M1 only 4 / model only 2, p = 0.69 |
| n5_e1_chunk_tfidf | -0.02 [-0.08, +0.04] (not distinguishable) | -0.05 [-0.13, +0.06] (not distinguishable) | M1 only 18 / model only 13, p = 0.47 |
| n5_e2_minilm_lr | +0.01 [-0.05, +0.08] (not distinguishable) | +0.02 [-0.09, +0.13] (not distinguishable) | M1 only 17 / model only 19, p = 0.87 |
| n5_e2_mpnet_lr | -0.00 [-0.07, +0.06] (not distinguishable) | -0.02 [-0.12, +0.10] (not distinguishable) | M1 only 19 / model only 17, p = 0.87 |
| n5_e2o_mpnet_head_ordinal | -0.03 [-0.09, +0.04] (not distinguishable) | -0.04 [-0.13, +0.08] (not distinguishable) | M1 only 22 / model only 18, p = 0.64 |
| ens_prespecified | +0.02 [-0.04, +0.08] (not distinguishable) | +0.02 [-0.08, +0.12] (not distinguishable) | M1 only 15 / model only 17, p = 0.86 |
| ens_x1_m1_mpnet | +0.02 [-0.01, +0.06] (not distinguishable) | +0.01 [-0.07, +0.09] (not distinguishable) | M1 only 8 / model only 9, p = 1.00 |
| ens_x2_m1_minilm_mpnet | +0.03 [-0.01, +0.08] (not distinguishable) | +0.03 [-0.05, +0.12] (not distinguishable) | M1 only 11 / model only 14, p = 0.69 |
| ens_x3_m1_n5minilm_n5mpnet | +0.04 [+0.00, +0.09] (distinguishable) | +0.05 [-0.02, +0.13] (not distinguishable) | M1 only 6 / model only 11, p = 0.33 |
| ens_x4_five | +0.05 [-0.00, +0.10] (not distinguishable) | +0.07 [-0.03, +0.16] (not distinguishable) | M1 only 10 / model only 17, p = 0.25 |

## 3. Ablations (what each design choice did)

| Question | A -> B | AUROC difference | Review-30% difference |
| --- | --- | --- | --- |
| documents vs chunks (TF-IDF) | e1_chunk_tfidf -> m1_doc_tfidf | +0.02 [-0.04, +0.07] (not distinguishable) | +0.05 [-0.05, +0.13] (not distinguishable) |
| MiniLM vs MPNet embeddings | e2_minilm_lr -> e2_mpnet_lr | -0.01 [-0.05, +0.03] (not distinguishable) | -0.01 [-0.09, +0.06] (not distinguishable) |
| synthetic messages in training (embeddings + LR) | e2_mpnet_lr -> e2s_mpnet_lr_syn | +0.01 [-0.01, +0.03] (not distinguishable) | +0.04 [-0.02, +0.09] (not distinguishable) |
| synthetic messages in training (TF-IDF) | e1_chunk_tfidf -> e1s_chunk_tfidf_syn | -0.00 [-0.01, +0.01] (not distinguishable) | +0.02 [-0.05, +0.06] (not distinguishable) |
| ordinal vs softmax head (embeddings) | e2h_mpnet_head_ce -> e2o_mpnet_head_ordinal | -0.01 [-0.03, +0.02] (not distinguishable) | -0.03 [-0.10, +0.02] (not distinguishable) |
| chunk logistic regression vs attention MIL | e2_mpnet_lr -> e5_mpnet_mil | -0.01 [-0.07, +0.05] (not distinguishable) | -0.01 [-0.12, +0.09] (not distinguishable) |
| ordinal vs softmax head (MIL) | e5_mpnet_mil -> e5o_mpnet_mil_ordinal | -0.03 [-0.10, +0.04] (not distinguishable) | -0.02 [-0.12, +0.09] (not distinguishable) |
| synthetic messages in training (MIL) | e5_mpnet_mil -> e5s_mpnet_mil_syn | -0.10 [-0.18, -0.02] (distinguishable) | -0.06 [-0.17, +0.04] (not distinguishable) |
| frozen embeddings + MIL vs fine-tuned DistilRoBERTa | e5_mpnet_mil -> e3_distilroberta_ft | +0.03 [-0.03, +0.10] (not distinguishable) | +0.01 [-0.10, +0.12] (not distinguishable) |
| ordinal vs softmax head (fine-tuned) | e3_distilroberta_ft -> e3o_distilroberta_ft_ordinal | -0.01 [-0.03, +0.02] (not distinguishable) | +0.01 [-0.06, +0.07] (not distinguishable) |
| synthetic messages in training (fine-tuned) | e3_distilroberta_ft -> e3s_distilroberta_ft_syn | +0.02 [-0.01, +0.05] (not distinguishable) | +0.05 [-0.01, +0.12] (not distinguishable) |
| five psychiatrist labels vs three urgency labels (whole documents) | m1_doc_tfidf -> n5_m1_doc_tfidf | +0.00 [-0.01, +0.01] (not distinguishable) | -0.02 [-0.06, +0.03] (not distinguishable) |
| five psychiatrist labels vs three urgency labels (TF-IDF chunks) | e1_chunk_tfidf -> n5_e1_chunk_tfidf | -0.00 [-0.01, +0.01] (not distinguishable) | +0.00 [-0.03, +0.04] (not distinguishable) |
| five psychiatrist labels vs three urgency labels (MPNet + LR) | e2_mpnet_lr -> n5_e2_mpnet_lr | +0.00 [-0.01, +0.01] (not distinguishable) | -0.01 [-0.05, +0.04] (not distinguishable) |
| five psychiatrist labels vs three urgency labels (MiniLM + LR) | e2_minilm_lr -> n5_e2_minilm_lr | +0.00 [-0.01, +0.02] (not distinguishable) | +0.02 [-0.04, +0.07] (not distinguishable) |
| 5-level ordinal head vs 3-class softmax head | e2h_mpnet_head_ce -> n5_e2o_mpnet_head_ordinal | -0.02 [-0.05, +0.01] (not distinguishable) | -0.04 [-0.10, +0.03] (not distinguishable) |

## 4. Sensitivity to the label mapping (`lenient`: Indicator counted as Low)

| Model | AUROC | Review-30% | Macro-F1 | High recall at argmax |
| --- | --- | --- | --- | --- |
| m1_doc_tfidf | 0.71 | 48% | 0.54 | 33% |
| e2_mpnet_lr | 0.69 | 51% | 0.45 | 48% |
| e2s_mpnet_lr_syn | 0.69 | 50% | 0.40 | 43% |
| e5_mpnet_mil | 0.67 | 53% | 0.48 | 49% |
| e5s_mpnet_mil_syn | 0.57 | 36% | 0.34 | 30% |
| e3_distilroberta_ft | 0.70 | 49% | 0.49 | 50% |
| n5_m1_doc_tfidf | 0.70 | 48% | 0.36 | 43% |
| n5_e2_mpnet_lr | 0.71 | 52% | 0.39 | 73% |
| ens_x1_m1_mpnet | 0.73 | 50% | 0.52 | 36% |

## 5. The decision layer on top of each model (documents; rule layer off because long histories contain explicit phrases everywhere)

Cost-sensitive policy: a case goes to a human when the model is unsure (confidence below the threshold) or when a person is cheaper than any automated choice; otherwise the cheapest action is taken. 'High cases nobody reads' are High cases the system would have treated as ordinary without any human seeing them.

| Model | Min confidence | Humans read | High cases seen by a human or flagged High | High cases nobody reads | Mean cost |
| --- | --- | --- | --- | --- | --- |
| m1_doc_tfidf | 0.5 | 85% | 96/103 (93%) | 7 | 0.96 |
| m1_doc_tfidf | 0.6 | 92% | 98/103 (95%) | 5 | 0.99 |
| m1_doc_tfidf | 0.7 | 97% | 99/103 (96%) | 4 | 1.01 |
| m1_doc_tfidf | 0.8 | 99% | 101/103 (98%) | 2 | 1.01 |
| e2_mpnet_lr | 0.5 | 96% | 102/103 (99%) | 1 | 0.98 |
| e2_mpnet_lr | 0.6 | 97% | 102/103 (99%) | 1 | 0.99 |
| e2_mpnet_lr | 0.7 | 98% | 103/103 (100%) | 0 | 0.99 |
| e2_mpnet_lr | 0.8 | 99% | 103/103 (100%) | 0 | 0.99 |
| e5_mpnet_mil | 0.5 | 99% | 102/103 (99%) | 1 | 1.00 |
| e5_mpnet_mil | 0.6 | 99% | 102/103 (99%) | 1 | 1.00 |
| e5_mpnet_mil | 0.7 | 99% | 102/103 (99%) | 1 | 1.00 |
| e5_mpnet_mil | 0.8 | 100% | 103/103 (100%) | 0 | 1.00 |
| e3_distilroberta_ft | 0.5 | 93% | 100/103 (97%) | 3 | 0.98 |
| e3_distilroberta_ft | 0.6 | 95% | 100/103 (97%) | 3 | 0.99 |
| e3_distilroberta_ft | 0.7 | 97% | 103/103 (100%) | 0 | 0.98 |
| e3_distilroberta_ft | 0.8 | 98% | 103/103 (100%) | 0 | 0.99 |
| ens_prespecified | 0.5 | 100% | 103/103 (100%) | 0 | 1.00 |
| ens_prespecified | 0.6 | 100% | 103/103 (100%) | 0 | 1.00 |
| ens_prespecified | 0.7 | 100% | 103/103 (100%) | 0 | 1.00 |
| ens_prespecified | 0.8 | 100% | 103/103 (100%) | 0 | 1.00 |

## 6. Workload on ORDINARY support chat (ESConv seeker messages, 6,000 sampled)

ESConv is real chat-style emotional-support conversation (academic-research-only licence, so it is used **only** for this audit, never for training). Almost all of it is ordinary distress, so a system that sends many of these messages to a human or calls them High is raising false alarms and would swamp reviewers. We do not know the true urgency of each message (nobody has labelled them); a few may be genuinely concerning. Temperature scaling was fitted on documents, so message-level confidence is **not verified**.

| Model | Rule layer flags | Policy min confidence | Sent to a human | Final: low | medium | high |
| --- | --- | --- | --- | --- | --- | --- |
| m1_doc_tfidf | 0% | 0.50 | 34% | 0% | 74% | 26% |
| m1_doc_tfidf | 0% | 0.60 | 58% | 0% | 74% | 26% |
| m1_doc_tfidf | 0% | 0.70 | 81% | 0% | 74% | 26% |
| m1_doc_tfidf | 0% | 0.80 | 94% | 0% | 74% | 26% |
| e1_chunk_tfidf | 0% | 0.50 | 93% | 0% | 8% | 92% |
| e1_chunk_tfidf | 0% | 0.60 | 94% | 0% | 8% | 92% |
| e1_chunk_tfidf | 0% | 0.70 | 95% | 0% | 8% | 92% |
| e1_chunk_tfidf | 0% | 0.80 | 97% | 0% | 8% | 92% |
| n5_e2_minilm_lr | 0% | 0.50 | 99% | 0% | 1% | 99% |
| n5_e2_minilm_lr | 0% | 0.60 | 100% | 0% | 1% | 99% |
| n5_e2_minilm_lr | 0% | 0.70 | 100% | 0% | 1% | 99% |
| n5_e2_minilm_lr | 0% | 0.80 | 100% | 0% | 1% | 99% |
| n5_e2_mpnet_lr | 0% | 0.50 | 99% | 0% | 2% | 98% |
| n5_e2_mpnet_lr | 0% | 0.60 | 99% | 0% | 2% | 98% |
| n5_e2_mpnet_lr | 0% | 0.70 | 100% | 0% | 2% | 98% |
| n5_e2_mpnet_lr | 0% | 0.80 | 100% | 0% | 2% | 98% |
| e2_mpnet_lr | 0% | 0.50 | 86% | 3% | 11% | 86% |
| e2_mpnet_lr | 0% | 0.60 | 88% | 3% | 11% | 86% |
| e2_mpnet_lr | 0% | 0.70 | 90% | 3% | 11% | 86% |
| e2_mpnet_lr | 0% | 0.80 | 94% | 3% | 11% | 86% |
| e2s_mpnet_lr_syn | 0% | 0.50 | 62% | 17% | 21% | 62% |
| e2s_mpnet_lr_syn | 0% | 0.60 | 65% | 17% | 21% | 62% |
| e2s_mpnet_lr_syn | 0% | 0.70 | 67% | 17% | 21% | 62% |
| e2s_mpnet_lr_syn | 0% | 0.80 | 72% | 17% | 21% | 62% |
| e5_mpnet_mil | 0% | 0.50 | 99% | 0% | 2% | 98% |
| e5_mpnet_mil | 0% | 0.60 | 99% | 0% | 2% | 98% |
| e5_mpnet_mil | 0% | 0.70 | 100% | 0% | 2% | 98% |
| e5_mpnet_mil | 0% | 0.80 | 100% | 0% | 2% | 98% |
| e5s_mpnet_mil_syn | 0% | 0.50 | 99% | 0% | 2% | 98% |
| e5s_mpnet_mil_syn | 0% | 0.60 | 100% | 0% | 2% | 98% |
| e5s_mpnet_mil_syn | 0% | 0.70 | 100% | 0% | 2% | 98% |
| e5s_mpnet_mil_syn | 0% | 0.80 | 100% | 0% | 2% | 98% |
| e3_distilroberta_ft | 0% | 0.50 | 91% | 0% | 9% | 91% |
| e3_distilroberta_ft | 0% | 0.60 | 91% | 0% | 9% | 91% |
| e3_distilroberta_ft | 0% | 0.70 | 92% | 0% | 9% | 91% |
| e3_distilroberta_ft | 0% | 0.80 | 96% | 0% | 9% | 91% |
| e3s_distilroberta_ft_syn | 0% | 0.50 | 26% | 56% | 18% | 26% |
| e3s_distilroberta_ft_syn | 0% | 0.60 | 28% | 56% | 18% | 26% |
| e3s_distilroberta_ft_syn | 0% | 0.70 | 31% | 56% | 18% | 26% |
| e3s_distilroberta_ft_syn | 0% | 0.80 | 34% | 56% | 18% | 26% |
| ens_prespecified | 0% | 0.50 | 100% | 0% | 0% | 100% |
| ens_prespecified | 0% | 0.60 | 100% | 0% | 0% | 100% |
| ens_prespecified | 0% | 0.70 | 100% | 0% | 0% | 100% |
| ens_prespecified | 0% | 0.80 | 100% | 0% | 0% | 100% |

## 7. Challenge set (hand-written by the code author; NOT gold, NOT independent, regression and false-alarm check only)

Rule layer alone: benign items kept low 41/41; items that should escalate handled 19/31.

| System | Benign kept low | Should-escalate met | Implicit High caught | Model alone: benign kept low | Model alone: should-escalate met |
| --- | --- | --- | --- | --- | --- |
| m1_doc_tfidf + rules + policy | 0/41 | 28/31 | 3/4 | 0/41 | 24/31 |
| e1_chunk_tfidf + rules + policy | 0/41 | 31/31 | 4/4 | 0/41 | 30/31 |
| n5_e2_minilm_lr + rules + policy | 0/41 | 31/31 | 4/4 | 0/41 | 31/31 |
| n5_e2_mpnet_lr + rules + policy | 0/41 | 31/31 | 4/4 | 0/41 | 31/31 |
| e2_mpnet_lr + rules + policy | 0/41 | 31/31 | 4/4 | 0/41 | 31/31 |
| e2s_mpnet_lr_syn + rules + policy | 17/41 | 31/31 | 4/4 | 17/41 | 31/31 |
| e5_mpnet_mil + rules + policy | 0/41 | 31/31 | 4/4 | 0/41 | 31/31 |
| e5s_mpnet_mil_syn + rules + policy | 0/41 | 31/31 | 4/4 | 0/41 | 31/31 |
| e3_distilroberta_ft + rules + policy | 0/41 | 31/31 | 4/4 | 0/41 | 31/31 |
| e3s_distilroberta_ft_syn + rules + policy | 39/41 | 30/31 | 4/4 | 39/41 | 27/31 |
| ens_prespecified + rules + policy | 0/41 | 31/31 | 4/4 | 0/41 | 31/31 |

## 8. Assuming a lower High rate (prior shift): the false-alarm / missed-case trade-off

The models learned from a population where about a quarter of users are High. Ordinary chat has far fewer. Re-weighting the probabilities for a lower assumed High share reduces false alarms and, unavoidably, raises the risk of missing real cases. **The right value is a safety decision for the project owner and a clinician, to be taken from real message data. The default is no shift.** The rule layer and the check-in floor are unaffected by this setting.

| System | Assumed High share | Ordinary chat sent to a human (ESConv, min conf 0.6) | Challenge: benign kept Low | Challenge: should-escalate met | Implicit High caught |
| --- | --- | --- | --- | --- | --- |
| m1_doc_tfidf | no shift (24%) | 58% | 0/41 | 28/31 | 3/4 |
| m1_doc_tfidf | 10% | 30% | 0/41 | 26/31 | 1/4 |
| m1_doc_tfidf | 5% | 27% | 0/41 | 25/31 | 1/4 |
| m1_doc_tfidf | 2% | 25% | 0/41 | 25/31 | 1/4 |
| e1_chunk_tfidf | no shift (24%) | 94% | 0/41 | 31/31 | 4/4 |
| e1_chunk_tfidf | 10% | 79% | 0/41 | 31/31 | 4/4 |
| e1_chunk_tfidf | 5% | 60% | 0/41 | 29/31 | 4/4 |
| e1_chunk_tfidf | 2% | 35% | 0/41 | 28/31 | 3/4 |
| n5_e2_minilm_lr | no shift (24%) | 100% | 0/41 | 31/31 | 4/4 |
| n5_e2_minilm_lr | 10% | 93% | 0/41 | 31/31 | 4/4 |
| n5_e2_minilm_lr | 5% | 77% | 0/41 | 30/31 | 3/4 |
| n5_e2_minilm_lr | 2% | 45% | 0/41 | 28/31 | 1/4 |
| n5_e2_mpnet_lr | no shift (24%) | 99% | 0/41 | 31/31 | 4/4 |
| n5_e2_mpnet_lr | 10% | 92% | 0/41 | 31/31 | 4/4 |
| n5_e2_mpnet_lr | 5% | 75% | 0/41 | 31/31 | 4/4 |
| n5_e2_mpnet_lr | 2% | 46% | 0/41 | 29/31 | 3/4 |
| e2_mpnet_lr | no shift (24%) | 88% | 0/41 | 31/31 | 4/4 |
| e2_mpnet_lr | 10% | 75% | 0/41 | 31/31 | 4/4 |
| e2_mpnet_lr | 5% | 64% | 0/41 | 31/31 | 4/4 |
| e2_mpnet_lr | 2% | 47% | 1/41 | 30/31 | 3/4 |
| e2s_mpnet_lr_syn | no shift (24%) | 65% | 17/41 | 31/31 | 4/4 |
| e2s_mpnet_lr_syn | 10% | 44% | 26/41 | 29/31 | 3/4 |
| e2s_mpnet_lr_syn | 5% | 31% | 30/41 | 28/31 | 3/4 |
| e2s_mpnet_lr_syn | 2% | 21% | 32/41 | 27/31 | 3/4 |
| e5_mpnet_mil | no shift (24%) | 99% | 0/41 | 31/31 | 4/4 |
| e5_mpnet_mil | 10% | 86% | 0/41 | 30/31 | 4/4 |
| e5_mpnet_mil | 5% | 67% | 0/41 | 28/31 | 3/4 |
| e5_mpnet_mil | 2% | 54% | 0/41 | 25/31 | 1/4 |
| e5s_mpnet_mil_syn | no shift (24%) | 100% | 0/41 | 31/31 | 4/4 |
| e5s_mpnet_mil_syn | 10% | 79% | 0/41 | 31/31 | 4/4 |
| e5s_mpnet_mil_syn | 5% | 63% | 0/41 | 27/31 | 3/4 |
| e5s_mpnet_mil_syn | 2% | 55% | 0/41 | 25/31 | 1/4 |
| e3_distilroberta_ft | no shift (24%) | 91% | 0/41 | 31/31 | 4/4 |
| e3_distilroberta_ft | 10% | 69% | 0/41 | 31/31 | 4/4 |
| e3_distilroberta_ft | 5% | 60% | 0/41 | 31/31 | 4/4 |
| e3_distilroberta_ft | 2% | 42% | 0/41 | 31/31 | 4/4 |
| e3s_distilroberta_ft_syn | no shift (24%) | 28% | 39/41 | 30/31 | 4/4 |
| e3s_distilroberta_ft_syn | 10% | 22% | 39/41 | 30/31 | 4/4 |
| e3s_distilroberta_ft_syn | 5% | 17% | 39/41 | 30/31 | 4/4 |
| e3s_distilroberta_ft_syn | 2% | 12% | 39/41 | 30/31 | 4/4 |
| ens_prespecified | no shift (24%) | 100% | 0/41 | 31/31 | 4/4 |
| ens_prespecified | 10% | 96% | 0/41 | 31/31 | 4/4 |
| ens_prespecified | 5% | 78% | 0/41 | 31/31 | 4/4 |
| ens_prespecified | 2% | 40% | 0/41 | 26/31 | 1/4 |

## 9. Sensitivity to the cost matrix (the matrix is awaiting clinical review)

How the decision layer behaves if a missed High case is judged to cost 3, 5, 10 (the default) or 20 times a false escalation. Documents, rule layer off, minimum confidence 0.6. If conclusions flipped between rows, the result would depend on one guess; the trend, more review for a higher miss cost, is what a clinician should weigh.

| Model | Miss-High cost | Humans read | High cases seen | High cases nobody reads |
| --- | --- | --- | --- | --- |
| m1_doc_tfidf | 3x | 67% | 72/103 (70%) | 31 |
| m1_doc_tfidf | 5x | 80% | 89/103 (86%) | 14 |
| m1_doc_tfidf | 10x | 92% | 98/103 (95%) | 5 |
| m1_doc_tfidf | 20x | 98% | 101/103 (98%) | 2 |
| e2_mpnet_lr | 3x | 91% | 101/103 (98%) | 2 |
| e2_mpnet_lr | 5x | 93% | 101/103 (98%) | 2 |
| e2_mpnet_lr | 10x | 97% | 102/103 (99%) | 1 |
| e2_mpnet_lr | 20x | 99% | 103/103 (100%) | 0 |
| e5_mpnet_mil | 3x | 95% | 99/103 (96%) | 4 |
| e5_mpnet_mil | 5x | 96% | 101/103 (98%) | 2 |
| e5_mpnet_mil | 10x | 99% | 102/103 (99%) | 1 |
| e5_mpnet_mil | 20x | 100% | 103/103 (100%) | 0 |
| e3_distilroberta_ft | 3x | 88% | 98/103 (95%) | 5 |
| e3_distilroberta_ft | 5x | 91% | 99/103 (96%) | 4 |
| e3_distilroberta_ft | 10x | 95% | 100/103 (97%) | 3 |
| e3_distilroberta_ft | 20x | 97% | 103/103 (100%) | 0 |
| ens_prespecified | 3x | 99% | 103/103 (100%) | 0 |
| ens_prespecified | 5x | 100% | 103/103 (100%) | 0 |
| ens_prespecified | 10x | 100% | 103/103 (100%) | 0 |
| ens_prespecified | 20x | 100% | 103/103 (100%) | 0 |
