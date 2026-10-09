"""Phase 2 experiment engine: every model, one protocol.

Protocol (fixed in advance, identical for all models)
  * development users only (train + val of the frozen split); the 76 held-out test users and the gold set are never loaded;
  * repeated stratified 5-fold cross-validation with the SAME seed and folds for every model;
  * every user is predicted by a model that never saw that user (out-of-fold);
  * synthetic messages, when used, are added to TRAINING folds only;
  * calibration by temperature scaling fitted on the other folds;
  * results are cached to disk, keyed by the full model specification.

Families
  doc_tfidf    Phase 1 baseline (M1): TF-IDF + logistic regression on whole documents
  chunk_tfidf  TF-IDF + logistic regression on message-sized chunks (weak labels), pooled per user
  emb_lr       frozen sentence embeddings + logistic regression on chunks, pooled per user
  emb_head     frozen sentence embeddings + softmax or ORDINAL head on chunks, pooled per user
  mil          attention multiple-instance model over a user's chunk embeddings (label per user)
  finetune     DistilRoBERTa fine-tuned on chunks (GPU), pooled per user
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import RepeatedStratifiedKFold
from sklearn.pipeline import Pipeline

from . import ROOT, URGENCY, URGENCY_INDEX
from . import embeddings, neural
from .baselines import BaselineConfig, assert_no_test, build_pipeline
from .calibration import apply_temperature, crossfit_temperature
from .chunks import build_chunks
from .metrics import ece, expected_cost, load_costs, review_curve, urgency_report
from .ranking import auroc_high, pr_auc_high, recall_at_review_rate
from .synth import build_synthetic

ART = ROOT / "artifacts" / "phase2"
SEED = 2026
LEVELS = np.arange(3.0)
RATES = (0.1, 0.2, 0.3, 0.4, 0.5)


@dataclass(frozen=True)
class Spec:
    name: str
    family: str                     # see module docstring
    embedder: str | None = None
    syn: bool = False
    head: str = "ce"                # ce | ordinal (emb_head, mil, finetune)
    repeats: int = 3
    epochs: int | None = None       # neural families; None = family default
    target: str = "urgency"         # "urgency" (3 classes) | "native5": train on the psychiatrists' 5 labels, map to urgency after

    def key(self) -> str:
        d = asdict(self)
        if d["target"] == "urgency":          # keep cache keys of the original experiments unchanged
            d.pop("target")
        return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:10]


@dataclass
class Prepared:
    variant: str
    dev: pd.DataFrame               # one row per development user
    y: np.ndarray                   # urgency index per user
    chunks: pd.DataFrame            # message-sized pieces of the development users' text
    chunk_doc: np.ndarray           # which user row each chunk belongs to
    synth: pd.DataFrame             # synthetic messages (train only)
    y5: np.ndarray | None = None    # the psychiatrists' 5-level label per user (Supportive..Attempt)
    map5: np.ndarray | None = None  # (5, 3) 0/1 matrix mapping native classes to urgency under this variant's mapping


def prepare(variant: str = "conservative") -> Prepared:
    from .datasets import reddit_cssrs as rc
    df = rc.to_frame(rc.load_raw(), variant)
    rc.verify_manifest(df)
    dev = df[df["split"] != "test"].reset_index(drop=True)
    assert_no_test(dev)
    ch = build_chunks(dev)
    idx = {d: i for i, d in enumerate(dev["id"])}
    order = {n: i for i, n in enumerate(rc.NATIVE_ORDER)}
    m5 = np.zeros((len(order), len(URGENCY)))
    for native, urg in rc.VARIANTS[variant].items():
        m5[order[native], URGENCY_INDEX[urg]] = 1.0
    return Prepared(variant, dev, dev["urgency"].map(URGENCY_INDEX).to_numpy(), ch,
                    ch["doc_id"].map(idx).to_numpy(), build_synthetic(),
                    dev["native_label"].map(order).to_numpy(), m5)


def user_splits(y: np.ndarray, n_repeats: int, seed: int = SEED, n_splits: int = 5):
    cv = RepeatedStratifiedKFold(n_splits=n_splits, n_repeats=n_repeats, random_state=seed)
    for k, (tr, te) in enumerate(cv.split(np.zeros(len(y)), y)):
        yield k // n_splits, k % n_splits, tr, te


# --- model fitting ----------------------------------------------------------------------------------------------------------

def _tfidf_lr() -> Pipeline:
    return Pipeline([("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_df=0.9, sublinear_tf=True,
                                               max_features=50_000, strip_accents="unicode")),
                     ("clf", LogisticRegression(C=1.0, class_weight="balanced", max_iter=3000))])


def _full_proba(clf, X, n_classes: int = 3) -> np.ndarray:
    out = np.zeros((X.shape[0], n_classes))
    out[:, clf.classes_] = clf.predict_proba(X)
    return out


def _pool_mean(chunk_probs: np.ndarray, owner: np.ndarray, users: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-user mean probability and top-3 mean expected urgency, in the order of `users`."""
    pos = {u: i for i, u in enumerate(users)}
    mean = np.zeros((len(users), chunk_probs.shape[1]))
    risk = np.zeros(len(users))
    ev = chunk_probs @ LEVELS
    for u in users:
        m = owner == u
        if not m.any():
            continue
        mean[pos[u]] = chunk_probs[m].mean(axis=0)
        risk[pos[u]] = np.sort(ev[m])[-3:].mean()
    return mean, risk


