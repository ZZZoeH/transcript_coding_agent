"""Validate legacy/baseline predictions or the full evidence-grounded agent contract."""
import argparse
import json
from pathlib import Path
from .io_utils import ROOT, load_records, read_ids, record_hash
from .schema import PREDICTION_SCHEMA, SCHEMA, check_model_output, schema_errors


def check_call(pred, record, strict=False):
    if not isinstance(pred, dict): return ["prediction must be an object"]
    core = {k: pred[k] for k in PREDICTION_SCHEMA["properties"] if k in pred}
    errors = schema_errors(core, PREDICTION_SCHEMA)
    if errors: return errors
    if pred["call_id"] != record["call_id"]: errors.append("call_id does not match source")
    if pred["input_hash"] != record_hash(record): errors.append("transcript was changed")
    caller_turns = [t["turn_index"] for t in record["conversation"] if t["role"] == "user"]
    coded_turns = [t["turn_index"] for t in pred["caller_utterances"]]
    if coded_turns != caller_turns: errors.append("turns do not match")
    if strict:
        model = {k: pred[k] for k in SCHEMA["properties"] if k in pred}
        errors += check_model_output(model, record)
    return errors


def validate(pred_file, ids, strict=False):
    if not ids or len(ids) != len(set(ids)): return ["requested IDs must be nonempty and unique"]
    records = load_records()
    try:
        data = json.loads(Path(pred_file).read_text()); preds = data["predictions"]
    except (ValueError, KeyError, OSError, TypeError) as e: return ["cannot read predictions: " + str(e)]
    if not isinstance(preds, list): return ["predictions must be an array"]
    errors, coded = [], []
    for pred in preds:
        if not isinstance(pred, dict): errors.append("prediction must be an object"); continue
        c = pred.get("call_id")
        if not isinstance(c, str): errors.append("missing or invalid call_id"); continue
        coded.append(c)
        if c not in records: errors.append(c + ": unknown call_id"); continue
        errors += [c + ": " + e for e in check_call(pred, records[c], strict)]
    if sorted(coded) != sorted(ids): errors.append("predicted calls do not match the id list")
    frozen = json.loads((Path(ROOT)/"splits/test_hashes.json").read_text())
    for c in set(ids) & set(frozen):
        if c not in records or frozen[c] != record_hash(records[c]): errors.append(c + ": frozen transcript hash mismatch")
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions"); parser.add_argument("ids_file")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    errors = validate(args.predictions, read_ids(args.ids_file), args.strict)
    for error in errors[:20]: print("ERROR", error)
    print(f"{len(errors)} errors")
    raise SystemExit(bool(errors))
