# Safety review checklist for the IRIS support messages

> **AI-ASSISTED DRAFT - CLINICAL REVIEW PENDING.** Not clinically approved. Not safe for deployment. Not a medical, diagnostic or crisis service. Written by an AI system, not by a clinician.

For the clinician or counsellor reviewing this. Generated; **do not edit by hand**. Fill in the `clinician_*` columns of `support_messages.csv` (and `support_scenarios.csv`); nothing there has been pre-filled.

## What to check on every message

1. **Dismissive.** Could the message sound dismissive, minimising or like telling the person to 'just' cope? Check for 'just', 'only', 'simply', 'everyone', and for advice that could feel like pressure.
2. **Implies a diagnosis.** Does it name or imply a condition, a label or a cause ('you have...', 'this is depression')?
3. **Unsupported promise.** Does it promise an outcome, a response time, a service that does not exist, or imply the person is safe?
4. **Inappropriate advice.** Could the suggestion be harmful or unsuitable for some people (breathing exercises in panic, 'talk to HR' where the workplace is the problem, 'wait before replying' in an abusive relationship)?
5. **Delays urgent help.** Could it lead someone to wait, rely on self-help, or not reach urgent help when they need it?

Every message in the CSV already carries the drafting AI's own answer to these five questions and the results of automatic wording checks. Treat those as a starting point to confirm or overturn, not as an assessment.

## How to record a decision

In `clinician_decision` write one of: `approve`, `approve with changes`, `reject`, `needs discussion`. Put changes in `clinician_approved_wording`. Add your name, role and the date. Until a row has a decision, it stays an **AI-assisted draft - clinical review pending**.

## Decisions that need a clinician (not just wording)

1. Should explicit first-person ideation without a stated plan (SC08 to SC12) trigger the urgent response, or is 'helplines plus Medium priority plus human review' acceptable?
2. Should warning signs such as giving possessions away or a 'last day' (SC13) trigger the urgent response?
3. A past attempt or past self-harm that the person says is behind them (SC33, SC34): helplines plus priority review is the current behaviour. Is that right?
4. Is it acceptable that ambiguous phrases such as 'I can't do this anymore' and 'I can't take it anymore' (SC24, SC25) are not flagged, given that a person reads every message?
5. Is an always-visible 'IRIS is not an emergency service' line (SM-COMMON-FOOTER) appropriate for every message, or only for some?
6. Is the breathing exercise appropriate to offer, and is the 'breathe at your own pace' wording enough?
7. Do the 'wait an hour before replying' (SM-REL-SH2) and 'talk to HR' (SM-WORK-RO1) suggestions need a caveat for abusive situations?
8. Is 'a couple of weeks' (SM-MOOD-RO2) and 'weeks' (SM-SLEEP-RO1) an acceptable threshold before suggesting professional help?
9. Are the helpline numbers and hours (SM-CRISIS-LINE1, SM-CRISIS-LINE2) correct and current, and are these the right services for the user base?
10. Is the tone right for people in distress? Are there words that sound clinical, cold or culturally unfamiliar? Should the reading level be simpler?
11. Should there be Hindi or Hinglish versions? v1 is English only and SC23 shows what happens without them.

## Messages the draft self-check already flags for attention

