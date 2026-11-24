# evaluate.py
# Scores a predictions file against the human codes.
#   python3 -m coding.evaluate runs/baseline/test_predictions.json splits/test_ids.txt

import json
import sys

from .agreement import bootstrap_ci, f1, kappa
from .io_utils import load_records, read_ids
from .labels import normalize_codes

CALL_FIELDS = ["category", "subcategory", "hook_phase.execution", "hook_phase.consent",
               "hook_phase.only_greeting_turns", "hook_phase.transfer.intent", "hook_phase.transfer.success"]
TURN_FIELDS = ["persuasion", "complementary_persuasion", "functional_states", "requested_info"]


def format_score(score):
    return "undefined" if score is None else f"{score:.3f}"


def get(call, path):
    # get(call, "hook_phase.consent") -> call["hook_phase"]["consent"]
    for key in path.split("."):
        call = call[key]
    return call


def call_kappa(field, ids, gold, pred):
    pairs = [(get(gold[c], field), get(pred[c], field)) for c in ids if get(gold[c], field) is not None]
    return kappa([g for g, _ in pairs], [p for _, p in pairs])


def turn_f1(field, ids, gold, pred):
    tp = fp = fn = 0
    for c in ids:
        guessed = {u["turn_index"]: set(u[field]) for u in pred[c]["caller_utterances"]}
        for u in gold[c]["caller_utterances"]:
            g, p = set(u[field]), guessed[u["turn_index"]]
            tp, fp, fn = tp + len(g & p), fp + len(p - g), fn + len(g - p)
    return f1(tp, fp, fn)[2]


def evaluate(pred_file, ids, extended=False):
    from .validate import validate
    errors = validate(pred_file, ids)
    if errors: raise ValueError("predictions must validate before scoring: " + "; ".join(errors[:5]))
    records = load_records()
    if any(normalize_codes(c, records[c]["codes"]) is None for c in ids):
        raise ValueError("all scored calls require human codes")
    gold = {c: normalize_codes(c, records[c]["codes"]) for c in ids}
    with open(pred_file) as f:
        pred = {p["call_id"]: p for p in json.load(f)["predictions"]}

    table = ["| field | score | 95% CI |", "|---|---|---|"]
    extra_call = ["hook_phase.exists", "hook_phase.caller_identification.name",
                  "hook_phase.caller_identification.organization", "hook_phase.transfer.failure_reason"] if extended else []
    for field in CALL_FIELDS + extra_call:
        score = call_kappa(field, ids, gold, pred)
        ci = bootstrap_ci(ids, lambda s: call_kappa(field, s, gold, pred))
        table.append(f"| {field} (kappa) | {format_score(score)} | {ci} |")
    for field in TURN_FIELDS:
        score = turn_f1(field, ids, gold, pred)
        ci = bootstrap_ci(ids, lambda s: turn_f1(field, s, gold, pred))
        table.append(f"| {field} (F1) | {format_score(score)} | {ci} |")
    if extended:
        def question_f1(sample):
            tp = fp = fn = 0
            for c in sample:
                g = set(gold[c]["hook_phase"]["qualification"]["question"])
                p = set(pred[c]["hook_phase"]["qualification"]["question"])
                tp += len(g & p); fp += len(p - g); fn += len(g - p)
            return f1(tp, fp, fn)[2]
        table.append(f"| hook_phase.qualification.question (F1) | {question_f1(ids):.3f} | {bootstrap_ci(ids, question_f1)} |")
    return "\n".join(table)


if __name__ == "__main__":
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions"); parser.add_argument("ids_file")
    parser.add_argument("--extended", action="store_true"); parser.add_argument("--output")
    args = parser.parse_args()
    table = evaluate(args.predictions, read_ids(args.ids_file), args.extended)
    if args.output: Path(args.output).write_text(table + "\n")
    print(table)
