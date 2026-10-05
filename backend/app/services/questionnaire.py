"""Clinical intake definition. Served to the client and used to validate submissions.

Instruments (all free to use for screening; cite in the capstone report):
  PHQ-9   Kroenke, Spitzer & Williams, 2001  -> items m1..m8 + s0 (item 9, self-harm)
  GAD-7   Spitzer et al., 2006               -> items g1..g7
  C-SSRS  Posner et al., Columbia Univ.      -> screener items c1..c7 (asked only if s0 > 0)
"""
from typing import Literal

from pydantic import BaseModel

VERSION = "1.0"


class Option(BaseModel):
    value: int
    label: str


class Condition(BaseModel):
    question: str
    op: Literal["gt", "eq"]
    value: int


class Question(BaseModel):
    id: str
    section: str
    type: Literal["text", "single", "multi", "frequency", "yesno"]
    prompt: str
    stem: str | None = None
    options: list[Option] = []
    show_if: Condition | None = None


class Section(BaseModel):
    id: str
    title: str
    description: str


class Questionnaire(BaseModel):
    version: str
    sections: list[Section]
    questions: list[Question]


def _opts(*labels: str) -> list[Option]:
    return [Option(value=i, label=label) for i, label in enumerate(labels)]


FREQUENCY = _opts("Not at all", "Several days", "More than half the days", "Nearly every day")
YESNO = _opts("No", "Yes")
STEM = "Over the last 2 weeks, how often have you been bothered by the following problem?"


def _freq(qid: str, section: str, prompt: str) -> Question:
    return Question(id=qid, section=section, type="frequency", stem=STEM, prompt=prompt, options=FREQUENCY)


def _single(qid: str, section: str, prompt: str, *labels: str) -> Question:
    return Question(id=qid, section=section, type="single", prompt=prompt, options=_opts(*labels))


def _yn(qid: str, prompt: str, cond: Condition) -> Question:
    return Question(id=qid, section="safety", type="yesno", prompt=prompt, options=YESNO, show_if=cond)


SECTIONS = [
    Section(id="about", title="Background", description="What brought you here and how long it has been going on."),
    Section(id="mood", title="Mood", description="Depression screening: PHQ-9 items 1 to 8. Item 9 is asked in the Safety step."),
    Section(id="worry", title="Worry", description="Anxiety screening (GAD-7)."),
    Section(id="daily", title="Daily life", description="Sleep, functioning, habits and support."),
    Section(id="history", title="History", description="Previous care and health background."),
    Section(id="safety", title="Safety", description="Self-harm safety assessment: PHQ-9 item 9 and the C-SSRS screener."),
]

_PHQ = [
    "Little interest or pleasure in doing things",
    "Feeling down, depressed, or hopeless",
    "Trouble falling or staying asleep, or sleeping too much",
    "Feeling tired or having little energy",
    "Poor appetite or overeating",
    "Feeling bad about yourself, or that you are a failure or have let yourself or your family down",
    "Trouble concentrating on things, such as reading or watching television",
    "Moving or speaking so slowly that other people could have noticed, or being so fidgety or restless "
    "that you have been moving around a lot more than usual",
]
_GAD = [
    "Feeling nervous, anxious, or on edge",
    "Not being able to stop or control worrying",
    "Worrying too much about different things",
    "Trouble relaxing",
    "Being so restless that it is hard to sit still",
    "Becoming easily annoyed or irritable",
    "Feeling afraid, as if something awful might happen",
]

_S0 = Condition(question="s0", op="gt", value=0)
_C2 = Condition(question="c2", op="eq", value=1)
_C6 = Condition(question="c6", op="eq", value=1)

