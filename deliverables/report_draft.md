# Codebook guided coding of scam call transcripts

Report draft for CSE 598/494 Forensics Computing. Tech Girls: Mansi Ganga Nayak, Ju-Won Hyun, Shuyi Huang, and Pin-Jun Liu. Submission date: December 7, 2026.

This draft describes the implemented system and completed offline experiments as of November 22, 2026. Live LLM evaluation, independent qualification coding, measured human effort, and final member contribution confirmations remain pending. It does not establish that the agent outperforms the baseline or can replace human coding. Complete the pending results, verify the final length of at least 12 body pages, and obtain genuine member signatures before submission.

## 1 Introduction

### 1.1 Motivation and research problem

Qualitative coding turns an unstructured conversation into a set of observations that can be compared across calls. In a scam-call setting, those observations include the apparent purpose of the call, whether the caller prescreens the recipient, what information the caller requests, and which persuasion techniques appear. The work requires more than finding isolated keywords. A question about insurance coverage can function as an eligibility check, a later request for information, or both under a particular annotation convention. A transfer proposal can occur without a successful transfer. These distinctions make coding an interesting test of structured language-model reasoning.

CallTrap provides the underlying research context and released redacted materials [1, 2]. Our project asks whether a codebook-guided agent can apply the existing coding framework with useful agreement, while exposing uncertainty and preserving an audit trail. We compare it with the deterministic baseline already present in the project repository. We treat human review as part of the workflow and measure the burden it creates rather than assuming every machine-generated label is trustworthy.

The proposal describes evolving aliases and free-form qualification answers as two central challenges. New topics may not appear in a fixed reference list, and new organization names may resemble familiar entities without being identical. Qualification answers introduce another difficulty: a recipient can contradict the caller's stated target profile, yet the caller may continue. A single extracted answer does not represent that exchange. We therefore combine novelty signals with a small operational outcome taxonomy for qualification.

### 1.2 Questions and success criteria

RQ1 asks whether the LLM agent improves held-out agreement over the deterministic baseline across call, hook and turn fields. RQ2 asks whether novelty signals detect a deliberately withheld topic while controlling false alarms on known topics. RQ3 asks whether two independent human coders can consistently apply the qualification-outcome guide and whether model outcomes agree with independently adjudicated labels. RQ4 asks how measured human labor changes when model output is checked through a review queue.

Structural success requires valid types and code vocabularies, one result for every caller turn, and evidence pointers into the unchanged source conversation. Empirical success additionally requires useful agreement and an acceptable workload. Passing the schema is necessary, but a structurally valid label can still be wrong. We report these forms of success separately. An abstention is retained as an unknown and may trigger review; it is not replaced with a baseline guess to improve reported completion.

### 1.3 Scope

The pipeline codes released transcript text. It does not generate transcripts, analyze audio, intervene in live calls, identify callers, or perform telephony operations. The original telephony implementation retained in the repository is background material rather than the program used for this experiment. Accent and background noise are explicitly not observable. Execution entity can also be uncertain from text, so the agent may leave it unknown rather than infer a human or bot from call length alone.

The report distinguishes implementation evidence from experimental outcomes. The current implementation and offline results can be inspected and reproduced without an API key. The requested ASU CreateAI access is still pending, so all LLM accuracy, model-assisted novelty and token-cost results remain unmeasured.

## 2 Our approach

### 2.1 Data and immutable source handling

A read-only audit finds 2,429 distinct call IDs across the five local transcript files. Of these calls, 1,941 have human category labels and 488 do not. The existing split contains 1,358 development calls and 583 test calls. No duplicate call IDs were found in this local release. The loader now rejects a duplicate ID if future input files introduce one, avoiding a silent last-record-wins choice that could conceal conflicting annotations.

Each call retains its original conversation, stable turn indices and speaker roles. The source role named user denotes the caller; assistant denotes the callee. These role names differ from how a model interprets its own system and user messages, so the request states the mapping explicitly. Both sides of a conversation are available as evidence, while the agent emits turn labels only for caller turns.

Source files are not rewritten during coding. A record fingerprint is SHA-256 over the call ID and canonical JSON serialization of its conversation. File-level SHA-256 values separately identify the exact input bytes. This distinction permits checking conversation preservation independently of formatting differences in JSON files. Every frozen test conversation matches the retained test hash. These checks detect changes relative to the recorded hashes, but do not by themselves provide an externally signed chain of custody.

