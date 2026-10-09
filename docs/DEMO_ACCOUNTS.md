# Demo accounts for hand testing

> Generated from `backend/devtools/demo_data.py`. **Do not edit by hand.** An automated test submits exactly these answers through the real API and checks the results below.

## How to start the sandbox

The sandbox uses a **stand-in login and a throwaway database**. It never touches Supabase, needs no email, and every restart wipes it clean (only the reviewer is re-created). Start both servers:

```bash
cd backend && .venv\Scripts\python -m devtools.demo_server      # API on http://127.0.0.1:8000
cd frontend && npm run dev                          # website on http://localhost:5173
```

Open **http://localhost:5173**. The three patients are **not** pre-created: you sign them up by hand with the details below, then log out and log in again to test login. The reviewer already exists.

## Reviewer (already created)

| Email | Password |
| --- | --- |
| `reviewer.demo@example.com` | `Demo-Reviewer-2026` |

Sign in as the reviewer after the patients have completed their check-ins. The queue is sorted with the highest urgency first. Click a name to open the full record (each opening is written to the audit log).

## Other things worth trying (before or between the three users)

- **Wrong password** at login: you get a generic 'Incorrect email or password' message.
- **Skip for now** on the check-in (top right): confirm, and the home page offers 'Start check-in' instead of 'completed'.
- **Back** and **Clear answer** inside the check-in; single-choice answers move on by themselves, text and multi-select need Next.
- **Under 18:** sign up with a birth date less than 18 years ago; the guardian name and email fields appear.
- **Forgot password** page: always answers the same, whether or not the email exists.
- As a patient, open `/reviewer` in the address bar: you are sent back home. As the reviewer, the home page sends you to the queue.

## Normal (low risk): Ananya Rao

### Sign-up form

| Field | Enter |
| --- | --- |
| Full name | Ananya Rao |
| Email | `ananya.normal@example.com` |
| Password | `Demo-Normal-2026` |
| Date of birth | 2002-06-14 (shown as day-month-year in the browser) |
| Gender | Female |
| Occupation | Student |
| Preferred language | English |
| Phone (optional) | +91 90000 00001 |
| Emergency contact (optional) | Suresh Rao, +91 90000 10001 |

Then tick the consent box and **Agree and continue**.

### Check-in answers (in the order the app asks them)

Answer exactly as shown. 'Frequency' questions have four buttons: Not at all, Several days, More than half the days, Nearly every day.

| # | Question | What to choose |
| --- | --- | --- |
| 1 | In your own words, what has been troubling you lately? | **type: Feeling mostly fine, just a bit busy with college this month.** |
| 2 | How long have you been feeling this way? | **Less than 2 weeks** |
| 3 | Has anything happened recently that has been weighing on you? | **select: Nothing specific** |
| 4 | Little interest or pleasure in doing things | **Not at all** |
| 5 | Feeling down, depressed, or hopeless | **Not at all** |
| 6 | Trouble falling or staying asleep, or sleeping too much | **Several days** |
| 7 | Feeling tired or having little energy | **Several days** |
| 8 | Poor appetite or overeating | **Not at all** |
| 9 | Feeling bad about yourself, or that you are a failure or have let yourself or your family down | **Not at all** |
| 10 | Trouble concentrating on things, such as reading or watching television | **Not at all** |
| 11 | Moving or speaking so slowly that other people could have noticed, or being so fidgety or restless that you have been moving around a lot more than usual | **Not at all** |
| 12 | Feeling nervous, anxious, or on edge | **Several days** |
| 13 | Not being able to stop or control worrying | **Not at all** |
| 14 | Worrying too much about different things | **Not at all** |
| 15 | Trouble relaxing | **Several days** |
| 16 | Being so restless that it is hard to sit still | **Not at all** |
| 17 | Becoming easily annoyed or irritable | **Not at all** |
| 18 | Feeling afraid, as if something awful might happen | **Not at all** |
| 19 | How difficult have these problems made it to do your work or studies, take care of things at home, or get along with other people? | **Not difficult at all** |
| 20 | How many hours do you usually sleep at night? | **6 to 8 hours** |
| 21 | How often do you have a drink containing alcohol? | **Never** |
| 22 | Do you use tobacco or any other substances? | **No** |
| 23 | Is there someone you trust that you can talk to? | **Yes** |
| 24 | Have you ever talked to a counsellor, psychologist, or psychiatrist? | **No, never** |
| 25 | Are you taking any medicine for your mental health? | **No** |
| 26 | Has anyone in your family had mental health difficulties? | **No** |
| 27 | Do you have any long-term physical health condition? | **No** |
| 28 | Thoughts that you would be better off dead, or of hurting yourself in some way | **Not at all** |

