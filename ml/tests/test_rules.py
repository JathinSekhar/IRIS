"""The rule layer is the last line of defence, so its tests are explicit lists a clinician can read and extend."""
import pytest

from iris_ml.rules import normalize, scan

# Explicit intent, plan, means, timing, or an attempt in progress: must reach HIGH.
MUST_BE_HIGH = [
    "I'm going to kill myself tonight",
    "i am going to end my life",
    "gonna take my own life after the results come out",
    "I have pills and I'm going to end it tonight",
    "I wrote a suicide note",
    "this is my last message, goodbye everyone",
    "I already took all the pills",
    "I'm planning to hang myself",
    "I bought a rope and I want to die",
    "My brother is going to kill himself tonight",
    "i'm gonna k!ll myself",
    "k*ll myself tonight",
    "I'm going to jump off the bridge",
    "I'm about to overdose",
    "I'm cutting my wrists",
    "I decided to commit suicide",
    "going to su1c1de tomorrow",
    "I will kill myself this weekend",
    "I'M GOING TO KILL MYSELF",
    "i left a goodbye note on my desk",
    "The means are ready and tonight I am going to do it",
    "I have the pills all ready and I will go through with it",
    "By the time you read this it will all be over",
]

# Ideation, self-harm, euphemisms, third-party risk: must be flagged at least REVIEW.
MUST_BE_FLAGGED = [
    "I want to die",
    "i wanna die",
    "I wish I was dead",
    "everyone would be better off without me",
    "I don't want to be here anymore",
    "I don't want to wake up tomorrow",
    "there is no reason to live",
    "I think about suicide a lot",
    "I've been cutting myself",
    "I self harm when I'm stressed",
    "I want to unalive myself",
    "thinking about ending it all",
    "I want to kill myself",
    "my friend wants to kill himself",
    "I'm suicidal",
    "I can't go on like this",
    "I hurt myself again last night",
    "I want to jump off a bridge",
    "su*cidal thoughts again",
    "I just want to not wake up",
    "I keep thinking about hanging myself",
    "she talks about suicide all the time",
    "i feel like i should just unalive",
    "I want to kIlL mYsElF",
    "I’m so tired and I want to die",
    "I wish I wasn't here anymore",
    "I wish I had never been born",
    "i wish i could just disappear",
    "I wish I wouldn't wake up",
    "sometimes I think I should never have been born",
    "Tomorrow is my last day and I have given away all my things",
    "I will not be here anymore after this week",
    "I feel hopeless and I have been thinking about ending my life",       # found by the demo walkthrough: "ending" was missed
    "I keep thinking about ending my own life",
]

# Everyday language that must NOT be flagged.
MUST_BE_NONE = [
    "This exam is killing me",
    "I'm dying to see the new movie",
    "I'm dead tired after the gym",
    "My phone died again",
    "I could die of embarrassment",
    "Killing time before class",
    "That joke killed me lol",
    "I've been feeling a bit low and anxious about my results",
    "How do I book a counsellor appointment?",
    "Hello",
    "I can't sleep because of exams",
    "She is killing it at work",
    "I'm so stressed I could scream",
    "my battery is dead",
    "This traffic is killing me",
    "I can't do this anymore, the workload is too much",
    "my dog died last year and I still miss him",
    "I feel hopeless about my grades",
    "Everyone says I should relax more",
    "I need to end this conversation soon, class is starting",
    "I wish I wasn't so tired all the time",
    "I wish I could disappear into a good book this weekend",
    "I wish I had studied more",
    "The pills are ready at the pharmacy for my mother",
    "Everything is ready for the exam and I am going to do it tomorrow",
    "I am going to do it tonight, the cake for the party is ready",
    "I have been thinking about ending things with my boyfriend, we argue too much",
    "I ended up finishing the exam early",
]


@pytest.mark.parametrize("text", MUST_BE_HIGH)
def test_explicit_intent_reaches_high(text):
    r = scan(text)
    assert r.level == "high" and r.urgency_floor == "high", (text, r)


@pytest.mark.parametrize("text", MUST_BE_FLAGGED)
def test_ideation_and_euphemisms_are_flagged(text):
    r = scan(text)
    assert r.flagged, (text, r)
    assert r.urgency_floor in ("medium", "high")


@pytest.mark.parametrize("text", MUST_BE_NONE)
def test_everyday_language_is_not_flagged(text):
    r = scan(text)
    assert not r.flagged, (text, r)
    assert r.urgency_floor == "none"