class _Fitted:
    """What `fit_split` returns for one fold; knows how to score the held-out users."""

    def __init__(self, predict_users: Callable[[np.ndarray], tuple[np.ndarray, np.ndarray]],
                 predict_texts: Callable[[list[str]], np.ndarray] | None = None):
        self.predict_users = predict_users
        self.predict_texts = predict_texts        # probabilities for single messages (the final system uses this)
        self.artifact: tuple | None = None         # what to persist: ("sklearn", obj) or ("mil", model)


def _fit_native5(spec: Spec, prep: Prepared, train: np.ndarray, embed_fn, seed: int) -> _Fitted:
    """Train on the 5 native C-SSRS labels, then aggregate to urgency with this variant's mapping.

    Benefits: richer supervision (Indicator, Ideation, Behavior and Attempt are different things), and the model no longer depends on
    the unreviewed label mapping: a clinician can change the mapping and the SAME model is re-read, without retraining."""
    if prep.y5 is None or prep.map5 is None:
        raise ValueError("native5 needs prepare() with native labels")
    if spec.syn or spec.family not in ("doc_tfidf", "chunk_tfidf", "emb_lr", "emb_head"):
        raise NotImplementedError("native5 supports doc_tfidf, chunk_tfidf, emb_lr and emb_head without synthetic data")
    y5, M, cfg = prep.y5, prep.map5, BaselineConfig()
    agg = lambda p5: p5 @ M

    def chunk_predict(score_fn):
        def predict(test):
            m = np.isin(prep.chunk_doc, test)
            return _pool_mean(agg(score_fn(m)), prep.chunk_doc[m], test)
        return predict

    if spec.family == "doc_tfidf":
        pipe = build_pipeline(cfg).fit(prep.dev["text"].iloc[train].str.slice(0, cfg.max_chars), y5[train])

        def predict(test):
            p = agg(_full_proba(pipe.named_steps["clf"], pipe.named_steps["tfidf"].transform(
                prep.dev["text"].iloc[test].str.slice(0, cfg.max_chars)), 5))
            return p, p @ LEVELS
        f = _Fitted(predict, lambda ts: agg(_full_proba(pipe.named_steps["clf"],
                                                        pipe.named_steps["tfidf"].transform([t[:cfg.max_chars] for t in ts]), 5)))
        f.artifact = ("sklearn", pipe)
        return f

    in_train = np.isin(prep.chunk_doc, train)
    labels = y5[prep.chunk_doc[in_train]]
    if spec.family == "chunk_tfidf":
        pipe = _tfidf_lr().fit(prep.chunks["text"][in_train].tolist(), labels)
        f = _Fitted(chunk_predict(lambda m: _full_proba(pipe.named_steps["clf"],
                                                        pipe.named_steps["tfidf"].transform(prep.chunks["text"][m]), 5)),
                    lambda ts: agg(_full_proba(pipe.named_steps["clf"], pipe.named_steps["tfidf"].transform(ts), 5)))
        f.artifact = ("sklearn", pipe)
        return f
    all_emb = embed_fn(prep.chunks["text"].tolist(), spec.embedder)
    if spec.family == "emb_lr":
        clf = LogisticRegression(C=1.0, class_weight="balanced", max_iter=3000).fit(all_emb[in_train], labels)
        f = _Fitted(chunk_predict(lambda m: _full_proba(clf, all_emb[m], 5)),
                    lambda ts: agg(_full_proba(clf, embed_fn(list(ts), spec.embedder), 5)))
        f.artifact = ("sklearn", clf)
        return f
    head = neural.fit_embedding_head(all_emb[in_train], labels, kind=spec.head, epochs=spec.epochs or 100, seed=seed, n_classes=5)
    return _Fitted(chunk_predict(lambda m: neural.predict_head(head, all_emb[m])),
                   lambda ts: agg(neural.predict_head(head, embed_fn(list(ts), spec.embedder))))


