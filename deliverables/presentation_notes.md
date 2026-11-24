# Presentation notes

Draft with 18 slides and 25 minutes planned speaking time. Rehearse and update pending results before presenting.

## 1 Project question (60 seconds)

Introduce the task: apply an existing research codebook to redacted transcripts and compare the resulting labels with released human annotations. Distinguish the offline results shown today from live agent experiments still awaiting API access. The final presentation must be updated after those experiments.

## 2 Motivation (90 seconds)

Use the example of a caller asking about Medicare eligibility before an attempted handoff. Explain why identifying words is easier than interpreting the exchange. A continued conversation does not by itself establish a successful transfer. Avoid claiming that transcript evidence can recover vocal or acoustic observations.

## 3 Research questions (60 seconds)

State each question and the evidence needed to answer it. Structural validity addresses completeness; agreement addresses interpretation; novelty needs false positives as well as recall; labor needs observed coding and review time. A functioning API client alone does not answer these questions.

## 4 Data audit (90 seconds)

Explain the difference between all released calls and the subset with codes. No duplicate call IDs were found. The local development labels cover three of the five available category labels. The release contains one codes object per call, and no identifiable pairwise 337-call reliability mapping. These limits constrain generalization and human-baseline comparisons.

## 5 Pipeline (90 seconds)

Walk through the data flow. The code works on structured source JSON and never rewrites source transcripts. The model sees only call ID and conversation from each source record. Validation either accepts a complete, evidence-grounded object or creates an explicit failure. Review remains part of the measured workflow.

## 6 Schema and evidence (90 seconds)

Explain the difference between the API-side JSON Schema and local semantic checks. Every nonempty coded field needs source indices; turn labels cite their own source turn. Negative findings can cite inspected turns. These rules help auditing, but a source pointer is not proof that an interpretation is correct. Unknown material fields trigger review.

## 7 Label alignment (90 seconds)

Use age or possession_medicare as examples. Explain why silently removing those human labels would change the scoring target. Complementary labels retain nag/time/dh and the artifact compatibility mapping. Information tiers are derived only where appendix Table 2 supplies a mapping; other open labels remain unmapped.

## 8 Baseline results (90 seconds)

These are reproduced offline results, not LLM scores. Emphasize transfer intent versus transfer success as different tasks. The report includes all primary fields and bootstrap intervals; avoid treating kappa and F1 as interchangeable. The unchanged baseline uses keyword and phrase heuristics and is an inspectable minimum system.

## 9 ASU runner (90 seconds)

Explain that no live requests have been made. The runner reads the token from the local environment and does not save it in request artifacts. The API request includes a nested JSON Schema response format. Actual provider support and backend metadata must be checked using development calls before the final run. Temperature zero does not guarantee identical future outputs.

## 10 Novelty design (90 seconds)

Describe fixed lexical vectors and fifth-percentile calibration. Candidate organizations require literal unredacted text; redaction markers never become aliases. Model-inferred out-of-reference topics and unconfirmed candidates add signals to the lexical comparator. Neither model pretraining nor codebook examples are erased by reference withholding.

## 11 Novelty results (120 seconds)

Do not present high recall without false-positive cost. The fixed detector flags 443 total calls; calibration reduces that count to 23 while missing most withheld examples. The revised threshold used development data only, but initial test results had already been inspected, so call the revision exploratory. Full model-assisted novelty results remain pending.

## 12 Qualification outcomes (90 seconds)

Describe the last exchange before the first transfer. Explain that the existing guide places some insufficient-evidence cases into call_terminates; it is not always proof of an actual hang-up. The model should retain uncertainty in those cases. The 50-call outcome study does not reproduce full-codebook reliability or the paper’s separate 337-call sample.

## 13 Evaluation (90 seconds)

Explain turn dependence within calls. Paired resampling measures uncertainty in the difference rather than informally comparing two separate intervals. Call-ID splits can still share campaign templates, so they are not evidence of new-campaign generalization. Failures must remain visible and prediction files must cover requested IDs before scoring.

## 14 Forensic traceability (60 seconds)

Clarify the practical scope: hashes detect changes relative to a retained manifest but are not a signed tamper-proof chain of custody. Backend model revision can only be recorded if ASU returns one. Every evidence index is checked for existence; semantic evidence auditing remains a human task.

## 15 Pending experiment (60 seconds)

Replace this slide after the live run with an actual result table and model identifiers. Until then, say exactly what is implemented and what is unmeasured. API access is the external dependency. A valid draft should not contain invented improvement, token costs or latency figures.

## 16 Workload analysis (60 seconds)

Measure manual minutes, review minutes, setup and review fraction on representative calls. Include a random audit of unflagged calls to estimate missed-error risk. The source paper’s 115 hours describes audio duration, not measured annotation effort. If assisted labor exceeds manual labor, report the negative saving.

## 17 Limitations (90 seconds)

Connect each limitation to the claim it restricts. Avoid generalizing this dataset to all scams or treating model agreement as legal attribution. Label mismatch and qualification operationalization should be discussed explicitly. The final report needs errors and uncertainty alongside any eventual improvements.

## 18 Contributions and next steps (90 seconds)

Confirm actual member contributions before presenting them as completed work. This slide currently summarizes proposal assignments. End with the verified result: the offline comparator and auditable integration are available, while empirical improvement and practical labor savings remain open questions. The report is due December 7 and the presentation materials must precede the actual presentation date.

References: https://github.com/sefcom/calltrap-artifact ; https://mschloegel.me/paper/lyu2026scammers.pdf ; https://docs.aiml.asu.edu/endpoints/query
