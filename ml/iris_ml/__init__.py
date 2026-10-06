"""IRIS ML: intent, urgency and routing models, evaluation, and the data tooling around them."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIGS = ROOT / "configs"


def load_yaml(name: str) -> dict:
    with open(CONFIGS / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


_labels = load_yaml("labels.yaml")
URGENCY: list[str] = _labels["urgency"]
INTENT: list[str] = _labels["intent"]
SUBJECT: list[str] = _labels["subject"]
SPLITS: list[str] = _labels["splits"]
URGENCY_INDEX = {name: i for i, name in enumerate(URGENCY)}
INTENT_INDEX = {name: i for i, name in enumerate(INTENT)}
HIGH = URGENCY_INDEX["high"]