def fit_split(spec: Spec, prep: Prepared, train: np.ndarray, embed_fn, seed: int) -> _Fitted:
    if spec.target == "native5":
        return _fit_native5(spec, prep, train, embed_fn, seed)
    y = prep.y
    cfg = BaselineConfig()
    if spec.family == "doc_tfidf":
        pipe = build_pipeline(cfg).fit(prep.dev["text"].iloc[train].str.slice(0, cfg.max_chars), y[train])

        def predict(test):
            p = _full_proba(pipe.named_steps["clf"], pipe.named_steps["tfidf"].transform(
                prep.dev["text"].iloc[test].str.slice(0, cfg.max_chars)))
            return p, p @ LEVELS

        def predict_texts(texts):
            return _full_proba(pipe.named_steps["clf"], pipe.named_steps["tfidf"].transform([t[:cfg.max_chars] for t in texts]))
        f = _Fitted(predict, predict_texts)
        f.artifact = ("sklearn", pipe)
        return f

    in_train = np.isin(prep.chunk_doc, train)
    texts = prep.chunks["text"][in_train].tolist()
    labels = y[prep.chunk_doc[in_train]]
    emb = None
    if spec.embedder:
        all_emb = embed_fn(prep.chunks["text"].tolist(), spec.embedder)
        emb_train = all_emb[in_train]
        syn_emb = embed_fn(prep.synth["text"].tolist(), spec.embedder) if spec.syn else None
    syn_labels = prep.synth["urgency"].map(URGENCY_INDEX).to_numpy() if spec.syn else None
    syn_texts = prep.synth["text"].tolist() if spec.syn else []

    def chunk_scorer(score_fn):
        def predict(test):
            m = np.isin(prep.chunk_doc, test)
            probs = score_fn(m)
            return _pool_mean(probs, prep.chunk_doc[m], test)
        return predict

    if spec.family == "chunk_tfidf":
        pipe = _tfidf_lr().fit(texts + syn_texts, np.concatenate([labels, syn_labels]) if spec.syn else labels)
        f = _Fitted(chunk_scorer(lambda m: _full_proba(pipe.named_steps["clf"],
                                                       pipe.named_steps["tfidf"].transform(prep.chunks["text"][m]))),
                    lambda ts: _full_proba(pipe.named_steps["clf"], pipe.named_steps["tfidf"].transform(ts)))
        f.artifact = ("sklearn", pipe)
        return f
    if spec.family in ("emb_lr", "emb_head"):
        X = np.vstack([emb_train, syn_emb]) if spec.syn else emb_train
        yy = np.concatenate([labels, syn_labels]) if spec.syn else labels
        if spec.family == "emb_lr":
            clf = LogisticRegression(C=1.0, class_weight="balanced", max_iter=3000).fit(X, yy)
            f = _Fitted(chunk_scorer(lambda m: _full_proba(clf, all_emb[m])),
                        lambda ts: _full_proba(clf, embed_fn(list(ts), spec.embedder)))
            f.artifact = ("sklearn", clf)
            return f
        head = neural.fit_embedding_head(X, yy, kind=spec.head, epochs=spec.epochs or 100, seed=seed)
        return _Fitted(chunk_scorer(lambda m: neural.predict_head(head, all_emb[m])),
                       lambda ts: neural.predict_head(head, embed_fn(list(ts), spec.embedder)))
    if spec.family == "mil":
        bags = [all_emb[prep.chunk_doc == u] for u in train]
        by = list(y[train])
        if spec.syn:
            bags += [syn_emb[i:i + 1] for i in range(len(syn_emb))]
            by += list(syn_labels)
        model = neural.fit_mil(bags, np.array(by), kind=spec.head, epochs=spec.epochs or 40, seed=seed)

        def predict(test):
            p, _ = neural.predict_mil(model, [all_emb[prep.chunk_doc == u] for u in test])
            return p, p @ LEVELS

        def predict_texts(texts):          # a single message is a bag with one chunk
            e = embed_fn(list(texts), spec.embedder)
            p, _ = neural.predict_mil(model, [e[i:i + 1] for i in range(len(e))])
            return p
        f = _Fitted(predict, predict_texts)
        f.artifact = ("mil", model)
        return f
    if spec.family == "finetune":
        ft = neural.FineTuneScorer(neural.FTConfig(kind=spec.head, epochs=spec.epochs or 3, seed=seed))
        ft.fit(texts + syn_texts, np.concatenate([labels, syn_labels]) if spec.syn else labels)

        def predict(test):
            m = np.isin(prep.chunk_doc, test)
            res = _pool_mean(ft.predict_proba(prep.chunks["text"][m].tolist()), prep.chunk_doc[m], test)
            return res
        fitted = _Fitted(predict, lambda ts: ft.predict_proba(list(ts)))
        fitted.free = ft.free
        fitted.scorer = ft                 # lets the Colab run save the model after the final fit
        return fitted
    raise ValueError(f"unknown family {spec.family!r}")


