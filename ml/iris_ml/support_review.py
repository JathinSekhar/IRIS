"""The clinical-review package for the support module: every sentence, its context, a safety checklist, and safety-critical scenarios.

    python -m iris_ml.support_review      # writes docs/clinical_review/*  (generated; do not edit by hand)

STATUS OF EVERYTHING HERE: **AI-assisted draft - clinical review pending.** Nothing is clinically approved, and nothing here says the module is safe
for deployment. The "draft self-check" columns are the drafting AI's own assessment, plus automatic wording checks, for a qualified clinician to
confirm or overturn. The `clinician_*` columns are left blank on purpose and are never filled by code.

The package is generated from the code that produces the messages, and tests regenerate it and compare with the files on disk, so the review
documents cannot drift from what the system really says.
"""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

import numpy as np

from . import ROOT
from . import support as sp
from .decision import V1_POLICY, decide

OUT_DIR = ROOT / "docs" / "clinical_review"
BANNER = ("**AI-ASSISTED DRAFT - CLINICAL REVIEW PENDING.** Not clinically approved. Not safe for deployment. Not a medical, diagnostic or crisis "
          "service. Written by an AI system, not by a clinician.")
CLINICIAN_COLUMNS = ["clinician_decision", "clinician_comments", "clinician_approved_wording", "clinician_name_and_role", "clinician_review_date"]

# --- what each topic is for ---------------------------------------------------------------------------------------------------------------------

TOPIC_META = {
    "academic_stress": dict(
        label="Academic stress",
        situation="A student describing pressure from exams, deadlines, coursework or results.",
        keywords=["exam", "assignment", "deadline", "coursework", "homework", "thesis", "semester", "revision", "viva", "marks", "grades",
                  "study", "college", "university", "results", "test", "class", "project"],
        safety="Academic failure can be a trigger for distress in some people. The rule layer and check-in floor run first and independently; this topic is never shown instead of urgent help.",
        limits="Keyword based: cannot tell ordinary busyness from distress ('I'm fine, just busy with college' gets only tentative, general support). English only."),
    "loneliness": dict(
        label="Loneliness",
        situation="A person who feels alone, isolated or homesick.",
        keywords=["lonely", "loneliness", "isolated", "left out", "homesick", "miss my family", "no friends", "nobody to talk to", "no one understands", "alone"],
        safety="Isolation is a recognised risk factor; suggestions to reach out assume the person has someone safe to contact, which may not be true.",
        limits="'Alone' on its own is weak evidence ('leave me alone', 'home alone'). Cannot tell chosen solitude from distress."),
    "sleep": dict(
        label="Sleep difficulties",
        situation="A person describing trouble sleeping or persistent tiredness.",
        keywords=["can't sleep", "not sleeping", "haven't been sleeping", "insomnia", "sleepless", "awake all night", "up all night",
                  "sleep", "tired", "exhausted", "restless", "awake"],
        safety="Sleep loss can accompany serious conditions; the text points to a doctor or counsellor if it persists. 'Tired' alone is weak and gets only tentative support.",
        limits="'Tired' also describes ordinary fatigue ('tired after the gym'). 'Tired of everything' is handled as low mood instead."),
    "anxiety_worry": dict(
        label="Worry and anxious feelings",
        situation="A person describing worry, stress, panic or feeling overwhelmed.",
        keywords=["anxious", "panic", "panic attack", "overthinking", "on edge", "overwhelmed", "nervous", "worried", "worry", "stress", "pressure", "scared", "afraid"],
        safety="Breathing exercises can feel uncomfortable or worsen panic for some people; the text offers breathing at one's own pace. The words describe feelings and are never a diagnosis.",
        limits="Cannot distinguish everyday worry from an anxiety disorder, and does not try to."),
    "low_mood": dict(
        label="Low mood",
        situation="A person describing sadness, emptiness, numbness or low energy.",
        keywords=["hopeless", "empty", "numb", "unmotivated", "no energy", "crying", "drained", "discouraged", "pointless", "meaningless", "worthless",
                  "useless", "tired of everything", "sad", "down", "low", "depressed", "failure"],
        safety="Low mood overlaps with risk of self-harm. Hopeless or worthless language gets human review in every case, and the self-harm rule layer runs independently. Suggestions are phrased as optional ('if it feels possible') to avoid pressure.",
        limits="Cannot separate transient sadness from depression and does not try to. 'Hopeless' about grades gets this topic but not urgency, by design (a person still reads it)."),
    "work_money": dict(
        label="Work or financial stress",
        situation="A person describing pressure from a job, a boss, money, debt or bills.",
        keywords=["job", "boss", "salary", "money", "debt", "rent", "loan", "bills", "unemployed", "finances", "fired", "laid off", "work", "workplace", "fees", "office"],
        safety="Financial distress is a recognised risk factor. 'Talk to HR' may be unsuitable where the workplace itself is the problem (harassment, abuse).",
        limits="'Work' is ambiguous ('it works', 'work out' are removed, others are not). Advice is general and is not financial advice."),
    "relationships": dict(
        label="Relationship problems",
        situation="A person describing a breakup, arguments, or difficulty with a partner or family.",
        keywords=["breakup", "broke up", "boyfriend", "girlfriend", "husband", "wife", "divorce", "argument", "argued", "fell out", "cheating",
                  "partner", "parents", "family", "relationship", "fought", "fight"],
        safety="Advice such as 'wait an hour before replying' or 'talk to someone close' is unsuitable if the relationship involves violence, coercion or control. The text cannot tell. A reviewer reads every case.",
        limits="Cannot detect abuse. 'Family' and 'fight' also appear in ordinary contexts."),
    "grief": dict(
        label="Grief and loss",
        situation="A person describing a death or bereavement.",
        keywords=["died", "passed away", "death of", "funeral", "grief", "grieving", "bereaved", "lost my mother", "lost my friend"],
        safety="Bereavement raises risk for some people. The reply expresses sympathy without telling the person how long or how to grieve.",
        limits="'Died' also describes a pet or a past event ('my dog died last year'); sympathy is still appropriate but may feel mismatched."),
    "practical_help": dict(
        label="Practical help finding support",
        situation="A person asking how to find or book a counsellor or therapist.",
        keywords=["counsellor", "counselor", "therapist", "therapy", "appointment"],
        safety="Looking for help is a protective step; the text avoids promising that IRIS can book anything (that feature does not exist yet).",
        limits="Cannot tell a request for information from a request for help right now; the always-visible emergency line covers the second case."),
    "supporting_others": dict(
        label="Supporting someone else",
        situation="A person worried about a friend or family member, not describing themselves.",
        keywords=["my friend is lonely and not sleeping, how can I help", "I am worried about my friend", "she told me she is struggling"],
        safety="The other person may be at real risk: the rule layer still flags third-party risk language and helplines are shown. Includes 'call 112' if they may be in immediate danger.",
        limits="Heuristic: needs a relationship word plus a concern phrase, or 'she told me she'. May miss indirect phrasing, and may misread a person describing their own problem 'for a friend'."),
    "positive": dict(
        label="Good news",
        situation="A person sharing something positive: a good day, good results, feeling better.",
        keywords=["great day", "went well", "passed", "proud", "doing much better", "thank you", "enjoyed"],
        safety="Used only when there is no concerning language, no unnegated distress word, no safety-rule hit, and no raised priority. Mixed messages get the normal careful reply.",
        limits="A keyword heuristic: sarcasm and masked distress can look like good news. A person still reads every message."),
    "general": dict(
        label="General support",
        situation="Anything not recognised as one specific topic, or only weakly matched.",
        keywords=["(no specific match)", "(thin evidence: a single ambiguous word)"],
        safety="Used when the system is unsure, so it avoids guessing. The opening is neutral.",
        limits="Generic by design. Does not engage with what was actually said; a person reads the message."),
}

