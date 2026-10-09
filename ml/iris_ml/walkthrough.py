"""Illustrative walkthrough of the V1 design for the three demo patients. NOT ML evaluation.

    python -m iris_ml.walkthrough          # writes reports/phase2_walkthrough.md

The three people are the fictional demo accounts of the local sandbox (docs/DEMO_ACCOUNTS.md). Their check-in outcomes and messages are
copied from backend/devtools/demo_data.py (a backend test checks the copy has not drifted). They were written by hand to exercise the app, so
they are never part of any training, validation or evaluation of a model, and nothing here is evidence of performance.

No model is run here: the table shows what the rule layer, the check-in floor and the mandatory-review policy decide by themselves. The
AI step in the V1 design only changes the ORDER of the review queue, so leaving it out cannot change a decision; it is never allowed to clear a case.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import ROOT
from .decision import V1_POLICY, decide
from .rules import scan
from .support import plan_support


@dataclass(frozen=True)
class DemoCase:
    name: str
    level: str                  # the demo account's intended risk level
    phq9: int
    gad7: int
    safety_tier: int            # C-SSRS screener tier (0-3)
    checkin_baseline: str       # overall baseline risk from the check-in (PHQ-9, GAD-7, functioning, safety)
    floor: str                  # urgency floor from the SAFETY answers only: this is what message triage receives
    message: str                # the free-text answer to "what brings you here"


CASES = [
    DemoCase("Ananya Rao", "normal", 2, 2, 0, "low", "none",
             "Feeling mostly fine, just a bit busy with college this month."),
    DemoCase("Rohit Verma", "medium", 12, 11, 0, "medium", "none",
             "Exams and money worries are stressing me out and I sleep badly most nights."),
    DemoCase("Arjun Mehta", "high", 23, 17, 3, "high", "high",
             "I feel hopeless and I have been thinking about ending my life."),
]


def decisions() -> list[dict]:
    out = []
    for c in CASES:
        rule = scan(c.message)
        r = decide(None, c.message, c.floor, V1_POLICY)           # no model is run: see the module docstring
        out.append({"case": c, "rule": rule, "result": r})
    return out


def render() -> str:
    L: list[str] = []
    w = L.append
    w("# Demo walkthrough (illustrative only)\n")
    w("> **Illustrative only. Not used for ML training, validation or evaluation, and not evidence that IRIS works.** The three people are "
      "fictional demo accounts written by hand (see `docs/DEMO_ACCOUNTS.md`). No model was run to produce this table.\n")
    w("## The V1 design this table follows\n")
    w("```\nrules + check-in floor  ->  AI ranks the queue  ->  a person reviews EVERY case  ->  the person decides\n```\n")
    w("- The rule layer and the check-in safety floor can only raise urgency. The highest layer wins.")
    w("- The AI model only decides the **order** in which people read cases. It can raise priority. It never clears a case as Low.")
    w("- Every case goes to a human reviewer. The urgency shown below is a **provisional priority**, not a decision.\n")
    w("## Table\n")
    w("| Person | Check-in answers | Check-in baseline risk | Safety floor sent to message triage | Rule layer on their message | Provisional priority | Route | Human review | Support recommended |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for d in decisions():
        c, rule, r = d["case"], d["rule"], d["result"]
        hits = f"{rule.level}" + (f" ({', '.join(rule.hits)})" if rule.hits else "")
        sup = plan_support(c.message, r)
        advice = ("urgent response: helplines shown, a person follows the urgent protocol" if sup.urgent_protocol
                  else f"topics: {', '.join(sup.topics)}; self-help: {', '.join(t for t, _ in sup.self_help)}")
        w(f"| {c.name} ({c.level}) | PHQ-9 {c.phq9}, GAD-7 {c.gad7}, C-SSRS tier {c.safety_tier} | {c.checkin_baseline} | {c.floor} | {hits} | "
          f"**{r.urgency}** | {r.route.replace('_', ' ')} | **mandatory** | {advice} |")
    w("\n## Their messages\n")
    for c in CASES:
        w(f"- **{c.name}:** \"{c.message}\"")
    w("\n## How to read this\n")
    w("- **Ananya** has nothing raising her priority, so her provisional priority is Low. A person still looks at it: the model is not "
      "allowed to clear her, and with no model loaded the fail-safe applies in any case.")
    w("- **Arjun** is High because of his check-in: the C-SSRS answers set a High floor. The rule layer separately flags his words at "
      "*review* level (a Medium floor), which alone would not reach High. No model can lower either layer.")
    w("- **Rohit** shows a gap worth a decision. His check-in baseline is **medium** (PHQ-9 12, GAD-7 11), but only the self-harm "
      "answers feed the floor that message triage receives, and his tier is 0. So his provisional priority is Low. In the V1 design a "
      "person still reads it and the AI ranking could raise it, but whether a medium baseline from the questionnaire scores should "
      "also raise the floor is **open for the project owner and a clinician**.")
    w("\n_Generated by `python -m iris_ml.walkthrough`. Reasons for each decision are in the audit trail returned by `decide()`._\n")
    return "\n".join(L) + "\n"


def main() -> None:
    out = ROOT / "reports" / "phase2_walkthrough.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(render(), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
