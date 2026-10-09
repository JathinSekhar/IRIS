"""Builds reports/phase2_results.md and phase2_metrics.json from cached experiment results.

Every number in the report is computed here from the cached out-of-fold predictions or from the audits; nothing is typed in.
Only development users are used. The held-out test users and the gold set are never loaded.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import ROOT, URGENCY, embeddings
from .decision import DecisionPolicy, simulate
from .experiments import ART, LEVELS, Prepared, Result, Spec, ensemble_result, prepare, run_spec, summarise
from .ranking import auroc_high, mcnemar_exact, paired_bootstrap_diff, recall_at_review_rate
from .run_phase2 import SPECS
from .system import TriageSystem, challenge, ensemble_system, esconv_messages, fit_final, with_prior, workload

REPORTS = ROOT / "reports"
BASELINE = "m1_doc_tfidf"
# The ONE ensemble defined before any ensemble result was seen (message-capable members only). The others are exploratory
# and are reported too, so the reader can see how many were tried.
PRESPEC_ENSEMBLE = ("ens_prespecified", ["n5_e2_minilm_lr", "n5_e2_mpnet_lr", "e1_chunk_tfidf"])
EXPLORATORY_ENSEMBLES = {
    "ens_x1_m1_mpnet": ["m1_doc_tfidf", "e2_mpnet_lr"],
    "ens_x2_m1_minilm_mpnet": ["m1_doc_tfidf", "e2_minilm_lr", "e2_mpnet_lr"],
    "ens_x3_m1_n5minilm_n5mpnet": ["m1_doc_tfidf", "n5_e2_minilm_lr", "n5_e2_mpnet_lr"],
    "ens_x4_five": ["m1_doc_tfidf", "e1_chunk_tfidf", "e2_minilm_lr", "e2_mpnet_lr", "e5_mpnet_mil"],
}
ENSEMBLES = {PRESPEC_ENSEMBLE[0]: PRESPEC_ENSEMBLE[1], **EXPLORATORY_ENSEMBLES}
AUDITED = ["m1_doc_tfidf", "e1_chunk_tfidf", "n5_e2_minilm_lr", "n5_e2_mpnet_lr", "e2_mpnet_lr", "e2s_mpnet_lr_syn",
           "e5_mpnet_mil", "e5s_mpnet_mil_syn", "e3_distilroberta_ft", "e3s_distilroberta_ft_syn"]
AUDITED_ENSEMBLES = [PRESPEC_ENSEMBLE[0]]
PAIRS = [  # (A, B, what it tests). B minus A.
    ("e1_chunk_tfidf", "m1_doc_tfidf", "documents vs chunks (TF-IDF)"),
    ("e2_minilm_lr", "e2_mpnet_lr", "MiniLM vs MPNet embeddings"),
    ("e2_mpnet_lr", "e2s_mpnet_lr_syn", "synthetic messages in training (embeddings + LR)"),
    ("e1_chunk_tfidf", "e1s_chunk_tfidf_syn", "synthetic messages in training (TF-IDF)"),
    ("e2h_mpnet_head_ce", "e2o_mpnet_head_ordinal", "ordinal vs softmax head (embeddings)"),
    ("e2_mpnet_lr", "e5_mpnet_mil", "chunk logistic regression vs attention MIL"),
    ("e5_mpnet_mil", "e5o_mpnet_mil_ordinal", "ordinal vs softmax head (MIL)"),
    ("e5_mpnet_mil", "e5s_mpnet_mil_syn", "synthetic messages in training (MIL)"),
    ("e5_mpnet_mil", "e3_distilroberta_ft", "frozen embeddings + MIL vs fine-tuned DistilRoBERTa"),
    ("e3_distilroberta_ft", "e3o_distilroberta_ft_ordinal", "ordinal vs softmax head (fine-tuned)"),
    ("e3_distilroberta_ft", "e3s_distilroberta_ft_syn", "synthetic messages in training (fine-tuned)"),
    ("m1_doc_tfidf", "n5_m1_doc_tfidf", "five psychiatrist labels vs three urgency labels (whole documents)"),
    ("e1_chunk_tfidf", "n5_e1_chunk_tfidf", "five psychiatrist labels vs three urgency labels (TF-IDF chunks)"),
    ("e2_mpnet_lr", "n5_e2_mpnet_lr", "five psychiatrist labels vs three urgency labels (MPNet + LR)"),
    ("e2_minilm_lr", "n5_e2_minilm_lr", "five psychiatrist labels vs three urgency labels (MiniLM + LR)"),
    ("e2h_mpnet_head_ce", "n5_e2o_mpnet_head_ordinal", "5-level ordinal head vs 3-class softmax head"),
]


def pct(x: float) -> str:
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{100 * x:.0f}%"


def _recall30(y, s):
    return float(recall_at_review_rate(y, s, [0.3])["recall"].iloc[0])


def _load(variant: str) -> tuple[Prepared, dict[str, Result]]:
    prep = prepare(variant)
    out = {}
    for spec in SPECS:
        path = ART / f"{variant}_{spec.name}_{spec.key()}.npz"
        if path.exists():
            out[spec.name] = run_spec(spec, prep, verbose=False)
    for name, members in ENSEMBLES.items():
        if all(m in out for m in members):
            out[name] = ensemble_result(name, [out[m] for m in members])
    return prep, out


def paired(y, ra: Result, rb: Result, seed: int = 0) -> dict:
    sa, sb = ra.cal[0][:, 2], rb.cal[0][:, 2]                       # P(High), repeat 0 (same folds for every model)
    au = paired_bootstrap_diff(auroc_high, y, sa, sb, n_boot=1500, seed=seed)
    r30 = paired_bootstrap_diff(_recall30, y, sa, sb, n_boot=1500, seed=seed)
    k = int(np.ceil(0.3 * len(y)))
    high = y == 2
    top = lambda s: np.isin(np.arange(len(y)), np.lexsort((np.arange(len(y)), -s))[:k])[high]
    return {"auroc": au, "recall30": r30, "mcnemar": mcnemar_exact(top(sa), top(sb))}


def _fmt_diff(d: dict) -> str:
    mark = "distinguishable" if d["distinguishable"] else "not distinguishable"
    return f"{d['diff']:+.2f} [{d['ci_low']:+.2f}, {d['ci_high']:+.2f}] ({mark})"


class _Lookup:
    """Message-level probabilities computed once and stored, so the report re-runs without refitting."""

    def __init__(self, texts: list[str], probs: np.ndarray):
        self.map = {t: p for t, p in zip(texts, probs)}

    def __call__(self, texts):
        return np.array([self.map[t] for t in texts])


def audit_systems(prep: Prepared, results: dict[str, Result], esconv: list[str], challenge_texts: list[str]) -> dict:
    ART.mkdir(parents=True, exist_ok=True)
    systems: dict[str, TriageSystem] = {}
    temps: dict[str, float] = {}
    for name in AUDITED:
        if name not in results:
            continue
        spec = next(s for s in SPECS if s.name == name)
        path = ART / f"audit_{prep.variant}_{name}_{spec.key()}.npz"
        temps[name] = float(results[name].temps.mean())
        if path.exists():
            probs = np.load(path, allow_pickle=True)["probs"]
        elif spec.family == "finetune":
            # Fine-tuning is never run on the development laptop. Its audit comes from the Colab run (ml/colab/README.md).
            print(f"   skipped audit for {name}: no Colab audit file found ({path.name})", flush=True)
            temps.pop(name, None)
            continue
        else:
            print(f"   final fit + audit: {name}", flush=True)
            probs = fit_final(spec, prep, embeddings.embed, temps[name]).predict_proba(esconv + challenge_texts)
            np.savez(path, probs=probs)
        systems[name] = TriageSystem(name, _Lookup(esconv + challenge_texts, probs), temps[name])
    for ens in AUDITED_ENSEMBLES:
        members = ENSEMBLES[ens]
        if all(m in systems for m in members):
            systems[ens] = ensemble_system(ens, [systems[m] for m in members])
            temps[ens] = float(np.mean([temps[m] for m in members]))
    out = {}
    src = np.bincount(prep.y, minlength=3) / len(prep.y)
    for name, sys_ in systems.items():
        sweep = {}
        for hi in (None, 0.10, 0.05, 0.02):
            ps = with_prior(sys_, src, hi)
            sweep["none" if hi is None else f"{hi:.2f}"] = {
                "workload": workload(ps, esconv, min_confidences=(0.6,))["by_min_confidence"]["0.60"],
                "challenge": challenge(ps)}
        out[name] = {"workload": workload(sys_, esconv), "challenge": challenge(sys_),
                     "challenge_model_only": _challenge_model_only(sys_),
                     "temperature": temps[name], "prior_sweep": sweep, "dev_prior": [float(x) for x in src]}
    return out


def _challenge_model_only(system: TriageSystem) -> dict:
    from .challenge import challenge_frame, evaluate_challenge
    df = challenge_frame()
    res = system.triage_batch(list(df["text"]), use_rules=False)
    return evaluate_challenge(list(df["text"]), [r.urgency for r in res], [r.needs_human for r in res])


def build_report() -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    prep, res = _load("conservative")
    prep_l, res_l = _load("lenient")
    y = prep.y
    base = res[BASELINE]
    summ = {n: summarise(r, y) for n, r in res.items()}
    all_specs = SPECS + [Spec(n, "ensemble") for n in ENSEMBLES if n in res]

    L: list[str] = []
    w = L.append
    w("# Phase 2 results (development data only)\n")
    w(f"_Generated {now} by `python -m iris_ml.run_phase2 report`. Aggregates only; no dataset text appears here._\n")
    w("## Read this first\n")
    w("- Everything here is **development evidence on the 424 development users** (cross-validated, out-of-fold). The 76 held-out test users "
      "and the gold set were **not used**. No model was tuned against them.")
    w("- **These are not safety or performance claims about IRIS.** The label mapping is unreviewed, the data is long forum history "
      "rather than chat, and the gold set has not been labelled.")
    w("- Intervals are 95%. With about 100 High cases, differences smaller than roughly 0.05 AUROC or 12 points of recall cannot be detected, "
      "so results marked *not distinguishable* are ties, not small wins.\n")

    # ---- T1
    w("## 1. Every model (primary mapping `conservative`, repeat 0)\n")
    w("`Review x%` = share of High cases found when reviewers read the top x% of users ranked by the model (reading at random finds x%).\n")
    w("| Model | Family | Synthetic data | AUROC | Review 10% | 20% | **30%** | 40% | 50% | Macro-F1 | Kappa | ECE raw -> cal |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for s in all_specs:
        if s.name not in summ:
            continue
        m = summ[s.name]["repeat0"]
        ra = m["recall_at"]
        w(f"| {s.name} | {s.family} | {'yes' if s.syn else 'no'} | {m['auroc_high']:.2f} | {pct(ra['10%'])} | {pct(ra['20%'])} | **{pct(ra['30%'])}** | "
          f"{pct(ra['40%'])} | {pct(ra['50%'])} | {m['macro_f1']:.2f} | {m['qwk']:.2f} | {m['ece_raw']:.3f} -> {m['ece_cal']:.3f} |")
    sd_rows = [(n, v) for n, v in summ.items() if "auroc_high_sd" in v]
    if sd_rows:
        w("\nSplit-to-split spread (3 repeats of 5-fold CV; models with one repeat are omitted):\n")
        w("| Model | AUROC mean (sd) | Review-30% mean (sd) | Macro-F1 mean (sd) |\n| --- | --- | --- | --- |")
        for n, v in sd_rows:
            w(f"| {n} | {v['auroc_high_mean']:.2f} ({v['auroc_high_sd']:.3f}) | {pct(v['recall_at_30_mean'])} ({100 * v['recall_at_30_sd']:.1f} pts) | "
              f"{v['macro_f1_mean']:.2f} ({v['macro_f1_sd']:.3f}) |")

    # ---- T2
    w("\n## 2. Compared with the Phase 1 baseline (M1, TF-IDF on whole documents)\n")
    w("Paired bootstrap on the same users and folds; difference = model minus M1. 'Review 30%' is High cases found when reading the top 30%.\n")
    w("| Model | AUROC difference | Review-30% difference | McNemar (High found in top 30%) |\n| --- | --- | --- | --- |")
    cmp_ = {}
    for s in all_specs:
        if s.name == BASELINE or s.name not in res:
            continue
        pr = paired(y, base, res[s.name])
        cmp_[s.name] = pr
        w(f"| {s.name} | {_fmt_diff(pr['auroc'])} | {_fmt_diff(pr['recall30'])} | M1 only {pr['mcnemar']['only_a_correct']} / model only "
          f"{pr['mcnemar']['only_b_correct']}, p = {pr['mcnemar']['p_value']:.2f} |")

    # ---- T3
    w("\n## 3. Ablations (what each design choice did)\n")
    w("| Question | A -> B | AUROC difference | Review-30% difference |\n| --- | --- | --- | --- |")
    abl = []
    for a, b, what in PAIRS:
        if a in res and b in res:
            pr = paired(y, res[a], res[b])
            abl.append({"question": what, "a": a, "b": b, **pr})
            w(f"| {what} | {a} -> {b} | {_fmt_diff(pr['auroc'])} | {_fmt_diff(pr['recall30'])} |")

    # ---- T4
    w("\n## 4. Sensitivity to the label mapping (`lenient`: Indicator counted as Low)\n")
    w("| Model | AUROC | Review-30% | Macro-F1 | High recall at argmax |\n| --- | --- | --- | --- | --- |")
    lenient = {}
    for n, r in res_l.items():
        s = summarise(r, prep_l.y)["repeat0"]
        lenient[n] = s
        w(f"| {n} | {s['auroc_high']:.2f} | {pct(s['recall_at']['30%'])} | {s['macro_f1']:.2f} | {pct(s['high_recall_argmax']['recall'])} |")

    # ---- T5
    w("\n## 5. The decision layer on top of each model (documents; rule layer off because long histories contain explicit phrases everywhere)\n")
    w("Cost-sensitive policy: a case goes to a human when the model is unsure (confidence below the threshold) or when a person is "
      "cheaper than any automated choice; otherwise the cheapest action is taken. 'High cases nobody reads' are High cases the system "
      "would have treated as ordinary without any human seeing them.\n")
    w("| Model | Min confidence | Humans read | High cases seen by a human or flagged High | High cases nobody reads | Mean cost |\n| --- | --- | --- | --- | --- | --- |")
    texts = prep.dev["text"].tolist()
    sims = {}
    for n in [BASELINE] + [x for x in ("e2_mpnet_lr", "e5_mpnet_mil", "e3_distilroberta_ft", PRESPEC_ENSEMBLE[0]) if x in res]:
        for mc in (0.5, 0.6, 0.7, 0.8):
            sm = simulate(y, res[n].cal[0], texts, DecisionPolicy(min_confidence=mc), use_rules=False)
            sims[f"{n}@{mc}"] = sm
            w(f"| {n} | {mc:.1f} | {pct(sm['human_review_rate'])} | {sm['high_caught']}/{sm['high_total']} ({pct(sm['high_recall'])}) | "
              f"{sm['high_auto_missed']} | {sm['mean_cost']:.2f} |")

    # ---- T6, T7
    esc = esconv_messages(6000)
    ch_texts = list(__import__("iris_ml.challenge", fromlist=["x"]).challenge_frame()["text"])
    audits = audit_systems(prep, res, esc, ch_texts)
    w("\n## 6. Workload on ORDINARY support chat (ESConv seeker messages, 6,000 sampled)\n")
    w("ESConv is real chat-style emotional-support conversation (academic-research-only licence, so it is used **only** for this audit, "
      "never for training). Almost all of it is ordinary distress, so a system that sends many of these messages to a human or "
      "calls them High is raising false alarms and would swamp reviewers. We do not know the true urgency of each message (nobody "
      "has labelled them); a few may be genuinely concerning. Temperature scaling was fitted on documents, so message-level "
      "confidence is **not verified**.\n")
    w("| Model | Rule layer flags | Policy min confidence | Sent to a human | Final: low | medium | high |\n| --- | --- | --- | --- | --- | --- | --- |")
    for n, a in audits.items():
        for mc, v in a["workload"]["by_min_confidence"].items():
            w(f"| {n} | {pct(a['workload']['rule_flag_rate'])} | {mc} | {pct(v['needs_human'])} | {pct(v['final_low'])} | {pct(v['final_medium'])} | {pct(v['final_high'])} |")
    w("\n## 7. Challenge set (hand-written by the code author; NOT gold, NOT independent, regression and false-alarm check only)\n")
    rules_only = challenge(None)
    w(f"Rule layer alone: benign items kept low {rules_only['benign_stay_low']['passed']}/{rules_only['benign_stay_low']['total']}; "
      f"items that should escalate handled {rules_only['must_escalate_met']['passed']}/{rules_only['must_escalate_met']['total']}.\n")
    w("| System | Benign kept low | Should-escalate met | Implicit High caught | Model alone: benign kept low | Model alone: should-escalate met |\n| --- | --- | --- | --- | --- | --- |")
    for n, a in audits.items():
        c, cm = a["challenge"], a["challenge_model_only"]
        ih = c["by_category"].get("implicit_high", {"passed": 0, "total": 0})
        w(f"| {n} + rules + policy | {c['benign_stay_low']['passed']}/{c['benign_stay_low']['total']} | "
          f"{c['must_escalate_met']['passed']}/{c['must_escalate_met']['total']} | {ih['passed']}/{ih['total']} | "
          f"{cm['benign_stay_low']['passed']}/{cm['benign_stay_low']['total']} | {cm['must_escalate_met']['passed']}/{cm['must_escalate_met']['total']} |")

    w("\n## 8. Assuming a lower High rate (prior shift): the false-alarm / missed-case trade-off\n")
    w("The models learned from a population where about a quarter of users are High. Ordinary chat has far fewer. Re-weighting the "
      "probabilities for a lower assumed High share reduces false alarms and, unavoidably, raises the risk of missing real cases. "
      "**The right value is a safety decision for the project owner and a clinician, to be taken from real message data. The default "
      "is no shift.** The rule layer and the check-in floor are unaffected by this setting.\n")
    w("| System | Assumed High share | Ordinary chat sent to a human (ESConv, min conf 0.6) | Challenge: benign kept Low | Challenge: should-escalate met | Implicit High caught |\n| --- | --- | --- | --- | --- | --- |")
    for n, a in audits.items():
        for hi, v in a["prior_sweep"].items():
            c = v["challenge"]
            ih = c["by_category"].get("implicit_high", {"passed": 0, "total": 0})
            w(f"| {n} | {'no shift (' + format(a['dev_prior'][2], '.0%') + ')' if hi == 'none' else format(float(hi), '.0%')} | {pct(v['workload']['needs_human'])} | "
              f"{c['benign_stay_low']['passed']}/{c['benign_stay_low']['total']} | {c['must_escalate_met']['passed']}/{c['must_escalate_met']['total']} | "
              f"{ih['passed']}/{ih['total']} |")

    w("\n## 9. Sensitivity to the cost matrix (the matrix is awaiting clinical review)\n")
    w("How the decision layer behaves if a missed High case is judged to cost 3, 5, 10 (the default) or 20 times a false escalation. "
      "Documents, rule layer off, minimum confidence 0.6. If conclusions flipped between rows, the result would depend on one guess; "
      "the trend, more review for a higher miss cost, is what a clinician should weigh.\n")
    w("| Model | Miss-High cost | Humans read | High cases seen | High cases nobody reads |\n| --- | --- | --- | --- | --- |")
    from .metrics import load_costs
    base_m, _ = load_costs()
    cost_sweep = {}
    for n in [BASELINE] + [x for x in ("e2_mpnet_lr", "e5_mpnet_mil", "e3_distilroberta_ft", PRESPEC_ENSEMBLE[0]) if x in res]:
        for c in (3, 5, 10, 20):
            m = base_m.copy()
            m[2, 0] = float(c)
            m[2, 1] = c * 0.4
            sm = simulate(y, res[n].cal[0], texts, DecisionPolicy(min_confidence=0.6, cost_matrix=m), use_rules=False)
            cost_sweep[f"{n}@{c}"] = sm
            w(f"| {n} | {c}x | {pct(sm['human_review_rate'])} | {sm['high_caught']}/{sm['high_total']} ({pct(sm['high_recall'])}) | {sm['high_auto_missed']} |")

    meta = {"generated": now, "n_dev": int(len(y)), "n_chunks": int(len(prep.chunks)), "n_synthetic": int(len(prep.synth)),
            "device": __import__("torch").cuda.get_device_name(0) if __import__("torch").cuda.is_available() else "cpu"}
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "phase2_results.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (REPORTS / "phase2_metrics.json").write_text(json.dumps(
        {"meta": meta, "summary": summ, "paired_vs_m1": cmp_, "ablations": abl, "lenient": lenient, "simulations": sims,
         "audits": audits, "rules_only_challenge": rules_only, "cost_sweep": cost_sweep}, indent=1, default=float), encoding="utf-8")
    print("report ->", REPORTS / "phase2_results.md")