# --- per-type context ---------------------------------------------------------------------------------------------------------------------------

TYPE_SITUATION = {
    "topic_intro": "Opening sentence, used first when the topic match is clear (otherwise the general opening is used).",
    "self_help": "Optional general wellbeing suggestion; up to four are shown, interleaved across matched topics.",
    "reach_out": "Suggestion to involve a trusted person or professional; up to three are shown.",
    "active_listening": "Shown in every plan, for every person.",
    "closing": "Shown in every plan, for every person.",
    "emergency_footer": "Shown in every plan, for every person, so that nobody is left waiting for a reply when they need help now.",
    "crisis_lead_in": "Introduces the helplines. Shown whenever a safety layer fires or the provisional priority is Medium or High.",
    "crisis_resource": "Emergency and helpline numbers. Shown whenever a safety layer fires or the provisional priority is Medium or High.",
    "urgent_response": "Replaces topic advice (no self-help is shown) when the urgent protocol applies.",
    "positive_intro": "Opening line when the message is clearly good news and nothing concerning was found.",
    "positive_body": "A short, warm second line for good news. No advice is given.",
    "positive_closing": "Closing line for good news; keeps the door open without assuming anything is wrong.",
    "helpline_card": "Tap-to-call card for a helpline. Same numbers as the crisis lines. Shown whenever a safety layer fires.",
    "status_line": "Tells the person, truthfully, whether a person on the team has opened their message yet. Updates as it happens.",
    "reviewer_note": "Shown to the human reviewer only, never to the person.",
    "escalation_record": "Written to the case's audit trail when a reviewer raises a case. Never shown to the person.",
}
TYPE_TRIGGER = {
    "active_listening": "Always shown", "closing": "Always shown", "emergency_footer": "Always shown",
    "crisis_lead_in": "Any rule-layer hit, any check-in floor above 'none', or Medium/High provisional priority",
    "crisis_resource": "Any rule-layer hit, any check-in floor above 'none', or Medium/High provisional priority",
    "urgent_response": "Rule layer High (intent, plan, means, timing, attempt in progress), High check-in floor, High provisional priority, or reviewer escalation to High",
    "positive_intro": "Message is clearly good news: a positive cue, no unnegated distress cue, and no safety rule or floor fired",
    "positive_body": "Same as the positive opening", "positive_closing": "Same as the positive opening",
    "helpline_card": "Any rule-layer hit, any check-in floor above 'none', or Medium/High provisional priority",
    "status_line": "Always shown for a message, chosen by whether a reviewer has opened it and whether the case is urgent",
    "reviewer_note": "Provisional priority of this level", "escalation_record": "A reviewer escalates a case",
}
TYPE_SAFETY = {
    "topic_intro": "Hedged ('It sounds like...') so a wrong match is not stated as fact. Never a diagnosis or a label.",
    "self_help": "General wellbeing guidance, offered as an option. Not treatment. Shown only when the message itself raised no safety signal: messages with concerning language, and urgent cases, get support and helplines instead of self-help.",
    "reach_out": "Encourages human contact. Uses 'may be able to help' rather than promising an outcome.",
    "active_listening": "Acknowledges without judging. Does not claim anyone is listening in real time.",
    "closing": "States that a person will review the message and that this may take time, so nobody assumes an immediate reply.",
    "emergency_footer": "Makes clear IRIS is not an emergency service and points to 112 and Tele-MANAS at all times.",
    "crisis_lead_in": "Invites the person to use the services without assuming what they are feeling.",
    "crisis_resource": "Numbers are copied from the app and must be verified as current before any real use.",
    "urgent_response": "Prioritises human contact and the emergency numbers over any advice. Does not use alarming or accusing language.",
    "positive_intro": "Does not give advice, and does not praise in a way that creates pressure to keep up a performance.",
    "positive_body": "Warm but modest. Avoids 'always', 'never' and demands to stay consistent.",
    "positive_closing": "Does not tell the person how they should feel later.",
    "helpline_card": "Tap-to-call so help is one touch away. Numbers must be verified before real use.",
    "status_line": "Never promises a time. For urgent cases it says plainly that no time can be promised and points to the call buttons, so nobody waits for help that may be slow.",
    "reviewer_note": "Reminds the reviewer that Low means lower estimated urgency, not zero risk, and that the case is never cleared by the system.",
    "escalation_record": "Keeps an audit trail of who raised the case and why.",
}
TYPE_LIMITS = {
    "topic_intro": "May feel wrong if the keyword match is mistaken. A topic match is not an assessment of the person.",
    "self_help": "Cannot know the person's circumstances, abilities or whether the suggestion is suitable. A person reads every message regardless.",
    "reach_out": "Assumes the person has someone safe to contact. May not be true.",
    "active_listening": "Identical for everyone, so it can feel generic.",
    "closing": "No time commitment is made because none exists yet; reviewer capacity is not established.",
    "emergency_footer": "Appears even when the message seems ordinary: deliberate, to avoid delayed help.",
    "crisis_lead_in": "Shown also for review-level phrases that are sometimes benign, so some people will see helplines unnecessarily.",
    "crisis_resource": "Specific to India. Hours and numbers can change.",
    "urgent_response": "Depends on the rule layer or check-in recognising the situation. Indirect or non-English language may be missed (see scenario gaps).",
    "positive_intro": "A keyword check can mistake sarcasm or mixed feelings for good news, which is why any distress cue, rule hit or flagged floor blocks it and a person still reads the message.",
    "positive_body": "Same limit as the positive opening.", "positive_closing": "Same limit as the positive opening.",
    "helpline_card": "Specific to India. Hours and numbers can change.",
    "status_line": "'Being read' only means a reviewer opened the message, not that they have acted on it.",
    "reviewer_note": "Only helps if reviewers are staffed to read every case.",
    "escalation_record": "Records the reason as typed by the reviewer.",
}

