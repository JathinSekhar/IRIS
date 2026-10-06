# IRIS labelling guide (v0.1 DRAFT)

> **Status: draft for clinical review.** This guide defines how messages are labelled for training and for the gold
> test set. It is built on the C-SSRS screener's published triage logic and ordinary triage practice, but it has **not**
> yet been reviewed by a qualified clinician. A counsellor or clinical psychologist must review and sign off before the
> gold set is labelled. It is a screening aid for routing, not a diagnostic instrument.

## 1. Who labels, and how

- **Two annotators** label every gold item independently and blind to each other.
- A **counsellor adjudicates** every disagreement on urgency or intent, High and crisis cases first.
- Agreement target: **Cohen's kappa >= 0.6** (quadratic-weighted for urgency). Below that, the guide is unclear: stop,
  fix the guide, and relabel.
- **Annotator wellbeing:** this content can be distressing. Label in sessions of at most 45 minutes, take breaks, never
  label alone at night, and know who to talk to. Anyone can stop at any time without giving a reason.
- Never try to identify a person from a text, and never copy texts outside the labelling tool.

## 2. What you label

For each message (with up to the last 3 turns of context if available):

| Field | Values |
| --- | --- |
| `urgency` | `low`, `medium`, `high` |
| `intent` | `emotional_support`, `stress`, `crisis`, `other` |
| `subject` | `self`, `third_party`, `unclear` (who is at risk, if anyone) |
| `uncertain` | `1` if you are genuinely unsure, else `0` |
| `notes` | optional, one line |

## 3. Urgency: how quickly must a human act?

Label the **highest** urgency that the text supports. When torn between two levels, **choose the higher one** and set
`uncertain=1`. This is on purpose: a missed urgent case costs far more than an unnecessary escalation.

### HIGH: a human should see this now
Any of: a stated **intention** to die or self-harm; a **plan**; access to **means** with intent; **timing** (tonight,
today, soon); a **recent or ongoing attempt** or self-harm; saying goodbye or leaving a note; **immediate danger from
another person**. This also applies when the person describes **someone else** in that situation (`subject=third_party`).

### MEDIUM: needs timely support from a counsellor
Suicidal **thoughts without** plan, intent or timing (including passive: "I wish I wouldn't wake up"); **self-harm urges**
or **past** self-harm; **severe hopelessness or distress** with loss of functioning (not sleeping for days, cannot leave
bed, cannot study or work); heavy substance use to cope; non-immediate safety concerns (abuse, bullying, being unsafe).
Also **hyperbole using explicit first-person self-harm words** ("I'll kill myself if I fail"): label Medium, because
hyperbole cannot be told apart from real thoughts without context.

### LOW: normal support or self-help is appropriate
Everyday stress, sadness, worry, loneliness, grief, relationship or exam worries, venting, asking for advice, with no
self-harm content and no acute danger. Phrases like "this exam is killing me" or "I'm dead tired" are **Low**.

## 4. Intent: what is the person trying to do?

Choose the highest-priority intent present: **crisis > stress > emotional_support > other**.

- `crisis`: the message is mainly about self-harm, suicide, or immediate danger. **Always urgency medium or high.**
- `stress`: tension linked to identifiable demands (exams, deadlines, money, workload) without crisis content.
- `emotional_support`: wants comfort or to talk about feelings, loneliness, grief or relationships, without crisis content.
- `other`: greetings, logistics ("how do I book a counsellor?"), off-topic, thanks, unclear or empty.

**Consistency rules** (the dataset validator rejects violations): `crisis` implies urgency at least `medium`; urgency
`high` implies intent `crisis`.

## 5. Examples (invented for training annotators; they are not dataset items)

| Message | urgency | intent | subject | Why |
| --- | --- | --- | --- | --- |
| "I'm going to kill myself tonight." | high | crisis | self | intent and timing |
| "I have pills ready and nobody will miss me." | high | crisis | self | means plus intent |
| "My brother texted that he's ending it all tonight." | high | crisis | third_party | imminent risk to someone else |
| "I took a handful of tablets an hour ago." | high | crisis | self | attempt in progress |
| "I keep thinking everyone would be better off without me." | medium | crisis | self | ideation, no plan or timing |
| "I wish I could just not wake up." | medium | crisis | self | passive ideation |
| "I cut myself last month, and I feel the urge again." | medium | crisis | self | past self-harm plus urge |
| "I haven't slept in four days and can't get out of bed." | medium | emotional_support | self | severe distress, functional collapse |
| "I'll kill myself if I fail this paper." | medium | crisis | self | explicit self-harm words, hyperbole possible |
| "My friend says she wants to die and I don't know what to do." | medium | crisis | third_party | ideation reported about someone else; raise to high if timing is stated |
| "I have three exams this week and I can't cope." | low | stress | self | demands, no crisis content |
| "I feel really lonely since I moved here." | low | emotional_support | self | loneliness |
| "This assignment is killing me." | low | stress | self | idiom |
| "Thanks, that helped." | low | other | unclear | no content |
| "How do I book a counsellor?" | low | other | unclear | logistics |
| "I'm so anxious I can't breathe, my heart is racing." | medium | stress | self | acute symptoms; uncertain=1 (could be panic) |

## 6. Edge cases

- **Past events:** "I attempted last year" with no current content: Medium (`crisis`). Add a note.
- **Fiction, song lyrics, quotes:** if the text is clearly not about the writer, Low. If you cannot tell, treat it as
  the writer's own and `uncertain=1`.
- **Sarcasm and jokes:** label what the words say unless the context makes it unmistakable. Explicit self-harm words are
  never lower than Medium.
- **Negation:** "I'm not going to kill myself, I just feel low" is Medium (the words are present and the person is
  distressed), `uncertain=1`.
- **Reassurance after danger:** "I was going to end it last night but I'm OK now": Medium or High? Choose High if there
  was a plan or attempt in the last few days, and set `uncertain=1`.
- **Abuse or violence by others:** immediate danger is High (`intent=crisis`); past abuse without current danger is Medium.
- **Messages in other languages or mixed languages:** v1 labels English only. Skip anything else and note `lang`.
- **Several messages in a row:** judge the **last message in context**, but let earlier turns raise the level.

## 7. What these labels are NOT

They do not diagnose anyone and they do not tell a person that they are safe. "Low" means "normal support is
appropriate for what was written", never "no risk". Every product screen must keep that wording.

## 8. Change log

| Version | Change |
| --- | --- |
| 0.1 | First draft. Awaiting clinician review. |
