"""Template-based synthetic chat messages (NO language-model API involved).

What this is: fictional, programmatically composed messages in the voice of someone chatting with a support service,
written by the code author from fragments. They are always flagged `is_synthetic=True`, belong to the TRAIN split only,
and are never used to evaluate anything.

Why it exists: the real training data (Reddit C-SSRS) is long suicide-forum text with no everyday conversation, so a model
trained on it alone treats any emotional message as an emergency. These messages teach the difference between ordinary
stress, loneliness, logistics and idioms ("this exam is killing me") and genuine crisis language.

What it is not: clinical truth. Labels follow the draft labelling guide (not yet clinician-approved), templates are my own
wording, and nothing here includes method details. Results that depend on it are reported as development results.
"""
from __future__ import annotations

import hashlib
import random

import pandas as pd

SOURCE = "synthetic_templates"

_NUM = ["two", "three", "four", "five", "far too many"]
_TASK = ["assignments", "exams", "lab reports", "presentations", "project deadlines", "quizzes"]
_WHEN = ["this week", "on Friday", "by Monday", "tomorrow", "before the end of the month", "next week"]
_STRESS_STATE = ["can't keep up", "don't know where to start", "feel completely swamped", "am running out of time",
                 "keep putting it off and it makes me anxious", "am scared I will fall behind"]
_STRESS_STANDALONE = [
    "Money is really tight this month and the rent is due soon.", "My manager keeps adding tasks and I never get a break.",
    "Placement season is so stressful, everyone seems ahead of me.", "I have not slept properly since the exams started.",
    "I'm worried I will fail my final year project.", "My workload is huge and I feel behind on everything.",
    "I keep comparing my grades with my friends and it stresses me out.", "The pressure from my family about results is a lot.",
    "I have a viva coming up and my mind goes blank when I think about it.", "I'm overwhelmed with studying for entrance exams.",
]
_LONELY_FEEL = ["really lonely", "sad and a bit empty", "down", "homesick", "out of place", "disconnected from everyone"]
_LONELY_EVENT = ["I moved to a new city", "my best friend stopped replying", "the new semester started", "my breakup",
                 "I lost my grandmother", "I started living in the hostel", "I stopped hanging out with my old group"]
_SUPPORT_STANDALONE = [
    "Can we just talk for a bit? I had a rough day.", "I miss my family and I don't know who to tell.",
    "My friends don't really understand what I'm going through.", "I feel like I'm always the one who reaches out first.",
    "I cried after class today and I'm not sure why.", "I just need someone to listen right now.",
    "I feel so tired of pretending that everything is fine.", "Lately I feel unmotivated and flat.",
    "I had a big fight with my mom and I feel terrible about it.", "I'm grieving and some days are harder than others.",
]
_OTHER = [
    "Hi, how does this service work?", "How can I book a session with a counsellor?", "Thank you, that really helped.",
    "What are your opening hours?", "Is this chat private?", "Hello, is anyone available to talk?", "Good evening.",
    "Can I change my appointment to next week?", "Where can I find the self-help resources?", "Thanks for listening to me today.",
    "How long does a counselling session usually last?", "Do I need to create an account to use this?",
]
_IDIOM_THING = ["exam", "traffic", "assignment", "queue at the canteen", "group project", "heat", "deadline", "commute"]
_IDIOM_FORMS = [
    "This {t} is killing me.", "Ugh, this {t} is absolutely killing me today.", "I'm dying to finish this {t}.",
    "I'm dead tired after this {t}.", "I could die of embarrassment after that {t} presentation.",
    "My phone died in the middle of the {t}, so annoying.", "My mom is going to kill me if I fail this {t}.",
    "That {t} joke killed me, I can't stop laughing.", "I'm so done with this {t}, honestly.",
]
_IDEATION = [
    "Sometimes I wish I could just disappear.", "I think everyone would be better off without me.",
    "I don't see the point in going on anymore.", "I wish I would not wake up tomorrow.",
    "Lately I keep thinking about not being around anymore.", "I'm so tired of being alive.",
    "I feel like a burden and I keep thinking it would be easier if I was gone.",
    "Nothing matters and I can't see it ever getting better.", "I keep thinking about ending my life but I have no plan.",
    "I've been having thoughts of hurting myself again.", "I feel completely hopeless and trapped.",
    "I don't want to be here anymore.",
]
_INTENT_LEAD = ["I have decided to", "I am going to", "I am planning to", "I can't wait any longer, I will"]
_INTENT_ACT = ["end my life", "kill myself", "take my own life"]
_INTENT_TIME = ["tonight", "today", "this weekend", "after my exam tomorrow", "as soon as everyone is asleep"]
_HIGH_OTHER = [
    "I have written my goodbye note and tonight is the night.", "This is my last message, goodbye everyone.",
    "I have everything ready and I won't be here tomorrow.", "I'm saying goodbye to everyone today.",
    "I already took what I had and I am scared now.", "I made up my mind, it ends tonight.",
]
_THIRD_MED = ["My friend told me she sometimes wishes she was not alive and I don't know what to say.",
              "My roommate keeps saying he wants to die and I'm worried."]
