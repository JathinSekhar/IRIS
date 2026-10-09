"""The cost matrix, in its own tiny module so the decision layer (and the backend that uses it) needs only numpy and PyYAML.

`metrics.load_costs` still works: it is re-exported from here.
"""
from __future__ import annotations

import numpy as np

from . import URGENCY, load_yaml


def load_costs() -> tuple[np.ndarray, float]:
    cfg = load_yaml("costs.yaml")
    matrix = np.array([cfg["matrix"][name] for name in URGENCY], dtype=float)
    if matrix.shape != (len(URGENCY), len(URGENCY)):
        raise ValueError("cost matrix must be urgency x urgency")
    return matrix, float(cfg["review_cost"])