### 2.2 Development and test boundaries

The existing split files remain unchanged. Test calls are never used as prompt examples, reference-fitting documents, or calibration examples. The current implementation uses no few-shot examples at all. The request builder allowlists only call_id and conversation from the source record; human codes and other source annotation fields are not transmitted. A targeted test verifies that sentinel gold labels and withheld-topic metadata do not reach the prompt.

For the calibrated topic reference, 100 development accident_claim calls are deliberately excluded. The remaining known-topic development calls are stratified by topic into 1,018 fitting calls and 240 disjoint calibration calls. Topics with fewer than five development examples remain in fitting rather than receiving an unreliable one-example calibration group. All vocabulary, inverse document frequency and topic vectors are estimated from fitting documents. The calibration group determines one threshold and does not contribute words or vector weights.

The earlier fixed-threshold detector was evaluated on the test set before this development-only recalibration. Consequently, we label the revised held-out results exploratory. Development-only threshold estimation does not erase prior test inspection. A future confirmatory claim would require a fresh locked evaluation set. This qualification also prevents repeated test-set tuning from being presented as a single untouched evaluation.

### 2.3 Coding contract and label alignment

The model contract includes category, subcategory, hook fields, caller-utterance labels, evidence, uncertainty, qualification outcome, and novelty candidates. Category and the established persuasion and functional-state fields use finite vocabularies. Topic and requested-information values remain open strings because the supplied material contains open coding and does not provide a complete closed taxonomy. The structure itself remains fixed.

The proposal and codebook prose exclude qualification questions from requested information. The released annotation objects include labels such as age and possession_medicare in that field. Our primary comparison follows the released annotation convention and states that choice in the system prompt. This makes the main score interpretable as agreement with released labels. A future analysis using the narrower codebook definition would need separately adjudicated ground truth rather than silently deleting inconvenient human labels.

The artifact documents five original persuasion labels and three complementary labels [2]. Our representation preserves auth, crc, dis, lsd and sp, alongside nag, time and dh. It follows the artifact's compatibility mapping: nag and time also appear under dis, while dh maps under crc. Identity fields record disclosed or none; a redacted disclosure still counts as disclosed. Original names cannot be reconstructed from the released text.

Requested-information sensitivity tiers are derived conservatively from appendix Table 2. For example, name and zip_code map to T1, address and dob to T2, and ssn or bank_account_number to T3. Labels outside the explicit table mapping remain unmapped. The system does not assign a sensitive tier merely because a qualification label sounds related. These derived tiers are not independently scored in the absence of comparable tier annotations.

### 2.4 Deterministic baseline

The retained baseline applies phrase dictionaries and regular expressions to caller text. It identifies topic keyword hits, assigns categories through topic rules, detects questions, searches for transfer phrases and codes persuasion and functional states. Its decisions are deterministic and require no network access. We preserve its existing rules so the comparison remains tied to the baseline already reported in the repository.

The baseline exposes important limitations that motivate the agent. Its default category can be telemarketing when a topic has no special mapping. It approximates execution using surface patterns and caller-turn counts. Continued speech after a transfer proposal is treated as evidence of transfer success, although subsequent speech can also be a failed transfer or a repeated pitch. Its vocabulary cannot express every open information label in the data.

These limitations do not invalidate the comparator. They establish what a lightweight, inspectable system achieves before adding an LLM. The baseline's call and turn outputs pass the structural validator, and its test scores can be reproduced. Its evidence output predates the complete agent contract, so it is evaluated under the legacy structural contract rather than falsely described as supplying full field-level evidence.

### 2.5 Structured model coding through ASU

The new runner uses the native ASU CreateAI query interface with a nested JSON Schema response contract [3]. The project identifier is configured, while the approved provider and model identifiers must be taken from the granted project access. The authenticated project settings were not available during this session, and no model or backend revision is assumed.

A request contains the codebook, the qualification guide, development-derived reference vocabularies, and the unchanged conversation. Search, conversation history, prompt date/time enhancement and semantic caching are disabled for the requested experiment. Temperature is set to zero; this reduces one source of variation but does not promise byte-identical outputs. The exact prompt, schema, model request and returned provider metadata are saved for each call.

