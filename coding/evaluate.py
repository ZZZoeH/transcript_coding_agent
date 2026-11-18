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


def evaluate(pred_file, ids):
    records = load_records()
    gold = {c: normalize_codes(c, records[c]["codes"]) for c in ids}
    with open(pred_file) as f:
        pred = {p["call_id"]: p for p in json.load(f)["predictions"]}

    table = ["| field | score | 95% CI |", "|---|---|---|"]
    for field in CALL_FIELDS:
        score = call_kappa(field, ids, gold, pred)
        ci = bootstrap_ci(ids, lambda s: call_kappa(field, s, gold, pred))
        table.append(f"| {field} (kappa) | {score:.3f} | {ci} |")
    for field in TURN_FIELDS:
        score = turn_f1(field, ids, gold, pred)
        ci = bootstrap_ci(ids, lambda s: turn_f1(field, s, gold, pred))
        table.append(f"| {field} (F1) | {score:.3f} | {ci} |")
    return "\n".join(table)


if __name__ == "__main__":
    print(evaluate(sys.argv[1], read_ids(sys.argv[2])))
