"""M1: TF-IDF + logistic regression, evaluated with repeated stratified cross-validation.

Protocol (the same every time, so results are comparable and honest):
  * only train + val users are used (the held-out TEST split is never read by this module);
  * every user's prediction comes from a model that never saw that user (out-of-fold);
  * 5-fold x 3 repeats; calibration by temperature scaling fitted on the other folds;
  * per-user probabilities are averaged across repeats, so each user counts once in every metric and interval.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import RepeatedStratifiedKFold
from sklearn.pipeline import Pipeline

from . import URGENCY, URGENCY_INDEX
from .calibration import crossfit_temperature
from .rules import scan


@dataclass(frozen=True)
class BaselineConfig:
    seed: int = 2026
    n_splits: int = 5
    n_repeats: int = 3
    max_features: int = 50_000
    C: float = 1.0
    max_chars: int = 20_000


def build_pipeline(cfg: BaselineConfig) -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_df=0.9, sublinear_tf=True,
                                  max_features=cfg.max_features, strip_accents="unicode")),
        ("clf", LogisticRegression(C=cfg.C, class_weight="balanced", max_iter=3000)),
    ])


def assert_no_test(df: pd.DataFrame) -> None:
    if (df["split"] == "test").any():
        raise RuntimeError("the test split must never be used for training or model selection")


def oof_probabilities(texts: pd.Series, y: np.ndarray, n_classes: int, cfg: BaselineConfig = BaselineConfig()):
    """Returns (raw averaged probs, calibrated averaged probs, mean temperature). Out-of-fold throughout."""
    texts = texts.astype(str).str.slice(0, cfg.max_chars).to_numpy()
    y = np.asarray(y, dtype=int)
    cv = RepeatedStratifiedKFold(n_splits=cfg.n_splits, n_repeats=cfg.n_repeats, random_state=cfg.seed)
    raw = np.zeros((cfg.n_repeats, len(y), n_classes))
    cal = np.zeros_like(raw)
    temps: list[float] = []
    fold_of = np.zeros((cfg.n_repeats, len(y)), dtype=int)
    for k, (train_idx, test_idx) in enumerate(cv.split(texts, y)):
        r, f = divmod(k, cfg.n_splits)
        pipe = build_pipeline(cfg).fit(texts[train_idx], y[train_idx])
        p = np.zeros((len(test_idx), n_classes))
        p[:, pipe.named_steps["clf"].classes_] = pipe.predict_proba(texts[test_idx])
        raw[r, test_idx] = p
        fold_of[r, test_idx] = f
    for r in range(cfg.n_repeats):
        cal[r], t = crossfit_temperature(raw[r], y, fold_of[r])
        temps.extend(t.values())
    return raw.mean(axis=0), cal.mean(axis=0), float(np.mean(temps))


def rules_prediction(texts: pd.Series) -> np.ndarray:
    """M0 used as a document-level urgency predictor: high -> High, review -> Medium, none -> Low."""
    to_idx = {"high": URGENCY_INDEX["high"], "review": URGENCY_INDEX["medium"], "none": URGENCY_INDEX["low"]}
    return np.array([to_idx[scan(t).level] for t in texts], dtype=int)


def majority_prediction(y: np.ndarray) -> np.ndarray:
    return np.full(len(y), np.bincount(np.asarray(y, dtype=int)).argmax())


def stratified_random_prediction(y: np.ndarray, seed: int = 0) -> np.ndarray:
    """Guesses with the class frequencies of the data: the 'no skill' reference for macro-F1 and kappa."""
    rng = np.random.default_rng(seed)
    y = np.asarray(y, dtype=int)
    return rng.choice(np.arange(len(URGENCY)), size=len(y), p=np.bincount(y, minlength=len(URGENCY)) / len(y))


def top_terms(pipe: Pipeline, class_names: list[str], k: int = 12) -> dict[str, list[str]]:
    vocab = np.array(pipe.named_steps["tfidf"].get_feature_names_out())
    coef = pipe.named_steps["clf"].coef_
    classes = pipe.named_steps["clf"].classes_
    out = {}
    for row, c in enumerate(classes):
        order = np.argsort(coef[row])[::-1]
        out[class_names[c]] = [t for t in vocab[order] if t not in ("url", "user")][:k]
    return out
