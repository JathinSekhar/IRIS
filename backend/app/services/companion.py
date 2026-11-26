"""An optional conversational reply for ORDINARY messages, written by a language model (Groq).

This is the only place a model writes words a person reads, so it is fenced in on every side:

* It is OFF unless `IRIS_LLM_ENABLED=true` and a key is configured. Without it IRIS behaves exactly as before (fixed reviewed wording).
* It is used only when nothing worrying was found: no rule hit, not message-urgent, no High priority, and the check-in floor is not High.
  Anything flagged, urgent or from a High floor keeps the fixed reviewed wording, the helplines and the human review. The model never sees those cases.
* The person's own message is scanned by the rule layer BEFORE the call (the caller does that), and the model's output is scanned AFTER: any rule hit,
  a promise, a diagnosis, a time, a number, an emoji or an over-long answer is thrown away and the fixed wording is used instead.
* A failure of any kind (no key, timeout, bad answer) returns None. The chat never breaks and never waits on the model for long.
* Every reply carries a visible "written by an AI assistant" note, and a person still reads every message. It is an AI-assisted draft, not clinician approved.
"""
from __future__ import annotations

import re

import httpx

from ..config import settings
from . import triage

CONCERN_WORD = "CONCERN"
SYSTEM_PROMPT = (
    "You are the listening voice of IRIS, a student wellbeing support space. A person on the team reads every message later.\n"
    f"FIRST, before anything else: if the person's message could be about suicide, self-harm, wanting to die, not wanting to live, ending everything, "
    f"or giving up on life, in any language, slang or mix of languages (for example Hindi or Hinglish), even indirectly, answer with only the word "
    f"{CONCERN_WORD} and nothing else. When in doubt, answer {CONCERN_WORD}. Otherwise write the reply below.\n"
    "Write a short, warm reply in plain language: two or three sentences, at most 60 words.\n"
    "First reflect back, in your own words, what the person said or seems to be feeling. Then ask ONE gentle, open follow-up question that helps them say more.\n"
    "Rules you must follow:\n"
    "- Do not give a diagnosis, a label, medical advice or a list of tips.\n"
    "- Do not promise anything, and do not say or imply that anyone will contact them, help is coming, or when anyone will reply.\n"
    "- Do not say they are safe or fine, and do not tell them not to worry.\n"
    "- Do not mention helplines, numbers or emergencies.\n"
    "- Do not use emojis, lists or headings. Do not say you are a doctor, counsellor or human.\n"
    "- If the message is only a greeting, greet them back and invite them to share what is on their mind.\n"
    "- If the message is good news, share in it simply and ask what made it good."
)

_FORBIDDEN = re.compile(
    r"\b(?:promise|guarantee|guaranteed|you(?:'re| are) (?:safe|fine|okay|ok)|don'?t worry|diagnos\w+|disorder|depress(?:ed|ion)|"
    r"anxiety disorder|medicat\w+|prescri\w+|someone will|a (?:person|doctor|counsellor|counselor|therapist) will|we will (?:call|contact|reach|be there)|"
    r"help is (?:on|coming)|within|minutes?|hours?|soon|112|14416|helpline|emergency|i am a|i'?m a (?:doctor|counsel|therap|human))\b",
    re.IGNORECASE,
)
# The guard: if the model's own words talk about self-harm, death or pills, the person most likely wrote something the rule layer missed (other
# languages, unusual phrasing). The reply is then never shown; the message is treated as flagged instead (fixed wording, helplines, Medium priority).
_CONCERN = re.compile(
    r"\b(?:suicid\w*|self[\s-]*harm\w*|overdos\w*|(?:harm|hurt|kill|end)(?:ing)?\s+yourself|(?:end(?:ing)?|take|taking)\s+your\s+(?:own\s+)?life"
    r"|die|dying|death|dead|pills?|tablets?|no\s+(?:desire|will|wish|reason)\s+to\s+(?:keep\s+going|go\s+on|live|be\s+alive|be\s+here)"
    r"|(?:not\s+)?want(?:ing)?\s+to\s+(?:live|be\s+alive|be\s+here|wake\s+up)\s+any\s*more|giv(?:e|ing)\s+up\s+on\s+(?:life|living))\b",
    re.IGNORECASE,
)
GUARD_REASON = ("AI reply guard: the rules found nothing, but the AI judged this message may be about suicide or self-harm (or its draft mentioned "
                "self-harm, death or pills), so no AI reply was shown and the message was flagged for review")
_EMOJI = re.compile("[\U0001F000-\U0001FFFF☀-➿⬀-⯿]")
_DIGITS = re.compile(r"\d")
MAX_CHARS = 420
HISTORY_TURNS = 4
DISCLOSURE = "Written by an AI assistant. A person on our team still reads your message."


def enabled() -> bool:
    return bool(settings.llm_enabled and settings.groq_api_key)


def eligible(result: triage.TriageResult, floor: str) -> bool:
    """Only when nothing worrying was found anywhere. The default for anything else is the fixed reviewed wording."""
    return (
        enabled()
        and result.rule_level == "none"
        and not result.message_urgent
        and result.urgency not in ("high", "medium")
        and floor != "high"
    )


def acceptable(reply: str) -> str | None:
    """The cleaned reply if it is safe to show, otherwise None."""
    reply = " ".join((reply or "").split()).strip().strip('"')
    if not reply or len(reply) > MAX_CHARS:
        return None
    if _FORBIDDEN.search(reply) or _EMOJI.search(reply) or _DIGITS.search(reply):
        return None
    if triage.run(reply, "none")[0].rule_level != "none":              # the model's words go through the same safety scan
        return None
    return reply


def _messages(text: str, history: list[tuple[str, str | None]]) -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for said, answered in history[-HISTORY_TURNS:]:
        msgs.append({"role": "user", "content": said})
        if answered:
            msgs.append({"role": "assistant", "content": answered})
    msgs.append({"role": "user", "content": text})
    return msgs


def concern(raw: str) -> bool:
    """True when the model answered CONCERN (it judged the message may be about suicide or self-harm), or its words talk about self-harm, death or pills.
    A model judgement can only RAISE a message to review; it never lowers or clears one."""
    raw = raw or ""
    return raw.strip().strip("\"'*[]").upper().startswith(CONCERN_WORD) or bool(_CONCERN.search(raw))


def reply(text: str, history: list[tuple[str, str | None]]) -> tuple[str | None, bool]:
    """(the reply to show or None, concern). `history` is earlier (what they said, what IRIS said back or None), oldest first. Sends the text only.
    With concern=True the reply is always None: the caller must flag the message instead of showing ordinary wording."""
    try:
        r = httpx.post(
            f"{settings.groq_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json={"model": settings.groq_model, "messages": _messages(text, history), "temperature": 0.5, "max_tokens": 600, "reasoning_effort": "low"},
            timeout=settings.llm_timeout_seconds,
        )
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"] or ""
    except Exception:                                                    # noqa: BLE001 - any failure means "use the fixed wording"
        return None, False
    if concern(raw):
        return None, True
    return acceptable(raw), False
