# IRIS in one page

**What it is.** A student mental-health support prototype: a check-in, a chat, a human review queue, and a way to reach a doctor. It is
built so that a person reads every message and nothing is ever closed by software.

**Status.** A working prototype on a local sandbox with fictional accounts. **Not for real people.** No clinician has reviewed the
wording, the questionnaire, the session form or the safety rules.

## What works

| Part | What it does |
| --- | --- |
| Sign-up, consent, check-in | PHQ-9, GAD-7 and self-harm questions; a High answer shows helplines at once and sets a safety floor |
| Chat | Explicit self-harm language gets an urgent reply, helplines and an instant reviewer alert. Ordinary messages get a short conversational reply (optional, Groq model, output checked). Every message goes to the review queue |
| Review queue | Sorted by priority; reviewers can raise priority (never lower), record a review, and offer a doctor; every opening is audited |
| Doctor | On/off duty, open requests, accept, summary, start, chat and video, required session form; IRIS offers a doctor after an explicit message or a High check-in |
| Honesty rules | The person is never told a doctor is coming, or when, before one accepts; tests check the wording |

## How priority is decided

Rules for explicit language plus the check-in safety floor. **No machine-learning model decides anything.** Phase 2 tested 21 model
configurations and a fine-tuned DistilRoBERTa; none reached the target (95% of high-risk cases found while reviewing 30%), and false alarms
on ordinary chat were high (`ml/reports/phase2_final_summary.md`). So every message is read by a person.

## What is measured, and what is not

- **Measured:** 226 backend tests, 589 ML tests, rule behaviour on fixed phrase lists, and a 58-scenario wording check (43 as intended,
  13 need a clinician's decision, 2 known gaps). These show the software does what it is designed to do.
- **Not measured:** how well IRIS finds real risk. That needs a gold set labelled by two independent annotators with a counsellor
  adjudicating. **No accuracy or safety claim is made until then.**

## Known gaps

- Hinglish, slang and indirect phrasing are often missed by the rules.
- Wording, questionnaire and session form need clinical review; consent text does not yet mention the doctor feature or the AI.
- Database migrations 0002 to 0006 are written but not applied to Supabase; message text is not encrypted and has no retention period.
- Video has no TURN relay, so it can fail on some networks. A real deployment needs doctor verification, staffing, and a privacy review
  of every third party (Groq, the STUN server).

More: [ARCHITECTURE.md](ARCHITECTURE.md) · [TRIAGE_INTEGRATION_SPEC.md](TRIAGE_INTEGRATION_SPEC.md) · [DOCTOR_FEATURE.md](DOCTOR_FEATURE.md) ·
[DEMO_ACCOUNTS.md](DEMO_ACCOUNTS.md)
