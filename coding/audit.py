"""Read-only dataset and split audit; does not regenerate splits or labels."""
import argparse
import collections
import csv
import json
from pathlib import Path
from .io_utils import ROOT, INPUT_FILES, file_hash, load_records, read_ids, record_hash, write_json
from .labels import normalize_codes


def audit():
    root = Path(ROOT); records = load_records()
    dev, test, uncoded = [read_ids(root/f"splits/{name}_ids.txt") for name in ["dev", "test", "uncoded"]]
    frozen = json.loads((root/"splits/test_hashes.json").read_text())
    errors = []
    for name, ids in [("dev", dev), ("test", test), ("uncoded", uncoded)]:
        if len(ids) != len(set(ids)): errors.append("duplicate IDs in " + name)
        if set(ids) - records.keys(): errors.append("unknown IDs in " + name)
    if set(dev)&set(test) or set(dev)&set(uncoded) or set(test)&set(uncoded): errors.append("split overlap")
    if set(dev+test+uncoded) != set(records): errors.append("split coverage mismatch")
    if set(frozen) != set(test): errors.append("frozen hash IDs differ from test split")
    mismatches = [c for c in test if c not in records or record_hash(records[c]) != frozen.get(c)]
    if mismatches: errors.append("frozen test hash mismatch")
    categories = collections.Counter(); topics = collections.Counter()
    for c in dev:  # reference/tuning summaries deliberately development-only
        p = normalize_codes(c, records[c].get("codes"))
        if p is None: errors.append("uncoded development call: " + c); continue
        categories[p["category"]] += 1; topics[p["subcategory"]] += 1
    qual = {}
    for name in ["A", "B"]:
        with (root/f"qual_sample/sheet_{name}.csv").open() as f: rows = list(csv.DictReader(f))
        qual[name] = {"calls": len(rows), "completed": sum(bool(x["outcome"].strip()) for x in rows)}
    return {"unique_calls": len(records), "coded_calls": sum(normalize_codes(c, r.get("codes")) is not None for c,r in records.items()),
            "split_counts": {"dev": len(dev), "test": len(test), "uncoded": len(uncoded)},
            "test_hash_mismatches": mismatches, "dev_categories": dict(categories), "dev_topics": dict(topics),
            "qualification_sheets": qual,
            "independent_reliability_annotations_available": False,
            "reliability_note": "Local records have one codes object per call and no 337-call pairwise coder files or mapping.",
            "files": {str(Path(p).relative_to(root)): file_hash(p) for p in INPUT_FILES}, "errors": errors}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output")
    args = parser.parse_args(); result = audit()
    if args.output: write_json(args.output, result)
    print(json.dumps(result, indent=2)); raise SystemExit(bool(result["errors"]))