def test_gate_every_explicit_phrase_is_caught():
    """Acceptance gate from the ML plan: the rule layer catches 100% of the explicit-phrase list."""
    missed = [t for t in MUST_BE_HIGH + MUST_BE_FLAGGED if not scan(t).flagged]
    assert missed == []


def test_benign_false_alarm_rate_is_reported_and_small():
    false_alarms = [t for t in MUST_BE_NONE if scan(t).flagged]
    assert false_alarms == [] and len(MUST_BE_NONE) >= 20


# Documented trade-offs: these are flagged ON PURPOSE (recall-first). If one stops being flagged, review the change.
KNOWN_FALSE_POSITIVES = [
    "We watched a documentary about suicide prevention in class",
    "I want to die laughing at this meme",
    "Tomorrow is my last day at this job and I am excited",
    "I can't face another day of rain",                     # ambiguous on purpose: the same words are a hopelessness phrase, so it is flagged for a person
]


@pytest.mark.parametrize("text", KNOWN_FALSE_POSITIVES)
def test_known_false_positives_stay_flagged(text):
    assert scan(text).flagged


def test_negation_is_noted_but_never_lowers_the_level():
    r = scan("I'm not going to kill myself, I just feel low")
    assert r.flagged and r.negated
    r2 = scan("I am not suicidal")
    assert r2.flagged and r2.negated


def test_third_person_is_noted_and_still_escalated():
    r = scan("my friend wants to kill himself")
    assert r.flagged and r.third_person
    r2 = scan("I want to kill myself")
    assert r2.flagged and not r2.third_person


def test_high_wins_over_review():
    r = scan("I want to die and I'm going to end my life tonight")
    assert r.level == "high" and len(r.hits) >= 2


def test_obfuscation_and_unicode_tricks():
    assert scan("k​i​ll myself tonight").flagged            # zero-width characters
    assert scan("I wanna diiiiie").flagged                            # elongated word
    assert scan("I want to kiiiiill myself").flagged                  # elongated letters
    assert scan("Ｉ ｗａｎｔ ｔｏ ｄｉｅ").flagged  # full-width characters


def test_normalize_is_idempotent_and_safe_on_odd_input():
    for s in ["", "   ", "a" * 10_000, "\u0000\u0001", "😢 i want to die 😢"]:
        assert normalize(normalize(s)) == normalize(s)
        scan(s)  # must never raise
    assert scan("😢 i want to die 😢").flagged
    assert scan("").level == "none"


# Found while probing the support matcher: implicit "I would not be missed" language.
@pytest.mark.parametrize("text", ["Nobody would notice if I was gone", "no one would even miss me if I died", "nobody would care if I disappeared",
                                  "Nobody would notice if I were not around"])
def test_not_being_missed_is_flagged(text):
    assert scan(text).flagged, text


@pytest.mark.parametrize("text", ["Nobody would notice if I took a day off", "No one would know if I left the party early",
                                  "nobody would care if I changed my seat"])
def test_not_being_noticed_for_everyday_things_is_not_flagged(text):
    assert not scan(text).flagged, text


# Closed after the support-message review found them missed (docs/clinical_review/support_scenarios.csv).
@pytest.mark.parametrize("text", [
    "I don't see the point in anything anymore", "I can't see the point of going on", "I just can't face another day",
    "I can't get through another night like this", "Everyone would be happier if I wasn't around", "they would be better off if I was gone",
    "She told me she is thinking of hurting herself", "my brother keeps harming himself", "he is killing himself slowly",
])
def test_phrasings_found_missing_in_the_review_are_flagged(text):
    assert scan(text).flagged, text


@pytest.mark.parametrize("text", [
    "I don't see the point in this assignment", "I don't see the point of the meeting on Monday",
    "I can't do another day of that commute", "Everyone would be happier if I wasn't so grumpy", "my team would be better off if the deadline was moved",
    "my friend keeps hurting his knee playing football", "she hurt her hand yesterday",
])
def test_everyday_sentences_near_the_new_patterns_are_not_flagged(text):
    assert not scan(text).flagged, text


# From a hand test of the chat: these got only self-help tips and no helplines.
@pytest.mark.parametrize("text", ["I can't take it anymore. Everything feels too difficult right now.", "I cannot take this any longer", "i can't take it any more"])
def test_cant_take_it_anymore_is_flagged(text):
    assert scan(text).flagged, text


@pytest.mark.parametrize("text", ["I can't take the noise in the hostel", "I can't take my eyes off this show", "I can't take a day off this week"])
def test_cant_take_something_else_is_not_flagged(text):
    assert not scan(text).flagged, text
