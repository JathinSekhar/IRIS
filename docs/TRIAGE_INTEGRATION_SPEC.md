# Triage integration spec (DRAFT, nothing here is applied)

How the Phase 2 triage system (`ml/iris_ml/system.py`) will plug into the IRIS backend in Phase 4. No migration in this document
has been run, and no backend code has been changed. It exists so the ML work and the product meet at a defined interface.

## 1. Flow

```
user message -> POST /api/messages
   1. store the message
   2. load the user's latest check-in -> baseline urgency floor (backend safety.py)
   3. TriageSystem.triage(text, baseline_floor) with the V1 policy (mandatory_review=True)
        rules -> check-in floor -> model ranks (risk_score) -> out-of-scope guard   [highest urgency wins; nothing lowers another layer]
   4. store the prediction (with model version and reasons); its urgency is a PROVISIONAL priority, not a decision
   5. return a user-safe response; place EVERY case in the reviewer queue ordered by priority then risk_score (mandatory human review)
reviewer opens a case -> audit entry -> records their own judgement -> becomes feedback data (with consent only)
```

### 1a. Low-priority messages: recommended support, never cleared

`ml/iris_ml/support.py` (deterministic, no language-model API; wording is for clinical review). **Low means lower estimated urgency, not zero risk.**

- A Low message goes into the **normal review queue** (`queue_status = pending_human_review`). It is never approved, closed or ignored automatically.
- The person gets a supportive reply chosen from what they wrote (academic stress, loneliness, sleep, worry, low mood, work or money, relationships, grief,
  practical help, or general): active listening, a few self-help ideas (breathing, grounding, journaling, routines, study planning), and a nudge to talk to
  a trusted person, a counsellor or a mental-health professional. No diagnosis, no claim that they are safe or at no risk, no scores or labels.
- A reviewer who finds warning signs, a contradiction or any uncertainty can **escalate** the case to Medium or High (`escalate()`; raise only, reason required).
- Explicit self-harm, a High check-in floor or a High provisional priority triggers the urgent-response protocol and shows the helplines, **whatever the model predicted**.
- The reviewer sees a note on every case; for Low it says the case is not cleared and what to look for.
- Every sentence the person can see has an ID and is listed, with a safety checklist and scenarios, in `ml/docs/clinical_review/`. It is an **AI-assisted draft,
  clinical review pending**; it must not be shown to real users until a qualified clinician has reviewed it. Every reply also carries an always-visible
  "IRIS is not an emergency service. If you need help right now, call 112 or Tele-MANAS 14416" line, so nobody waits on a reply when they need help now.

## 2. API

| Method | Path | Who | Notes |
| --- | --- | --- | --- |
| POST | `/api/messages` | signed-in user | body `{text, conversation_id?}`. Returns the user-safe response below |
| GET | `/api/reviewer/queue` | reviewer | summaries only, ordered by `needs_human desc, risk_score desc, created_at asc`. Logged as `list_queue` |
| GET | `/api/reviewer/messages/{id}` | reviewer | full message, prediction and reasons. **Audited per record** (same pattern as check-ins) |
| POST | `/api/reviewer/messages/{id}/review` | reviewer | `{urgency, intent, notes}`: the reviewer's own judgement |

**User-safe response** (never contains scores, urgency labels or the word "risk"):
`{message_id, reply_mode: "supportive" | "supportive_with_resources", show_crisis_resources: bool, a_person_may_reach_out: bool}`.
`show_crisis_resources` is true whenever the final urgency is medium or high, or any rule or floor fired. A "Low" decision is never
presented to the user as "you are safe".

## 3. Draft tables (Postgres; Row Level Security on, no policies, privileges revoked from `anon` and `authenticated`, like the existing tables)

```sql
create table messages (
  id bigint generated always as identity primary key,
  user_id uuid not null references profiles(id) on delete cascade,
  conversation_id uuid,
  text text not null check (char_length(text) <= 5000),
  created_at timestamptz not null default now()
);
create table predictions (
  id bigint generated always as identity primary key,
  message_id bigint not null references messages(id) on delete cascade,
  model_version text not null,            -- hash of model artefact + data manifest + code commit
  policy_version text not null,           -- policy settings, cost matrix hash
  rule_level text not null,               -- none | review | high
  rule_hits text[] not null default '{}',
  baseline_floor text not null,           -- none | medium | high
  probabilities jsonb,                    -- calibrated [low, medium, high]; null when the model was unavailable
  model_urgency text,
  urgency text not null,                  -- final
  route text not null,                    -- human_reviewer | counsellor | normal_support
  needs_human boolean not null,
  risk_score real not null,
  reasons jsonb not null,
  latency_ms integer,
  created_at timestamptz not null default now()
);
create index on predictions (needs_human, risk_score desc, created_at);
create table reviews (
  id bigint generated always as identity primary key,
  message_id bigint not null references messages(id) on delete cascade,
  reviewer_id uuid not null,
  urgency text not null check (urgency in ('low','medium','high')),
  intent text not null,
  notes text,
  created_at timestamptz not null default now()
);
```
Message text is sensitive: consider application-level encryption, a retention period, and deletion on account removal (already cascades).

## 4. Safety invariants (each becomes an automated test)

1. **Fail safe.** If the model is unavailable, slow or raises, the decision is `needs_human = true`, never low. Rules and the floor still apply.
2. **Highest urgency wins.** Final urgency = max(model decision, rule layer, check-in floor). No layer can lower another.
3. **A model never clears a message.** (Decided 2026-10-09; replaces the earlier draft, which let a confident model reach Low.) Under the V1 policy
   every case is reviewed by a person and the person makes the final decision. The urgency the system stores is a provisional priority for the
   reviewer. Tested in `ml/tests/test_decision.py`.
4. **Out-of-scope goes to a human.** Empty, very short or non-English text.
5. **Everything is explainable.** Every prediction stores its reasons (rule hits, floor, confidence, cost) and the model and policy versions.
6. **Kill switch.** A feature flag switches the model off (rules + floor + human review continue) without a deployment.
7. **No scores to users.** Verified by a test on the response schema.
8. **Mandatory review is capacity-bound.** Because every case needs a reader, the queue length and time-to-first-read are monitored, and an
   over-capacity queue is surfaced to the project owner; it is never relieved by letting the model close cases.

## 5. Performance and operations

- Target: p95 under 300 ms per message on CPU for the chosen scorer (measured and reported in the Phase 2 results).
- Model version is recorded with every prediction; a rollback means pointing to the previous version.
- Daily monitoring: share sent to humans, share High, reviewer-vs-model agreement, confidence distribution, input-length distribution
  (drift), and any case where a reviewer raises the model's urgency (the most important error signal).
- Reviewer capacity is a hard constraint: the policy's `min_confidence` is set from the review rate the team can actually staff.

## 6. Learning from reviewers

Reviewer judgements can improve calibration and training data only with user consent and ethics approval. Until then they are used
for monitoring only. Any retraining produces a new model version, evaluated on the frozen gold set before use.

## 7. Open items before Phase 4

**Reviewer capacity for mandatory review of every message** (and what to do if it cannot be staffed: that changes the safety case and needs the
owner and a clinician); whether a *medium* check-in baseline from PHQ-9/GAD-7 should also raise the floor passed to message triage (today only the self-harm
answers do); calibration on real messages (currently verified only on documents); reviewer staffing; a clinician-approved cost matrix and mapping;
consent wording for feedback use; ethics approval for any pilot with real users.