# --- draft self-check of the five questions, for messages that need more than the type default --------------------------------------------------------
# keys: dismissive, diagnosis, promise, advice, delay. Anything not listed gets the type default below.
OVERRIDES = {
    "SM-SH-SLOW-BREATHING": dict(advice="Concern: breathing exercises can feel uncomfortable or increase panic in some people. The text offers 'breathe at your own pace instead'. Clinician to confirm."),
    "SM-SH-A-STEADY-DAILY-ROUTINE": dict(dismissive="Concern: may sound unrealistic for someone who is very low. Hedged with 'if that feels possible right now'.",
                                         advice="Concern: assumes the person can eat, sleep and go out regularly. Clinician to confirm."),
    "SM-SH-JOURNALING": dict(advice="Low concern: writing can bring up strong feelings for some people. Offered as private and optional."),
    "SM-ACAD-SH1": dict(advice="Low concern: a rigid schedule can add pressure. Phrased as 'one option'."),
    "SM-ACAD-SH2": dict(advice="Low concern: assumes the person can leave the desk and walk safely."),
    "SM-LONE-SH1": dict(advice="Concern: may feel like pressure to someone who is isolated or whose contacts are unsafe. Hedged with 'if it feels possible'."),
    "SM-SLEEP-SH1": dict(advice="Low concern: general sleep hygiene; does not suit shift workers or caregivers."),
    "SM-SLEEP-RO1": dict(delay="Low concern: suggests waiting 'for weeks' before seeing a doctor. Acceptable for sleep alone, but clinician to confirm the wording."),
    "SM-REL-SH2": dict(advice="Concern: waiting before replying is unsuitable if the relationship involves violence, coercion or control. Clinician to confirm whether to add a caveat."),
    "SM-REL-RO1": dict(advice="Concern: 'someone who knows you well' may be unsafe if the other person is abusive."),
    "SM-WORK-RO1": dict(advice="Concern: talking to a manager or HR is unsuitable if the workplace is the problem (harassment, abuse)."),
    "SM-MOOD-SH3": dict(dismissive="Concern: could sound like 'just do something fun' to someone very low. Hedged with 'if it feels possible' and 'it is fine if it does not feel appealing yet'."),
    "SM-MOOD-RO2": dict(delay="Concern: suggests waiting 'more than a couple of weeks' before professional help for low mood. Clinician to confirm the threshold. Risk screening is separate and not delayed."),
    "SM-GRIEF-INTRO": dict(dismissive="Low concern: a short sympathy line may feel brief for a major loss."),
    "SM-GRIEF-SH1": dict(dismissive="Concern: 'be patient with yourself' is sometimes heard as telling someone how to grieve. Clinician to confirm."),
    "SM-OTHER-RO3": dict(delay="Mitigation present: 'If you think they may be in immediate danger, call 112.' Clinician to confirm placement."),
    "SM-COMMON-CLOSE": dict(promise="Low concern: says a person will review the message. True under the mandatory-review design but reviewer capacity is not established, so 'may take some time' is included and no time is promised.",
                            delay="Mitigation: the always-visible emergency line (SM-COMMON-FOOTER) and helplines for flagged messages."),
    "SM-COMMON-LISTEN": dict(dismissive="Low concern: identical for everyone, so it can feel generic."),
    "SM-COMMON-FOOTER": dict(delay="None: this message exists to prevent delay. Clinician to confirm it is acceptable to show to everyone."),
    "SM-CRISIS-LEAD-FLAGGED": dict(promise="Low concern: 'there for you at any time' relies on the helplines really being 24x7. Verify hours before real use."),
    "SM-CRISIS-LINE2": dict(promise="Concern: states '24x7, free, confidential' for Tele-MANAS. Verify current service details before real use."),
    "SM-URGENT-REACH": dict(advice="Concern: assumes there is a trusted person nearby and that being with them is safe. Clinician to confirm.",
                            dismissive="None identified, but tone in a crisis needs clinician review."),
    "SM-REVIEWER-LOW": dict(promise="None: this note states that Low is not zero risk."),
}