QUESTIONS: list[Question] = [
    Question(id="a1", section="about", type="text", prompt="In your own words, what has been troubling you lately?"),
    _single("a2", "about", "How long have you been feeling this way?",
            "Less than 2 weeks", "2 weeks to 1 month", "1 to 6 months", "More than 6 months"),
    Question(id="a3", section="about", type="multi",
             prompt="Has anything happened recently that has been weighing on you?",
             options=_opts("Studies or exams", "Relationship", "Family", "Money", "Health",
                           "Losing someone close", "Work", "Nothing specific")),
    *[_freq(f"m{i + 1}", "mood", t) for i, t in enumerate(_PHQ)],
    *[_freq(f"g{i + 1}", "worry", t) for i, t in enumerate(_GAD)],
    _single("f1", "daily",
            "How difficult have these problems made it to do your work or studies, take care of things at home, "
            "or get along with other people?",
            "Not difficult at all", "Somewhat difficult", "Very difficult", "Extremely difficult"),
    _single("f2", "daily", "How many hours do you usually sleep at night?",
            "Less than 4 hours", "4 to 6 hours", "6 to 8 hours", "More than 8 hours"),
    _single("f3", "daily", "How often do you have a drink containing alcohol?",
            "Never", "Monthly or less", "2 to 4 times a month", "2 or more times a week"),
    _single("f4", "daily", "Do you use tobacco or any other substances?",
            "No", "Tobacco", "Other substances", "Prefer not to say"),
    _single("f5", "daily", "Is there someone you trust that you can talk to?", "Yes", "Not sure", "No"),
    _single("h1", "history", "Have you ever talked to a counsellor, psychologist, or psychiatrist?",
            "No, never", "Yes, in the past", "Yes, currently"),
    _single("h2", "history", "Are you taking any medicine for your mental health?", "No", "Yes", "Prefer not to say"),
    _single("h3", "history", "Has anyone in your family had mental health difficulties?", "No", "Yes", "Not sure"),
    _single("h4", "history", "Do you have any long-term physical health condition?", "No", "Yes", "Prefer not to say"),
    Question(id="s0", section="safety", type="frequency", stem=STEM, options=FREQUENCY,
             prompt="Thoughts that you would be better off dead, or of hurting yourself in some way"),
    _yn("c1", "In the past month, have you wished you were dead, or wished you could go to sleep and not wake up?", _S0),
    _yn("c2", "In the past month, have you had any actual thoughts of ending your life?", _S0),
    _yn("c3", "Have you been thinking about how you might do this?", _C2),
    _yn("c4", "Have you had these thoughts and had some intention of acting on them?", _C2),
    _yn("c5", "Have you started to work out, or worked out, the details of how to do it? "
              "Do you intend to carry out this plan?", _C2),
    _yn("c6", "Have you ever done anything, started to do anything, or prepared to do anything to end your life?", _S0),
    _yn("c7", "Was this within the past 3 months?", _C6),
]

QUESTIONNAIRE = Questionnaire(version=VERSION, sections=SECTIONS, questions=QUESTIONS)
BY_ID = {q.id: q for q in QUESTIONS}

Answer = int | str | list[int]


def is_visible(q: Question, answers: dict[str, Answer]) -> bool:
    if q.show_if is None:
        return True
    v = answers.get(q.show_if.question)
    if not isinstance(v, int) or isinstance(v, bool):
        return False
    return v > q.show_if.value if q.show_if.op == "gt" else v == q.show_if.value


def clean_answers(raw: dict[str, Answer]) -> dict[str, Answer]:
    """Validate against the definition. Unknown ids or bad values raise ValueError.
    Answers to questions hidden by branching logic are discarded."""
    cleaned: dict[str, Answer] = {}
    for qid, val in raw.items():
        q = BY_ID.get(qid)
        if q is None:
            raise ValueError(f"unknown question '{qid}'")
        valid = {o.value for o in q.options}
        if q.type == "text":
            if not isinstance(val, str):
                raise ValueError(f"'{qid}' expects text")
            if len(val) > 2000:
                raise ValueError(f"'{qid}' is too long")
            if val.strip():
                cleaned[qid] = val.strip()
        elif q.type == "multi":
            if not isinstance(val, list) or not all(isinstance(x, int) and x in valid for x in val):
                raise ValueError(f"'{qid}' has invalid choices")
            if val:
                cleaned[qid] = sorted(set(val))
        else:
            if isinstance(val, bool) or not isinstance(val, int) or val not in valid:
                raise ValueError(f"'{qid}' has an invalid choice")
            cleaned[qid] = val
    # Drop answers to questions whose branch is not active (definition order guarantees parents come first).
    final: dict[str, Answer] = {}
    for q in QUESTIONS:
        if q.id in cleaned and is_visible(q, final):
            final[q.id] = cleaned[q.id]
    return final