| ID | Message | Concern |
| --- | --- | --- |
| `SM-COMMON-LISTEN` | Thank you for telling us how you are feeling. What you wrote matters, and it is okay to talk about it. | **dismissive:** Low concern: identical for everyone, so it can feel generic. |
| `SM-COMMON-CLOSE` | You deserve support. A person on our team will review your message, which may take some time. | **promise:** Low concern: says a person will review the message. True under the mandatory-review design but reviewer capacity is not established, so 'may take some time' is included and no time is promised. |
| `SM-CRISIS-LEAD-FLAGGED` | If things ever feel like too much, these services are there for you at any time. | **promise:** Low concern: 'there for you at any time' relies on the helplines really being 24x7. Verify hours before real use. |
| `SM-CRISIS-LINE2` | To talk to someone now: Tele-MANAS 14416 (24x7, free, confidential) or KIRAN 1800-599-0019. | **promise:** Concern: states '24x7, free, confidential' for Tele-MANAS. Verify current service details before real use. |
| `SM-URGENT-REACH` | If you can, be with someone you trust right now, such as a family member or friend, and tell them how you are  | **advice:** Concern: assumes there is a trusted person nearby and that being with them is safe. Clinician to confirm. |
| `SM-ACAD-SH1` | Study planning: One option is to split the work into 25-minute blocks with 5-minute breaks, and to pick the th | **advice:** Low concern: a rigid schedule can add pressure. Phrased as 'one option'. |
| `SM-ACAD-SH2` | A real break: You could step away from the desk for a short walk or stretch between blocks. | **advice:** Low concern: assumes the person can leave the desk and walk safely. |
| `SM-SH-SLOW-BREATHING` | Slow breathing: You could try breathing in for 4 seconds, holding for 4, breathing out for 4 and holding for 4 | **advice:** Concern: breathing exercises can feel uncomfortable or increase panic in some people. The text offers 'breathe at your own pace instead'. Clinician to confirm. |
| `SM-LONE-SH1` | One small social step: If it feels possible, you could send a short message to someone you trust, or join one  | **advice:** Concern: may feel like pressure to someone who is isolated or whose contacts are unsafe. Hedged with 'if it feels possible'. |
| `SM-SH-A-STEADY-DAILY-ROUTINE` | A steady daily routine: Regular meals, some daylight, a short walk and a regular bedtime help many people feel | **dismissive:** Concern: may sound unrealistic for someone who is very low. Hedged with 'if that feels possible right now'. |
| `SM-SH-A-STEADY-DAILY-ROUTINE` | A steady daily routine: Regular meals, some daylight, a short walk and a regular bedtime help many people feel | **advice:** Concern: assumes the person can eat, sleep and go out regularly. Clinician to confirm. |
| `SM-SLEEP-SH1` | A wind-down routine: Some people find it helps to put screens away 30 to 60 minutes before bed and do somethin | **advice:** Low concern: general sleep hygiene; does not suit shift workers or caregivers. |
| `SM-SLEEP-RO1` | If sleep trouble goes on for weeks, a doctor or counsellor may be able to help look at what is behind it. | **delays help:** Low concern: suggests waiting 'for weeks' before seeing a doctor. Acceptable for sleep alone, but clinician to confirm the wording. |
| `SM-SH-JOURNALING` | Journaling: You could write down what is on your mind for five minutes. It is private to you and does not need | **advice:** Low concern: writing can bring up strong feelings for some people. Offered as private and optional. |
| `SM-MOOD-SH3` | One small thing you usually enjoy: If it feels possible, you could pick something short, such as music or a wa | **dismissive:** Concern: could sound like 'just do something fun' to someone very low. Hedged with 'if it feels possible' and 'it is fine if it does not feel appealing yet'. |
| `SM-MOOD-RO2` | If this has lasted more than a couple of weeks, a counsellor or doctor may be able to help. | **delays help:** Concern: suggests waiting 'more than a couple of weeks' before professional help for low mood. Clinician to confirm the threshold. Risk screening is separate and not delayed. |
| `SM-WORK-RO1` | You could talk to your manager or HR about workload, or to a financial counsellor about money. | **advice:** Concern: talking to a manager or HR is unsuitable if the workplace is the problem (harassment, abuse). |
| `SM-REL-SH2` | Pause before replying: If you are upset, it may help to wait an hour before answering a hard message. | **advice:** Concern: waiting before replying is unsuitable if the relationship involves violence, coercion or control. Clinician to confirm whether to add a caveat. |
| `SM-REL-RO1` | You could talk with someone neutral who knows you well. | **advice:** Concern: 'someone who knows you well' may be unsafe if the other person is abusive. |
| `SM-GRIEF-INTRO` | We are sorry for what you are going through. | **dismissive:** Low concern: a short sympathy line may feel brief for a major loss. |
| `SM-GRIEF-SH1` | Small routines: You could keep a few simple routines going, such as meals and a short walk, and be patient wit | **dismissive:** Concern: 'be patient with yourself' is sometimes heard as telling someone how to grieve. Clinician to confirm. |

## Scenarios where the system does not do what is desired today

| ID | Example (fictional) | Desired | Observed | Notes |
| --- | --- | --- | --- | --- |
| SC21 | I'm so done with everything | support_with_helplines | ordinary_support | Ambiguous: may be frustration or may be hopelessness. Currently not flagged. |
| SC23 | ab jeene ka mann nahi karta | support_with_helplines | ordinary_support | Hinglish. v1 is English only. The message still goes to a human, but no helplines are shown automatically. |
| SC25 | I can't take it anymore | support_with_helplines | ordinary_support |  |

These are gaps in the hand-written rule patterns and in English-only coverage. In every one of them a person still reads the message under the mandatory-review design, but the person would not automatically be shown helplines. Closing a gap means adding a pattern with tests, and no list of patterns can be shown to catch every urgent phrasing.