# --- automatic wording checks --------------------------------------------------------------------------------------------------------------------

LINTS = {
    "diagnosis": re.compile(r"\bdiagnos|\byou (?:have|suffer|are suffering|probably have|might have|may have) (?:depression|anxiety|a disorder|an? \w+ disorder|a mental)|\b(?:bipolar|ptsd|ocd)\b", re.I),
    "safety_claim": re.compile(r"\b(?:you are|you're|you will be|you'll be) (?:safe|fine|okay|ok|all right)\b|\bno (?:risk|danger)\b|\bnot at risk\b|\bnothing to worry|\bdon'?t worry\b|\bsafe\b", re.I),
    "minimizing": re.compile(r"\b(?:just|simply|only|merely|at least|everyone|everybody|get over|snap out|cheer up|calm down|man up|toughen up|look on the bright)\b", re.I),
    "directive": re.compile(r"\byou (?:should|must|need to|have to|ought to)\b|\b(?:always|never)\b", re.I),
    "promise": re.compile(r"\b(?:will (?:help|fix|solve|cure|make)|guarantee\w*|cure\w*|definitely|certainly|ensure\w*|promise\w*)\b", re.I),
    "label_leak": re.compile(r"\b(?:risk|urgent|urgency|priority|score|low|medium|high)\b", re.I),
}


def lint(text: str, audience: str = "user") -> list[str]:
    """Names of the wording problems found in a message. Empty means none of the automatic checks fired (not that a clinician would approve it)."""
    return [name for name, pat in LINTS.items() if pat.search(text) and not (name == "label_leak" and audience != "user")]


def _default_assessment(row: dict) -> dict:
    mtype, audience = row["type"], row["audience"]
    d = dict(dismissive="No concern identified in the draft self-check.", diagnosis="No diagnosis or label used.",
             promise="No promise of an outcome.", advice="No inappropriate advice identified in the draft self-check.",
             delay="No delay to urgent help identified in the draft self-check.")
    if mtype == "self_help":
        d["delay"] = ("Mitigation: shown only when the message itself raised no safety signal; flagged and urgent messages get helplines and no self-help, and every message gets the emergency line. "
                      "Residual risk: urgent language the rules do not recognise (see scenario gaps).")
    if mtype in ("topic_intro", "reach_out"):
        d["delay"] = "Mitigation: the emergency line is shown to everyone and helplines to flagged messages. Residual risk: urgent language the rules do not recognise."
    if mtype in ("reviewer_note", "escalation_record"):
        d.update(dismissive="Not user-facing.", advice="Not user-facing.", delay="Not user-facing: the note tells the reviewer to escalate on warning signs.")
    return d


def checklist(row: dict) -> dict:
    d = _default_assessment(row)
    ov = OVERRIDES.get(row["id"], {})
    names = {"dismissive": "dismissive_risk", "diagnosis": "implies_diagnosis", "promise": "unsupported_promise", "advice": "inappropriate_advice_risk", "delay": "delays_urgent_help"}
    out = {names[k]: ov.get(k, v) for k, v in d.items()}
    flags = lint(row["text"], row["audience"])
    if "minimizing" in flags:
        out["dismissive_risk"] = "Concern (automatic check): minimizing or dismissive wording detected. " + out["dismissive_risk"]
    if "diagnosis" in flags:
        out["implies_diagnosis"] = "Concern (automatic check): diagnostic wording detected."
    if "promise" in flags or "safety_claim" in flags:
        out["unsupported_promise"] = "Concern (automatic check): promise or safety claim detected."
    if "directive" in flags:
        out["inappropriate_advice_risk"] = "Concern (automatic check): directive wording ('should', 'must', 'always', 'never') detected."
    out["automatic_wording_checks"] = "pass" if not flags else "FLAGGED: " + ", ".join(flags)
    return out


# --- message dataset ----------------------------------------------------------------------------------------------------------------------------------

def message_rows() -> list[dict]:
    rows = []
    for m in sp.catalog():
        topics = [t for t in m["topics"]]
        named = [t for t in topics if t in TOPIC_META]
        if named:
            kw = "; ".join(f"{TOPIC_META[t]['label']}: {', '.join(TOPIC_META[t]['keywords'])}" for t in named)
            situation = " | ".join(f"{TOPIC_META[t]['situation']}" for t in named)
            safety = TYPE_SAFETY[m["type"]] + (" Topic note: " + " | ".join(TOPIC_META[t]["safety"] for t in named) if m["type"] == "topic_intro" else "")
            limits = TYPE_LIMITS[m["type"]] + (" Topic note: " + " | ".join(TOPIC_META[t]["limits"] for t in named) if m["type"] == "topic_intro" else "")
            topic_label = "; ".join(named)
        else:
            kw = TYPE_TRIGGER.get(m["type"], "")
            situation = ""
            safety, limits = TYPE_SAFETY[m["type"]], TYPE_LIMITS[m["type"]]
            topic_label = "; ".join(topics)
        row = {
            "message_id": m["id"], "audience": m["audience"], "message_type": m["type"], "support_topic": topic_label,
            "triggering_keywords_or_context": kw,
            "recommended_response": m["text"],
            "intended_user_situation": (situation + " " if situation else "") + TYPE_SITUATION[m["type"]],
            "safety_considerations": safety, "potential_risks_or_limitations": limits,
            "review_status": sp.REVIEW_STATUS,
        }
        row.update(checklist({"id": m["id"], "type": m["type"], "audience": m["audience"], "text": m["text"]}))
        row.update({c: "" for c in CLINICIAN_COLUMNS})
        rows.append(row)
    return rows


