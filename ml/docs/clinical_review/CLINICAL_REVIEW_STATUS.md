# Clinical review status of the support module

> **AI-ASSISTED DRAFT - CLINICAL REVIEW PENDING.** Not clinically approved. Not safe for deployment. Not a medical, diagnostic or crisis service. Written by an AI system, not by a clinician.

## Status in one line

**AI-assisted draft, clinical review pending. Nothing here has been reviewed by a clinician, counsellor or psychologist, and nothing is approved for use with real people.**

## What exists and is ready for a clinician to review

- **92 messages** (87 shown to people, 5 for reviewers), each with an ID, topic, trigger keywords, intended situation, safety considerations, limitations and a five-question draft self-check (`support_messages.csv`, `.json`, `SUPPORT_MESSAGES.md`).
- **58 safety-critical scenarios** covering explicit and indirect self-harm language, ambiguity, negation, past-tense distress, another person's difficulties, everyday idioms and ordinary support: 43 behave as desired, 13 are covered but need a clinician's decision, 2 are known gaps (`support_scenarios.csv`).
- A checklist and a list of decisions that need a clinician (`SAFETY_REVIEW_CHECKLIST.md`).
- Automated tests that regenerate these files and fail if they drift from the code, check that every sentence a person can see is in the list, that every message passes the automatic wording checks, that safety-critical scenarios trigger the right workflow whatever a model predicts, and that nothing claims a person is safe.

## What is verified (by automated tests, on the scenarios written for them)

- Every sentence shown to a person comes from the reviewed list; nothing is generated at run time.
- A confident 'Low' prediction never removes human review, and the rule layer and check-in floor override it where they apply.
- No message claims the person is safe or at no risk, gives a diagnosis, or shows a score or urgency label.

## What is NOT verified

- That the wording is **clinically appropriate, empathetic or safe** for people in distress. Only a qualified professional can judge this.
- That the rule layer detects every urgent case. The scenario table lists phrasings it misses today; others certainly exist.
- That topic matching is accurate on real messages. It is a hand-written keyword heuristic never measured on labelled data.
- That the helpline numbers and hours are correct and current, or suitable for the people using IRIS.
- Anything in Hindi, Hinglish or any language other than English.
- Reading level, cultural fit, accessibility, or how real users react.

## What requires future clinical review

1. Every message, using `SAFETY_REVIEW_CHECKLIST.md`.
2. The decisions listed in the checklist, especially whether explicit ideation without a stated plan triggers the urgent response.
3. Closing the known gaps, with the clinician's input on which phrasings matter.
4. Then evaluation on real, independently labelled messages (the gold set), which this package does not replace.

## What this does not claim

Passing the automated tests shows the tested scenarios behave as written. It does not show that IRIS detects every urgent case, that the wording is appropriate, or that the system is ready for real-world use.

