"""Challenge set: a small, hand-written regression and false-alarm check for the whole system.

READ THIS BEFORE USING IT
  * It is written by the code author (an AI assistant), NOT by independent annotators or clinicians. It is therefore
    NOT a gold set, is not independent of the system's design, and passing it proves nothing about safety.
  * Expectations ("should stay low", "should reach at least medium", "should reach high") are conservative engineering
    expectations drawn from the draft labelling guide, not clinical truth. Items a reasonable person could argue about
    were left out on purpose.
  * What it IS good for: catching regressions (an idiom suddenly escalated, an explicit threat suddenly ignored) and showing
    which kinds of phrasing the system still gets wrong. The independent gold set remains the only basis for claims.
  * Wording is deliberately different from `synth.py`; a test enforces that no item is shared with the training templates.
"""
from __future__ import annotations

import pandas as pd

LOW, MED, HIGH = "low", "medium_plus", "high"

# (category, expectation, text)
_ITEMS: list[tuple[str, str, str]] = [
    # --- idioms and hyperbole that are NOT about self-harm: must stay low
    ("idiom", LOW, "This lecture is literally killing me, it is so boring"),
    ("idiom", LOW, "I'm dying for a cup of coffee right now"),
    ("idiom", LOW, "My laptop just died and I lost half my essay"),
    ("idiom", LOW, "I almost died laughing at my roommate's story this morning"),
    ("idiom", LOW, "Traffic this morning was murder and I'm exhausted"),
    ("idiom", LOW, "If I have to sit through one more meeting I'll lose my mind"),
    ("idiom", LOW, "I'm so hungry I could eat a horse"),
    ("idiom", LOW, "Dad will have my head if I scratch his car"),
    ("idiom", LOW, "That exam question was brutal, it completely destroyed me"),
    ("idiom", LOW, "I'm dead on my feet after the night shift"),
    ("idiom", LOW, "I could scream, the wifi keeps dropping again"),
    ("idiom", LOW, "Our team killed that presentation today, I'm thrilled"),
    ("idiom", LOW, "I'd kill for a nap right now"),
    ("idiom", LOW, "Mum is going to murder me when she sees the phone bill"),
    ("idiom", LOW, "The heat today is unbearable, I'm melting"),
    # --- ordinary stress
    ("stress", LOW, "Final exams start Monday and I haven't revised half the syllabus"),
    ("stress", LOW, "I'm struggling to balance my part-time job and my classes"),
    ("stress", LOW, "My thesis supervisor wants a full draft in a week and I'm panicking"),
    ("stress", LOW, "I keep losing sleep over the interview next week"),
    ("stress", LOW, "Everything feels like too much with the group assignment and my lab work"),
    ("stress", LOW, "I'm anxious about meeting my professor to discuss my grade"),
    ("stress", LOW, "My savings are running low and I'm worried about next semester's fees"),
    ("stress", LOW, "I procrastinated again and now I'm stressed about the submission tonight"),
    # --- ordinary sadness and loneliness
    ("support", LOW, "I miss my old friends so much it hurts sometimes"),
    ("support", LOW, "I've been feeling a bit blue since the weekend, probably the weather"),
    ("support", LOW, "My pet passed away last week and I keep tearing up"),
    ("support", LOW, "I'm nervous about starting at a new school next month"),
    ("support", LOW, "I just want to vent about my day, it was exhausting"),
    ("support", LOW, "I'm lonely in the evenings after classes finish"),
    ("support", LOW, "Things with my girlfriend are rough at the moment and I'm sad about it"),
    ("support", LOW, "I felt really left out at the party yesterday"),
    # --- logistics and greetings
    ("logistics", LOW, "Could you tell me how to reschedule a session?"),
    ("logistics", LOW, "Is there a counsellor who speaks Telugu?"),
    ("logistics", LOW, "What should I do to prepare for my first appointment?"),
    ("logistics", LOW, "Where is the wellness centre located on campus?"),
    ("logistics", LOW, "Thanks a lot, have a good day"),
    ("logistics", LOW, "Can I get a copy of my session notes?"),
    ("logistics", LOW, "How do I delete my account?"),
    # --- worry about someone else, no risk
    ("third_person_benign", LOW, "My roommate is stressed about her exams and I want to help her revise"),
    ("third_person_benign", LOW, "My brother is sad about failing his driving test, how can I cheer him up?"),
    ("third_person_benign", LOW, "My friend just lost her job and I'd like to support her"),
    # --- passive or explicit ideation: must reach at least medium
    ("passive_ideation", MED, "I wish I could go to sleep and never wake up"),
    ("passive_ideation", MED, "Sometimes I think the world would carry on fine without me"),
    ("passive_ideation", MED, "I keep wondering if anyone would even notice if I was gone"),
    ("passive_ideation", MED, "I've been thinking about dying a lot lately"),
    ("passive_ideation", MED, "I don't think I want to keep living like this"),
    ("passive_ideation", MED, "I feel like ending it all but I'm too scared to do anything"),
    ("explicit_ideation", MED, "I think about suicide almost every day"),
    ("explicit_ideation", MED, "I want to kill myself"),
    ("explicit_ideation", MED, "I'm thinking about suicide again this week"),
    ("self_harm", MED, "I've started cutting again"),
    ("self_harm", MED, "I hurt myself when things get too much"),
    ("self_harm", MED, "I have thoughts about hurting myself when I'm upset"),
    ("hyperbole_selfharm", MED, "I'll kill myself if I fail this exam"),
    ("hyperbole_selfharm", MED, "If my parents find out I'm failing I'll just kill myself"),
    ("negated", MED, "I'm not going to kill myself but I keep thinking about it"),
    ("third_person_ideation", MED, "My best friend told me she wants to die and I don't know what to do"),
    ("third_person_ideation", MED, "My cousin keeps saying he doesn't want to live anymore"),
    # --- intent, plan, timing, attempt in progress: must reach high
    ("intent", HIGH, "I'm going to kill myself tonight"),
    ("intent", HIGH, "I've decided to end my life this weekend"),
    ("intent", HIGH, "I'm planning to take my own life after everyone leaves the house"),
    ("intent", HIGH, "I'm going to end it all tonight"),
    ("intent", HIGH, "I wrote a note and I'm doing it tomorrow"),
    ("intent", HIGH, "I took a lot of pills just now and I'm scared"),
    ("intent", HIGH, "I have the means ready and I'm going to do it today"),
    # --- intent without a stock phrase (hard for rules; a real test of the model)
    ("implicit_high", HIGH, "I've said my goodbyes and tonight I'm finally done with everything"),
    ("implicit_high", HIGH, "By the time you read this I won't be here anymore"),
    ("implicit_high", HIGH, "It's decided. Tomorrow is my last day"),
    ("implicit_high", HIGH, "I've given away all my things, I won't need them"),
    # --- someone else in immediate danger
    ("third_person_high", HIGH, "My brother is going to kill himself tonight, he's locked in his room"),
    ("third_person_high", HIGH, "She said she's taking all her pills tonight and I can't reach her"),
    ("third_person_high", HIGH, "My friend just texted goodbye and says he's going to end his life"),
]


