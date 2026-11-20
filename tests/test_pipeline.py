import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coding.agreement import kappa
from coding.evaluate import evaluate
from coding.io_utils import ROOT, load_records, read_ids, record_hash, write_json
from coding.labels import normalize_codes
from coding.validate import check_call, validate

records = load_records()
ids = read_ids(os.path.join(ROOT, "splits", "dev_ids.txt"))[:100]

# 1. kappa gives the known answers
assert kappa(list("abab"), list("abab")) == 1.0
assert kappa(list("aaab"), list("aabb")) == 0.5
print("ok 1: kappa")

# 2. "predictions" copied from the human codes must pass and score 1.000 everywhere
perfect = []
for c in ids:
    p = normalize_codes(c, records[c]["codes"])
    p["input_hash"] = record_hash(records[c])
    perfect.append(p)
write_json("/tmp/perfect.json", {"predictions": perfect})
assert validate("/tmp/perfect.json", ids) == []
assert evaluate("/tmp/perfect.json", ids).count("| 1.000 |") == 11
print("ok 2: perfect predictions pass and score 1.000")

# 3. the validator catches an edited transcript and a missing turn
edited = copy.deepcopy(records[ids[0]])
edited["conversation"][0]["content"] += " (edited)"
assert "transcript was changed" in check_call(perfect[0], edited)
missing_turn = copy.deepcopy(perfect[0])
missing_turn["caller_utterances"].pop()
assert "turns do not match" in check_call(missing_turn, records[ids[0]])
print("ok 3: tampering is caught")