# --- running and caching ------------------------------------------------------------------------------------------------------

@dataclass
class Result:
    spec: Spec
    variant: str
    raw: np.ndarray                 # (repeats, n, 3) out-of-fold probabilities
    cal: np.ndarray                 # same, temperature-scaled with cross-fitted T
    risk_topk: np.ndarray           # (repeats, n) top-3-chunk pooled expected urgency
    temps: np.ndarray               # fitted temperatures (all folds, all repeats)
    seconds: float = 0.0


def run_spec(spec: Spec, prep: Prepared, embed_fn=embeddings.embed, cache_dir: Path | None = None,
             verbose: bool = True) -> Result:
    import time
    cache_dir = Path(cache_dir) if cache_dir is not None else ART
    path = cache_dir / f"{prep.variant}_{spec.name}_{spec.key()}.npz"
    if path.exists():
        z = np.load(path)
        return Result(spec, prep.variant, z["raw"], z["cal"], z["risk"], z["temps"], float(z["seconds"]))
    t0 = time.time()
    n, R = len(prep.y), spec.repeats
    raw, cal, risk = np.zeros((R, n, 3)), np.zeros((R, n, 3)), np.zeros((R, n))
    fold_of = np.zeros((R, n), dtype=int)
    for r, f, tr, te in user_splits(prep.y, R):
        fitted = fit_split(spec, prep, tr, embed_fn, seed=SEED + 100 * r + f)
        p, rk = fitted.predict_users(te)
        raw[r, te], risk[r, te], fold_of[r, te] = p, rk, f
        if hasattr(fitted, "free"):
            fitted.free()
        if verbose:
            print(f"  [{spec.name}] repeat {r} fold {f} done ({time.time() - t0:.0f}s)", flush=True)
    temps = []
    for r in range(R):
        cal[r], t = crossfit_temperature(raw[r], prep.y, fold_of[r])
        temps.extend(t.values())
    res = Result(spec, prep.variant, raw, cal, risk, np.array(temps), time.time() - t0)
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.savez(path, raw=raw, cal=cal, risk=risk, temps=res.temps, seconds=res.seconds)
    return res


