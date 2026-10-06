"""Phase 1 in one command:   python -m iris_ml.run_phase1 [--write-manifest]

Loads the Reddit C-SSRS data, checks the frozen split, evaluates the trivial baselines, the rule layer (M0) and the
TF-IDF + logistic regression model (M1) on the development users only, and writes:
    reports/phase1_baseline.md    human-readable results (aggregates only, no text)
    reports/phase1_metrics.json   the same numbers for machines
    artifacts/m1_v0/              the fitted model (git-ignored)
The held-out TEST users are never touched here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from . import ROOT, URGENCY, URGENCY_INDEX
from .baselines import (BaselineConfig, assert_no_test, build_pipeline, majority_prediction, oof_probabilities,
                        rules_prediction, stratified_random_prediction, top_terms)
from .datasets import reddit_cssrs as rc
from .metrics import (cheapest_review_for_recall, ece, expected_cost, load_costs, review_curve, urgency_report)
from .schema import assert_valid

REPORTS = ROOT / "reports"
ARTIFACTS = ROOT / "artifacts" / "m1_v0"
RECALL_TARGET = 0.95


def _fmt_ci(r: dict) -> str:
    return f"{r['recall']:.2f} ({r['ci_low']:.2f}-{r['ci_high']:.2f}), {r['caught']}/{r['total']}"


def _row(name: str, y: np.ndarray, pred: np.ndarray) -> dict:
    rep = urgency_report(y, pred)
    rep["mean_cost"] = expected_cost(y, pred)
    rep["name"] = name
    return rep


def evaluate_variant(dev: pd.DataFrame, cfg: BaselineConfig) -> dict:
    assert_no_test(dev)
    y = dev["urgency"].map(URGENCY_INDEX).to_numpy()
    raw, cal, temp = oof_probabilities(dev["text"], y, len(URGENCY), cfg)
    out: dict = {
        "n_dev": int(len(dev)),
        "class_counts": {u: int((y == i).sum()) for i, u in enumerate(URGENCY)},
        "mean_temperature": temp,
        "models": {},
    }
    out["models"]["majority"] = _row("Majority class", y, majority_prediction(y))
    out["models"]["random"] = _row("Random (class frequencies)", y, stratified_random_prediction(y, cfg.seed))
    out["models"]["m0_rules"] = _row("M0 rules on documents", y, rules_prediction(dev["text"]))
    m1 = _row("M1 TF-IDF + logistic regression (calibrated)", y, cal.argmax(axis=1))
    m1["ece_raw"], m1["ece_calibrated"] = ece(raw, y), ece(cal, y)
    out["models"]["m1"] = m1
    curve = review_curve(y, cal, thresholds=np.round(np.linspace(0.34, 1.0, 34), 3))
    out["review_curve"] = curve.round(4).to_dict(orient="records")
    point = cheapest_review_for_recall(curve, RECALL_TARGET)
    out["review_at_target"] = None if point is None else point.round(4).to_dict()
    return out


def render_report(results: dict, meta: dict) -> str:
    L: list[str] = []
    w = L.append
    w("# Phase 1 baseline results (M0 and M1)\n")
    w(f"_Generated {meta['generated']} by `python -m iris_ml.run_phase1`. Aggregates only; no text from the dataset appears here._\n")
    w("## Read this first\n")
    w("- The data is the **Reddit C-SSRS** set: 500 users, **one long document per user**, labels from psychiatrists on "
      "the C-SSRS scale. It is **not chat messages**, it contains **only suicide-risk content** (nothing on everyday stress, "
      "logistics or greetings), and it has **500 people**.")
    w("- Mapping C-SSRS labels to IRIS urgency is a **clinical hypothesis not yet reviewed by a clinician**. Both mappings "
      "are reported; the conclusions should hold under both.")
    w("- Everything below uses development users only (train + val). The held-out **test users were not touched**.")
    w("- Intervals are 95% Wilson intervals. With this few High cases they are wide: **these numbers are a reference "
      "point for later models, not evidence that IRIS is safe.**\n")
    w("## Setup\n")
    w(f"- Dev users: {meta['n_dev']} (test users held out: {meta['n_test']}); split manifest sha256 `{meta['manifest_sha256'][:16]}...`")
    w(f"- Data file md5 verified against Zenodo: `{meta['data_md5']}`")
    w(f"- M1: TF-IDF (1-2 grams, min_df=2, {meta['cfg']['max_features']} features) + logistic regression (C={meta['cfg']['C']}, balanced); "
      f"{meta['cfg']['n_splits']}-fold x {meta['cfg']['n_repeats']} repeats, out-of-fold; temperature scaling fitted on the other folds; seed {meta['cfg']['seed']}")
    w(f"- Cost matrix (`configs/costs.yaml`): miss High = {load_costs()[0][2, 0]:g}, false escalation Low->High = {load_costs()[0][0, 2]:g}, human review = {load_costs()[1]:g}\n")
    for variant, res in results.items():
        w(f"## Urgency mapping: `{variant}`\n")
        cc = res["class_counts"]
        w(f"Dev class counts: low {cc['low']}, medium {cc['medium']}, high {cc['high']} (n = {res['n_dev']})\n")
        w("| Model | High recall (95% CI) | Macro-F1 | Quadratic kappa | Mean cost / message | ECE |")
        w("| --- | --- | --- | --- | --- | --- |")
        for key in ("majority", "random", "m0_rules", "m1"):
            m = res["models"][key]
            e = f"{m['ece_raw']:.3f} raw / {m['ece_calibrated']:.3f} calibrated" if key == "m1" else "n/a"
            w(f"| {m['name']} | {_fmt_ci(m['high_recall'])} | {m['macro_f1']:.2f} | {m['quadratic_weighted_kappa']:.2f} | {m['mean_cost']:.2f} | {e} |")
        cm = res["models"]["m1"]["confusion_matrix"]
        w("\nM1 confusion matrix (rows = true, columns = predicted):\n")
        w("| true \\ predicted | low | medium | high |\n| --- | --- | --- | --- |")
        for i, name in enumerate(URGENCY):
            w(f"| {name} | {cm[i][0]} | {cm[i][1]} | {cm[i][2]} |")
        w("\n**Human-review tradeoff** (cases below a confidence threshold go to a human who resolves them correctly):\n")
        w("| threshold | cases sent to a human | High cases caught | mean cost |\n| --- | --- | --- | --- |")
        curve = pd.DataFrame(res["review_curve"])
        for tau in (0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
            r = curve.iloc[(curve["threshold"] - tau).abs().argmin()]
            w(f"| {r['threshold']:.2f} | {r['review_rate']:.0%} | {r['high_recall']:.0%} | {r['mean_cost']:.2f} |")
        pt = res["review_at_target"]
        w("\n" + (f"To reach High recall >= {RECALL_TARGET:.0%}, M1 would have to send **{pt['review_rate']:.0%}** of messages to a human "
                  f"(threshold {pt['threshold']:.2f})." if pt else f"M1 **cannot** reach High recall >= {RECALL_TARGET:.0%} at any threshold."))
        w("(The project gate is a human-review rate of at most 30%.)\n")
    w("## What the model relies on (primary mapping, fit on all dev users)\n")
    for cls, terms in meta["top_terms"].items():
        w(f"- **{cls}**: {', '.join(terms)}")
    w("\n## Limitations\n")
    w("1. **Domain gap.** Long forum histories are very different from short chat messages. M1 here says nothing about chat performance; "
      "the team-labelled gold set (and later, consented pilot data) must measure that.")
    w("2. **Narrow label space.** No everyday-stress, emotional-support or logistics examples, so intent classification cannot be learned "
      "from this data. A model trained on it would see \"supportive\" forum replies as the only Low class.")
    w("3. **Tiny sample.** About 100 High cases at most; intervals above are wide, and per-class numbers vary a lot between splits.")
    w("4. **Per-user labels.** A user labelled Attempt wrote many neutral sentences too; document-level labels cannot be pushed down to messages.")
    w("5. **Label mapping is unreviewed.** See the two variants above.")
    w("6. **The rule layer on documents** is not what it will do on a single message: long histories contain explicit phrases "
      "even for supportive users, so its precision here is not meaningful.\n")
    w("## Citation\n")
    w("Gaur, M., Alambo, A., Sain, J. P., Kursuncu, U., Thirunarayan, K., Kavuluru, R., Sheth, A., Welton, R., Pathak, J. (2019). "
      "*Knowledge-aware Assessment of Severity of Suicide Risk for Early Intervention.* The Web Conference (WWW). "
      "Dataset: Zenodo, DOI 10.5281/zenodo.2667859, CC-BY-4.0.\n")
    w(f"_Environment: Python {meta['python']}, scikit-learn {meta['sklearn']}, numpy {meta['numpy']}, pandas {meta['pandas']}._")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write-manifest", action="store_true", help="write the split manifest once (first run only)")
    ap.add_argument("--raw", default=str(rc.RAW_PATH))
    ap.add_argument("--out", default=str(REPORTS))
    args = ap.parse_args(argv)
    cfg = BaselineConfig()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw = rc.load_raw(args.raw)
    frames = {v: rc.to_frame(raw, v) for v in rc.VARIANTS}
    for v, df in frames.items():
        assert_valid(df, max_chars=rc.MAX_DOC_CHARS)
    primary = frames[rc.PRIMARY_VARIANT]
    if args.write_manifest and not rc.MANIFEST_PATH.exists():
        print("wrote split manifest, sha256", rc.write_manifest(primary))
    rc.verify_manifest(primary)
    for v, df in frames.items():  # the held-out users must be identical under every mapping
        assert (df["split"] == primary["split"]).all()

    results = {v: evaluate_variant(df[df["split"] != "test"].reset_index(drop=True), cfg) for v, df in frames.items()}

    dev = primary[primary["split"] != "test"].reset_index(drop=True)
    assert_no_test(dev)
    pipe = build_pipeline(cfg).fit(dev["text"].str.slice(0, cfg.max_chars), dev["urgency"].map(URGENCY_INDEX))
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, ARTIFACTS / "pipeline.joblib")

    meta = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "n_dev": int(len(dev)), "n_test": int((primary["split"] == "test").sum()),
        "manifest_sha256": rc.manifest_sha256(rc.split_manifest(primary)),
        "data_md5": hashlib.md5(Path(args.raw).read_bytes()).hexdigest(),
        "cfg": cfg.__dict__, "top_terms": top_terms(pipe, URGENCY),
        "python": platform.python_version(), "sklearn": sklearn.__version__, "numpy": np.__version__, "pandas": pd.__version__,
    }
    (out_dir / "phase1_metrics.json").write_text(json.dumps({"meta": meta, "results": results}, indent=1, default=float), encoding="utf-8")
    (out_dir / "phase1_baseline.md").write_text(render_report(results, meta), encoding="utf-8")
    print("report ->", out_dir / "phase1_baseline.md")


if __name__ == "__main__":
    main()
