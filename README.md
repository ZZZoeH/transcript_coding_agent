# Codebook-guided scam-call transcript coding

CSE 598/494 Forensics Computing project, Tech Girls. The project compares an evidence-grounded LLM coder with a deterministic baseline using the released [CallTrap artifact](https://github.com/sefcom/calltrap-artifact).

The baseline and offline checks run without an API key. The ASU agent is implemented and tested with mocked transport, but **live model results are pending API access**. The qualification study still needs two independent human coders. See [current status](docs/PROJECT_STATUS.md) and [the complete runbook](docs/RUNBOOK.md).

## Data and experiments

- 2,429 distinct calls; 1,941 coded and 488 uncoded.
- Existing frozen split: 1,358 development / 583 test calls. Do not regenerate it.
- Source transcripts and existing human sheets remain unchanged.
- Baseline category kappa: 0.538; subcategory kappa: 0.677.
- Lexical novelty has an unfavorable recall/false-positive tradeoff. Both experiments are preserved; see [methods](docs/METHODS.md). The calibrated test is exploratory.

## Offline verification

Python 3.10+; the research pipeline has no external Python dependencies.

```bash
python3 tests/test_pipeline.py
python3 -m unittest discover -s tests -p 'test_agent.py' -v
python3 -m coding.audit
python3 -m coding.baseline splits/test_ids.txt runs/baseline/test_predictions.json
python3 -m coding.validate runs/baseline/test_predictions.json splits/test_ids.txt
python3 -m coding.evaluate runs/baseline/test_predictions.json splits/test_ids.txt --extended
```

## Prepare the agent

```bash
python3 -m coding.agent splits/dev_ids.txt runs/novelty/reference_calibrated.json runs/dry_run/new --dry-run --limit 3
```

Dry runs save requests and make no API calls. When access is granted, use `.env.example` to configure `ASU_API_KEY`, `ASU_MODEL_PROVIDER`, and `ASU_MODEL_NAME` locally, then follow the development smoke test and final-run commands in [RUNBOOK.md](docs/RUNBOOK.md). Actual provider/model identifiers must come from the ASU project. Never commit the key.

## Components

| Module | Purpose |
|---|---|
| `agent.py`, `prompts.py`, `schema.py` | ASU structured coding, evidence contract, checkpoints and failure handling |
| `novelty.py`, `novelty_eval.py` | Frozen dev reference, calibration, novelty evaluation |
| `review.py`, `sensitivity.py` | Human review queue and conservative derived information tiers |
| `baseline.py`, `validate.py` | Deterministic comparator and schema/preservation checks |
| `evaluate.py`, `agreement.py`, `compare.py` | Agreement, call bootstrap and paired comparison |
| `audit.py`, `io_utils.py` | Read-only data audit, source hashes and run manifests |
| `qual_kit.py`, `qualification_eval.py` | Independent qualification coding and model scoring |
| `time_savings.py` | Labor scenarios from measured coding/review minutes |

Modules above live in `coding/`. `paper_system_implementation.py` is the original telephony implementation and is not used by this coding pipeline.

## Deliverables and remaining work

`deliverables/` contains editable report and presentation drafts and their sources. These are not final submissions. Integrate live agent results, independent human coding, measured time/costs and verified member contributions; verify the final report has at least 12 body pages in 12-point single spacing. The report is due December 7, 2026. The approximately 25-minute presentation is due before the actual presentation date. Each member must personally complete the integrity attachment.

Important interpretation details: released requested-information labels include qualification questions; organization names are redacted; the 337-call pairwise reliability set is not identifiable locally; and the paper's 115 hours is audio duration, not annotation labor. These limits are documented in the report and methods.
