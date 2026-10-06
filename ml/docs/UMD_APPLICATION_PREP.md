# UMD Reddit Suicidality Dataset (v2): application preparation

**STATUS: DRAFT. NOT SUBMITTED. Do not submit until (1) institutional ethics approval or an exemption letter has been obtained and
(2) the supervisor and accountable researcher details are confirmed.** The project owner decided this on 2026-10-06.

> **Nothing here has been sent.** These are drafts for the project owner and supervisor. Submitting an application, signing
> a data management plan, or emailing the governance committee is outward-facing and is done by you, not by the code
> assistant. Everything below is based on the dataset's own application page
> (https://psresnik.github.io/umd_reddit_suicidality_dataset.html); re-read it before applying, because requirements can change.

## What it is

Version 2 of the UMD Reddit Suicidality Dataset: 11,129 SuicideWatch users and 11,129 control users with their full
posting history (de-identified), crowdsourced risk labels for 621 + 621 users, and **expert** labels for 245 + 245 users.
Risk scale: no risk, low, moderate, severe. It is far larger than the 500-user Reddit C-SSRS set we already use, and its
expert labels would give us much more evidence about the severe class.

## The hard requirement: ethics review comes first

The application must include documentation that "your project plan has been reviewed and approved by an Institutional Review
Board or equivalent ethical review panel" (an approval or an exemption letter). For us that means **your institution's ethics
committee** has to review the project protocol *before* we can apply. This is the long pole: start it now.

## What the application contains

1. **Cover letter (two pages at most)** covering: project description, intended duration, commitment to the ethical
   principles in the cited papers, a commitment to call the data the "University of Maryland Reddit Suicidality Dataset,
   Version 2" with the required citations (Shing et al., 2018; Zirikly et al., 2019), acknowledgement of the American
   Association of Suicidology, and a **data management statement**.
2. **Ethics approval or exemption documentation** and a copy of the research protocol submitted to the ethics committee.
3. Sent to **Philip Resnik (resnik@umd.edu)**; the page also links an application template (.docx).

The five-member governance committee replies with: approval, questions, revise and resubmit, or rejection. Conditions of
use include mandatory citations, restricted redistribution, and password-protected storage with group-based access.

## Who needs to do what

| Step | Owner |
| --- | --- |
| Name a faculty supervisor / principal investigator (committees expect an accountable researcher, not only students) | Project owner |
| Submit the project protocol to the institutional ethics committee; obtain approval or exemption | Project owner + supervisor |
| Review and sign the data management statement | Project owner + supervisor |
| Send the application email | Supervisor (or owner, with supervisor in copy) |
| Prepare secure storage and a named list of everyone who will access the data | Project owner |
| Draft documents below | Code assistant (done), then edited by you |

## Draft: project description (for the cover letter and the ethics protocol)

> **IRIS (Intent and Risk Intelligence System)** is a capstone research project that builds a decision-support layer for
> mental-health support services. It estimates, for an incoming message, what the writer needs, how urgent it is, and
> whether a human must act, and always routes high-risk and uncertain cases to a trained human reviewer. The system is a
> screening and routing aid, not a diagnostic tool, and no automated decision replaces a person for high-risk cases.
> We request the dataset to (1) train and evaluate classifiers of suicide-risk severity, (2) measure calibration and the
> cost of missed urgent cases, and (3) validate that our labelling guide and models agree with expert clinical labels.
> Only text from the dataset is used; we will not attempt to identify, contact or link any user. Intended duration: [DATES].
> Researchers with access: [NAMES AND ROLES]. Institutional ethics review: [COMMITTEE NAME, REFERENCE NUMBER, DATE].

## Draft: data management statement (edit to match what you can truly commit to)

- **Storage:** the data will be kept on [ONE ENCRYPTED, PASSWORD-PROTECTED LOCATION], accessible only to the named
  researchers listed in the application. It will not be stored in cloud drives, email, chat tools or shared repositories.
- **Access control:** named individuals only; access is removed when a person leaves the project.
- **Re-distribution:** we will not share the data or any raw text from it. Derived artefacts (model weights, metrics) are
  shared only if they cannot reproduce text; model weights are reviewed for memorisation before any release.
- **Publications and demos:** no raw posts or quotes beyond what the dataset terms allow; results are aggregate.
- **Notification:** we will tell the governance committee who holds access and refer any external request for the data to it.
- **Retention and deletion:** the data is deleted at [END DATE / PROJECT END] and we will confirm deletion on request.
- **Safety of researchers:** annotators and developers have breaks, support contacts and the right to stop (see the labelling guide).

## Draft: protocol outline for the ethics committee

1. Background and aim. 2. Data source and why it is appropriate (existing, de-identified, public posts, governed access).
3. Participants: none recruited; secondary use of de-identified data. 4. Risks: distress for researchers reading the
content; re-identification risk; model misuse. 5. Mitigations: access control, no linkage attempts, wellbeing protocol,
no deployment on real users without separate approval. 6. Data management (above). 7. Expected benefit. 8. Dissemination.

## Checklist

- [ ] Supervisor named
- [ ] Ethics protocol submitted; approval or exemption letter received
- [ ] Secure storage ready; list of people with access written
- [ ] Cover letter edited (placeholders filled), with the required citations and AAS acknowledgement
- [ ] Application sent; committee reply recorded in `DATA_REGISTRY.md`

Until this is approved, **no UMD data is used** and the project proceeds with the Reddit C-SSRS data and the team gold set.
