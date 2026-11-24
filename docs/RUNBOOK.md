# Running and completing the project

Run commands from the repository root. The research pipeline uses Python 3.10+ standard-library modules; no pip install is needed. `paper_system_implementation.py` is the original telephony system and is unrelated to this transcript coding experiment.

## Reproduce offline checks

```bash
python3 tests/test_pipeline.py
python3 -m unittest discover -s tests -p 'test_agent.py' -v
python3 -m coding.audit --output runs/audit/dataset_audit.json
python3 -m coding.baseline splits/test_ids.txt runs/baseline/test_predictions.json
python3 -m coding.validate runs/baseline/test_predictions.json splits/test_ids.txt
python3 -m coding.evaluate runs/baseline/test_predictions.json splits/test_ids.txt --extended
```

Do not regenerate `splits/` or overwrite the qualification packet. Data, ID files, and human coding sheets are preserved. Validation exits nonzero on malformed output and scoring refuses incomplete predictions. The loader rejects duplicate call IDs instead of choosing an annotation automatically.

## Frozen novelty experiment

The existing `runs/novelty/reference_calibrated.json` is the current reference. It withholds `accident_claim` calls, uses 1,018 development calls for topic vectors and 240 disjoint development calls for threshold calibration, and excludes 100 development calls from the withheld topic. Its 44 topic centroids and IDF never use test transcripts. The threshold is the fifth percentile of similarities for known-topic calibration calls. It is fixed during inference. No human-confirmed aliases are added during an evaluation run.

The earlier `reference.json` and `test_results.json` retain the initial fixed-threshold experiment. `test_results_calibrated.json` retains the revised experiment. Because the initial test results were inspected before development-only recalibration, the revised test experiment is exploratory. Do not tune again against this test set and call it a fresh confirmatory result.

To score the current detector again, use a new output path:

```bash
python3 -m coding.novelty_eval runs/novelty/reference_calibrated.json splits/test_ids.txt runs/novelty/reproduction.json
```

Reference-only detection is a weak lexical comparator. It is not the complete LLM novelty mechanism. The agent also flags inferred topics absent from the reference and literal unconfirmed topic/organization candidates. Evaluate both variants separately. Withholding a topic from a reference does not remove that topic from a model's pretraining or the public codebook.

## Prepare the ASU connection

The user's project is `ecc2a166ce994c6280373e494d39aa28`. API access is still pending. We could not inspect the authenticated CreateAI project, so its allowed provider/model IDs are not assumed.

Copy `.env.example` to a local `.env` and fill in the granted key and the exact provider/model identifiers shown in CreateAI. Then load it in the current shell:

```bash
source .env
```

`.env` is ignored by Git. The runner reads `ASU_API_KEY` from the environment, never includes it in saved requests or manifests, and does not follow HTTP redirects. It uses the native ASU `/query` API and nested `model_params.response_format` JSON Schema contract documented at https://docs.aiml.asu.edu/endpoints/query.md. No SDK dependency is needed. Confirm actual model/schema support with a small development smoke test once access is granted.

## Dry run with no key or network calls

```bash
python3 -m coding.agent splits/dev_ids.txt runs/novelty/reference_calibrated.json runs/dry_run/new --dry-run --limit 3
```

Inspect `calls/*/request.json` to confirm the caller/callee roles, codebook and schema. Source `codes` objects, held-out labels, withheld-topic metadata, credentials and reliability sample examples are never sent. Dry-run requests have no model predictions and cannot be scored as LLM results.

## Development smoke test and final test run

```bash
python3 -m coding.agent runs/audit/dev_smoke_ids.txt runs/novelty/reference_calibrated.json runs/agent/dev_smoke
```

The supplied smoke ID list selects one development call from each of six duration buckets, including long transcripts, to expose context/output limits. Use development calls only for model/schema compatibility checks and any prompt changes. The schema requires every caller turn and evidence for every nonempty coded field. Missing/invalid responses become failures and review requests; the runner never substitutes baseline predictions for failed model calls. No automatic semantic repair is attempted. HTTP 429/selected 5xx responses receive bounded retries; a timeout fails the call for explicit retry, since another request may incur another charge.

Once the prompt and model are frozen:

```bash
python3 -m coding.agent splits/test_ids.txt runs/novelty/reference_calibrated.json runs/agent/test
python3 -m coding.validate runs/agent/test/predictions.json splits/test_ids.txt --strict
python3 -m coding.evaluate runs/agent/test/predictions.json splits/test_ids.txt --extended --output runs/agent/test/scores.md
python3 -m coding.compare runs/baseline/test_predictions.json runs/agent/test/predictions.json splits/test_ids.txt runs/agent/test/comparison.json
python3 -m coding.novelty_eval runs/novelty/reference_calibrated.json splits/test_ids.txt runs/agent/test/novelty.json --predictions runs/agent/test/predictions.json
python3 -m coding.review runs/agent/test/predictions.json runs/agent/test/review_queue.csv --failures runs/agent/test/failures.json
```

Use `--resume` with exactly the original run arguments to reuse successful calls and retry failures. Source code, data, IDs, reference and config hashes must match. After any code/prompt/model change, start a new run directory. Checkpoints and raw model responses are retained; invalid model responses are never counted as successful predictions. If the process is interrupted, resolve failures before evaluation: missing calls cannot be silently omitted. Manifests identify the requested model and provider-returned metadata; an immutable backend model revision can only be reported if ASU supplies one. A temperature of zero does not guarantee bit-identical reruns.

## Human qualification study

Two people independently complete `qual_sample/sheet_A.csv` and `sheet_B.csv`, following the existing `coding_guide.md` and reading `packet.md`. Both sheets currently contain 50 blank outcomes. Preserve independence: do not show model results or the other coder's labels while coding.

```bash
python3 -m coding.qual_kit compare qual_sample/sheet_A.csv qual_sample/sheet_B.csv
```

A third coder resolves disagreements blind to model predictions and records final outcomes in a separate `qual_sample/adjudicated.csv` with `call_id,outcome` columns. Do not invent an adjudicated sheet or replace original entries.

```bash
python3 -m coding.qualification_eval runs/agent/test/predictions.json qual_sample/adjudicated.csv runs/agent/test/qualification_scores.json
```

The provided 50-call study covers qualification outcomes. It does not reproduce full-codebook reliability or the paper's separate 337-call coder-pair sample. The local release has one annotation object per coded call and no identifiable pairwise reliability set. A full-codebook team double-coding study would require additional independent annotation, recorded separately.

## Workload and cost

Measure manual minutes per call and review minutes per flagged call on a representative blinded sample; record call duration groups, coder, and elapsed time. Record model wall time, token usage and provider costs separately. Report review rate and audit a random sample of unflagged calls to estimate missed errors. Use measured numbers in:

```bash
python3 -m coding.time_savings --calls 583 --manual-minutes MANUAL --review-minutes REVIEW --review-rate FLAGGED_FRACTION --setup-minutes SETUP --audit-rate AUDIT_FRACTION
```

The names in capitals are placeholders for actual measurements. The paper's 115 hours is audio duration and must not be treated as measured annotation labor. Negative savings are possible and must be reported.

## Final submission

The editable report and slides are drafts. Replace pending LLM results and human study fields with verified outputs; check member contribution statements with the team; each member fills their own integrity details/signature. Re-render and check the final report: at least 12 body pages excluding cover/integrity, 12-point font, single spacing, due December 7, 2026. Rehearse the presentation for approximately 25 minutes and submit materials before the actual presentation date. Source generation scripts and references accompany the drafts.