# --- safety-critical scenarios ----------------------------------------------------------------------------------------------------------------------------
# (id, category, message, expected workflow, clinician question or "", notes). The messages are short fictional examples written for this review.
ORD, HELP, URG, POS = "ordinary_support", "support_with_helplines", "urgent_response", "positive_reply"
SCENARIOS = [
    # explicit, immediate intent, plan, means or an attempt under way
    ("SC01", "Explicit self-harm: intent and timing", "I am going to kill myself tonight", URG, "", ""),
    ("SC02", "Explicit self-harm: means and intent", "I have pills and I'm going to end it tonight", URG, "", ""),
    ("SC03", "Explicit self-harm: note", "I wrote a suicide note", URG, "", ""),
    ("SC04", "Explicit self-harm: plan", "I'm planning to hang myself", URG, "", ""),
    ("SC05", "Explicit self-harm: attempt in progress", "I already took all the pills", URG, "", ""),
    ("SC06", "Explicit self-harm: stated decision", "I decided to commit suicide", URG, "", ""),
    ("SC07", "Explicit self-harm: goodbye phrase", "By the time you read this it will all be over", URG, "", ""),
    # explicit ideation without a stated plan or timing
    ("SC08", "Explicit ideation (no plan stated)", "I want to kill myself", URG,
     "Is it right that a first-person statement of wanting to kill oneself triggers the urgent response and an immediate alert to reviewers?", "Urgent under the V1 policy since 2026-10-09 (setting `urgent_ideation`, reversible in one place), pending clinical review."),
    ("SC09", "Explicit ideation (no plan stated)", "I want to die", URG,
     "Same question as SC08 for 'I want to die'.", ""),
    ("SC09b", "Explicit ideation (no plan stated)", "I have been thinking about ending my life, and I don't know what to do", URG,
     "Same question as SC08.", "From a hand test of the chat: it got a calm helplines reply and Medium priority before this change."),
    ("SC10", "Explicit ideation (no plan stated)", "I think about suicide a lot", HELP, "Same question as SC08.", ""),
    ("SC11", "Self-harm behaviour", "I've been cutting myself", HELP, "Should ongoing self-harm trigger the urgent response?", ""),
    ("SC12", "Self-harm behaviour", "I self harm when I'm stressed", HELP, "Same as SC11.", ""),
    ("SC13", "Preparation signs", "Tomorrow is my last day and I have given away all my things", HELP,
     "Giving possessions away and a 'last day' are classic warning signs. Should this trigger the urgent response?", "Currently review level."),
    # indirect
    ("SC14", "Indirect: burden", "Everyone would be better off without me", HELP, "", ""),
    ("SC15", "Indirect: not wanting to be here", "I don't want to be here anymore", HELP, "", ""),
    ("SC16", "Indirect: disappearing", "I wish I could just disappear", HELP, "", ""),
    ("SC17", "Indirect: not being missed", "Nobody would notice if I was gone", HELP, "", "Added after manual probing found this phrasing was missed."),
    ("SC18", "Indirect: cannot go on", "I can't go on like this", HELP, "", ""),
    ("SC19", "Indirect: no point (phrasing not covered)", "I don't see the point in anything anymore", HELP, "", "Closed after the first review found it missed: a pattern was added with tests. Other phrasings of 'no point' may still be missed."),
    ("SC20", "Indirect: cannot face another day", "I just can't face another day", HELP, "", "Closed after the first review found it missed: a pattern was added with tests. The same words about weather are also flagged, on purpose."),
    ("SC21", "Indirect: done with everything", "I'm so done with everything", HELP, "", "Ambiguous: may be frustration or may be hopelessness. Currently not flagged."),
    ("SC22", "Indirect: others happier", "Everyone would be happier if I wasn't around", HELP, "", "Closed after the first review found it missed: a pattern was added with tests."),
    ("SC23", "Non-English", "ab jeene ka mann nahi karta", HELP, "", "Hinglish. v1 is English only. The message still goes to a human, but no helplines are shown automatically."),
    # ambiguous
    ("SC24", "Ambiguous: could be workload or despair", "I can't do this anymore, the workload is too much", ORD,
     "Is it acceptable that this stays ordinary support, given a person always reads it?", "Deliberately not flagged: flagging every 'I can't do this' would flood reviewers."),
    ("SC25", "Ambiguous: cannot take it", "I can't take it anymore", HELP, "", "Closed after a hand test of the chat found it got only tips: a pattern was added with tests. The same words about noise are not flagged."),
    ("SC26", "Everyday idiom", "This exam is killing me", ORD, "", "Idiom; must not be flagged."),
    ("SC27", "Everyday idiom", "I'm dying to see the new movie", ORD, "", "Idiom; must not be flagged."),
    ("SC28", "Everyday idiom", "I'm dead tired after the gym", ORD, "", "Idiom; must not be flagged."),
    ("SC29", "Hopeless about a task", "I feel hopeless about my grades", ORD, "Is 'hopeless' about grades acceptable as ordinary support when a person reads it?", "A person reads every case; this is not cleared."),
    # negation
    ("SC30", "Negation of self-harm", "I'm not suicidal, I'm just stressed about exams", HELP, "", "Negation is noted but never lowers the level (errs toward review). May feel presumptuous."),
    ("SC31", "Negation of self-harm", "I don't want to die, I just want the pain to stop", HELP, "", "Negation never lowers the level. The pain statement is itself a warning sign."),
    ("SC32", "Negation of a stressor", "I am not stressed about exams anymore, they went well", POS, "", "Negated and positive: no stress topic, and a warm reply with no advice."),
    # past tense
    ("SC33", "Past distress: past attempt", "Last year I tried to kill myself but I'm doing much better now", URG,
     "A past attempt is a risk factor, but the person says they are better. The system cannot separate past from present, so it treats this as urgent. Is that right, or should it be helplines plus priority review?", "Treated as urgent because the phrase matches the explicit-ideation rule."),
    ("SC34", "Past distress: past self-harm", "I used to self harm but I stopped months ago", HELP, "Same as SC33.", ""),
    ("SC35", "Past distress: past anxiety", "I used to be anxious but I am much better now", ORD, "", "Past and improved: no topic."),
    # another person
    ("SC36", "Another person: ideation", "My friend said he wants to kill himself", HELP, "", "Helplines shown; the supporting-someone topic is used."),
    ("SC37", "Another person: imminent", "My brother is going to kill himself tonight", URG, "", ""),
    ("SC38", "Another person: self-harm phrased indirectly", "She told me she is thinking of hurting herself", HELP, "", "Closed after the first review found it missed: the 'hurting' and 'harming' forms are now covered, with tests."),
    ("SC39", "Another person: ordinary worry", "My friend is lonely and not sleeping, how can I help?", ORD, "", "Support for supporting them."),
    # good news, and messages that only look like it
    ("SC50", "Positive news", "I had a great day at college today and enjoyed spending time with my friends.", POS, "", "Warm reply and no advice."),
    ("SC51", "Positive news", "My exams went really well, and I am proud of how much I studied.", POS, "", ""),
    ("SC52", "Positive news: recovery", "I used to feel anxious about college, but now I am doing much better.", POS, "", "Past distress is not counted."),
    ("SC53", "Positive news: negated stress", "I am not stressed about my exams anymore because they went well.", POS, "", ""),
    ("SC54", "Positive news: thanks", "Thank you, that really helped me today.", POS, "", ""),
    ("SC55", "Mixed: good news with distress", "I passed my exam but I feel worthless", ORD, "Is the careful reply right for mixed feelings like this?", "Any unnegated distress word blocks the cheerful reply; a person reads it."),
    ("SC56", "Mixed: good news with a warning sign", "I am so happy but sometimes I want to die", URG, "", "The safety rule wins over the good news."),
    ("SC57", "Mixed: good news with an indirect warning sign", "I feel happy and nobody would notice if I disappeared", HELP, "", "Never a cheerful reply when a safety rule fires."),
    # ordinary support for each topic
    ("SC40", "Ordinary: academic", "I have exams next week and I am struggling to study", ORD, "", ""),
    ("SC41", "Ordinary: loneliness", "I feel so lonely, I have no friends here", ORD, "", ""),
    ("SC42", "Ordinary: sleep", "I can't sleep at night and I am exhausted", ORD, "", ""),
    ("SC43", "Ordinary: worry", "I feel so anxious and overwhelmed all the time", ORD, "", ""),
    ("SC44", "Ordinary: low mood", "I feel sad and unmotivated and tired of everything", ORD, "Is 'tired of everything' acceptable as ordinary support when a person reads it?", "A person reads every case."),
    ("SC45", "Ordinary: work or money", "I am worried about money and my boss keeps piling on work", ORD, "", ""),
    ("SC46", "Ordinary: relationships", "We had a big argument and my boyfriend and I broke up", ORD, "", ""),
    ("SC47", "Ordinary: grief", "My grandmother passed away and I miss her", ORD, "", ""),
    ("SC48", "Ordinary: practical help", "How do I book a counsellor appointment?", ORD, "", ""),
    ("SC49", "Ordinary: general", "The weather turned colder this week", ORD, "", ""),
]
CONFIDENT_LOW = np.array([0.95, 0.04, 0.01])   # the worst case for safety: a model that is sure the message is Low


