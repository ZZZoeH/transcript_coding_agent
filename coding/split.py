# Splits the human-coded calls into dev (for tuning) and test (for final scoring).

import os
import random

from .io_utils import ROOT, load_records, record_hash, write_json
from .labels import Log, normalize_codes

SEED = 598
TEST_SHARE = 0.3

records = load_records()
log = Log()

# group coded calls by (category, call length) so both sides get a fair mix
groups = {}
uncoded = []
for call_id, rec in records.items():
    codes = normalize_codes(call_id, rec["codes"], log)
    if codes is None:
        uncoded.append(call_id)
        continue
    key = (codes["category"], rec["_bucket"])
    groups.setdefault(key, []).append(call_id)

rng = random.Random(SEED)
dev, test = [], []
for key in sorted(groups):
    ids = sorted(groups[key])
    rng.shuffle(ids)
    n_test = round(len(ids) * TEST_SHARE)
    test += ids[:n_test]
    dev += ids[n_test:]

out = os.path.join(ROOT, "splits")
os.makedirs(out, exist_ok=True)
for name, ids in [("dev", dev), ("test", test), ("uncoded", uncoded)]:
    with open(os.path.join(out, name + "_ids.txt"), "w") as f:
        f.write("\n".join(sorted(ids)) + "\n")

# hashes of the test transcripts prove the test set was not changed later
write_json(os.path.join(out, "test_hashes.json"), {c: record_hash(records[c]) for c in sorted(test)})
write_json(os.path.join(out, "label_fixes_log.json"), log.rows)

print(f"dev={len(dev)} test={len(test)} uncoded={len(uncoded)} label fixes={len(log.rows)}")
