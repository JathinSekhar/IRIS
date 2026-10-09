"""Neural pieces: an ordinal output head, an attention multiple-instance model, and GPU fine-tuning.

Everything is seeded and deterministic enough to reproduce on the same machine. No test or gold data is ever passed in here:
callers hand over training arrays only.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

EPS = 1e-6


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def class_weights(y: np.ndarray, n_classes: int) -> torch.Tensor:
    """Balanced weights: rare classes (High) count more, matching the cost principle that misses are expensive."""
    counts = np.bincount(np.asarray(y, dtype=int), minlength=n_classes).astype(float)
    w = counts.sum() / (n_classes * np.maximum(counts, 1.0))
    return torch.tensor(w, dtype=torch.float32)


# --- heads ------------------------------------------------------------------------------------------------------------

class SoftmaxHead(nn.Module):
    def __init__(self, in_dim: int, n_classes: int = 3):
        super().__init__()
        self.fc = nn.Linear(in_dim, n_classes)

    def forward(self, h: torch.Tensor) -> torch.Tensor:           # log-probabilities
        return F.log_softmax(self.fc(h), dim=-1)


class OrdinalHead(nn.Module):
    """Cumulative-link ordinal regression: one score and ordered thresholds, so Low < Medium < High is built in.

    A far mistake (High read as Low) is therefore more costly to the model than a near one, which matches how the labels
    behave. P(y <= k) = sigmoid(theta_k - z), with theta increasing."""

    def __init__(self, in_dim: int, n_classes: int = 3):
        super().__init__()
        self.score = nn.Linear(in_dim, 1)
        self.first = nn.Parameter(torch.tensor(-0.5))
        self.gaps = nn.Parameter(torch.zeros(max(n_classes - 2, 0)))

    def thresholds(self) -> torch.Tensor:
        return torch.cumsum(torch.cat([self.first[None], F.softplus(self.gaps) + 0.1]), dim=0)

    def forward(self, h: torch.Tensor) -> torch.Tensor:
        z = self.score(h).squeeze(-1)
        cdf = torch.sigmoid(self.thresholds()[None, :] - z[:, None])             # (B, K-1)
        probs = torch.cat([cdf[:, :1], cdf[:, 1:] - cdf[:, :-1], 1 - cdf[:, -1:]], dim=1).clamp_min(EPS)
        return torch.log(probs / probs.sum(dim=1, keepdim=True))


def make_head(kind: str, in_dim: int, n_classes: int = 3) -> nn.Module:
    if kind == "ce":
        return SoftmaxHead(in_dim, n_classes)
    if kind == "ordinal":
        return OrdinalHead(in_dim, n_classes)
    raise ValueError(f"unknown head {kind!r}")


# --- chunk-level head on frozen embeddings (ordinal ablation) --------------------------------------------------------------

def fit_embedding_head(X: np.ndarray, y: np.ndarray, kind: str = "ordinal", epochs: int = 100, lr: float = 1e-2,
                       weight_decay: float = 1e-3, batch_size: int = 256, seed: int = 0, n_classes: int = 3) -> nn.Module:
    set_seed(seed)
    dev = device()
    head = make_head(kind, X.shape[1], n_classes).to(dev)
    opt = torch.optim.AdamW(head.parameters(), lr=lr, weight_decay=weight_decay)
    w = class_weights(y, n_classes).to(dev)
    Xt = torch.tensor(X, dtype=torch.float32, device=dev)
    yt = torch.tensor(np.asarray(y, dtype=int), device=dev)
    n = len(yt)
    for _ in range(epochs):
        perm = torch.randperm(n, device=dev)
        for i in range(0, n, batch_size):
            idx = perm[i:i + batch_size]
            loss = F.nll_loss(head(Xt[idx]), yt[idx], weight=w)
            opt.zero_grad()
            loss.backward()
            opt.step()
    return head.eval()


@torch.no_grad()
def predict_head(head: nn.Module, X: np.ndarray) -> np.ndarray:
    dev = next(head.parameters()).device
    return head(torch.tensor(X, dtype=torch.float32, device=dev)).exp().cpu().numpy()


# --- attention multiple-instance model ------------------------------------------------------------------------------------

class AttentionMIL(nn.Module):
    """A user is a bag of chunk embeddings; attention learns which chunks matter; one label per bag.

    This respects the structure of the data (labels are per user, not per message) instead of pretending every chunk of a
    user shares the user's label."""

    def __init__(self, in_dim: int, hidden: int = 128, kind: str = "ce", n_classes: int = 3, dropout: float = 0.2):
        super().__init__()
        self.v = nn.Linear(in_dim, hidden)
        self.w = nn.Linear(hidden, 1)
        self.drop = nn.Dropout(dropout)
        self.head = make_head(kind, in_dim, n_classes)

    def forward(self, bags: torch.Tensor, mask: torch.Tensor):
        a = self.w(torch.tanh(self.v(bags))).squeeze(-1).masked_fill(~mask, float("-inf"))
        a = torch.softmax(a, dim=1)
        pooled = (a.unsqueeze(-1) * bags).sum(dim=1)
        return self.head(self.drop(pooled)), a