The system message treats transcript text as untrusted evidence. Instructions spoken by a caller or callee must not control the agent. The runner provides no tool-execution loop or call-intervention capability. The API token is read from the environment and is absent from saved requests and manifests. HTTP redirects are rejected rather than forwarding credentials to an unexpected endpoint.

Each raw response is preserved before parsing. A valid response must fit the model contract and pass deterministic semantic checks. Invalid or missing results become explicit failures; there is no silent baseline fallback. Selected transient HTTP errors receive bounded retries, while timeouts fail for explicit investigation or resume. Successful calls can be reused only when the run's source, input, reference and configuration fingerprints match.

### 2.6 Evidence and uncertainty

Every nonempty coded leaf field must have an evidence entry naming the field and source turn indices. A turn label must cite its own caller turn. Call-level findings can cite several turns, including context on the callee side. Absence findings can cite the inspected turns; an empty multi-label list does not require fabricated evidence. Qualification outcomes also require evidence when a non-null class is emitted.

Validation checks field types, vocabularies, exact caller-turn order and coverage, duplicate labels, existing evidence indices, valid evidence paths, plausible greeting counts and basic transfer consistency. For example, no transfer intent requires unknown success and failure reason; a successful transfer cannot simultaneously have a failure reason. These rules catch internal contradictions without pretending to settle all interpretive disputes.

The review rule combines model-reported uncertainty with deterministic missing-observation checks, novelty flags and failures. Unknown category, topic, execution or other material hook observations cannot silently appear confident just because the model omitted an uncertainty entry. Audio observability is retained separately and never converted into invented accent or background-noise codes.

Evidence pointers make a decision easier to inspect, but do not prove that the cited text supports it. Likewise, the absence of an uncertainty flag is not a calibrated error probability. We therefore reserve a workload analysis and an audit of unflagged calls for the final experiment. Human review edits should remain separate from original model output and original human gold.

### 2.7 Frozen novelty reference

The reference-only detector tokenizes caller text, removes a fixed list of common conversational terms, estimates inverse document frequency from development fitting calls, and retains 80 weighted terms per known topic. At inference it computes similarity against each topic vector and flags calls below the frozen threshold. The initial threshold was 0.25. The revised threshold is the fifth percentile of similarities among known-topic development calibration calls, approximately 0.066026.

The complete agent mechanism additionally flags inferred topics outside the reference and unconfirmed candidate terms extracted by the model. Candidate organizations must be literal unredacted text in cited evidence, and redaction markers are not aliases. Candidates enter a review queue; they do not automatically modify the reference during a frozen evaluation run. A subsequent human-approved reference would constitute a new experiment version.

Withholding accident_claim from this reference tests whether the mechanism reacts to a topic omitted from the development reference. It does not make accident-related concepts unknown to a pretrained model. The public codebook itself contains topic examples. The experiment therefore measures reference novelty rather than open-world discovery of an entirely unknown concept. Organization-level novelty cannot be established for names that were removed from the public release.

### 2.8 Qualification outcomes

The retained coding guide defines matches_profile, mismatch_call_continues and call_terminates. Coders focus on the final qualification exchange before the first transfer and interpret answers in the surrounding context. The guide has explicit rules for unstated criteria, truncated exchanges and obvious transcription errors. The same guide is sent to the model.

The third outcome needs careful interpretation: some insufficient-evidence cases are operationally placed in call_terminates. That class therefore does not always prove a real-world hang-up. Model uncertainty should identify such ambiguity. If no qualification exchange exists, the model can return an unknown outcome rather than invent an exchange.

The prepared study consists of a 50-call packet and two blank independent coding sheets. Two members must complete their own sheet without seeing the model's labels or the other coder's answers. A third person adjudicates disagreements blind to model predictions and records a separate final sheet. Model-versus-adjudicated agreement is then distinct from human-versus-human reliability. The existing sample only covers qualification outcomes; it does not establish reliability of the entire codebook.

### 2.9 Evaluation and resampling

Call-level nominal outcomes are evaluated using Cohen's kappa. Turn-level multi-label outputs use micro-F1 from pooled true positives, false positives and false negatives. An extended table additionally covers hook existence, identity disclosure, transfer failure reason and the set of qualification questions. Unknown or unannotated gold values are handled under the established scoring contract; the report identifies conditional metrics such as failure reason rather than treating them as unconditional detection performance.

