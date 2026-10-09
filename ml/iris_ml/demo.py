"""Decision lab: type a sentence, see exactly what IRIS would do.   python -m iris_ml.demo   ->   http://127.0.0.1:8765

This runs the SAME code as the chat (the rule layer, the check-in floor, the V1 mandatory-review policy and the reply wording). No AI model is used, because no model was good
enough in the Phase 2 evaluation (ml/reports/phase2_final_summary.md). It starts instantly and needs no data, no GPU and no network.

A DEVELOPMENT TOOL. The wording is an AI-assisted draft awaiting clinical review. It is not clinically validated and must never be used with real people.
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import support as sp
from .decision import V1_POLICY, decide
from .rules import scan
from .support_review import HELP, ORD, POS, URG, scenario_rows

PAGE = Path(__file__).with_name("demo_page.html")
LAYOUT_WORKFLOW = {"help_now": URG, "support": HELP, "celebrate": POS, "tips": ORD}


def triage_payload(text: str, floor: str = "none") -> dict:
    """What the shipped system does for one message from a person whose check-in set `floor`."""
    r = decide(None, text, floor, V1_POLICY)                   # no model: rules + check-in floor + mandatory human review
    p = sp.plan_support(text, r)
    rule = scan(text)
    return {
        "priority": r.urgency, "message_urgent": r.message_urgent, "workflow": LAYOUT_WORKFLOW[p.layout], "layout": p.layout,
        "needs_human": r.needs_human, "human_review_required": p.human_review_required,
        "reply": {
            "intro": p.intro, "listening": p.listening, "self_help": [{"title": t, "how": h} for t, h in p.self_help], "reach_out": list(p.reach_out),
            "crisis_lead": p.crisis_lead, "helplines": [{"name": n, "detail": d, "number": num} for n, d, num, _ in p.helplines],
            "status": sp.status_line("waiting", r.message_urgent), "match": p.match_confidence, "topics": list(p.topics),
        },
        "reviewer_note": p.reviewer_note.split(" Reasons:")[0],
        "rule_level": rule.level, "rule_hits": list(rule.hits), "third_person": rule.third_person, "negated": rule.negated,
        "baseline_floor": floor, "reasons": list(r.reasons),
    }


def scenarios_payload() -> dict:
    rows = scenario_rows()
    counts: dict[str, int] = {}
    for s in rows:
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    return {"rows": rows, "counts": counts, "total": len(rows)}


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
        elif self.path == "/api/scenarios":
            self._send(200, json.dumps(scenarios_payload()).encode())
        else:
            self._send(404, b'{"detail":"not found"}')

    def do_POST(self):
        if self.path != "/api/triage":
            return self._send(404, b'{"detail":"not found"}')
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            text = str(body.get("text", "")).strip()
            floor = body.get("floor", "none")
            if floor not in ("none", "medium", "high") or not text or len(text) > 5000:
                raise ValueError("bad input")
            self._send(200, json.dumps(triage_payload(text, floor)).encode())
        except (ValueError, json.JSONDecodeError):
            self._send(400, b'{"detail":"send {text, floor} with 1 to 5000 characters"}')


def main(port: int = 8765) -> None:
    print(f"ready: http://127.0.0.1:{port}  (no model, no data, no GPU)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
