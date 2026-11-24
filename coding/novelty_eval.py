"""Score the frozen novelty detector separately from the LLM's coding accuracy."""
import argparse
import json
from pathlib import Path
from .agreement import bootstrap_ci
from .io_utils import load_records, read_ids, record_hash, write_json, write_manifest, INPUT_FILES
from .novelty import detect


def evaluate_novelty(records, ids, reference, predictions=None):
    if set(ids) & set(reference["source_dev_ids"]): raise ValueError("novelty evaluation must exclude reference development calls")
    if len(ids) != len(set(ids)): raise ValueError("duplicate evaluation IDs")
    pred = {} if predictions is None else {p["call_id"]: p for p in predictions}
    if predictions is not None and (len(pred) != len(predictions) or set(pred) != set(ids)):
        raise ValueError("predictions must match evaluation IDs exactly; failures cannot be silently dropped")
    rows = []
    for c in ids:
        topic = str(records[c].get("codes", {}).get("subcategory") or "").strip().lower()
        if not topic: raise ValueError("missing gold topic: " + c)
        if c in pred and pred[c].get("input_hash") != record_hash(records[c]): raise ValueError("prediction input hash mismatch")
        result = detect(records[c], reference, pred.get(c))
        # Topics absent naturally are a third group, not mislabeled as known negatives.
        group = "withheld" if topic in reference["withheld_topics"] else ("known" if topic in reference["topics"] else "naturally_unseen")
        rows.append({"call_id": c, "gold_topic": topic, "group": group, **result})
    metrics = {}
    for group, name in [("withheld", "withheld_recall"), ("known", "known_false_positive_rate"),
                        ("naturally_unseen", "naturally_unseen_recall")]:
        subset = [r for r in rows if r["group"] == group]
        n = len(subset); flagged = sum(r["topic_flagged"] for r in subset)
        by_id = {r["call_id"]: r["topic_flagged"] for r in subset}
        metrics[name] = {"n": n, "flagged": flagged, "rate": flagged/n if n else None,
                         "ci95": bootstrap_ci(list(by_id), lambda s: sum(by_id[c] for c in s)/len(s)) if n else None}
    return {"system": "topic_reference_detector" if predictions is None else "agent_plus_topic_reference",
            "calls": len(ids), "flagged": sum(r["flagged"] for r in rows),
            "topic_flagged": sum(r["topic_flagged"] for r in rows),
            "organization_flagged": sum(r["organization_flagged"] for r in rows),
            "metric_target": "topic novelty; organization review is counted separately",
            "threshold": reference["threshold"], "metrics": metrics, "calls_detail": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference"); parser.add_argument("ids_file"); parser.add_argument("output")
    parser.add_argument("--predictions")
    args = parser.parse_args()
    if Path(args.output).exists(): parser.error("output exists; use a new path")
    ref = json.loads(Path(args.reference).read_text()); records = load_records(); ids = read_ids(args.ids_file)
    from .io_utils import ROOT
    frozen = json.loads((Path(ROOT)/"splits/test_hashes.json").read_text())
    for c in ids:
        if c not in frozen or frozen[c] != record_hash(records[c]): raise ValueError("evaluation input is not a frozen test record")
    preds = json.loads(Path(args.predictions).read_text())["predictions"] if args.predictions else None
    result = evaluate_novelty(records, ids, ref, preds)
    write_json(args.output, result)
    inputs = INPUT_FILES + [args.reference, args.ids_file, __file__] + ([args.predictions] if args.predictions else [])
    write_manifest(str(Path(args.output).with_suffix(".manifest.json")), result["system"], "v1", inputs, [args.output])
    print(json.dumps({k:v for k,v in result.items() if k != "calls_detail"}, indent=2))


if __name__ == "__main__": main()