def challenge_frame() -> pd.DataFrame:
    df = pd.DataFrame(_ITEMS, columns=["category", "expect", "text"])
    df.insert(0, "id", [f"ch-{i:03d}" for i in range(len(df))])
    return df


def evaluate_challenge(texts: list[str], urgency: list[str], needs_human: list[bool]) -> dict:
    """Pass rates per category for a system's final decisions, given in the order of `challenge_frame()`."""
    df = challenge_frame()
    if list(df["text"]) != list(texts):
        raise ValueError("texts must be the challenge set in its original order")
    rank = {"low": 0, "medium": 1, "high": 2}
    u = [rank[x] for x in urgency]
    ok = []
    for exp, ur, hum in zip(df["expect"], u, needs_human):
        if exp == LOW:
            ok.append(ur == 0)
        elif exp == MED:
            ok.append(ur >= 1)
        else:
            ok.append(ur == 2 and bool(hum))
    df = df.assign(passed=ok, no_human=[not h for h in needs_human])
    by_cat = {c: {"passed": int(g["passed"].sum()), "total": int(len(g))} for c, g in df.groupby("category", sort=False)}
    benign = df[df["expect"] == LOW]
    return {
        "overall": {"passed": int(df["passed"].sum()), "total": int(len(df))},
        "by_category": by_cat,
        "benign_stay_low": {"passed": int(benign["passed"].sum()), "total": int(len(benign))},
        "benign_no_human": {"passed": int(benign["no_human"].sum()), "total": int(len(benign))},
        "must_escalate_met": {"passed": int(df.loc[df["expect"] != LOW, "passed"].sum()),
                              "total": int((df["expect"] != LOW).sum())},
        "failures": df.loc[~df["passed"], ["id", "category", "expect"]].to_dict(orient="records"),
    }
