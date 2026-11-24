"""Export review requests without changing model predictions or human gold labels."""
import argparse
import csv
import json
from pathlib import Path
from .io_utils import load_records
from .novelty import attach


def queue_rows(predictions, failures=()):
    rows = []
    for p in predictions:
        if p.get("review_required") or p.get("uncertainty"):
            rows.append({"call_id": p["call_id"], "input_hash": p["input_hash"],
                         "reasons": json.dumps(p.get("uncertainty", [])),
                         "candidates": json.dumps(p.get("novelty", {}).get("candidates", [])),
                         "status": "pending", "review_seconds": "", "reviewer": "", "notes": ""})
    for p in failures:
        rows.append({"call_id": p["call_id"], "input_hash": p["input_hash"], "reasons": p["reason"],
                     "candidates": "[]", "status": "pending", "review_seconds": "", "reviewer": "", "notes": ""})
    return sorted(rows, key=lambda row: row["call_id"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions"); parser.add_argument("output")
    parser.add_argument("--failures"); parser.add_argument("--reference")
    args = parser.parse_args()
    if Path(args.output).exists(): parser.error("queue exists; preserve human edits and use a new output path")
    preds = json.loads(Path(args.predictions).read_text())["predictions"]
    if args.reference:
        reference = json.loads(Path(args.reference).read_text()); records = load_records()
        preds = [attach(p, records[p["call_id"]], reference) for p in preds]
    failures = json.loads(Path(args.failures).read_text()) if args.failures else []
    rows = queue_rows(preds, failures)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    fields = ["call_id", "input_hash", "reasons", "candidates", "status", "review_seconds", "reviewer", "notes"]
    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    print(f"{len(rows)} review requests -> {args.output}")


if __name__ == "__main__": main()