# --- metrics ----------------------------------------------------------------------------------------------------------------------

def metrics_for(y: np.ndarray, raw: np.ndarray, cal: np.ndarray) -> dict:
    """All headline numbers for one set of out-of-fold probabilities (one repeat)."""
    risk = cal @ LEVELS
    rep = urgency_report(y, cal.argmax(axis=1))
    rr = recall_at_review_rate(y, risk, RATES).set_index("review_rate")
    return {
        "high_recall_argmax": rep["high_recall"], "macro_f1": rep["macro_f1"], "qwk": rep["quadratic_weighted_kappa"],
        "confusion": rep["confusion_matrix"], "mean_cost": expected_cost(y, cal.argmax(axis=1)),
        "auroc_high": auroc_high(y, cal[:, 2]), "auroc_expected": auroc_high(y, risk), "pr_auc_high": pr_auc_high(y, cal[:, 2]),
        "recall_at": {f"{int(k * 100)}%": rr.loc[k, "recall"] for k in RATES},
        "recall_at_ci": {f"{int(k * 100)}%": [rr.loc[k, "ci_low"], rr.loc[k, "ci_high"]] for k in RATES},
        "ece_raw": ece(raw, y), "ece_cal": ece(cal, y),
        "nll": float(-np.mean(np.log(np.clip(cal[np.arange(len(y)), y], 1e-12, 1)))),
    }


def summarise(res: Result, y: np.ndarray) -> dict:
    """Repeat-0 metrics (used for paired comparisons) plus the spread across repeats."""
    per = [metrics_for(y, res.raw[r], res.cal[r]) for r in range(res.cal.shape[0])]
    out = {"name": res.spec.name, "family": res.spec.family, "repeat0": per[0], "n_repeats": len(per),
           "seconds": res.seconds, "mean_temperature": float(res.temps.mean())}
    if len(per) > 1:
        for key in ("macro_f1", "auroc_high", "qwk"):
            v = np.array([p[key] for p in per])
            out[f"{key}_mean"], out[f"{key}_sd"] = float(v.mean()), float(v.std(ddof=1))
        v = np.array([p["recall_at"]["30%"] for p in per])
        out["recall_at_30_mean"], out["recall_at_30_sd"] = float(v.mean()), float(v.std(ddof=1))
    return out


def ensemble_result(name: str, members: list[Result]) -> Result:
    """Average the calibrated out-of-fold probabilities of several models that used the SAME folds.

    Valid because each member's prediction for a user came from a model that never saw that user, so the average is still
    out-of-fold. No extra calibration is fitted: the ensemble is evaluated as the plain mean of already-calibrated probabilities."""
    reps = min(m.cal.shape[0] for m in members)
    cal = np.mean([m.cal[:reps] for m in members], axis=0)
    risk = np.mean([m.risk_topk[:reps] for m in members], axis=0)
    return Result(Spec(name, "ensemble", repeats=reps), members[0].variant, cal.copy(), cal, risk, np.ones(1), 0.0)
