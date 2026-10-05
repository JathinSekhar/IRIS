# IRIS Architecture (Module 1: onboarding and clinical baseline)

## Purpose

Before IRIS reads a single message, it builds a **baseline profile** of the user the way a clinician does at intake.
The profile gives the later urgency model context: the same sentence ("I can't do this anymore") means different
things for someone with a severe baseline and someone with none.

```
Login -> Consent -> Clinical check-in -> Scoring -> Baseline profile (DB) -> [Module 2: message pipeline]
                                              \-> Safety tier >= moderate -> reviewer queue (escalated)
```

Full system (later modules): `Message -> Intent -> Urgency (+baseline) -> Confidence -> Cost-sensitive decision
-> Routing -> Human review -> Feedback/evaluation`.

## Clinical instruments

| Instrument | Items | Used for | Source |
| --- | --- | --- | --- |
| PHQ-9 | m1..m8 (Mood step) + s0 (item 9, Safety step) | Depression severity, 0-27. All 9 items are required for a complete score; item 9 is asked in the Safety step because it is also the entry point to the self-harm assessment | Kroenke, Spitzer & Williams, 2001 |
| GAD-7 | g1..g7 | Anxiety severity, 0-21 | Spitzer et al., 2006 |
| C-SSRS screener | c1..c7 (asked only if s0 > 0) | Suicide-risk triage | Posner et al., Columbia University |
| Functioning item | f1 | PHQ/GAD functional-impairment question | Standard follow-up to PHQ-9 / GAD-7 |
| Background | a1..a3, f2..f5, h1..h4 | Duration, triggers, sleep, alcohol (AUDIT-C style), support, history | Standard intake topics |

Bands: PHQ-9 0-4 minimal, 5-9 mild, 10-14 moderate, 15-19 moderately severe, 20-27 severe.
GAD-7 0-4 minimal, 5-9 mild, 10-14 moderate, 15-21 severe.
C-SSRS tier: **high** = intent, plan, or behaviour in the past 3 months; **moderate** = method without intent, or
behaviour older than 3 months; **low** = wish to be dead or thoughts without method.

## Safety assessment (first-class part of the design)

Self-harm risk is assessed by its own module, `backend/app/services/safety.py`, separate from the symptom scales,
because it answers a different question: not "how has this person been feeling?" but "how urgently must a human act?".
It is the part of Module 1 that most directly implements IRIS's urgency routing.

```
PHQ-9 item 9 (s0, always asked)
   |-- "Not at all" -------------> tier 0 none      no override
   `-- any other answer ---------> C-SSRS screener (c1..c7) + crisis resources shown immediately
                                    tier 1 low       wish to be dead / thoughts without method  -> urgency floor MEDIUM
                                    tier 2 moderate  method without intent, or past behaviour   -> urgency floor HIGH
                                    tier 3 high      intent, plan, or behaviour in last 3 months -> urgency floor HIGH
```

| Tier | Triggers | Shown to user | IRIS urgency floor | Routing |
| --- | --- | --- | --- | --- |
| 0 none | s0 = 0, or not answered | nothing | none | normal flow |
| 1 low | s0 > 0, c1 or c2 | helplines | medium | counsellor / support channel |
| 2 moderate | c3, or c6 without c7 | helplines + care-team notice | high | human reviewer immediately |
| 3 high | c4, c5, or c6 with c7 | helplines + care-team notice | high | human reviewer immediately |

Rules specific to safety:
1. **The urgency floor can only be raised downstream, never lowered.** Neither good symptom scores nor a calm-sounding
   message may reduce it (this is the same cost-sensitive principle as the message pipeline: a missed urgent case costs
   far more than an unnecessary escalation).
2. **Silence is visible.** An unanswered item 9 does not mean "safe": the PHQ-9 total is marked incomplete and the
   reviewer is shown how many items were answered.
3. **Help is immediate and independent of submission.** Helplines appear on the first affirmative answer, not after the
   check-in is saved.
4. The tier thresholds follow the published C-SSRS screener triage and must be confirmed by a clinician before use.
5. The reviewer queue sorts escalated cases first (tier 2 and 3), then by baseline risk.

In Module 2 (message pipeline), the stored `urgency_floor` is read alongside each message's predicted urgency and the
higher of the two is used for routing.

## Baseline risk rule

```
unknown   no answers (never inferred as low)
high      safety urgency floor = high (C-SSRS tier 2-3), OR PHQ-9 >= 20
medium    safety urgency floor = medium (tier 1), OR PHQ-9 >= 10, OR GAD-7 >= 10, OR functional difficulty "very"/"extremely"
low       answered, none of the above
```

Design rules:
1. **Missing data is never "low".** Skipped check-ins produce `unknown`. Scales carry a `complete` flag.
2. **The baseline can only raise urgency downstream, never lower it.** Good scores must not hide an urgent message.
3. **Scores are never returned to the end user.** The user API returns only `safety_flag` and `show_crisis_resources`.
4. **Crisis help is not gated on submission.** The Safety step shows helplines the moment self-harm is endorsed.
5. **Everything is skippable**, per question or as a whole check-in (snoozed for 24 hours, then re-prompted).

## Data model

`users` (role: user | reviewer; date of birth; guardian fields for minors) -> `consents` (versioned) ->
`checkins` (answers JSON, scores JSON, `baseline_risk`, `safety_flag`, `escalated`, `free_text`, timestamps).
Check-ins are valid for 14 days (PHQ-9 and GAD-7 measure the previous two weeks), then the user is prompted again.

## API

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| POST | `/api/auth/register`, `/login`, `/logout` | - | Sets or clears the httpOnly session cookie |
| GET | `/api/auth/me` | user | Includes server-computed `consent_accepted` and `checkin.prompt` |
| POST | `/api/consent` | user | Versioned; stale versions rejected (409) |
| GET | `/api/checkin/questionnaire` | user | Questions, branching rules, options |
| POST | `/api/checkin` | user + consent | Validates, drops answers of inactive branches, scores, stores |
| GET | `/api/reviewer/checkins[/{id}]` | reviewer | Sorted: escalated, high, medium, low, unknown |

The questionnaire definition lives only in `backend/app/services/questionnaire.py`. The frontend renders whatever it
serves, and the server re-validates every submission, so the two cannot drift.

## Security and privacy decisions

- Passwords hashed with bcrypt; login does a dummy hash check for unknown emails to avoid user enumeration by timing.
- Session JWT in an `httpOnly`, `SameSite=Lax` cookie (not `localStorage`, so XSS cannot read it). Production needs
  `IRIS_COOKIE_SECURE=true` and a strong `IRIS_SECRET_KEY`.
- Check-in answers are deliberately **not persisted in the browser**; the page warns before unloading mid-check-in.
- Role checks are enforced server-side (`require_reviewer`), not only in the UI.

## Before this is used with real people

1. Have a qualified clinician (for example the college counsellor) review question wording, thresholds, and the
   escalation procedure, and record their sign-off in the capstone report.
2. Define who monitors the reviewer queue and how fast, since escalation is only as good as the response.
3. Complete guardian-consent verification for minors, add rate limiting, and run on HTTPS.
4. Get ethics or institutional review approval as your institution requires.
