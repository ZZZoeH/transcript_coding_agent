"""Paired call-bootstrap differences between two systems on exactly the same calls."""
import argparse
import json
from pathlib import Path
from .agreement import bootstrap_ci
from .evaluate import CALL_FIELDS, TURN_FIELDS, call_kappa, turn_f1
from .io_utils import load_records, read_ids, write_json
from .labels import normalize_codes
from .validate import validate


def compare(baseline_file, agent_file, ids):
    for path in [baseline_file, agent_file]:
        errors = validate(path, ids)
        if errors: raise ValueError("Cannot compare invalid/incomplete predictions: " + "; ".join(errors[:3]))
    records = load_records(); gold = {c: normalize_codes(c, records[c]["codes"]) for c in ids}
    if any(p is None for p in gold.values()): raise ValueError("comparison calls must have gold labels")
    systems = [{p["call_id"]: p for p in json.loads(Path(path).read_text())["predictions"]}
               for path in [baseline_file, agent_file]]
    rows = []
    for field in CALL_FIELDS + TURN_FIELDS:
        stat = call_kappa if field in CALL_FIELDS else turn_f1
        def difference(sample):
            scores = [stat(field, sample, gold, pred) for pred in systems]
            return None if None in scores else scores[1]-scores[0]
        scores = [stat(field, ids, gold, pred) for pred in systems]
        rows.append({"field": field, "metric": "kappa" if field in CALL_FIELDS else "micro_f1",
                     "baseline": scores[0], "agent": scores[1], "difference": difference(ids),
                     "difference_ci95": bootstrap_ci(ids, difference)})
    return {"calls": len(ids), "bootstrap_unit": "call", "bootstrap_rounds": 1000, "seed": 598, "metrics": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline"); parser.add_argument("agent"); parser.add_argument("ids_file"); parser.add_argument("output")
    args = parser.parse_args()
    if Path(args.output).exists(): parser.error("comparison output exists; use a new path")
    result = compare(args.baseline, args.agent, read_ids(args.ids_file)); write_json(args.output, result)
    print(json.dumps(result, indent=2))
