"""Cut long documents into short, message-sized windows (for the gold-set pool and short-input models)."""
from __future__ import annotations

import re

_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(<])")


def sentences(text: str) -> list[str]:
    parts = _SENT.split(re.sub(r"\s+", " ", text).strip())
    return [p.strip() for p in parts if p.strip()]


def _hard_wrap(sentence: str, max_chars: int) -> list[str]:
    """A single 'sentence' longer than the window (no punctuation): wrap at word boundaries."""
    words, out, cur = sentence.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        out.append(cur)
    return out


def windows(text: str, min_chars: int = 120, max_chars: int = 600, max_sentences: int = 4) -> list[str]:
    """Non-overlapping windows of consecutive sentences, each between min_chars and max_chars long."""
    pieces: list[str] = []
    for s in sentences(text):
        pieces.extend(_hard_wrap(s, max_chars) if len(s) > max_chars else [s])
    out: list[str] = []
    cur: list[str] = []
    for s in pieces:
        if cur and (len(" ".join(cur + [s])) > max_chars or len(cur) >= max_sentences):
            w = " ".join(cur)
            if len(w) >= min_chars:
                out.append(w)
            cur = []
        cur.append(s)
    if cur and len(" ".join(cur)) >= min_chars:
        out.append(" ".join(cur))
    return out
