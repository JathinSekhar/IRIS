from iris_ml import walkthrough as wt


def test_walkthrough_follows_the_v1_design_for_each_demo_person():
    by = {d["case"].level: d for d in wt.decisions()}
    for d in by.values():
        assert d["result"].needs_human and d["result"].route == "human_reviewer"           # a person reviews every case
        assert d["result"].probabilities is None                                           # no model was run
    assert by["high"]["result"].urgency == "high" and by["high"]["case"].floor == "high"   # High comes from the check-in floor
    assert by["high"]["rule"].level == "review"                                            # his words are flagged by the rules too, at review level
    assert by["normal"]["result"].urgency == "low"
    assert by["medium"]["result"].urgency == "low" and by["medium"]["case"].checkin_baseline == "medium"   # the documented gap


def test_rendered_walkthrough_is_labelled_illustrative_and_says_nothing_about_performance():
    text = wt.render()
    assert "Illustrative only" in text and "Not used for ML" in text
    assert "mandatory" in text and "never clears a case" in text
    for word in ("AUROC", "recall", "accuracy"):
        assert word not in text
