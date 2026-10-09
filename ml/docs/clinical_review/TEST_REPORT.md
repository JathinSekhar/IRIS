# Test report: support module and clinical-review package

> AI-ASSISTED DRAFT - CLINICAL REVIEW PENDING. These results show that the **tested scenarios behave as written**. They do not show that IRIS detects every urgent case, that the wording is clinically appropriate, or that the system is ready for real-world use.

Run on 2026-10-09 with the project's virtual environments, on CPU, without the laptop GPU (`CUDA_VISIBLE_DEVICES=-1`). Light tests only; the heavy model tests were not run, to keep compute off the laptop.

| Command | Result |
| --- | --- |
| `cd ml && python -m pytest tests/test_support.py tests/test_support_review.py tests/test_decision.py tests/test_rules.py tests/test_walkthrough.py -q` | 391 passed in 4.97s |
| `cd backend && python -m pytest tests/test_demo_accounts.py -q` | 11 passed, 1 warning in 1.36s |

## By file

| File | Result |
| --- | --- |
| `tests/test_support.py` | 194 passed in 2.31s |
| `tests/test_support_review.py` | 53 passed in 3.10s |
| `tests/test_decision.py` | 23 passed in 2.21s |
| `tests/test_rules.py` | 119 passed in 0.19s |
| `tests/test_walkthrough.py` | 2 passed in 1.55s |

## What the tests check

- Every message has a unique ID and the review columns; every sentence a person can see comes from the reviewed list (nothing generated at run time).
- Every support category has an opening, self-help and a person to contact; every documented keyword triggers its topic; each ordinary scenario gets its own topic's wording.
- Explicit and imminent cases get the urgent workflow whatever a model predicts (five model outputs x three check-in floors); the check-in floor alone triggers it; no self-help is shown instead of help.
- A confident Low prediction never removes human review; every scenario stays in mandatory review.
- No message claims the person is safe, gives a diagnosis, minimises, over-promises, or shows a score or label. The wording checks are shown to catch planted bad sentences.
- The 3 known gaps are exactly the documented ones: closing one fails a test on purpose, so the documents are updated with the code.
- The generated review files equal what the code produces, and nothing is marked approved.

## What they do not check

Clinical appropriateness of any wording; detection of urgent phrasings that have no test; accuracy of topic matching on real messages; non-English text; whether the helpline details are current.