def pad_bags(bags: list[np.ndarray], dev: str) -> tuple[torch.Tensor, torch.Tensor]:
    n = max(len(b) for b in bags)
    d = bags[0].shape[1]
    x = np.zeros((len(bags), n, d), dtype=np.float32)
    m = np.zeros((len(bags), n), dtype=bool)
    for i, b in enumerate(bags):
        x[i, :len(b)] = b
        m[i, :len(b)] = True
    return torch.tensor(x, device=dev), torch.tensor(m, device=dev)


def fit_mil(bags: list[np.ndarray], y: np.ndarray, kind: str = "ce", epochs: int = 40, lr: float = 1e-3,
            weight_decay: float = 1e-3, batch_size: int = 16, seed: int = 0, n_classes: int = 3,
            hidden: int = 128) -> AttentionMIL:
    set_seed(seed)
    dev = device()
    model = AttentionMIL(bags[0].shape[1], hidden=hidden, kind=kind, n_classes=n_classes).to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    w = class_weights(y, n_classes).to(dev)
    y = np.asarray(y, dtype=int)
    rng = np.random.default_rng(seed)
    for _ in range(epochs):
        model.train()
        order = rng.permutation(len(bags))
        for i in range(0, len(order), batch_size):
            idx = order[i:i + batch_size]
            x, m = pad_bags([bags[j] for j in idx], dev)
            logp, _ = model(x, m)
            loss = F.nll_loss(logp, torch.tensor(y[idx], device=dev), weight=w)
            opt.zero_grad()
            loss.backward()
            opt.step()
    return model.eval()


@torch.no_grad()
def predict_mil(model: AttentionMIL, bags: list[np.ndarray], batch_size: int = 64) -> tuple[np.ndarray, list[np.ndarray]]:
    dev = next(model.parameters()).device
    probs, atts = [], []
    for i in range(0, len(bags), batch_size):
        chunk = bags[i:i + batch_size]
        x, m = pad_bags(chunk, dev)
        logp, a = model(x, m)
        probs.append(logp.exp().cpu().numpy())
        atts.extend(a[j, :len(chunk[j])].cpu().numpy() for j in range(len(chunk)))
    return np.concatenate(probs), atts


# --- fine-tuning a transformer on chunks --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class FTConfig:
    model_name: str = "distilroberta-base"
    max_len: int = 128
    epochs: int = 3
    lr: float = 3e-5
    batch_size: int = 16
    weight_decay: float = 0.01
    warmup: float = 0.1
    kind: str = "ce"
    seed: int = 0
    fp16: bool = True