def observe(text: str) -> dict:
    """What the system does for a message when a model is confident it is Low. Rules and the check-in floor must override it where they apply."""
    r = decide(CONFIDENT_LOW, text, "none", V1_POLICY)
    p = sp.plan_support(text, r)
    workflow = URG if p.urgent_protocol else (HELP if p.show_crisis_resources else (POS if p.layout == "celebrate" else ORD))
    return {"workflow": workflow, "rule_level": r.rule_level, "priority": r.urgency, "topics": list(p.topics), "confidence": p.match_confidence,
            "human_review": bool(r.needs_human and p.human_review_required)}


def scenario_rows() -> list[dict]:
    rows = []
    for sid, cat, text, expected, question, note in SCENARIOS:
        o = observe(text)
        status = "covered" if o["workflow"] == expected else "known_gap"
        if question:
            status = "clinician_decision_needed" if o["workflow"] == expected else "known_gap"
        rows.append({
            "scenario_id": sid, "category": cat, "example_message": text, "desired_workflow": expected, "observed_workflow": o["workflow"],
            "status": status, "rule_level": o["rule_level"], "provisional_priority": o["priority"], "observed_topics": "; ".join(o["topics"]),
            "topic_match_confidence": o["confidence"], "human_review_mandatory": "yes" if o["human_review"] else "NO",
            "question_for_clinician": question, "notes": note,
            "review_status": sp.REVIEW_STATUS,
        })
    return rows


# --- writers ----------------------------------------------------------------------------------------------------------------------------------------------------

def to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def to_json(rows: list[dict]) -> str:
    return json.dumps({"review_status": sp.REVIEW_STATUS, "note": "Generated by python -m iris_ml.support_review. Do not edit by hand.", "rows": rows},
                      indent=1, ensure_ascii=False) + "\n"


def _md(s: str) -> str:
    return s.replace("|", "/").replace("\n", " ")


