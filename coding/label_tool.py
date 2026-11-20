# Label one call at a time:  python3 -m coding.label_tool qual_sample/sheet_A.csv

import csv, sys
from .io_utils import load_records
from .qual_kit import OUTCOMES

sheet = sys.argv[1]
rows = list(csv.DictReader(open(sheet)))
records = load_records()

for row in [r for r in rows if not r["outcome"]]:
    for t in records[row["call_id"]]["conversation"]:
        print(("CALLER" if t["role"] == "user" else "callee") + ":", t["content"])
    answer = ""
    while answer not in ["1", "2", "3", "q"]:
        answer = input("\n1 matches_profile / 2 mismatch_call_continues / 3 call_terminates / q quit > ")
    if answer == "q":
        break
    row["outcome"] = OUTCOMES[int(answer) - 1]
    with open(sheet, "w", newline="") as f:          
        writer = csv.DictWriter(f, ["call_id", "outcome"])
        writer.writeheader()
        writer.writerows(rows)
    print("=" * 60)
