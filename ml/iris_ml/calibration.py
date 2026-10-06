"""Temperature scaling: one number T that makes a model's confidence honest (T > 1 softens, T < 1 sharpens).

Calibration matters for IRIS because the decision layer trusts confidence: below a threshold a case goes to a human.
`crossfit_temperature` fits T on the other folds and applies it to the held-out fold, so reported calibration is not
flattered by being measured on the data it was fitted on.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize_scalar

_EPS = 1e-12


def apply_temperature(probs: np.ndarray, temperature: float) -> np.ndarray:
    z = np.log(np.clip(np.asarray(probs, dtype=float), _EPS, 1.0)) / temperature
    z -= z.max(axis=1, keepdims=True)
    p = np.exp(z)
    return p / p.sum(axis=1, keepdims=True)


def nll(probs: np.ndarray, y_true: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=int)
    return float(-np.mean(np.log(np.clip(probs[np.arange(len(y_true)), y_true], _EPS, 1.0))))


def fit_temperature(probs: np.ndarray, y_true: np.ndarray, bounds: tuple[float, float] = (0.05, 20.0)) -> float:
    res = minimize_scalar(lambda t: nll(apply_temperature(probs, t), y_true), bounds=bounds, method="bounded")
    return float(res.x)


def crossfit_temperature(probs: np.ndarray, y_true: np.ndarray, folds: np.ndarray) -> tuple[np.ndarray, dict]:
    """Calibrate each fold with a temperature fitted on the OTHER folds. Returns calibrated probabilities and the Ts."""
    probs, y_true, folds = np.asarray(probs, float), np.asarray(y_true, int), np.asarray(folds)
    out = np.empty_like(probs)
    temps: dict = {}
    for f in np.unique(folds):
        held = folds == f
        t = fit_temperature(probs[~held], y_true[~held])
        out[held] = apply_temperature(probs[held], t)
        temps[int(f)] = t
    return out, temps
