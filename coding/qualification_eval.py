"""Compare model outcomes to a completed, independently adjudicated human sheet."""
import argparse
import json
from pathlib import Path
from .agreement import bootstrap_ci, kappa
from .io_utils import write_json
from .qual_kit import OUTCOMES, read_sheet


def score(predictions, human):
    if not human or any(label not in OUTCOMES for label in human.values()):
        raise ValueError("complete the independently adjudicated human sheet before scoring")
    pred = {p["call_id"]: p for p in predictions}
    if len(pred) != len(predictions): raise ValueError("duplicate predictions")
    if set(human) - pred.keys(): raise ValueError("missing sample predictions")
    labels = {c: pred[c].get("qualification_outcome", {}).get("label") for c in human}
    # Unknown is a model abstention and counts as disagreement, never silently excluded.
    def stat(ids): return kappa([human[c] for c in ids], [labels[c] for c in ids])
    return {"calls": len(human), "model_abstentions": sum(x is None for x in labels.values()),
            "kappa": stat(list(human)), "ci95": bootstrap_ci(list(human), stat),
            "accuracy": sum(human[c] == labels[c] for c in human)/len(human),
            "disagreements": [c for c in human if human[c] != labels[c]]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions"); parser.add_argument("adjudicated_sheet"); parser.add_argument("output")
    args = parser.parse_args()
    if Path(args.output).exists(): parser.error("output exists; use a new path")
    result = score(json.loads(Path(args.predictions).read_text())["predictions"], read_sheet(args.adjudicated_sheet))
    write_json(args.output, result); print(json.dumps(result, indent=2))
