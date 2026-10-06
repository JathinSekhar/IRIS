# Data registry

Every dataset is listed here with its terms and status. **Nothing in `data/raw/` is committed to git.**
Last updated 2026-10-06.

| Source | What it is | Maps to | Access | Status |
| --- | --- | --- | --- | --- |
| **Reddit C-SSRS** (Gaur et al., 2019) | 500 anonymised Reddit users, one long document each, labelled by four psychiatrists: Supportive, Indicator, Ideation, Behavior, Attempt | urgency (crisis severity) | Open, **CC-BY-4.0** | **Downloaded 2026-10-06, checksums verified, in use** (see below) |
| **UMD Reddit Suicidality v2** (CLPsych 2019) | 11,129 SuicideWatch + 11,129 control users; crowd labels (621+621) and expert labels (245+245): none, low, moderate, severe | urgency | **Application, with ethics (IRB-equivalent) approval, a supervisor and a data management plan** | **Not started.** Preparation drafts in `UMD_APPLICATION_PREP.md`; needs the project owner and supervisor |
| **Dreaddit** (Turcan & McKeown, 2019) | About 3.5K Reddit segments labelled stressed or not | stress intent | Licence unconfirmed | **To verify** before any use |
| **Synthetic chat messages** | Messages written to the taxonomy, including hard cases, to match the chat domain | train only | We generate them | **Blocked: Claude API not yet authorised.** Always `is_synthetic=True`, train split only |
| **Gold test set** | 300 segments from held-out users, two blind annotators, counsellor adjudication, then frozen | evaluation only | Our own work | **Pool and blind batches built.** Waiting on clinician sign-off of the guide, two annotators, a counsellor (`GOLD_SET_WORKFLOW.md`) |
| **IRIS app messages** | Real user messages from the product | feedback loop | Only with user consent and ethics approval | **Not used** |

## Reddit C-SSRS: provenance

- Source: https://zenodo.org/records/2667859 , DOI 10.5281/zenodo.2667859
- Licence: Creative Commons Attribution 4.0 International (re-use and redistribution allowed with attribution). **We attribute it
  in every report and model card.** Terms read before download; no access restrictions apply.
- Retrieved: 2026-10-06 from `https://zenodo.org/records/2667859/files/<name>?download=1`. All files match the md5 published on the record.

| File | Size | md5 | Used |
| --- | --- | --- | --- |
| `500_Reddit_users_posts_labels.csv` | 3.6 MB | `be0addddd2bb64129d866ac41b625d04` | **Yes** (columns `User`, `Post`, `Label`) |
| `suicidal_attempt.csv` | 4.2 kB | `6f6b6d2b33ead618a4cb7bffbbd528a0` | No (clinical-ontology term lists; not useful for chat text) |
| `suicidal_behavior.csv` | 3.6 kB | `88b5a7dfca9f6574204de8a5934f2127` | No |
| `suicidal_ideation.csv` | 14.9 kB | `17f6cacf1deae66201f9469706f36de0` | No |
| `suicidal_indicator.csv` | 53.4 kB | `1c96b872c7e305aba3f898ee84770c25` | No |

- Facts established by inspection: 500 rows, one per user, no missing values, no duplicate texts; labels Ideation 171, Supportive 108,
  Indicator 99, Behavior 77, Attempt 45. Text length median about 3,400 characters (max about 33,000), i.e. **documents, not messages**.
- Citation: Gaur, M., Alambo, A., Sain, J. P., Kursuncu, U., Thirunarayan, K., Kavuluru, R., Sheth, A., Welton, R., Pathak, J. (2019).
  *Knowledge-aware Assessment of Severity of Suicide Risk for Early Intervention.* The Web Conference (WWW). Check the Zenodo record
  for the preferred citation text before publishing.
- Frozen split: `data/splits/reddit_cssrs_v1.csv` (hashed user ids and labels only, committed). 424 development users
  (train + val), **76 held-out test users**, stratified by label, seed 2026. Verified on every run; any change fails loudly.

## Mapping external labels to IRIS urgency (**clinical hypothesis, unreviewed**)

`configs/label_maps.yaml`. Every result is reported under both variants.

| Reddit C-SSRS | conservative (primary) | lenient |
| --- | --- | --- |
| Supportive | low | low |
| Indicator | medium | low |
| Ideation | medium | medium |
| Behavior | high | high |
| Attempt | high | high |

**Open issue for the clinician:** C-SSRS Behavior and Attempt describe suicidal behaviour in the user's history, possibly long
ago, while the IRIS labelling guide reserves High for imminent, recent or ongoing danger. Mapping them to High may overstate urgency.
The correct handling (for example High only with recent timing, otherwise Medium) is a clinical decision.

| UMD risk level (if approved) | IRIS urgency (proposal) |
| --- | --- |
| no risk | low |
| low risk | low or medium |
| moderate | medium |
| severe | high |

## Handling rules

- Third-party text is used for research under each dataset's terms, stays out of git (`data/raw`, `data/gold/*.csv`, batches,
  annotations are git-ignored), and is never quoted in the app, reports or demos.
- Split by **user** (`group_id`), never by post. The test users are fixed by the committed manifest.
- User ids are replaced by a one-way hash on load; links and `u/` mentions are masked.
- Record every file's source, retrieval date and checksum here.