### What should happen

- After the last question the app opens the home page: 'Hi Ananya', check-in completed, next one due in 14 days.
- No crisis or helpline page appears.
- **Reviewer view:** baseline risk **LOW**, depression (PHQ-9) **2 / 27 (minimal)**, anxiety (GAD-7) **2 / 21 (minimal)**, suicide-risk screen tier **0**. Position in the queue when all three are done: **3**.

## Medium risk: Rohit Verma

### Sign-up form

| Field | Enter |
| --- | --- |
| Full name | Rohit Verma |
| Email | `rohit.medium@example.com` |
| Password | `Demo-Medium-2026` |
| Date of birth | 1999-11-03 (shown as day-month-year in the browser) |
| Gender | Male |
| Occupation | Working |
| Preferred language | English |
| Phone (optional) | +91 90000 00002 |
| Emergency contact (optional) | Neha Verma, +91 90000 10002 |

Then tick the consent box and **Agree and continue**.

### Check-in answers (in the order the app asks them)

Answer exactly as shown. 'Frequency' questions have four buttons: Not at all, Several days, More than half the days, Nearly every day.

| # | Question | What to choose |
| --- | --- | --- |
| 1 | In your own words, what has been troubling you lately? | **type: Exams and money worries are stressing me out and I sleep badly most nights.** |
| 2 | How long have you been feeling this way? | **1 to 6 months** |
| 3 | Has anything happened recently that has been weighing on you? | **select: Studies or exams, Money** |
| 4 | Little interest or pleasure in doing things | **More than half the days** |
| 5 | Feeling down, depressed, or hopeless | **More than half the days** |
| 6 | Trouble falling or staying asleep, or sleeping too much | **Several days** |
| 7 | Feeling tired or having little energy | **More than half the days** |
| 8 | Poor appetite or overeating | **Several days** |
| 9 | Feeling bad about yourself, or that you are a failure or have let yourself or your family down | **More than half the days** |
| 10 | Trouble concentrating on things, such as reading or watching television | **Several days** |
| 11 | Moving or speaking so slowly that other people could have noticed, or being so fidgety or restless that you have been moving around a lot more than usual | **Several days** |
| 12 | Feeling nervous, anxious, or on edge | **More than half the days** |
| 13 | Not being able to stop or control worrying | **More than half the days** |
| 14 | Worrying too much about different things | **Several days** |
| 15 | Trouble relaxing | **More than half the days** |
| 16 | Being so restless that it is hard to sit still | **Several days** |
| 17 | Becoming easily annoyed or irritable | **More than half the days** |
| 18 | Feeling afraid, as if something awful might happen | **Several days** |
| 19 | How difficult have these problems made it to do your work or studies, take care of things at home, or get along with other people? | **Very difficult** |
| 20 | How many hours do you usually sleep at night? | **4 to 6 hours** |
| 21 | How often do you have a drink containing alcohol? | **Monthly or less** |
| 22 | Do you use tobacco or any other substances? | **No** |
| 23 | Is there someone you trust that you can talk to? | **Not sure** |
| 24 | Have you ever talked to a counsellor, psychologist, or psychiatrist? | **No, never** |
| 25 | Are you taking any medicine for your mental health? | **No** |
| 26 | Has anyone in your family had mental health difficulties? | **Yes** |
| 27 | Do you have any long-term physical health condition? | **No** |
| 28 | Thoughts that you would be better off dead, or of hurting yourself in some way | **Not at all** |

### What should happen

- The app opens the home page (no helpline page), because no self-harm thoughts were reported.
- The reviewer, not you, sees the Medium baseline.
- **Reviewer view:** baseline risk **MEDIUM**, depression (PHQ-9) **12 / 27 (moderate)**, anxiety (GAD-7) **11 / 21 (moderate)**, suicide-risk screen tier **0**. Position in the queue when all three are done: **2**.

