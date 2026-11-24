# Project status on November 22 2026

## Confirmed requirements

Source: supplied Group Project Requirements.pdf. The report is due December 7, 2026, with at least 12 pages excluding the cover and academic integrity attachment, 12-point font and single spacing. Required content: motivation/challenges, approach, justified results/evaluation, contributions/limitations, specific contributions by member, references, and the mandatory integrity attachment signed by all members. The presentation is approximately 25 minutes and must be submitted before its actual presentation date. The proposal's December 7–9 preparation window does not establish a presentation date.

## Completed in this working session

- Inspected proposal, requirements, codebook, appendix, existing code and data.
- Preserved source transcripts, frozen split and the 50-call independent coding sheets.
- Added the ASU structured coding runner, full model schema, evidence validation, input and artifact hashes, raw response retention, atomic checkpoints, resume, and explicit failure handling.
- Added the frozen development reference, disjoint development calibration, novelty flags, proposed alias handling and review queue export.
- Added conservative derived requested-information tiers from appendix Table 2; unmapped labels remain explicit.
- Added read-only data audit, extended baseline field scoring, paired call-bootstrap comparison, qualification scoring, and measured-time scenarios.
- Reproduced the baseline and ran offline tests and a no-network request dry run.
- Preserved unfavorable novelty findings; report and presentation drafts distinguish completed results from pending experiments.

## Findings that change the proposal's assumptions

The local release has 2,429 distinct calls, of which 1,941 have category labels and 488 do not. There are no duplicate call IDs in these files. The existing split has 1,358 development and 583 test calls; frozen hashes match. The development categories include telemarketing and two vishing categories, with no nuisance/others; broad five-category generalization is therefore unverified. Original organization names are redacted. There is no identifiable 337-call two-coder reliability set. Both qualification sheets are blank.

The written codebook excludes qualification questions from requested information, but released labels include them. The agent's primary scoring contract follows the released labels and explicitly reports that choice. Its derived information tiers do not convert unmapped qualification labels into invented sensitivity classes.

The source paper's 115 hours measures audio duration rather than coder effort. Time savings need measurements from this project.

## Current evidence

Reproduced baseline on 583 calls: category kappa 0.538; subcategory kappa 0.677; persuasion micro-F1 0.549; functional states micro-F1 0.567; requested information micro-F1 0.564. Full original and extended tables remain under runs/baseline/.

Initial reference-only novelty: 28/30 withheld accident_claim calls flagged, but 409/545 known-topic calls incorrectly flagged. The calibrated lexical detector reduces known false positives to 21/545 but detects only 2/30 withheld calls. Neither operating point establishes reliable novelty detection. Eight naturally unseen topics/calls are treated separately from known-topic negatives. The revised experiment is exploratory because initial test results were already inspected. The complete model-assisted novelty system has not been evaluated.

## Still required

1. API access: confirm exact approved model/provider IDs and structured output support; run development smoke test, freeze configuration, then run the 583-call agent evaluation. No real LLM results exist yet.
2. Human study: Mansi and Ju-Won independently label the 50 calls; a third coder adjudicates disagreements blind to model output. Confirm actual team assignments. These activities cannot be replaced by model-generated human labels.
3. Measure manual/review time and assess accuracy of unflagged calls. Do not claim automation can replace manual work without these results.
4. Finalize the Word report and PowerPoint, ensuring the report's final body reaches 12 pages with substantive results and analysis. Draft pagination is not submission approval.
5. Confirm actual completed contributions with all members. Each member supplies their own student ID details and signature on the mandatory attachment.

## Suggested completion sequence

November 22–24: review implementation and complete development smoke test when access arrives; start independent human coding now. November 25–27: freeze prompt/configuration and complete held-out and qualification evaluation. November 28–30: audit errors and review workload; measure times. December 1–4: integrate results and revise report/slides. December 5–6: final checks and rehearsal. December 7: submit report by the course deadline. These are planning targets, not scheduled tasks or promises about API availability.
