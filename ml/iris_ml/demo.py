"""Local browser demo of the triage system.   python -m iris_ml.demo   ->   http://127.0.0.1:8765

A DEVELOPMENT TOOL. It shows what the Phase 2 system decides for any sentence you type, and lets you say what the answer should
have been so it can mark the decision right or wrong. It is not clinically validated and must never be used with real people.

The scorer is a small embedding model trained on the development users plus flagged synthetic messages. It is a demo choice,
not the final selection. The rule layer, the check-in floor and the cost-sensitive policy are the real ones.
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

from . import embeddings
from .challenge import challenge_frame, evaluate_challenge
from .experiments import prepare, run_spec
from .rules import scan
from .run_phase2 import SPECS
from .system import TriageSystem, fit_final

PAGE = Path(__file__).with_name("demo_page.html")
DEMO_SPEC = "e2s_minilm_lr_syn"
SYSTEM: TriageSystem | None = None


def build_system() -> TriageSystem:
    prep = prepare("conservative")
    spec = next(s for s in SPECS if s.name == DEMO_SPEC)
    temp = float(run_spec(spec, prep, verbose=False).temps.mean())
    return fit_final(spec, prep, embeddings.embed, temp)


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    return o


def triage_payload(text: str, floor: str = "none") -> dict:
    r = SYSTEM.triage(text, floor)
    rule = scan(text)
    return _clean({
        "urgency": r.urgency, "route": r.route, "needs_human": r.needs_human, "model_urgency": r.model_urgency,
        "confidence": r.confidence, "probabilities": r.probabilities, "risk_score": r.risk_score,
        "rule_level": rule.level, "rule_hits": list(rule.hits), "third_person": rule.third_person, "negated": rule.negated,
        "baseline_floor": floor, "reasons": list(r.reasons),
    })


def challenge_payload() -> dict:
    df = challenge_frame()
    res = SYSTEM.triage_batch(list(df["text"]))
    summary = evaluate_challenge(list(df["text"]), [r.urgency for r in res], [r.needs_human for r in res])
    failed = {f["id"] for f in summary["failures"]}
    rows = [{"id": row.id, "category": row.category, "expect": row.expect, "text": row.text, "urgency": r.urgency,
             "route": r.route, "needs_human": r.needs_human, "passed": row.id not in failed}
            for row, r in zip(df.itertuples(), res)]
    return _clean({"rows": rows, "summary": summary})


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/challenge":
            self._send(200, json.dumps(challenge_payload()).encode())
        elif self.path == "/api/info":
            self._send(200, json.dumps({"scorer": DEMO_SPEC, "temperature": SYSTEM.temperature}).encode())
        else:
            self._send(404, b'{"detail":"not found"}')

    def do_POST(self):
        if self.path != "/api/triage":
            return self._send(404, b'{"detail":"not found"}')
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            text = str(body.get("text", "")).strip()
            floor = body.get("floor", "none")
            if floor not in ("none", "medium", "high") or len(text) > 5000:
                raise ValueError("bad input")
            self._send(200, json.dumps(triage_payload(text, floor)).encode())
        except (ValueError, json.JSONDecodeError):
            self._send(400, b'{"detail":"send {text, floor} with text up to 5000 characters"}')


def main(port: int = 8765) -> None:
    global SYSTEM
    print("loading the demo system (embedding model + classifier)...", flush=True)
    SYSTEM = build_system()
    print(f"ready: http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