Confidence intervals use 1,000 bootstrap samples of whole calls with seed 598. Resampling individual turns would ignore within-call dependence. The paired system comparison resamples the same call IDs for both systems and computes agent minus baseline. If both label vectors contain only the same one class, kappa is undefined, rather than automatically perfect. Rare fields and small samples can still produce unstable or degenerate intervals.

Novelty evaluation reports withheld-topic recall, known-topic false-positive rate, naturally unseen-topic recall and review counts. It does not merge topics absent from development into the known negative class. A model prediction file must cover the requested calls exactly; failures cannot be dropped from the denominator without being reported. Qualification scoring similarly counts model abstentions as disagreement instead of excluding difficult calls.

## 3 Results and implementation details

### 3.1 Audit and verification

The data audit completed with no split overlap, duplicate call IDs, missing coverage or frozen test hash mismatch. The existing self-checks pass after validation changes. Thirteen additional offline tests cover schema and evidence checks, source preservation, withheld-document exclusion, prompt allowlisting, false/unknown types, malformed provider responses, review routing, undefined agreement, workload arithmetic, mocked live transport, checkpoint resume and modified-artifact rejection. These tests establish software behavior under checked cases; they do not establish actual model accuracy.

A no-network dry run emits request artifacts for development calls without requiring a key and without creating fake predictions. The real ASU interface remains untested until access is granted. In particular, the approved model ID, native schema support, actual response metadata and maximum practical output length require a small development smoke test before running all held-out calls.

The audit also identifies limits of the available data. Only telemarketing, vishing_gov and vishing_co occur in development labels. The five-category contract can represent nuisance and others, but performance on them cannot be inferred from this release. Each coded call has one annotation object. The local files do not identify the separate 337-call two-coder reliability sample described in the paper [1]. We therefore do not label the current 583-call test set as that reliability subset.

### 3.2 Reproduced baseline results

The following results use the unchanged 583-call test split. Confidence intervals resample calls. The first eleven metrics reproduce the repository's existing table. The extended table supplies fields that were previously absent from the summary.

| Field | Metric | Score | 95 percent interval |
|---|---|---|---|
| Category | Kappa | 0.538 | 0.442 to 0.619 |
| Subcategory | Kappa | 0.677 | 0.640 to 0.717 |
| Execution | Kappa | 0.385 | 0.315 to 0.455 |
| Consent | Kappa | 0.364 | 0.204 to 0.514 |
| Greeting count | Kappa | 0.431 | 0.370 to 0.490 |
| Transfer intent | Kappa | 0.727 | 0.672 to 0.779 |
| Transfer success | Kappa | 0.323 | 0.244 to 0.405 |
| Persuasion | Micro F1 | 0.549 | 0.526 to 0.573 |
| Complementary persuasion | Micro F1 | 0.603 | 0.568 to 0.638 |
| Functional states | Micro F1 | 0.567 | 0.539 to 0.592 |
| Requested information | Micro F1 | 0.564 | 0.532 to 0.597 |

The strongest listed call-level baseline agreement is transfer intent, while transfer success is substantially weaker. This is consistent with a system that recognizes transfer-related phrases more easily than the actual outcome of a handoff. That interpretation is a hypothesis about the rule design; a systematic error audit is still needed before attributing all errors to a single cause.

The extended results give hook-existence kappa 0.000, name-disclosure kappa 0.537, organization-disclosure kappa 0.446, annotated failure-reason kappa 0.000 and qualification-question micro-F1 0.639. A zero kappa is not the same as zero raw accuracy. Failure-reason scoring is restricted to nonmissing human failure reasons and should be described as conditional agreement, not full transfer-failure detection.

### 3.3 Novelty results and tradeoff

The initial reference-only detector catches most deliberately withheld calls, but flags many known calls. Development-only calibration substantially reduces false positives and simultaneously loses most withheld-topic recall. Both observations must be retained.

| Reference detector | Withheld calls flagged | Known calls flagged | Naturally unseen calls flagged |
|---|---|---|---|
| Initial threshold 0.25 | 28 of 30 | 409 of 545 | 6 of 8 |
| Development calibrated threshold | 2 of 30 | 21 of 545 | 0 of 8 |

For the initial detector, withheld recall is 93.3 percent with bootstrap interval 83.3 to 100 percent, but the known-topic false-positive rate is 75.0 percent with interval 71.2 to 78.7 percent. It flags 443 of all 583 test calls. That operating point is unsuitable as evidence of reduced review labor, because most known-topic calls still require checking.

