# Talk to a doctor

A person who needs a human can reach a clinician inside IRIS. The rule that shapes everything: **IRIS never says a doctor is coming, or
when, until a doctor has actually accepted.** Before that the person is told the truth and the helplines stay on screen.

Prototype only. The doctor is a fictional test account, nothing here has been reviewed by a clinician, and the database migrations
(0003 to 0006) are written but **not applied to Supabase**.

## The flow

```
How a request starts
  the person asks ("Talk to a doctor")      IRIS offers one                     a reviewer offers one
                                             (explicit message or High check-in)  ("Offer a doctor" on a message)
                     \                              |                                  /
                      +---- the person ticks "I agree to share" and says yes ----------+
                                                    |
open        every on-duty doctor sees: first name, age, Urgent + why, check-in level      person: "We are trying to reach a doctor.
            (no message text, no scores: the person shared with "the doctor who accepts")         We cannot say how long." + helplines
              | first doctor to Accept owns it (the others get "no longer open")
accepted    doctor reads the summary; person: "A doctor has accepted. The conversation will begin when they are ready."
              | doctor presses Start conversation
in_session  chat (and optional video) for both; worrying lines are marked for the doctor only
              | doctor completes the session form (required)
closed      person: "This conversation has ended. You can ask again at any time."
```

If nobody accepts within the team's goal (`IRIS_DOCTOR_WAIT_GOAL_MINUTES`, default 5), the person reads "No doctor has been able to accept
your request yet... we cannot say when one will", keeps the helplines, and can keep the request open or cancel it. Reviewers get a red
banner and doctors see "Waiting N min". **The goal is for the team; no line the person reads mentions a time** (a test checks this).

## What each role sees

| Role | Before accepting | After accepting |
| --- | --- | --- |
| Person | Honest status, helplines, Cancel | Doctor's name, specialty and registration number; chat and video once started |
| Doctor | Open requests: first name, age, Urgent and reason, check-in level, how long waiting | Contact details, minor flag, a written summary ("In short"), check-in, recent messages, the optional AI overview, the chat, the session form |
| Reviewer | Banners: urgent doctor requests waiting, requests overdue | Can read a conversation or session note on request (audited) |

## Safety and privacy rules (all tested)

- **Consent first.** No request exists until the person ticks the agreement. "Not now" on an offer shares nothing. A reviewer can only *offer*.
- **Minimum before accepting.** No message text and no scores in the open requests list.
- **One owner.** Accepting is atomic; a second doctor cannot take the same case.
- **The person never sees flags or the clinical note.**
- **Audited:** opening the offers list, accepting, passing, reading a thread, the summary, the session note, starting and ending, video start and end.
- **The AI overview is optional and separate.** It needs its own tick, sends only age, gender, occupation and message text (no name, contact
  details or scores), runs in the background, drops sentences that reassure ("no risk factors mentioned"), and is labelled as a draft.
  The written "In short" summary is built by plain rules and never leaves the server.
- **Session form.** Concerns, observations, five suicide-risk questions each answered yes / no / not assessed, protective factors, overall risk,
  safety plan, impression, actions, follow-up (with an optional date), referral, emergency services. It is not a validated clinical form:
  a clinician must review it before real use.
- **Video** is direct between the two browsers (WebRTC); the backend only passes set-up messages and deletes them when the call ends.
  It uses a public STUN server and no TURN relay, so it can fail on strict networks; the chat stays available.

## Code

| Area | Files |
| --- | --- |
| Backend | `app/routers/consults.py` (person), `app/routers/doctor.py`, `app/services/consult.py`, `app/services/case_summary.py`, `app/models.py` |
| Frontend | `pages/AskDoctor.tsx`, `pages/Doctor.tsx`, `pages/DoctorCaseView.tsx`, `components/DoctorOfferCard.tsx`, `ConsultThread.tsx`, `VideoCall.tsx`, `CaseSummarySimple.tsx` |
| Tests | `backend/tests/test_consult*.py`, `test_case_narrative.py`, `test_doctor.py` |
| Migrations (not applied) | `0003_doctor_profiles`, `0004_consult_cases`, `0005_consult_messages`, `0006_session_notes` |