## High risk: Arjun Mehta

### Sign-up form

| Field | Enter |
| --- | --- |
| Full name | Arjun Mehta |
| Email | `arjun.high@example.com` |
| Password | `Demo-High-2026` |
| Date of birth | 1998-08-20 (shown as day-month-year in the browser) |
| Gender | Male |
| Occupation | Student |
| Preferred language | English |
| Phone (optional) | +91 90000 00003 |
| Emergency contact (optional) | Kavita Mehta, +91 90000 10003 |

Then tick the consent box and **Agree and continue**.

### Check-in answers (in the order the app asks them)

Answer exactly as shown. 'Frequency' questions have four buttons: Not at all, Several days, More than half the days, Nearly every day.

| # | Question | What to choose |
| --- | --- | --- |
| 1 | In your own words, what has been troubling you lately? | **type: I feel hopeless and I have been thinking about ending my life.** |
| 2 | How long have you been feeling this way? | **More than 6 months** |
| 3 | Has anything happened recently that has been weighing on you? | **select: Relationship, Losing someone close** |
| 4 | Little interest or pleasure in doing things | **Nearly every day** |
| 5 | Feeling down, depressed, or hopeless | **Nearly every day** |
| 6 | Trouble falling or staying asleep, or sleeping too much | **Nearly every day** |
| 7 | Feeling tired or having little energy | **More than half the days** |
| 8 | Poor appetite or overeating | **More than half the days** |
| 9 | Feeling bad about yourself, or that you are a failure or have let yourself or your family down | **Nearly every day** |
| 10 | Trouble concentrating on things, such as reading or watching television | **More than half the days** |
| 11 | Moving or speaking so slowly that other people could have noticed, or being so fidgety or restless that you have been moving around a lot more than usual | **More than half the days** |
| 12 | Feeling nervous, anxious, or on edge | **Nearly every day** |
| 13 | Not being able to stop or control worrying | **Nearly every day** |
| 14 | Worrying too much about different things | **More than half the days** |
| 15 | Trouble relaxing | **Nearly every day** |
| 16 | Being so restless that it is hard to sit still | **More than half the days** |
| 17 | Becoming easily annoyed or irritable | **More than half the days** |
| 18 | Feeling afraid, as if something awful might happen | **More than half the days** |
| 19 | How difficult have these problems made it to do your work or studies, take care of things at home, or get along with other people? | **Extremely difficult** |
| 20 | How many hours do you usually sleep at night? | **Less than 4 hours** |
| 21 | How often do you have a drink containing alcohol? | **Never** |
| 22 | Do you use tobacco or any other substances? | **No** |
| 23 | Is there someone you trust that you can talk to? | **No** |
| 24 | Have you ever talked to a counsellor, psychologist, or psychiatrist? | **No, never** |
| 25 | Are you taking any medicine for your mental health? | **No** |
| 26 | Has anyone in your family had mental health difficulties? | **Yes** |
| 27 | Do you have any long-term physical health condition? | **No** |
| 28 | Thoughts that you would be better off dead, or of hurting yourself in some way | **Nearly every day** |
| 29 | In the past month, have you wished you were dead, or wished you could go to sleep and not wake up? | **Yes** |
| 30 | In the past month, have you had any actual thoughts of ending your life? | **Yes** |
| 31 | Have you been thinking about how you might do this? | **Yes** |
| 32 | Have you had these thoughts and had some intention of acting on them? | **Yes** |
| 33 | Have you started to work out, or worked out, the details of how to do it? Do you intend to carry out this plan? | **No** |
| 34 | Have you ever done anything, started to do anything, or prepared to do anything to end your life? | **No** |

### What should happen

- When you answer the self-harm question, a box with 112, Tele-MANAS 14416 and KIRAN appears straight away.
- Extra safety questions appear one by one (31 -> 34 questions in total).
- After the last question the app opens the support page with the helplines, not the home page.
- **Reviewer view:** baseline risk **HIGH**, depression (PHQ-9) **23 / 27 (severe)**, anxiety (GAD-7) **17 / 21 (severe)**, suicide-risk screen tier **3**, **escalated**, minimum urgency high. Position in the queue when all three are done: **1**.