For the calibrated detector, withheld recall is 6.7 percent with interval 0 to 16.7 percent, while the known-topic false-positive rate is 3.9 percent with interval 2.2 to 5.5 percent. It flags 23 calls overall. The smaller queue comes with many missed withheld calls. A zero observed rate on eight naturally unseen calls does not establish a true zero detection probability; the sample is very small and its bootstrap interval is degenerate.

These results show a limitation of the lexical reference comparator. They do not establish the performance of the complete model-assisted mechanism, whose inferred out-of-reference topics may supply additional information. That mechanism still requires live testing. Since the initial test output was inspected before recalibration, the revised result remains exploratory and should not be described as a pristine confirmatory estimate.

### 3.4 Pending LLM comparison

PENDING EXPERIMENT: confirm the approved ASU model/provider identifiers, perform a development-only smoke test and freeze the code/prompt/reference configuration. Then run the agent on all 583 held-out calls and validate with the strict evidence contract. Preserve failures and report completion rates before comparing accuracy.

Insert a table containing baseline score, agent score, paired difference and paired 95 percent interval for every primary field. Report model-requested identifiers, available provider revision metadata, prompt/schema versions, total calls, failed calls, schema-valid rate and turn-complete rate. Averages alone should not conceal unsupported evidence, ambiguous execution decisions or missed transfer failures.

Select examples for qualitative error analysis under a declared procedure. Useful groups include disagreements with the baseline, high-impact requested-information errors, unflagged errors and cases routed to review. Preserve the original transcript and show both the relevant evidence span and the disputed label. If manual inspection changes gold labels, keep original labels and a blind adjudication record, then distinguish the original and revised evaluations.

### 3.5 Pending qualification and workload studies

PENDING HUMAN STUDY: both 50-call sheets are blank. Report completed call counts, class distributions, disagreements, human-human kappa and its interval only after genuine independent coding. After blind adjudication, report model-versus-adjudicated kappa, accuracy and abstentions on the same sample. No current result supports the claim that the qualification classifier matches human reliability.

PENDING TIME STUDY: record representative manual coding minutes per call and review minutes per flagged call, including setup effort. Also audit a random sample of unflagged calls. Report the sampling procedure and call-duration groups so short-call timing does not stand in for all calls. Keep model wall time and API token costs separate from human labor.

The source paper's approximately 115 hours refers to conversation audio, rather than a measured annotation labor budget [1]. We therefore do not divide that duration by a model runtime and call it labor savings. The implemented workload calculator requires explicit measured inputs. If the review burden is large, the assisted workflow can save little or even require more time; that would be a valid result to report.

## 4 Discussion and conclusion

### 4.1 Contributions supported by current evidence

The current software contributes a transcript-preserving path from a source call to structured codes, evidence references, uncertainty and a review request. It gives the project an executable ASU integration boundary, a versioned model contract and a way to retain invalid responses rather than concealing failures. The same original conversations support both the deterministic baseline and the future model comparison.

A second contribution is an explicit measurement boundary around novelty. The reference excludes a known topic and uses development-only fitting and calibration. The evaluation distinguishes withheld calls, known-topic negatives and naturally unseen topics. The unfavorable lexical results prevent a high-recall claim from being presented without its false-positive cost.

A third contribution is evaluation bookkeeping: immutable source hashes, source/configuration fingerprints, whole-call bootstrap intervals, paired system differences and separate human-versus-human and model-versus-adjudicated qualification analyses. These measures make the final claims easier to audit, even though they do not guarantee semantic correctness or exact model reproducibility.

### 4.2 Limitations and threats to validity

The main empirical limitation is the absence of a live model run. Local schema and mocked-transport tests cannot establish compatibility with the granted backend, token budget, inference accuracy or actual cost. The final report must replace the pending sections with measured results or explicitly conclude that only the offline minimum system was completed.

The released data is redacted and narrower than the original study's full set of call types. Organization aliases and acoustic evidence are unavailable. Calls split by ID can still belong to the same campaign or share scripts, so this evaluation does not establish new-campaign or future-period generalization. Some classes are rare, making aggregate metrics and intervals insufficient by themselves.

The codebook and released labels do not fully align on qualification-related information requests. Our stated dataset-compatible contract is one defensible evaluation choice, but does not erase the conceptual mismatch. The three-class qualification guide also combines certain unknown and terminated cases. Both decisions limit direct interpretation of agreement as agreement with an unambiguous real-world event.

