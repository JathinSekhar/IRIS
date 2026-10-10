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

SYSTEM_PROMPT = (
    "You are the listening voice of IRIS, a student wellbeing support space. A person on the team reads every message later.\n"
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


def reply(text: str, history: list[tuple[str, str | None]]) -> str | None:
    """One conversational reply, or None. `history` is earlier (what they said, what IRIS said back or None), oldest first. Sends the text only."""
    try:
        r = httpx.post(
            f"{settings.groq_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json={"model": settings.groq_model, "messages": _messages(text, history), "temperature": 0.5, "max_tokens": 600, "reasoning_effort": "low"},
            timeout=settings.llm_timeout_seconds,
        )
        r.raise_for_status()
        return acceptable(r.json()["choices"][0]["message"]["content"])
    except Exception:                                                    # noqa: BLE001 - any failure means "use the fixed wording"
        return None