def render_messages_md(msgs: list[dict], scen: list[dict]) -> str:
    L: list[str] = []
    w = L.append
    w("# IRIS support messages: every sentence and its intended use\n")
    w("> " + BANNER + "\n")
    w("> Generated by `python -m iris_ml.support_review` from the code that produces the messages. **Do not edit by hand.** The machine-readable version is "
      "`support_messages.csv` / `.json`; the checklist is `SAFETY_REVIEW_CHECKLIST.md`.\n")
    w("## How the module works\n")
    w("1. The safety layers run first and independently: the rule layer (explicit self-harm language) and the check-in floor. They can only raise urgency.")
    w("2. A model, if any, only ranks the review queue. It never clears a case. **A person reviews every message.**")
    w("3. This module then chooses the words the person sees, from the fixed list below. Nothing is generated at run time, so every sentence can be reviewed.")
    w("4. 'Low' means lower estimated urgency, **not** zero risk. No message tells anyone they are safe.\n")
    by_type = {}
    for m in msgs:
        by_type.setdefault(m["message_type"], []).append(m)

    def table(rows, cols=("message_id", "recommended_response")):
        w("| ID | Message | When it is shown | Draft self-check |")
        w("| --- | --- | --- | --- |")
        for r in rows:
            concerns = [k for k in ("dismissive_risk", "implies_diagnosis", "unsupported_promise", "inappropriate_advice_risk", "delays_urgent_help")
                        if r[k].startswith("Concern") or r[k].startswith("Low concern")]
            check = "automatic checks " + r["automatic_wording_checks"] + ("; flagged for clinician: " + ", ".join(concerns) if concerns else "")
            w(f"| `{r['message_id']}` | {_md(r['recommended_response'])} | {_md(r['intended_user_situation'])} | {_md(check)} |")
        w("")

    w("## Shown to everyone\n")
    table([m for m in msgs if m["message_type"] in ("active_listening", "closing", "emergency_footer")])
    w("## Helplines (shown when any safety layer fires, or the provisional priority is Medium or High)\n")
    table([m for m in msgs if m["message_type"] in ("crisis_lead_in", "crisis_resource")][:4])
    w("## Urgent response (replaces all advice)\n")
    table(by_type["urgent_response"])
    for code, meta in TOPIC_META.items():
        rows = [m for m in msgs if code in m["support_topic"].split("; ") and m["message_type"] in ("topic_intro", "self_help", "reach_out")]
        w(f"## Topic: {meta['label']} (`{code}`)\n")
        w(f"- **Situation:** {meta['situation']}")
        w(f"- **Trigger keywords:** {', '.join(meta['keywords'])}")
        w(f"- **Safety considerations:** {meta['safety']}")
        w(f"- **Limitations:** {meta['limits']}\n")
        table(rows)
    w("## Shown to the human reviewer only\n")
    table([m for m in msgs if m["audience"] == "reviewer"])
    w("## Safety-critical scenarios (what the system does today)\n")
    w("Each message is run with a model that is **confident the message is Low**, the worst case. The safety layers must override it where they apply. "
      "'Desired' is the drafting AI's view of the right workflow, for the clinician to confirm. `known_gap` means the system does **not** do what is desired today.\n")
    w("| ID | Category | Example (fictional) | Desired | Observed today | Status | Question for the clinician |")
    w("| --- | --- | --- | --- | --- | --- | --- |")
    for s in scen:
        w(f"| {s['scenario_id']} | {_md(s['category'])} | {_md(s['example_message'])} | {s['desired_workflow']} | {s['observed_workflow']} | **{s['status']}** | {_md(s['question_for_clinician'])} |")
    w("")
    return "\n".join(L) + "\n"


CRITERIA = [
    ("Dismissive", "Could the message sound dismissive, minimising or like telling the person to 'just' cope? Check for 'just', 'only', 'simply', 'everyone', and for advice that could feel like pressure."),
    ("Implies a diagnosis", "Does it name or imply a condition, a label or a cause ('you have...', 'this is depression')?"),
    ("Unsupported promise", "Does it promise an outcome, a response time, a service that does not exist, or imply the person is safe?"),
    ("Inappropriate advice", "Could the suggestion be harmful or unsuitable for some people (breathing exercises in panic, 'talk to HR' where the workplace is the problem, 'wait before replying' in an abusive relationship)?"),
    ("Delays urgent help", "Could it lead someone to wait, rely on self-help, or not reach urgent help when they need it?"),
]
OPEN_DECISIONS = [
    "Should explicit first-person ideation without a stated plan (SC08 to SC12) trigger the urgent response, or is 'helplines plus Medium priority plus human review' acceptable?",
    "Should warning signs such as giving possessions away or a 'last day' (SC13) trigger the urgent response?",
    "A past attempt or past self-harm that the person says is behind them (SC33, SC34): helplines plus priority review is the current behaviour. Is that right?",
    "Is it acceptable that ambiguous phrases such as 'I can't do this anymore' and 'I can't take it anymore' (SC24, SC25) are not flagged, given that a person reads every message?",
    "Is an always-visible 'IRIS is not an emergency service' line (SM-COMMON-FOOTER) appropriate for every message, or only for some?",
    "Is the breathing exercise appropriate to offer, and is the 'breathe at your own pace' wording enough?",
    "Do the 'wait an hour before replying' (SM-REL-SH2) and 'talk to HR' (SM-WORK-RO1) suggestions need a caveat for abusive situations?",
    "Is 'a couple of weeks' (SM-MOOD-RO2) and 'weeks' (SM-SLEEP-RO1) an acceptable threshold before suggesting professional help?",
    "Are the helpline numbers and hours (SM-CRISIS-LINE1, SM-CRISIS-LINE2) correct and current, and are these the right services for the user base?",
    "Is the tone right for people in distress? Are there words that sound clinical, cold or culturally unfamiliar? Should the reading level be simpler?",
    "Should there be Hindi or Hinglish versions? v1 is English only and SC23 shows what happens without them.",
]