_THIRD_HIGH = ["My brother just texted that he is going to end his life tonight, please help.",
               "My friend says she is going to kill herself today and she isn't answering."]
_FILLERS = ["honestly", "idk", "tbh", "like", "i guess", "ugh", "well"]


def _noise(text: str, rng: random.Random) -> str:
    """Light, realistic surface noise so templates are not all clean sentences."""
    r = rng.random()
    if r < 0.25:
        text = text.lower()
    if rng.random() < 0.2:
        text = text.rstrip(".!?")
    if rng.random() < 0.2:
        text = f"{rng.choice(_FILLERS)} {text[0].lower() + text[1:]}" if len(text) > 1 else text
    if rng.random() < 0.15 and len(text) > 8:                      # swap two adjacent letters
        i = rng.randrange(1, len(text) - 2)
        if text[i].isalpha() and text[i + 1].isalpha():
            text = text[:i] + text[i + 1] + text[i] + text[i + 2:]
    return text


def _compose(rng: random.Random) -> list[tuple[str, str, str]]:
    """One pass over all template families. Returns (text, intent, urgency)."""
    out: list[tuple[str, str, str]] = []
    out.append((f"I have {rng.choice(_NUM)} {rng.choice(_TASK)} due {rng.choice(_WHEN)} and I {rng.choice(_STRESS_STATE)}.", "stress", "low"))
    out.append((rng.choice(_STRESS_STANDALONE), "stress", "low"))
    out.append((f"I feel {rng.choice(_LONELY_FEEL)} since {rng.choice(_LONELY_EVENT)}.", "emotional_support", "low"))
    out.append((rng.choice(_SUPPORT_STANDALONE), "emotional_support", "low"))
    out.append((rng.choice(_OTHER), "other", "low"))
    out.append((rng.choice(_IDIOM_FORMS).format(t=rng.choice(_IDIOM_THING)), "stress", "low"))
    out.append((rng.choice(_IDEATION), "crisis", "medium"))
    out.append((rng.choice(_THIRD_MED), "crisis", "medium"))
    if rng.random() < 0.8:
        out.append((f"{rng.choice(_INTENT_LEAD)} {rng.choice(_INTENT_ACT)} {rng.choice(_INTENT_TIME)}.", "crisis", "high"))
    else:
        out.append((rng.choice(_HIGH_OTHER + _THIRD_HIGH), "crisis", "high"))
    return out


def build_synthetic(n_rounds: int = 220, seed: int = 2026) -> pd.DataFrame:
    """About 9 messages per round across all families, de-duplicated. Deterministic for a given seed."""
    rng = random.Random(seed)
    seen: dict[str, tuple[str, str]] = {}
    for _ in range(n_rounds):
        for text, intent, urgency in _compose(rng):
            text = _noise(text, rng)
            seen.setdefault(text, (intent, urgency))
    rows = []
    for text, (intent, urgency) in seen.items():
        gid = "syn-" + hashlib.sha256(text.encode()).hexdigest()[:10]
        rows.append({"id": gid, "text": text, "intent": intent, "urgency": urgency, "source": SOURCE, "split": "train",
                     "is_synthetic": True, "group_id": gid})
    return pd.DataFrame(rows).sort_values("id").reset_index(drop=True)


def template_fragments() -> set[str]:
    """Every literal fragment used above (for the test that the challenge set shares none of them)."""
    pools = [_STRESS_STANDALONE, _SUPPORT_STANDALONE, _OTHER, _IDEATION, _HIGH_OTHER, _THIRD_MED, _THIRD_HIGH, _IDIOM_FORMS]
    return {s.lower().strip(" .!?") for p in pools for s in p}
