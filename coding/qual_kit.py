# Two people label the same 50 calls separately; then we measure agreement.

import csv
import os
import random
import sys

from .agreement import bootstrap_ci, kappa
from .io_utils import ROOT, load_records, read_ids
from .labels import normalize_codes

OUTCOMES = ["matches_profile", "mismatch_call_continues", "call_terminates"]
FOLDER = os.path.join(ROOT, "qual_sample")


def sample(n=50):
    # 50 test calls that have qualification questions
    records = load_records()
    ids = [c for c in read_ids(os.path.join(ROOT, "splits", "test_ids.txt"))
           if normalize_codes(c, records[c]["codes"])["hook_phase"]["qualification"]["question"]]
    chosen = sorted(random.Random(598).sample(ids, n))
    os.makedirs(FOLDER, exist_ok=True)

    # one reading packet, same for both people
    with open(os.path.join(FOLDER, "packet.md"), "w") as f:
        f.write("# Pick one outcome per call: " + ", ".join(OUTCOMES) + "\n")
        f.write("Judge by what the caller does after the qualification questions.\n")
        for c in chosen:
            f.write(f"\n## {c}\n")
            for t in records[c]["conversation"]:
                who = "CALLER" if t["role"] == "user" else "callee"
                f.write(f"- [{t['turn_index']}] {who}: {t['content'].strip()}\n")

    # one blank sheet per person
    for person in ["A", "B"]:
        with open(os.path.join(FOLDER, f"sheet_{person}.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["call_id", "outcome"])
            w.writerows([c, ""] for c in chosen)
    print(f"{n} calls -> {FOLDER}")


def read_sheet(path):
    with open(path) as f:
        return {row["call_id"]: row["outcome"].strip() for row in csv.DictReader(f)}


def compare(path_a, path_b):
    a, b = read_sheet(path_a), read_sheet(path_b)
    ids = [c for c in a if a[c] in OUTCOMES and b.get(c) in OUTCOMES]
    if not ids:
        return print("No calls labeled by both people yet. Fill sheet_A.csv and sheet_B.csv first.")
    k = kappa([a[c] for c in ids], [b[c] for c in ids])
    ci = bootstrap_ci(ids, lambda s: kappa([a[c] for c in s], [b[c] for c in s]))
    print(f"calls: {len(ids)}  kappa: {k:.3f}  95% CI: {ci}")
    # disagreements go to a third person, who decides without seeing A or B
    print("disagreements:", [c for c in ids if a[c] != b[c]])


if __name__ == "__main__":
    if sys.argv[1] == "sample":
        sample()
    else:
        compare(sys.argv[2], sys.argv[3])
