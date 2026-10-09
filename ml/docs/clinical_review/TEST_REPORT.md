# Test report: support module and clinical-review package

> AI-ASSISTED DRAFT - CLINICAL REVIEW PENDING. These results show that the **tested scenarios behave as written**. They do not show that IRIS detects every urgent case, that the wording is clinically appropriate, or that the system is ready for real-world use.

Run on 2026-10-09 with the project's virtual environments, on CPU, without the laptop GPU (`CUDA_VISIBLE_DEVICES=-1`). Light tests only; the heavy model tests were not run, to keep compute off the laptop.

| Command | Result |
| --- | --- |
| `cd ml && python -m pytest tests/test_support.py tests/test_support_review.py tests/test_decision.py tests/test_rules.py tests/test_walkthrough.py -q` | 438 passed in 5.18s |
| `cd backend && python -m pytest tests/test_demo_accounts.py tests/test_messages.py -q` | 50 passed, 1 warning in 4.22s |

## By file

| File | Result |
| --- | --- |
| `tests/test_support.py` | 202 passed in 1.03s |
| `tests/test_support_review.py` | 76 passed in 2.01s |
| `tests/test_decision.py` | 33 passed in 2.11s |
| `tests/test_rules.py` | 125 passed in 0.19s |
| `tests/test_walkthrough.py` | 2 passed in 0.18s |

## What the tests check

- Every message has a unique ID and the review columns; every sentence a person can see comes from the reviewed list (nothing generated at run time).
- Every support category has an opening, self-help and a person to contact; every documented keyword triggers its topic; each ordinary scenario gets its own topic's wording.
- Explicit and imminent cases get the urgent workflow whatever a model predicts (five model outputs x three check-in floors); the check-in floor alone triggers it; no self-help is shown instead of help.
- A confident Low prediction never removes human review; every scenario stays in mandatory review.
- No message claims the person is safe, gives a diagnosis, minimises, over-promises, or shows a score or label. The wording checks are shown to catch planted bad sentences.
- The 2 known gaps (Hinglish and 'I'm so done with everything') are exactly the documented ones: closing one fails a test on purpose, so the documents are updated with the code.
- The generated review files equal what the code produces, and nothing is marked approved.
- Chat (backend): every message waits for a person and nothing is auto-closed; safety rules and the check-in floor override a calm message; reviewers can only raise priority and every reviewer action is audited; the person sees no scores or labels; people cannot reach reviewer endpoints; a person's data is removed with their account; good news gets a warm reply with no advice and mixed messages never do; explicit statements about ending one's life are urgent; the person's status line reflects whether a person has opened the message and promises no time or doctor; reviewer alerts are counts-only and not audited.

## What they do not check

Clinical appropriateness of any wording; detection of urgent phrasings that have no test; accuracy of topic matching on real messages; non-English text; whether the helpline details are current.
