# transcript_coding_agent

the original paper's materials are available at https://github.com/sefcom/calltrap-artifact.

CSE 598/494 Forensics Computing group project (Tech Girls).
Can an LLM agent apply the CallTrap codebook to scam-call transcripts reliably enough
to replace most of the manual coding?

The original paper's materials are available at https://github.com/sefcom/calltrap-artifact.

## Folders

| path | what it is |
|---|---|
| `transcript_inputs/` | 2,429 calls. input1 has no human codes; input2-5 (1,941 calls) are coded |
| `codebook.txt`, `appendix.pdf` | CallTrap codebook and paper appendix |
| `coding/` | our pipeline code (see below) |
| `splits/` | frozen dev (1,358) / test (583) split by call_id |
| `runs/baseline/` | baseline scores and run manifest (file hashes) |
| `qual_sample/` | 50-call qualification-outcome hand-coding sample |
| `tests/` | self-check tests |

## Pipeline (`coding/`)

| file | job |
|---|---|
| `labels.py` | cleans the human labels into one format (fixes are logged, data is never changed) |
| `io_utils.py` | loads transcripts, sha256 hashes, run manifests |
| `split.py` | makes the dev/test split (already run, do not re-run) |
| `validate.py` | checks a predictions file: format, codebook labels, every caller turn, transcript hash |
| `baseline.py` | rule-based baseline (keyword lists, no API key) |
| `agreement.py` | Cohen's kappa, F1, call-level bootstrap 95% CI |
| `evaluate.py` | scores a predictions file against the human codes |
| `qual_kit.py` | makes the 50-call sample and computes kappa between two coders |

## How to run

```bash
python3 tests/test_pipeline.py
python3 -m coding.baseline splits/test_ids.txt runs/baseline/test_predictions.json
python3 -m coding.validate runs/baseline/test_predictions.json splits/test_ids.txt
python3 -m coding.evaluate runs/baseline/test_predictions.json splits/test_ids.txt
```

**For the LLM agent:** write predictions in the same format as `baseline.py` output
(fields listed in `validate.py`), then run `validate` and `evaluate` the same way.
Tune prompts and pick few-shot examples from `splits/dev_ids.txt` only.

## Baseline results (test split, 583 calls)

| field | score | 95% CI |
|---|---|---|
| category (kappa) | 0.538 | [0.442, 0.619] |
| subcategory (kappa) | 0.677 | [0.640, 0.717] |
| execution (kappa) | 0.385 | [0.315, 0.455] |
| transfer intent (kappa) | 0.727 | [0.672, 0.779] |
| persuasion (F1) | 0.549 | [0.526, 0.573] |
| functional states (F1) | 0.567 | [0.539, 0.592] |
| requested info (F1) | 0.564 | [0.532, 0.597] |

Full table: `runs/baseline/test_scores.md`. The LLM agent should beat these numbers.

## Notes from the data

- `requested_info` in the human codes **includes** qualification questions (age, possession_medicare, ...).
- Complementary persuasion labels in the data are `nag` / `time` / `dh` (= NG / TIME /
