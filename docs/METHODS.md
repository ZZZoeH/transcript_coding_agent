# Measurement and interpretation

## Questions

RQ1: Does codebook-guided LLM coding exceed the deterministic baseline on the existing held-out calls? Report all call-level kappa and turn-level micro-F1 fields, not just favorable scores. RQ2: Does model-assisted novelty detection catch a reference-withheld topic while controlling known-topic false positives? RQ3: Can independent coders consistently assign qualification outcomes? RQ4: Under measured manual/review times, how much labor does the assisted workflow require?

## Leakage boundaries

Call IDs were split before this session; the existing files remain authoritative. Reference construction uses only development IDs. Within development, 240 known-topic calls are reserved for threshold calibration, 1,018 fit the vocabulary/IDF/centroids, and 100 accident_claim calls are excluded. The model sees only call_id and conversation from source records. Gold codes and withheld-topic metadata never appear in requests. No few-shot examples are used, so the reliability sample cannot enter as examples. Label/topic reference vocabularies are restricted to fitting development calls. The public codebook still names example topics and the model may know them from pretraining; this is reference novelty, not unknown-to-the-model novelty.

The initial fixed-threshold test has been inspected; subsequent test results must be called exploratory, even though recalibration used only development data. No additional tuning should be justified by held-out accuracy. A future confirmatory result requires a fresh locked dataset or independently collected calls.

## Model contract and evidence

The gateway receives the full output JSON Schema. The local validator checks types, required fields, code vocabularies, exact caller-turn coverage, evidence paths and source indices, and basic transfer consistency. Nulls represent unavailable observations and cause review where material. The runner saves exact requests, raw response envelopes, validated predictions, failures, requested model, returned metadata and SHA-256 manifests. Artifact hashes detect changes relative to a saved manifest; they are not proof against an attacker who can replace both files and manifest.

Evidence pointers show where an annotation should be checked, not whether the interpretation is right. Low model uncertainty is not a calibrated probability. The initial review rule routes every explicit uncertainty, missing material observation, novelty flag and failed call to a human. This can create substantial workload, which must be measured. Audio accent/noise is explicitly not observable. Execution entity may be ambiguous from text and remains null when unsupported.

## Label alignment

The five category labels are preserved, but only three occur in development data. Requested information follows the released labels, which include qualification questions; this differs from the codebook prose. Persuasion uses auth/crc/dis/lsd/sp and complementary nag/time/dh; as documented in the artifact, nag/time also map into dis and dh into crc. Open requested-info/topic labels remain strings because the codebook uses open coding; out-of-reference topics cause novelty flags. Original identity names are redacted, so only disclosed/none is evaluated. Table 2 sensitivity mappings are derived and unscored without independent tier gold; labels absent from the table remain unmapped.

## Statistics

Call-level categorical agreement is Cohen's kappa. If both sides use only the same single category, kappa is undefined rather than artificially perfect. Turn multi-label performance uses pooled true/false positives/negatives to report micro-F1. Empty gold values are excluded only where the existing scoring contract treats them as missing; this is particularly relevant to failure reasons, which are scored conditionally on annotated nonmissing failures and do not measure detection of all possible failures. Source gold turns omitted by human annotators are not independently adjudicated here.

Every interval uses 1,000 bootstrap samples of whole calls, with seed 598. The paired system comparison resamples the same calls for both systems and reports agent minus baseline; turn resampling is avoided because turns in one conversation are dependent. Call-ID splits can still share campaign/template content across sets; they do not establish generalization to new campaigns. Rare-class and small-sample bootstrap intervals can be unstable or degenerate and should be read with raw counts.

## Novelty

Report withheld-topic recall, known-topic false-positive rate, naturally unseen-topic recall and total review rate. Known negatives are calls whose gold topic is in the fitted reference. Naturally unseen topics form a separate group. Reference-only detection is an interpretable lexical comparator; the complete agent adds inferred out-of-reference labels and unconfirmed literal candidates. Redaction prevents an empirical claim about original organization alias novelty. Report both threshold experiments and their chronology. The observed precision/recall tradeoff is a limitation, not evidence of solved novelty detection.

## Human qualification reliability

Use the retained three-class guide. It maps some insufficient-evidence cases to call_terminates, so that label does not always mean the transcript proves an actual hang-up. Explicit uncertainty preserves that distinction for model outputs. Report the guide as an operationalization, rather than a natural ground-truth outcome. Independent A/B agreement is distinct from agent-versus-adjudicated agreement. Neither establishes full-codebook human reliability or reproduces the paper's 337-call sample. Do not compute final agreement on fabricated or automatically filled human labels.

## Workload

Let N be calls, m manual minutes per call, r the review fraction, q the fraction of unflagged calls audited, h review minutes per call, and s setup minutes. Manual labor is Nm and assisted labor is s + N[r + (1-r)q]h. Savings fraction is 1 minus assisted/manual. Measure these inputs; present model wall time and API costs separately. Audio duration is not a substitute for coding effort. A low review rate is useful only if unflagged error risk is acceptably low.
