"""M0: the rule-based safety net. It runs BEFORE any model and the model can never override it.

It is deliberately recall-first: a false alarm costs a reviewer a few seconds, a miss can cost a life. It looks only
for explicit self-harm / suicide language (including common obfuscations like "k*ll", "su1c1de", "unalive") and
does not try to understand nuance; that is the model's job.

Output levels
  high    explicit intent, plan, means, imminent timing, or an attempt in progress  -> urgency floor HIGH
  review  ideation, self-harm, euphemisms, or third-party risk                       -> urgency floor MEDIUM
  none    nothing explicit found (says nothing about whether the message is safe)

Known trade-offs (also covered by tests):
  * Third-person risk ("my friend wants to kill himself") is flagged; it needs a human too.
  * Negations ("I'm not suicidal") are still flagged, with `negated=True` for the reviewer: cheap to check, costly to miss.
  * Words like "suicide" in a neutral context ("a documentary about suicide prevention") are false positives by design.
  * "can't do this anymore" is NOT matched: far too common for exam stress. Leave it to the model.
English only in v1. Hindi/Hinglish/Telugu/Tamil patterns are future work and need native-speaker review.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Vowel positions tolerate common masking: k*ll, k!ll, k1ll, su1c1de, d!e
_V = r"[aeiou@!*0134]"


def _fz(word: str) -> str:
    """Fuzzy regex for a word: repeated letters allowed, vowels may be masked by symbols or digits."""
    return "".join((_V if ch in "aeiou" else re.escape(ch)) + "+" for ch in word)


KILL = _fz("kill")
SUICIDE = r"s+u+" + _V + r"+c+" + _V + r"+d+(?:" + _V + r"+|" + r"[a@4]+l+)"
MYSELF = r"(?:my\s*self)"
THIRD = r"(?:him\s*self|her\s*self|them\s*selves)"
ENDLIFE = (r"(?:end\s+(?:it\s+all|it|my\s+(?:own\s+)?life|things)|ending\s+(?:my\s+(?:own\s+)?life|it\s+all)"
           r"|take\s+my\s+(?:own\s+)?life|commit\s+" + SUICIDE + r")")
TIME = r"(?:tonight|today|tomorrow|right\s+now|this\s+(?:weekend|evening|morning|afternoon)|in\s+an\s+hour|later\s+today)"
INTENT_LEAD = r"(?:going\s+to|gonna|about\s+to|plan(?:ning)?\s+(?:to|on)|intend(?:ing)?\s+to|decided\s+to|will)"
METHODS = r"(?:pills|tablets|rope|gun|knife|blade|razor|poison|noose)"
DEATH = r"(?:" + KILL + r"\s+" + MYSELF + r"|" + ENDLIFE + r"|d+i+e+|de+a+d+|" + SUICIDE + r")"

# (name, level, pattern). Order does not matter; the highest level wins.
_RULES: list[tuple[str, str, str]] = [
    # ---- high: intent / plan / means / timing / in progress
    ("intent_statement", "high",
     INTENT_LEAD + r"\s+(?:finally\s+)?(?:" + KILL + r"\s+" + MYSELF + r"|" + ENDLIFE + r"|hang\s+" + MYSELF + r"|overdose|" + SUICIDE + r"\b"
     r"|jump\s+off\s+(?:a\s+|the\s+)?(?:bridge|building|roof|terrace|balcony|cliff))"),
    ("imminent_timing", "high",
     TIME + r".{0,50}(?:" + KILL + r"\s+" + MYSELF + r"|" + ENDLIFE + r"|" + SUICIDE + r")"),
    ("imminent_timing_after", "high",
     r"(?:" + KILL + r"\s+" + MYSELF + r"|" + ENDLIFE + r").{0,30}" + TIME),
    ("means_and_intent", "high",
     r"\b(?:i\s+(?:have|got|bought|found)|i'?ve\s+(?:got|bought|found)).{0,30}" + METHODS + r".{0,60}" + DEATH),
    ("note_or_goodbye", "high",
     r"(?:wrote|writing|left|leaving)\s+(?:a\s+)?(?:" + SUICIDE + r"|goodbye)\s+note|this\s+is\s+my\s+(?:last|final)\s+(?:message|post|goodbye)"),
    ("attempt_in_progress", "high",
     r"\bi\s+(?:already|just)\s+(?:took|swallowed|drank).{0,25}(?:all|many|too\s+many|a\s+lot).{0,20}(?:pills|tablets|meds|medication)"
     r"|(?:overdosed|overdosing)\s+on\s+purpose|cut(?:ting)?\s+my\s+wrists?"),
    ("third_party_imminent", "high",
     r"\b(?:he|she|they|my\s+\w+|\w+)\s+(?:is|are|'s)?\s*" + INTENT_LEAD + r"\s+(?:" + KILL + r"\s+" + THIRD
     + r"|end\s+(?:his|her|their)\s+life|commit\s+" + SUICIDE + r")"),
    ("means_ready", "high",
     r"\b(?:the\s+)?(?:means|method|pills|tablets|rope|gun|blade|poison)\s+(?:is\s+|are\s+)?(?:all\s+)?(?:ready|prepared|set|in\s+place)\b"
     r".{0,80}\b(?:do\s+it|go\s+through\s+with\s+it|end\s+it|finish\s+it)\b"),
    ("note_phrase", "high", r"by\s+the\s+time\s+you\s+(?:read|see|get)\s+this"),
    # ---- review: ideation / self-harm / euphemisms / third party
    ("kill_myself", "review", KILL + r"\s+" + MYSELF),
    ("end_my_life", "review", ENDLIFE),
    ("suicide_word", "review", r"\b" + SUICIDE + r"\b"),
    ("want_to_die", "review", r"\b(?:want(?:ed|s)?\s+to|wanna|wish(?:ed)?\s+(?:i|that\s+i)\s+(?:was|were|could)?)\s*(?:d+i+e+|be\s+de+a+d+|de+a+d+)\b"),
    ("better_off_dead", "review",
     r"better\s+off\s+(?:dead|without\s+me)|(?:everyone|they|family|world)(?:'d|\s+would)\s+be\s+better\s+off\s+without\s+me"),
    ("wouldnt_be_missed", "review",
     r"(?:nobody|no\s+one|no-one)\s+(?:would|will|'d)\s+(?:even\s+)?(?:notice|miss|care|know)(?:\s+(?:me|about\s+me))?\s+if\s+(?:i|i'?m|i\s+was|i\s+were|i\s+am)\s+"
     r"(?:gone|dead|died|disappear(?:ed)?|not\s+(?:here|around|alive))"),
    ("no_point_in_anything", "review",
     r"(?:don'?t|do\s+not|can'?t|cannot|no\s+longer)\s+see\s+(?:the\s+|any\s+)?(?:point|purpose|reason)\s+(?:in|of|to)\s+"
     r"(?:anything|living|life|going\s+on|being\s+here|all\s+this|any\s+of\s+it)"),
    ("cant_take_it_anymore", "review",
     r"(?:can'?t|cannot|couldn'?t)\s+(?:take|bear|stand|handle)\s+(?:it|this|any\s+of\s+it|everything)\s+(?:any\s*more|any\s+longer)"),
    ("cannot_face_another_day", "review",
     r"(?:can'?t|cannot|couldn'?t)\s+(?:face|survive|get\s+through|go\s+through)\s+(?:another|one\s+more|any\s+more)\s+(?:day|night|morning)"),
    ("happier_without_me", "review",
     r"(?:everyone|everybody|they|my\s+family|the\s+world)(?:'d|\s+would|\s+will)\s+(?:be|feel)\s+(?:so\s+much\s+|a\s+lot\s+)?(?:happier|better(?:\s+off)?|relieved|fine)\s+"
     r"if\s+i\s+(?:wasn'?t|weren'?t|was\s+not|were\s+not)\s+(?:around|here|alive|there)|(?:happier|better(?:\s+off)?|relieved)\s+if\s+i\s+(?:was|were)\s+gone"),
    ("dont_want_to_live", "review",
     r"don'?t\s+want\s+to\s+(?:be\s+here|live|exist|wake\s+up|be\s+alive)(?:\s+anymore)?|no\s+(?:reason|point)\s+(?:to|in)\s+(?:live|living|going\s+on|being\s+alive)|can'?t\s+go\s+on\b"),
    ("wish_not_here", "review",
     r"wish(?:ed)?\s+(?:i|that\s+i)\s+(?:wasn'?t|weren'?t|was\s+not|were\s+not|had\s+never\s+been|never\s+was)\s+(?:here|alive|born|around|existing|a\s+burden)"
     r"|wish(?:ed)?\s+(?:i|that\s+i)\s+(?:could\s+)?(?:just\s+)?(?:disappear|vanish)(?!\s+(?:into|in\s+a|for\s+(?:a\s+)?(?:while|week|weekend|day)))|wish(?:ed)?\s+(?:i|that\s+i)\s+(?:would|could)\s*n'?t\s+wake\s+up"
     r"|never\s+(?:have\s+)?been\s+born"),
    ("euphemism", "review", r"\bun-?alive\s+(?:my\s*self|me)\b|\bunalive\b|end(?:ing)?\s+it\s+all|(?:not|never)\s+wake\s+up|sleep\s+forever|disappear\s+forever"),
    ("self_harm", "review",
     r"self[\s-]*harm|(?:hurt|hurting|cut|cutting|burn|burning|slit|slitting|hang|hanging)\s+" + MYSELF
     + r"|slit\s+my\s+(?:wrists?|throat)"),
    ("last_day_signals", "review",
     r"(?:tonight|tomorrow|today)\s+(?:is|will\s+be)\s+my\s+last\s+(?:day|night)|(?:won'?t|will\s+not)\s+be\s+here\s+(?:anymore|tomorrow|after\s+(?:today|tonight))"
     r"|given\s+away\s+all\s+my\s+(?:things|stuff|belongings)"),
    ("jump_method", "review", r"jump\s+off\s+(?:a\s+|the\s+)?(?:bridge|building|roof|terrace|balcony|cliff)"),
    ("third_party_risk", "review",
     r"(?:" + KILL + r"|hurt|harm|hang)(?:ing)?\s+" + THIRD + r"|(?:friend|brother|sister|mom|mother|dad|father|cousin|classmate|roommate|boyfriend|girlfriend|partner|colleague|son|daughter)\b.{0,40}(?:" + SUICIDE + r"|want(?:s|ed)?\s+to\s+die)"),
]
_COMPILED = [(n, lvl, re.compile(p, re.IGNORECASE | re.DOTALL)) for n, lvl, p in _RULES]
_LEVEL_ORDER = {"none": 0, "review": 1, "high": 2}
_FLOOR = {"none": "none", "review": "medium", "high": "high"}
_THIRD_PERSON = re.compile(
    r"\b(?:my|a)\s+(?:best\s+)?(?:friend|brother|sister|mom|mother|dad|father|cousin|classmate|roommate|boyfriend|girlfriend|"
    r"partner|colleague|son|daughter|student)\b|\b(?:he|she|they)\s+(?:is|was|said|told|wants?|wanted|keeps?|talks?)\b|"
    + THIRD, re.IGNORECASE)
_NEGATION = re.compile(r"(?:\bnot\b|\bnever\b|n't\b|\bno\s+longer\b|\bwouldn'?t\b|\bwon'?t\b)\W+(?:\w+\W+){0,2}$", re.IGNORECASE)


@dataclass(frozen=True)
class RuleResult:
    level: str                  # "none" | "review" | "high"
    urgency_floor: str          # "none" | "medium" | "high": the minimum IRIS urgency this implies
    hits: tuple[str, ...]       # names of the rules that fired
    third_person: bool          # the risk seems to concern someone else (metadata only; level is not lowered)
    negated: bool               # the phrase appears negated, e.g. "not suicidal" (metadata only; level is not lowered)

    @property
    def flagged(self) -> bool:
        return self.level != "none"


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"[​-‏⁠﻿]", "", t)          # zero-width characters used to dodge filters
    t = t.replace("’", "'").replace("‘", "'")         # curly quotes
    t = re.sub(r"(\w)\1{3,}", r"\1\1", t)                       # sooooo -> soo
    return re.sub(r"\s+", " ", t).strip()


def scan(text: str) -> RuleResult:
    t = normalize(text)
    hits: list[str] = []
    level = "none"
    negated = False
    first_start: int | None = None
    for name, lvl, rx in _COMPILED:
        m = rx.search(t)
        if not m:
            continue
        hits.append(name)
        if _LEVEL_ORDER[lvl] > _LEVEL_ORDER[level]:
            level = lvl
        if first_start is None or m.start() < first_start:
            first_start = m.start()
        if _NEGATION.search(t[max(0, m.start() - 25):m.start()]):
            negated = True
    third = bool(hits) and (any(h.startswith("third_party") for h in hits) or
                            bool(_THIRD_PERSON.search(t[max(0, (first_start or 0) - 60):(first_start or 0) + 40])))
    return RuleResult(level=level, urgency_floor=_FLOOR[level], hits=tuple(hits), third_person=third, negated=negated)
