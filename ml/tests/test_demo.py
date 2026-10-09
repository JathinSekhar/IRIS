"""The decision lab must show exactly what the chat does, with no model and no data."""
import re

from iris_ml import demo
from iris_ml import support as sp


def test_the_lab_needs_no_model_data_or_gpu():
    import subprocess
    import sys
    code = "import sys, iris_ml.demo; print(sorted(m for m in ('torch', 'sklearn', 'pandas', 'sentence_transformers', 'iris_ml.embeddings', 'iris_ml.neural') if m in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(demo.PAGE.parent.parent)).stdout.strip()
    assert out == "[]", out                                                    # importing the lab loads no model stack at all
    d = demo.triage_payload("I have exams next week and I am struggling to study")
    assert d["workflow"] == "ordinary_support" and d["human_review_required"] and d["needs_human"]


def test_the_case_that_went_wrong_in_the_chat_is_right_in_the_lab():
    calm = demo.triage_payload("yah i am feeling better", "high")          # a person whose check-in was High
    assert calm["priority"] == "high" and calm["message_urgent"] is False and calm["workflow"] == "positive_reply"
    assert "concerned" not in calm["reply"]["intro"].lower() and calm["reply"]["helplines"]
    assert "check-in" in calm["reviewer_note"]


def test_concerning_messages_are_urgent_and_the_floor_never_lowers_anything():
    for floor in ("none", "medium", "high"):
        d = demo.triage_payload("I have been thinking about ending my life", floor)
        assert d["workflow"] == "urgent_response" and d["message_urgent"] and d["priority"] == "high"
    low = demo.triage_payload("ok thanks", "none")
    assert low["priority"] == "low" and low["needs_human"]                  # Low is never cleared
    assert demo.triage_payload("ok thanks", "high")["priority"] == "high"   # a floor can only raise


def test_the_lab_uses_the_same_reply_wording_as_the_chat():
    allowed = {m["text"] for m in sp.catalog()}
    for text in ["yah i am feeling better", "Nobody would notice if I was gone", "I want to die", "I feel lonely and I can't sleep"]:
        r = demo.triage_payload(text)["reply"]
        for s in (r["intro"], r["listening"], *r["reach_out"], r["status"]):
            assert s in allowed, (text, s)


def test_scenarios_are_served_with_counts_and_the_page_has_no_emoji():
    p = demo.scenarios_payload()
    assert p["total"] == len(p["rows"]) and sum(p["counts"].values()) == p["total"] and p["counts"]["known_gap"] == 2
    page = demo.PAGE.read_text(encoding="utf-8")
    assert not re.search("[\U0001F300-\U0001FAFF☀-➿]", page) and "No AI model is used" in page


def test_a_plain_greeting_gets_a_plain_hello_even_with_a_high_floor():
    from iris_ml.demo import triage_payload
    for text in ("hi", "Hello!", "good morning"):
        d = triage_payload(text, "high")
        assert d["reply"]["topics"] == ["positive"] or "positive" in d["reply"]["topics"]
        assert "breathing" not in str(d["reply"]).lower()
    assert triage_payload("hi I want to die", "high")["workflow"] == "urgent_response"