The paper's reported coder reliability is contextual evidence, not a target that can be reproduced by comparing different fields on different calls. The local release has no identified pairwise 337-call sample. Team double coding of qualification outcomes remains necessary and cannot substitute for full-codebook reliability. Actual contributions and study actions must be confirmed by members before they are described as completed work.

### 4.3 Human review and practical use

The initial review policy is deliberately explicit: uncertain fields, missing material observations, novelty and failures require attention. It may route many calls to review, particularly where execution is not text-observable. The system should therefore be judged jointly on retained accuracy, missed-error risk and labor. An automatic output should not be treated as final forensic interpretation simply because it is valid JSON.

Reviewers need the call ID, input hash, uncertainty reason, candidate terms and original evidence turns. The queue exporter supplies an editable record of review status, time, reviewer and notes. Original predictions and human gold remain separate. Candidate aliases enter a new reference only after confirmation and versioning, which permits evaluating a frozen reference without silently changing the target mid-run.

### 4.4 Reproducibility and AI assistance

The repository includes commands to reproduce the offline audit, baseline, novelty experiments, validation and dry-run requests. The ASU configuration template contains no key. Run manifests identify exact local input and artifact hashes alongside requested model settings. Provider-side model changes may still affect future outputs if no immutable backend revision is exposed.

AI assistance was used in this working session to inspect documents, draft code and tests, identify measurement issues and prepare report/presentation drafts. The team must review and validate the generated work and describe that assistance accurately under the course's applicable expectations. This draft does not certify that any member has read, signed or approved the final submission.

### 4.5 Current conclusion

The offline minimum system is reproducible and the project now has the main integration and evaluation components needed for a codebook-guided agent. The baseline supplies a measurable comparator. The lexical novelty experiments demonstrate a substantial recall/false-positive tradeoff rather than a solved detection problem. Evidence for improved LLM coding, reliable model-assisted novelty, human qualification agreement and labor savings remains pending. The final conclusion should follow those experiments, including unfavorable outcomes if they persist.

## 5 Contributions by member

The following assignments come from the proposal. They are not a certification that each task was personally completed by the named member. Before submission, replace this table with specific verified contributions, including relevant code, experiments, annotation work and writing. Confirm shared work with the team.

| Member | Proposal assignment | Completion record to confirm |
|---|---|---|
| Mansi Ganga Nayak | Data/schema, evaluation harness, independent qualification coding | Specific files, experiments and annotation work pending confirmation |
| Ju-Won Hyun | Baseline, validation, independent qualification coding, resampling | Specific files, experiments and annotation work pending confirmation |
| Shuyi Huang | Structured LLM coding, prompts, turn-level fields | Specific files, development runs and writing pending confirmation |
| Pin-Jun Liu | Novelty reference, uncertainty, review queue, withheld-topic evaluation | Review this session's code and results; confirm personally completed work |

All members share the planned evaluation, time analysis, report and presentation work. Preserve the distinction between authorship, reviewing AI-generated implementation and independent human annotation. Record actual effort and decisions while completing the remaining experiments so the final contribution section is specific and accurate.

## 6 References

[1] Zhuoer Lyu et al. 2026. When Scammers Talk Back: Understanding Potentially Unwanted Calls via LLM-Based Interaction. ACM CCS 2026. DOI: 10.1145/3830454.3846770. https://mschloegel.me/paper/lyu2026scammers.pdf

[2] SEFCOM. CallTrap Artifact. Released dataset, codebook, appendix and artifact documentation. https://github.com/sefcom/calltrap-artifact

[3] Arizona State University. CreateAI Query API Documentation. Native query parameters, structured output and response envelope. Accessed November 22, 2026. https://docs.aiml.asu.edu/endpoints/query

[4] Tech Girls. Group Project Proposal. Codebook-Guided Agent for Scam-Call Transcript Coding. October 9, 2026. Course project document supplied by the team.

[5] CSE 598/494 Forensics Computing. Group Project Requirements. Course requirements and academic integrity attachment supplied by the user.

[6] Tech Girls. transcript_coding_agent. Project source, frozen split, baseline results and experiment artifacts. https://github.com/ZZZoeH/transcript_coding_agent . This draft describes local uncommitted implementation additions; the remote repository is not assumed to contain them.
