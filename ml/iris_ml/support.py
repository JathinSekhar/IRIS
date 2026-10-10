"""What IRIS recommends for a message, and how a reviewer can escalate it. Deterministic, no language-model API.

Design (docs/ML_PLAN.md, 2026-10-09): rules + check-in floor -> the AI only ranks -> a person reviews EVERY case -> the person decides.
A "Low" priority therefore means LOWER ESTIMATED URGENCY, NOT ZERO RISK. It is never proof that someone is fine, it never closes a case, and it is
never shown to the person as reassurance.

  plan_support(text, triage_result)   the supportive reply, self-help and resources chosen from what the person actually wrote, plus a note for the
                                      reviewer. Same input, same output: every sentence can be read and approved by a clinician.
  escalate(triage_result, to, why)    a reviewer raises a case to Medium or High. It can only raise, and needs a reason.

Topic matching is keyword-based but context-aware: weighted cues, negation ("not stressed"), positive follow-ups ("exams went well"), idioms
("write down", "low battery"), "can't stop worrying", and whether the person is describing themselves or someone they care about. It is still
a heuristic: it can miss meaning, and when the evidence is thin the plan says so and adds general support instead of guessing.

Wording rules (enforced by tests/test_support.py): no diagnosis, no claim that the person is safe or at no risk, and no scores or urgency labels in
anything the person sees. Self-help is general wellbeing guidance, not treatment. All wording is a first draft for counsellor or clinician review.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

from . import URGENCY, URGENCY_INDEX
from .decision import TriageResult

QUEUE_STATUS = "pending_human_review"          # the only status a new case can have: nothing is approved or ignored automatically
REVIEW_STATUS = "AI-assisted draft - clinical review pending"   # EVERY message carries this until a qualified clinician signs it off (never set by code)

# --- messages that are not tied to one topic ---------------------------------------------------------------------------------------
LISTENING = "Thank you for telling us how you are feeling. What you wrote matters, and it is okay to talk about it."
CLOSING = "You deserve support. A person on our team will review your message, which may take some time."
EMERGENCY_FOOTER = "IRIS is not an emergency service. If you need help right now, call 112 or Tele-MANAS 14416."
CRISIS_LEAD_FLAGGED = "If things ever feel like too much, these services are there for you at any time."
CRISIS_LEAD_URGENT = "Please contact one of these now, even if it feels hard."
FLAGGED_INTRO = "It sounds like things are really hard right now, and we are glad you told us."
URGENT_INTRO = "We are concerned about how you are feeling, and you do not have to go through this alone."
URGENT_REACH_OUT = "If you can, be with someone you trust right now, such as a family member or friend, and tell them how you are feeling."

# Same numbers the app already shows (frontend/src/components/Brand.tsx, pages/Support.tsx).
CRISIS_LINES = (
    "If you are in immediate danger, call 112 or go to the nearest emergency room.",
    "To talk to someone now: Tele-MANAS 14416 (24x7, free, confidential) or KIRAN 1800-599-0019.",
)

# Reviewer-facing notes (never shown to the person).
REVIEWER_URGENT = ("URGENT. Explicit self-harm language or a High provisional priority: follow the urgent-response and human-escalation protocol now, "
                   "whatever any model predicted.")
REVIEWER_FLOOR = ("High priority because of this person's check-in: their safety answers set a High floor. Nothing in this message itself raised a concern. "
                  "Read it with their check-in in mind and look for anything that has changed.")
REVIEWER_MEDIUM = "Medium provisional priority. A person must read this message. Look for anything that should raise it."
REVIEWER_LOW = ("Low provisional priority means LOWER ESTIMATED URGENCY, NOT ZERO RISK. This message is not cleared. A person must read it in the normal review "
                "queue. Read for warning signs, contradictions or anything that does not fit, and escalate to Medium or High if you find any.")
ESCALATION_TEMPLATE = "escalated by a reviewer to {to}: {reason}"

# Good news gets a warm, short reply and NO advice. Only used when nothing concerning is present (see `positive_kind`); a person still reads every message.
POSITIVE_INTRO = {
    "achieve": "Congratulations, that is a real achievement.",
    "social": "That sounds like a lovely day.",
    "better": "We are really glad you are feeling better.",
    "general": "That is wonderful to hear.",
    "greeting": "Hello, and thank you for writing.",
}
POSITIVE_BODY = {
    "achieve": "You put in the effort, and it shows. Be proud of that.",
    "social": "Time with people you care about can be a real source of strength. Keep making room for it.",
    "better": "Keep going at your own pace, and keep doing what is helping.",
    "general": "Enjoy it, and keep doing what is working for you.",
    "greeting": "Write whatever is on your mind, at your own pace. We are listening.",
}
POSITIVE_CLOSE = "If things ever feel different, you are welcome to write here any time."

# What the person is told about their message, from what is really true: whether a person has opened it. No time is promised, because none can be.
STATUS_LINES = {
    ("waiting", False): "A person on our team will read this, which may take some time.",
    ("being_read", False): "A person on our team is reading this now.",
    ("reviewed", False): "A person on our team has read this.",
    ("waiting", True): "Our team has been alerted and a person will read this as soon as possible. We cannot say exactly when, so please call one of the numbers above if you need someone right away.",
    ("being_read", True): "A member of our team is reading your message now. If you need someone right away, please also call one of the numbers above.",
    ("reviewed", True): "A member of our team has read your message. If you need someone right away, you can call one of the numbers above at any time.",
}

# The same helplines as CRISIS_LINES, as tap-to-call cards: (name, detail, number to show, number to dial). A test keeps the numbers identical.
HELPLINES = (
    ("Tele-MANAS", "24×7, free, confidential", "14416", "14416"),
    ("KIRAN", "Mental health helpline", "1800-599-0019", "18005990019"),
    ("In immediate danger", "Emergency services", "112", "112"),
)


def status_line(care_status: str, urgent: bool) -> str:
    return STATUS_LINES[(care_status, bool(urgent))]

BREATHING = ("Slow breathing", "You could try breathing in for 4 seconds, holding for 4, breathing out for 4 and holding for 4, for a few minutes. "
                               "If counting feels uncomfortable, breathe at your own pace instead.")
JOURNAL = ("Journaling", "You could write down what is on your mind for five minutes. It is private to you and does not need to be neat.")
ROUTINE = ("A steady daily routine", "Regular meals, some daylight, a short walk and a regular bedtime help many people feel steadier, if that feels possible right now.")


@dataclass(frozen=True)
class Cue:
    pattern: re.Pattern
    weight: int = 1                  # 2 = specific to the topic, 1 = suggestive but ambiguous
    negatable: bool = True           # False when the pattern already contains its own negation ("can't sleep", "no friends")


@dataclass(frozen=True)
class Topic:
    name: str
    code: str                        # short code used in message ids
    cues: tuple[Cue, ...]
    intro: str
    self_help: tuple[tuple[str, str], ...]
    reach_out: tuple[str, ...]


def _cues(strong: str = "", weak: str = "", strong_fixed: str = "") -> tuple[Cue, ...]:
    out = []
    for pat, w, neg in ((strong, 2, True), (weak, 1, True), (strong_fixed, 2, False)):
        if pat:
            out.append(Cue(re.compile(r"\b(?:" + pat + r")\b", re.IGNORECASE), w, neg))
    return tuple(out)


def _t(name, code, cues, intro, self_help, reach_out) -> Topic:
    return Topic(name, code, cues, intro, tuple(self_help), tuple(reach_out))


TOPICS: tuple[Topic, ...] = (
    _t("academic_stress", "ACAD",
       _cues(strong=r"exams?|assignments?|deadlines?|coursework|homework|thesis|semester|revision|viva|marks|grades?",
             weak=r"study(?:ing)?|college|university|results?|tests?|classes|class|project"),
       "It sounds like study pressure is weighing on you.",
       [("Study planning", "One option is to split the work into 25-minute blocks with 5-minute breaks, and to pick the three most important tasks for tomorrow."),
        ("A real break", "You could step away from the desk for a short walk or stretch between blocks."), BREATHING],
       ["You could talk to a teacher, tutor or classmate about the workload.", "A college counsellor may be able to help with exam stress."]),
    _t("loneliness", "LONE",
       _cues(strong=r"lonely|loneliness|isolated|left out|homesick|miss (?:my )?(?:friends|family|home)", weak=r"alone",
             strong_fixed=r"no friends|(?:nobody|no one) (?:to talk to|understands|cares|to talk)"),
       "Feeling alone can be hard, and it makes sense to say so.",
       [("One small social step", "If it feels possible, you could send a short message to someone you trust, or join one group activity this week."),
        ("Writing it out", "You could write down what you wish someone knew right now. You do not have to share it."), ROUTINE],
       ["You could reach out to a friend or family member, even briefly.", "A counsellor or a peer-support group may be a good place to be heard."]),
    _t("sleep", "SLEEP",
       _cues(weak=r"sleep(?:ing)?|tired(?!\s+of\b)|exhausted|restless|awake",
             strong_fixed=r"(?:can'?t|cannot|couldn'?t|barely|hardly|unable to|trouble|difficulty|struggl\w+ to|not|haven'?t|hasn'?t|hadn'?t)\s+(?:been\s+|\w+\s+)?sleep\w*"
                          r"|insomnia|sleepless|awake (?:all night|at night|until)|up all night"),
       "Not sleeping well can make everything feel harder.",
       [("A wind-down routine", "Some people find it helps to put screens away 30 to 60 minutes before bed and do something calm, such as a warm shower or light reading."),
        ("A regular wake-up time", "Getting up at the same time each day, even after a poor night, can help the body clock settle."), BREATHING],
       ["If sleep trouble goes on for weeks, a doctor or counsellor may be able to help look at what is behind it."]),
    _t("anxiety_worry", "WORRY",
       _cues(strong=r"anxious|panic(?:king)?|panic attacks?|overthinking|on edge|overwhelmed|nervous",
             weak=r"worried|worry|worrying|worries|stress(?:ed|ful)?|pressure|scared|afraid|frightened"),
       "It sounds like a lot is on your mind.",
       [BREATHING, ("Grounding", "You could name 5 things you can see, 4 you can touch, 3 you can hear, 2 you can smell and 1 you can taste."),
        ("Worry list", "You could write each worry down with one small next step beside it, then put the list away for now.")],
       ["You could talk it through with someone you trust.", "A counsellor may be able to teach practical ways to handle worry."]),
    _t("low_mood", "MOOD",
       _cues(strong=r"hopeless|empty|numb|unmotivated|no energy|crying|cry|drained|discouraged|pointless|meaningless|worthless|useless",
             weak=r"sad|down|low|depressed|failure",
             strong_fixed=r"tired of (?:everything|it all|life|living|this|trying|pretending|fighting)|feel(?:ing)?\s+(?:nothing|numb)(?:\s+anymore)?"),
       "It sounds like things feel heavy right now.",
       [ROUTINE, JOURNAL, ("One small thing you usually enjoy", "If it feels possible, you could pick something short, such as music or a walk. It is fine if it does not feel appealing yet.")],
       ["You could tell a trusted friend or family member how you have been feeling.",
        "If this has lasted more than a couple of weeks, a counsellor or doctor may be able to help."]),
    _t("work_money", "WORK",
       _cues(strong=r"jobs?|boss|salary|money|debts?|rent|loans?|bills|unemployed|finances?|fired|laid off", weak=r"work|workplace|fees|office"),
       "Money and work worries can follow you everywhere.",
       [("List and shrink", "You could write down the main worries and one small step for each, and start with the smallest."),
        ("A set worry time", "You could choose a short time each day to plan, so the worry does not fill the whole day."), BREATHING],
       ["You could talk to your manager or HR about workload, or to a financial counsellor about money.", "You could share the load with someone you trust."]),
    _t("relationships", "REL",
       _cues(strong=r"breakup|broke up|boyfriend|girlfriend|husband|wife|divorce|arguments?|argued|fell out|cheat\w+",
             weak=r"partner|parents|family|relationship|fought|fights?"),
       "Difficult relationships can be draining.",
       [("An unsent letter", "You could write everything you want to say to the person without sending it. It may help you sort out your feelings."),
        ("Pause before replying", "If you are upset, it may help to wait an hour before answering a hard message."), BREATHING],
       ["You could talk with someone neutral who knows you well.", "A counsellor may be able to help with difficult relationships."]),
    _t("grief", "GRIEF",
       _cues(strong=r"died|passed away|death of|funeral|grief|grieving|bereaved|lost my (?:mother|father|friend|brother|sister|grandmother|grandfather)"),
       "We are sorry for what you are going through.",
       [("Small routines", "You could keep a few simple routines going, such as meals and a short walk, and be patient with yourself."),
        ("Remembering", "Some people find it helps to write down or share a memory of the person.")],
       ["You could share how you feel with someone close to you.", "A grief counsellor or support group may be able to help."]),
    _t("practical_help", "PRAC", _cues(strong=r"counsellors?|counselors?|therapist|therapy|appointments?"),
       "Looking for support is a good step.",
       [JOURNAL],
       ["You could ask your college, workplace or a local clinic about counselling services.",
        "A counsellor or mental-health professional may be able to help you work out what would suit you."]),
)

# Not cue-matched: chosen when the person is describing someone else they are worried about (see `_about_someone_else`).
SUPPORTING = _t("supporting_others", "OTHER", (),
                "It sounds like you are worried about someone you care about.",
                [("Listen without judging", "You could let them talk, ask how they are, and hold back from rushing to fix things."),
                 ("Encourage support", "You could gently suggest they talk to a counsellor or doctor, and offer to help them find one."),
                 ("Look after yourself too", "Supporting someone can be tiring. It may help to keep your own routines going and talk to someone you trust.")],
                ["You could talk to someone you trust about how this is affecting you.", "A counsellor may also be able to guide you on how to support them.",
                 "If you think they may be in immediate danger, call 112."])
GENERAL = _t("general", "GEN", (), "Thank you for sharing this with us.", (BREATHING, JOURNAL, ROUTINE),
             ("You could talk to a friend, family member or counsellor if you would like more support.",))
ALL_TOPICS = (*TOPICS, SUPPORTING, GENERAL)
_BY_NAME = {t.name: t for t in ALL_TOPICS}


def _slug(s: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", s.upper()).strip("-")


def catalog() -> list[dict]:
    """EVERY sentence the system can show, with a stable id: the single list a clinician reviews. `topics` says where each one is used.

    Shared items (for example the breathing exercise) appear once, with every topic that uses them. Plans are built only from these texts
    (a test checks it), so reviewing this list reviews everything a person can ever read from this module.
    """
    rows: list[dict] = []

    def add(mid, audience, mtype, topics, text):
        rows.append({"id": mid, "audience": audience, "type": mtype, "topics": list(topics), "text": text})

    add("SM-COMMON-LISTEN", "user", "active_listening", ["all"], LISTENING)
    add("SM-COMMON-CLOSE", "user", "closing", ["all"], CLOSING)
    add("SM-COMMON-FOOTER", "user", "emergency_footer", ["all"], EMERGENCY_FOOTER)
    add("SM-CRISIS-LEAD-FLAGGED", "user", "crisis_lead_in", ["flagged"], CRISIS_LEAD_FLAGGED)
    add("SM-CRISIS-LEAD-URGENT", "user", "crisis_lead_in", ["urgent"], CRISIS_LEAD_URGENT)
    for n, line in enumerate(CRISIS_LINES, 1):
        add(f"SM-CRISIS-LINE{n}", "user", "crisis_resource", ["flagged", "urgent"], line)
    add("SM-URGENT-INTRO", "user", "urgent_response", ["urgent"], URGENT_INTRO)
    add("SM-URGENT-REACH", "user", "urgent_response", ["urgent"], URGENT_REACH_OUT)

    sh_use: dict[tuple, list[str]] = {}
    ro_use: dict[str, list[str]] = {}
    for t in ALL_TOPICS:
        for item in t.self_help:
            sh_use.setdefault(item, []).append(t.name)
        for item in t.reach_out:
            ro_use.setdefault(item, []).append(t.name)
    seen: set[str] = set()
    for t in ALL_TOPICS:
        add(f"SM-{t.code}-INTRO", "user", "topic_intro", [t.name], t.intro)
        for n, item in enumerate(t.self_help, 1):
            mid = f"SM-SH-{_slug(item[0])}" if len(sh_use[item]) > 1 else f"SM-{t.code}-SH{n}"
            if mid not in seen:
                seen.add(mid)
                add(mid, "user", "self_help", sh_use[item], f"{item[0]}: {item[1]}")
        for n, item in enumerate(t.reach_out, 1):
            mid = f"SM-RO-{_slug(' '.join(item.split()[:5]))}" if len(ro_use[item]) > 1 else f"SM-{t.code}-RO{n}"
            if mid not in seen:
                seen.add(mid)
                add(mid, "user", "reach_out", ro_use[item], item)

    for kind in POSITIVE_INTRO:
        add(f"SM-POS-{kind.upper()}-INTRO", "user", "positive_intro", ["positive"], POSITIVE_INTRO[kind])
        add(f"SM-POS-{kind.upper()}-BODY", "user", "positive_body", ["positive"], POSITIVE_BODY[kind])
    add("SM-FLAGGED-INTRO", "user", "topic_intro", ["flagged"], FLAGGED_INTRO)
    add("SM-POS-CLOSE", "user", "positive_closing", ["positive"], POSITIVE_CLOSE)
    for n, (name, detail, number, _) in enumerate(HELPLINES, 1):
        add(f"SM-HELPLINE-{n}", "user", "helpline_card", ["flagged", "urgent"], f"{name}: {detail}: {number}")
    for (state, urgent), text in STATUS_LINES.items():
        add(f"SM-STATUS-{state.upper().replace('_', '-')}-{'URGENT' if urgent else 'NORMAL'}", "user", "status_line", ["urgent" if urgent else "all"], text)
    add("SM-REVIEWER-LOW", "reviewer", "reviewer_note", ["low"], REVIEWER_LOW)
    add("SM-REVIEWER-FLOOR", "reviewer", "reviewer_note", ["floor"], REVIEWER_FLOOR)
    add("SM-REVIEWER-MEDIUM", "reviewer", "reviewer_note", ["medium"], REVIEWER_MEDIUM)
    add("SM-REVIEWER-URGENT", "reviewer", "reviewer_note", ["urgent"], REVIEWER_URGENT)
    add("SM-REVIEWER-ESCALATION", "reviewer", "escalation_record", ["escalation"], ESCALATION_TEMPLATE)
    return rows


# --- context handling ------------------------------------------------------------------------------------------------------------------

_IDIOMS = [   # everyday phrases whose words would otherwise look like cues
    (re.compile(r"\b(?:write|writing|wrote|sit|sat|calm|slow|settle|shut|cool|put|jot|note|breaking)\s+down\b"), " "),
    (re.compile(r"\bbreak(?:s)?\s+down\b"), " "),
    (re.compile(r"\b(?:it|this|that|which|everything)\s+works\b|\bwork(?:s|ed)?\s+(?:out|fine|well)\b|\bworkout\b|\bnetwork\b"), " "),
    (re.compile(r"\blow\s+(?:battery|fat|carb|budget|key)\b|\blowest\b"), " "),
    (re.compile(r"\b(?:good|great|new|favou?rite|nice)\s+book\b"), " "),
    (re.compile(r"\b(?:can'?t|cannot|couldn'?t|won'?t|unable to)\s+(?:stop|help)\b"), "keep"),     # "can't stop worrying" = keeps worrying
]
_NEG = {"not", "no", "never", "without", "hardly", "barely", "nothing", "none", "neither", "nor", "isn't", "aren't", "wasn't", "weren't",
        "don't", "doesn't", "didn't", "haven't", "hasn't", "hadn't"}      # NOT can't / won't: "can't pay rent" is the problem, not its denial
_NEG_LONGER = re.compile(r"\bno longer\b|\bused to\b")      # past or finished: "I used to be anxious"
_POSITIVE_AFTER = re.compile(r"^\W*(?:\w+\W+){0,2}?(?:fine|well|okay|ok|great|good|better|alright|easy|smoothly)\b")
_OTHER = re.compile(r"\b(?:my|a)\s+(?:best\s+|close\s+|little\s+|older\s+|younger\s+)?(?:friend|brother|sister|mom|mother|dad|father|cousin|roommate|"
                    r"colleague|son|daughter|partner|boyfriend|girlfriend|husband|wife|classmate|student|neighbou?r|mate)\b")
_CONCERN = re.compile(r"\b(?:worried about|concerned about|how (?:can|do|should) i help|help (?:him|her|them)|what (?:can|should) i do|"
                      r"is (?:struggling|depressed|sad|lonely|stressed|anxious|not (?:eating|sleeping|talking|coming)|isolating)|"
                      r"isn'?t (?:eating|sleeping|talking|coming)|has been (?:sad|down|quiet|withdrawn)|(?:he|she|they) keeps? (?:crying|saying)|(?:told me|said|says|mentioned) (?:that )?(?:he|she|they))")
_SELF_FEELING = re.compile(r"\bi(?:'m| am| feel|'ve been| have been feeling| keep| can'?t| cannot| don'?t| am so| feel so)\b")


def _prepare(text: str) -> str:
    t = text.lower().replace("’", "'").replace("‘", "'")
    for pat, repl in _IDIOMS:
        t = pat.sub(repl, t)
    return re.sub(r"\s+", " ", t).strip()


def _negated(t: str, start: int) -> bool:
    before = t[max(0, start - 45):start].split()[-3:]
    return any(w.strip(",.;:!?\"()") in _NEG for w in before) or bool(_NEG_LONGER.search(t[max(0, start - 30):start]))


_REPORTED = re.compile(r"\b(?:told me|said|says|mentioned) (?:that )?(?:he|she|they)\b")      # "She told me she is ...": no relationship word needed


def _about_someone_else(t: str) -> bool:
    return bool(_REPORTED.search(t) or (_OTHER.search(t) and _CONCERN.search(t)))


def explain_topics(text: str) -> list[dict]:
    """Every topic with evidence, strongest first: score, whether any specific cue fired, and which cues (for audit and tests)."""
    t = _prepare(text)
    scores: dict[str, dict] = {}
    for order, topic in enumerate(TOPICS):
        score, strong, hits = 0, False, []
        for cue in topic.cues:
            counted = 0
            for m in cue.pattern.finditer(t):
                if cue.negatable and (_negated(t, m.start()) or _POSITIVE_AFTER.match(t[m.end():m.end() + 30])):
                    continue
                if counted < 2:                                   # a word repeated does not make a topic stronger than two mentions
                    score += cue.weight
                    counted += 1
                strong = strong or cue.weight == 2
                hits.append(m.group(0))
        if score:
            scores[topic.name] = {"topic": topic.name, "score": score, "strong": strong, "cues": hits, "order": order}
    if _about_someone_else(t):
        if not _SELF_FEELING.search(t):                           # only the other person is described: their cues are not the writer's
            scores = {}
        scores["supporting_others"] = {"topic": "supporting_others", "score": 3, "strong": True, "cues": ["someone else"], "order": -1}
    return sorted(scores.values(), key=lambda d: (-d["score"], not d["strong"], d["order"]))


_POSITIVE = re.compile(
    r"\b(?:great|wonderful|amazing|fantastic|happy|proud|excited|thrilled|delighted|glad|grateful|thankful|enjoy(?:ed|ing)?|celebrat\w+|"
    r"went (?:really |very |so )?well|good news|passed|promoted|got the job|got a job|achiev\w+|"
    r"(?:doing|feeling|feel|much|a lot) better|going (?:really |very |so )?well|feel calm|feeling calm|calm now|improv(?:ed|ing)|recover(?:ed|ing)|relieved|calmer|lovely day|good day|thank you|thanks|helped me|really helped|helpful)\b", re.IGNORECASE)
_DISTRESS = re.compile(
    r"\b(?:sad|anxious|anxiety|worried|worry|worries|worrying|stress(?:ed|ful)?|overwhelm\w*|lonely|alone|can'?t|cannot|couldn'?t|tired|exhaust\w*|hopeless|"
    r"worthless|useless|empty|numb|cry|crying|scared|afraid|struggl\w+|difficult|hard|bad|worse|worst|awful|terrible|horrible|angry|upset|hurt|pain|"
    r"depress\w*|nobody|no one|panic\w*|nervous|pressure|fail(?:ed|ure)?|lost|miss|missing|sorry|guilty|ashamed|burden|unhappy|miserable|down|low|"
    r"disappear\w*|gone|die|dead|death|kill\w*|suicid\w*|end it|ending)\b", re.IGNORECASE)
_KIND = [
    ("better", re.compile(r"\b(?:better|improv\w+|recover\w+|relieved|calmer)\b", re.IGNORECASE)),
    ("achieve", re.compile(r"\b(?:exams?|results?|passed|promot\w+|job|interview|marks|grades?|proud|achiev\w+|finished|completed|won)\b", re.IGNORECASE)),
    ("social", re.compile(r"\b(?:friends?|family|party|trip|together|met|with them)\b", re.IGNORECASE)),
]


_GREETING = re.compile(r"(?:hi+|hello+|hey+|hii+|good\s+(?:morning|afternoon|evening)|namaste)(?:\s+(?:there|iris|everyone))?\s*[.!]*", re.IGNORECASE)


def positive_kind(text: str) -> str | None:
    """'achieve' | 'social' | 'better' | 'general' when the message is clearly good news, else None.

    Deliberately strict: ANY sign of distress that is not negated or in the past ("not stressed", "I used to feel anxious") makes this None, so a mixed
    message ("I passed, but I feel worthless") gets the normal careful reply. The caller also requires that no safety rule fired. This is a keyword
    heuristic that can miss sarcasm and mixed feelings, which is one more reason a person reads every message.
    """
    t = _prepare(text)
    if _GREETING.fullmatch(t.strip()):
        return "greeting"
    pos = [m for m in _POSITIVE.finditer(t) if not _negated(t, m.start())]
    if not pos:
        return None
    if any(not _negated(t, m.start()) for m in _DISTRESS.finditer(t)):
        return None
    for kind, rx in _KIND:
        if rx.search(t):
            return kind
    return "general"


def match_topics(text: str, limit: int = 3) -> tuple[str, ...]:
    """The topics the message is actually about, best-supported first. Empty means nothing specific was recognised."""
    return tuple(d["topic"] for d in explain_topics(text)[:limit])


@dataclass(frozen=True)
class SupportPlan:
    # --- for the person (never contains scores, urgency labels, or the word "risk") ---
    topics: tuple[str, ...]
    intro: str
    listening: str
    self_help: tuple[tuple[str, str], ...]
    reach_out: tuple[str, ...]
    crisis_lead: str                  # one line introducing the helplines (empty when none are shown)
    crisis_lines: tuple[str, ...]
    show_crisis_resources: bool
    emergency_footer: str             # always present: IRIS is not an emergency service
    closing: str
    layout: str                       # how to present it: tips | celebrate | support | help_now (presentation only; never shown as a word)
    helplines: tuple[tuple[str, str, str, str], ...]   # tap-to-call cards, same numbers as crisis_lines; empty unless a safety layer fired
    a_person_may_reach_out: bool
    # --- for the system and the reviewer ---
    queue_status: str
    provisional_priority: str
    urgent_protocol: bool
    human_review_required: bool
    reviewer_note: str
    match_confidence: str = "none"    # "clear" | "tentative" | "none": how well the message matched a topic. Tentative and none add general support


def reviewer_note(result: TriageResult, urgent: bool) -> str:
    if urgent:
        base = REVIEWER_URGENT
    elif result.urgency == "high":
        base = REVIEWER_FLOOR                      # High only because of the check-in floor
    else:
        base = REVIEWER_MEDIUM if result.urgency == "medium" else REVIEWER_LOW
    return base + " Reasons: " + "; ".join(result.reasons)


def plan_support(text: str, result: TriageResult) -> SupportPlan:
    """The supportive plan for one message. `result` should come from the V1 policy, so `needs_human` is always true."""
    urgent = result.message_urgent                 # this MESSAGE is urgent (not merely a High floor from the check-in)
    flagged = urgent or result.urgency in ("medium", "high") or result.rule_level != "none" or result.baseline_floor != "none"
    positive = None if (urgent or result.rule_level != "none") else positive_kind(text)
    if positive is not None and result.rule_level == "none" and not urgent:
        return SupportPlan(
            topics=("positive",), intro=POSITIVE_INTRO[positive], listening=POSITIVE_BODY[positive], self_help=(), reach_out=(() if positive == "greeting" else (POSITIVE_CLOSE,)),
            crisis_lead=CRISIS_LEAD_FLAGGED if flagged else "", crisis_lines=CRISIS_LINES if flagged else (), show_crisis_resources=flagged,
            emergency_footer=EMERGENCY_FOOTER, closing=CLOSING, layout="celebrate", helplines=HELPLINES if flagged else (),
            a_person_may_reach_out=True, queue_status=QUEUE_STATUS, provisional_priority=result.urgency, urgent_protocol=False,
            human_review_required=True, reviewer_note=reviewer_note(result, False), match_confidence="clear",
        )
    found = explain_topics(text)[:3]
    found.sort(key=lambda d: not (d["topic"] == "low_mood" and d["strong"]))   # a heavy feeling comes first (stable sort)
    names = tuple(d["topic"] for d in found)
    best = found[0] if found else None
    confidence = "none" if best is None else ("clear" if best["score"] >= 2 and best["strong"] else "tentative")
    chosen = [_BY_NAME[n] for n in names]
    if confidence != "clear":
        chosen.append(GENERAL)                                    # thin evidence: add general support instead of guessing
    self_help: list[tuple[str, str]] = []
    reach_out: list[str] = []
    if urgent:
        intro = URGENT_INTRO
        reach_out = [URGENT_REACH_OUT]
    elif result.rule_level != "none" and "supporting_others" not in names:
        # The message itself contains concerning language: no self-help tips (they can read as dismissive), only support, a person to talk to and the helplines.
        intro = FLAGGED_INTRO
        reach_out = list(GENERAL.reach_out)
    else:
        intro = chosen[0].intro if confidence == "clear" else GENERAL.intro      # do not open with a guess
        for i in range(max(len(t.self_help) for t in chosen)):          # interleave, so every matched topic is represented
            for t in chosen:
                if i < len(t.self_help) and t.self_help[i] not in self_help:
                    self_help.append(t.self_help[i])
        for i in range(max(len(t.reach_out) for t in chosen)):
            for t in chosen:
                if i < len(t.reach_out) and t.reach_out[i] not in reach_out:
                    reach_out.append(t.reach_out[i])
        self_help = self_help[:4]
        if confidence == "none":
            self_help = []                                           # nothing was recognised: do not hand out a tip that may not fit
        reach_out = reach_out[:3]
    return SupportPlan(
        topics=names or ("general",), intro=intro,
        listening=LISTENING,
        self_help=tuple(self_help), reach_out=tuple(reach_out),
        crisis_lead=(CRISIS_LEAD_URGENT if urgent else CRISIS_LEAD_FLAGGED) if flagged else "",
        crisis_lines=CRISIS_LINES if flagged else (), show_crisis_resources=flagged,
        emergency_footer=EMERGENCY_FOOTER, closing=CLOSING,
        layout="help_now" if urgent else ("support" if result.rule_level != "none" else "tips"), helplines=HELPLINES if flagged else (),
        a_person_may_reach_out=True,
        queue_status=QUEUE_STATUS, provisional_priority=result.urgency, urgent_protocol=urgent,
        human_review_required=True, reviewer_note=reviewer_note(result, urgent), match_confidence=confidence,
    )


def user_facing_text(plan: SupportPlan) -> str:
    """Everything the person would read, as one string. The tests scan this for unsupported claims."""
    parts = [plan.intro, plan.listening, plan.closing, plan.emergency_footer, *plan.reach_out, *([plan.crisis_lead] if plan.crisis_lead else []), *plan.crisis_lines]
    parts += [f"{title}: {how}" for title, how in plan.self_help]
    parts += [f"{name}: {detail}: {number}" for name, detail, number, _ in plan.helplines]
    return "\n".join(parts)


def validate_escalation(current: str, to: str, reason: str) -> str:
    """The one rule for reviewer escalation, shared by the library and the backend: raise only, to medium or high, with a reason. Returns the clean reason."""
    if to not in ("medium", "high"):
        raise ValueError("a reviewer can escalate to 'medium' or 'high'")
    if not reason or not reason.strip():
        raise ValueError("an escalation needs a reason")
    if URGENCY_INDEX[to] < URGENCY_INDEX[current]:
        raise ValueError(f"cannot lower {current} to {to} here; escalation only raises")
    return reason.strip()


def escalate(result: TriageResult, to: str, reason: str) -> TriageResult:
    """A reviewer raises a case to medium or high. It can only raise, it needs a reason, and the case stays in human hands."""
    reason = validate_escalation(result.urgency, to, reason)
    idx = URGENCY_INDEX[to]
    return replace(result, urgency=URGENCY[idx], route="human_reviewer", needs_human=True, message_urgent=result.message_urgent or to == "high",
                   risk_score=max(result.risk_score, float(idx)),
                   reasons=result.reasons + (ESCALATION_TEMPLATE.format(to=to, reason=reason),))
