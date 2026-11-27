# All qualification numbers for the report:  python3 -m coding.qualification_summary <predictions.json.gz>
import csv, gzip, json, sys
from .agreement import bootstrap_ci, kappa

sheet = lambda p: {r["call_id"]: r["outcome"] for r in csv.DictReader(open(p, encoding="utf-8-sig"))}
a, b = sheet("qual_sample/sheet_A.csv"), sheet("qual_sample/sheet_B.csv")
final = sheet("runs/agent/qualification_review/adjudicated_after_C_v1/adjudicated_sheet.csv")
preds = json.load(gzip.open(sys.argv[1], "rt"))["predictions"]
model = {p["call_id"]: (p.get("qualification_outcome") or {}).get("label") for p in preds}  # None = no label

for name, x, y in [("A vs B", a, b), ("A vs final", a, final), ("B vs final", b, final), ("model vs final", model, final)]:
    score = lambda ids: kappa([x[c] for c in ids], [y[c] for c in ids])
    print(f"{name}: kappa {score(list(y)):.3f}  CI {bootstrap_ci(list(y), score)}  agree {sum(x[c] == y[c] for c in y)}/50")