class FineTuneScorer:
    """Fine-tunes a small transformer (default DistilRoBERTa, Apache-2.0) to score single chunks or messages."""

    def __init__(self, cfg: FTConfig = FTConfig(), n_classes: int = 3):
        self.cfg, self.n_classes = cfg, n_classes
        self.tok = self.enc = self.head = None

    def _load(self):
        import os
        from .embeddings import ARTIFACTS
        os.environ.setdefault("HF_HOME", str(ARTIFACTS / "hf_cache"))
        from transformers import AutoModel, AutoTokenizer
        self.tok = AutoTokenizer.from_pretrained(self.cfg.model_name)
        self.enc = AutoModel.from_pretrained(self.cfg.model_name)
        self.head = make_head(self.cfg.kind, self.enc.config.hidden_size, self.n_classes)

    def _batch(self, texts: list[str]) -> dict:
        return self.tok(list(texts), padding=True, truncation=True, max_length=self.cfg.max_len, return_tensors="pt")

    def _logp(self, batch: dict) -> torch.Tensor:
        h = self.enc(**batch).last_hidden_state[:, 0]
        return self.head(h.float())

    def fit(self, texts: list[str], y: np.ndarray) -> "FineTuneScorer":
        from transformers import get_linear_schedule_with_warmup
        c = self.cfg
        set_seed(c.seed)
        self._load()
        dev = device()
        self.enc.to(dev)
        self.head.to(dev)
        params = list(self.enc.parameters()) + list(self.head.parameters())
        opt = torch.optim.AdamW(params, lr=c.lr, weight_decay=c.weight_decay)
        steps = c.epochs * int(np.ceil(len(texts) / c.batch_size))
        sched = get_linear_schedule_with_warmup(opt, int(c.warmup * steps), steps)
        use_amp = c.fp16 and dev == "cuda"
        scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
        w = class_weights(y, self.n_classes).to(dev)
        y = np.asarray(y, dtype=int)
        rng = np.random.default_rng(c.seed)
        self.enc.train()
        self.head.train()
        for _ in range(c.epochs):
            order = rng.permutation(len(texts))
            for i in range(0, len(order), c.batch_size):
                idx = order[i:i + c.batch_size]
                batch = {k: v.to(dev) for k, v in self._batch([texts[j] for j in idx]).items()}
                with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_amp):
                    logp = self._logp(batch)
                loss = F.nll_loss(logp.float(), torch.tensor(y[idx], device=dev), weight=w)
                opt.zero_grad()
                scaler.scale(loss).backward()
                scaler.unscale_(opt)
                torch.nn.utils.clip_grad_norm_(params, 1.0)
                scaler.step(opt)
                scaler.update()
                sched.step()
        self.enc.eval()
        self.head.eval()
        return self

    @torch.no_grad()
    def predict_proba(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        dev = next(self.enc.parameters()).device
        use_amp = self.cfg.fp16 and dev.type == "cuda"
        out = []
        for i in range(0, len(texts), batch_size):
            batch = {k: v.to(dev) for k, v in self._batch(texts[i:i + batch_size]).items()}
            with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_amp):
                out.append(self._logp(batch).float().exp().cpu().numpy())
        return np.concatenate(out)

    def free(self) -> None:
        self.enc = self.head = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def save(self, directory) -> None:
        """Learned parameters only (encoder weights, tokenizer, head, config). No training text is stored."""
        import json
        from dataclasses import asdict
        from pathlib import Path
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        self.enc.save_pretrained(d / "encoder")
        self.tok.save_pretrained(d / "encoder")
        torch.save(self.head.state_dict(), d / "head.pt")
        (d / "ft_config.json").write_text(json.dumps({**asdict(self.cfg), "n_classes": self.n_classes}, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, directory) -> "FineTuneScorer":
        import json
        from pathlib import Path
        from transformers import AutoModel, AutoTokenizer
        d = Path(directory)
        cfg = json.loads((d / "ft_config.json").read_text(encoding="utf-8"))
        n_classes = cfg.pop("n_classes")
        self = cls(FTConfig(**cfg), n_classes)
        self.tok = AutoTokenizer.from_pretrained(d / "encoder")
        self.enc = AutoModel.from_pretrained(d / "encoder")
        self.head = make_head(self.cfg.kind, self.enc.config.hidden_size, n_classes)
        self.head.load_state_dict(torch.load(d / "head.pt", map_location="cpu", weights_only=True))
        dev = device()
        self.enc.to(dev).eval()
        self.head.to(dev).eval()
        return self