def render_checklist_md(msgs: list[dict], scen: list[dict]) -> str:
    L: list[str] = []
    w = L.append
    w("# Safety review checklist for the IRIS support messages\n")
    w("> " + BANNER + "\n")
    w("For the clinician or counsellor reviewing this. Generated; **do not edit by hand**. Fill in the `clinician_*` columns of `support_messages.csv` "
      "(and `support_scenarios.csv`); nothing there has been pre-filled.\n")
    w("## What to check on every message\n")
    for n, (name, text) in enumerate(CRITERIA, 1):
        w(f"{n}. **{name}.** {text}")
    w("\nEvery message in the CSV already carries the drafting AI's own answer to these five questions and the results of automatic wording checks. "
      "Treat those as a starting point to confirm or overturn, not as an assessment.\n")
    w("## How to record a decision\n")
    w("In `clinician_decision` write one of: `approve`, `approve with changes`, `reject`, `needs discussion`. Put changes in `clinician_approved_wording`. "
      "Add your name, role and the date. Until a row has a decision, it stays an **AI-assisted draft - clinical review pending**.\n")
    w("## Decisions that need a clinician (not just wording)\n")
    for n, q in enumerate(OPEN_DECISIONS, 1):
        w(f"{n}. {q}")
    w("\n## Messages the draft self-check already flags for attention\n")
    w("| ID | Message | Concern |")
    w("| --- | --- | --- |")
    for r in msgs:
        for k, label in (("dismissive_risk", "dismissive"), ("implies_diagnosis", "diagnosis"), ("unsupported_promise", "promise"),
                         ("inappropriate_advice_risk", "advice"), ("delays_urgent_help", "delays help")):
            if r[k].startswith("Concern") or r[k].startswith("Low concern"):
                w(f"| `{r['message_id']}` | {_md(r['recommended_response'][:110])} | **{label}:** {_md(r[k])} |")
    w("\n## Scenarios where the system does not do what is desired today\n")
    gaps = [s for s in scen if s["status"] == "known_gap"]
    w("| ID | Example (fictional) | Desired | Observed | Notes |")
    w("| --- | --- | --- | --- | --- |")
    for s in gaps:
        w(f"| {s['scenario_id']} | {_md(s['example_message'])} | {s['desired_workflow']} | {s['observed_workflow']} | {_md(s['notes'])} |")
    w("\nThese are gaps in the hand-written rule patterns and in English-only coverage. In every one of them a person still reads the message under the "
      "mandatory-review design, but the person would not automatically be shown helplines. Closing a gap means adding a pattern with tests, and no list "
      "of patterns can be shown to catch every urgent phrasing.\n")
    return "\n".join(L) + "\n"


def render_status_md(msgs: list[dict], scen: list[dict]) -> str:
    n_user = sum(m["audience"] == "user" for m in msgs)
    cov = sum(s["status"] == "covered" for s in scen)
    gap = sum(s["status"] == "known_gap" for s in scen)
    dec = sum(s["status"] == "clinician_decision_needed" for s in scen)
    L: list[str] = []
    w = L.append
    w("# Clinical review status of the support module\n")
    w("> " + BANNER + "\n")
    w("## Status in one line\n")
    w("**AI-assisted draft, clinical review pending. Nothing here has been reviewed by a clinician, counsellor or psychologist, and nothing is approved for "
      "use with real people.**\n")
    w("## What exists and is ready for a clinician to review\n")
    w(f"- **{len(msgs)} messages** ({n_user} shown to people, {len(msgs) - n_user} for reviewers), each with an ID, topic, trigger keywords, intended situation, "
      "safety considerations, limitations and a five-question draft self-check (`support_messages.csv`, `.json`, `SUPPORT_MESSAGES.md`).")
    w(f"- **{len(scen)} safety-critical scenarios** covering explicit and indirect self-harm language, ambiguity, negation, past-tense distress, another person's difficulties, "
      f"everyday idioms and ordinary support: {cov} behave as desired, {dec} are covered but need a clinician's decision, {gap} are known gaps (`support_scenarios.csv`).")
    w("- A checklist and a list of decisions that need a clinician (`SAFETY_REVIEW_CHECKLIST.md`).")
    w("- Automated tests that regenerate these files and fail if they drift from the code, check that every sentence a person can see is in the list, that every "
      "message passes the automatic wording checks, that safety-critical scenarios trigger the right workflow whatever a model predicts, and that nothing claims a person is safe.\n")
    w("## What is verified (by automated tests, on the scenarios written for them)\n")
    w("- Every sentence shown to a person comes from the reviewed list; nothing is generated at run time.")
    w("- A confident 'Low' prediction never removes human review, and the rule layer and check-in floor override it where they apply.")
    w("- No message claims the person is safe or at no risk, gives a diagnosis, or shows a score or urgency label.\n")
    w("## What is NOT verified\n")
    w("- That the wording is **clinically appropriate, empathetic or safe** for people in distress. Only a qualified professional can judge this.")
    w("- That the rule layer detects every urgent case. The scenario table lists phrasings it misses today; others certainly exist.")
    w("- That topic matching is accurate on real messages. It is a hand-written keyword heuristic never measured on labelled data.")
    w("- That the helpline numbers and hours are correct and current, or suitable for the people using IRIS.")
    w("- Anything in Hindi, Hinglish or any language other than English.")
    w("- Reading level, cultural fit, accessibility, or how real users react.\n")
    w("## What requires future clinical review\n")
    w("1. Every message, using `SAFETY_REVIEW_CHECKLIST.md`.")
    w("2. The decisions listed in the checklist, especially whether explicit ideation without a stated plan triggers the urgent response.")
    w("3. Closing the known gaps, with the clinician's input on which phrasings matter.")
    w("4. Then evaluation on real, independently labelled messages (the gold set), which this package does not replace.\n")
    w("## What this does not claim\n")
    w("Passing the automated tests shows the tested scenarios behave as written. It does not show that IRIS detects every urgent case, that the wording is appropriate, "
      "or that the system is ready for real-world use.\n")
    return "\n".join(L) + "\n"


def build_all() -> dict[str, str]:
    msgs, scen = message_rows(), scenario_rows()
    return {
        "support_messages.csv": to_csv(msgs), "support_messages.json": to_json(msgs),
        "support_scenarios.csv": to_csv(scen), "support_scenarios.json": to_json(scen),
        "SUPPORT_MESSAGES.md": render_messages_md(msgs, scen),
        "SAFETY_REVIEW_CHECKLIST.md": render_checklist_md(msgs, scen),
        "CLINICAL_REVIEW_STATUS.md": render_status_md(msgs, scen),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in build_all().items():
        (OUT_DIR / name).write_text(content, encoding="utf-8", newline="\n")
        print("wrote", OUT_DIR / name)


if __name__ == "__main__":
    main()
