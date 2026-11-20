# validate.py
# Checks a predictions file before we score it.
#   python3 -m coding.validate runs/baseline/test_predictions.json splits/test_ids.txt

import json
import sys

from .io_utils import load_records, read_ids, record_hash
from .labels import CATEGORIES, EXECUTION, PERSUASION, COMP_PERSUASION, FUNCTIONAL, YES_NO


def check_call(pred, record):
    errors = []
    hook = pred["hook_phase"]

    # 1. we must have coded the original transcript (not an edited one)
    if pred["input_hash"] != record_hash(record):
        errors.append("transcript was changed")

    # 2. labels must be from the codebook
    if pred["category"] not in CATEGORIES + [None]:
        errors.append("bad category")
    if hook["execution"] not in EXECUTION + [None]:
        errors.append("bad execution")
    for name in ["exists", "consent"]:
        if hook[name] not in YES_NO + [None]:
            errors.append("bad " + name)

    # 3. one coded entry for every caller turn, in order
    caller_turns = [t["turn_index"] for t in record["conversation"] if t["role"] == "user"]
    coded_turns = [u["turn_index"] for u in pred["caller_utterances"]]
    if coded_turns != caller_turns:
        errors.append("turns do not match")

    for u in pred["caller_utterances"]:
        if not set(u["persuasion"]) <= set(PERSUASION):
            errors.append(f"bad persuasion in turn {u['turn_index']}")
        if not set(u["complementary_persuasion"]) <= set(COMP_PERSUASION):
            errors.append(f"bad complementary persuasion in turn {u['turn_index']}")
        if not set(u["functional_states"]) <= set(FUNCTIONAL):
            errors.append(f"bad functional state in turn {u['turn_index']}")
    return errors


def validate(pred_file, ids):
    records = load_records()
    with open(pred_file) as f:
        preds = json.load(f)["predictions"]

    errors = []
    for pred in preds:
        try:
            errors += [pred["call_id"] + ": " + e for e in check_call(pred, records[pred["call_id"]])]
        except KeyError as e:
            errors.append(f"{pred.get('call_id')}: missing {e}")

    # 4. every requested call has exactly one prediction
    coded = [p.get("call_id") for p in preds]
    if sorted(coded) != sorted(ids):
        errors.append("predicted calls do not match the id list")
    return errors


if __name__ == "__main__":
    errors = validate(sys.argv[1], read_ids(sys.argv[2]))
    for e in errors[:20]:
        print("ERROR", e)
    print(f"{len(errors)} errors")
