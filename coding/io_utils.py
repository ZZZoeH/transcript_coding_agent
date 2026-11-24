# Loading the transcripts, hashing, and saving run records.

import datetime
import glob
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_FILES = sorted(glob.glob(os.path.join(ROOT, "transcript_inputs", "input*.json")))


def load_records():
    # returns {call_id: record} from all input files
    records = {}
    for path in INPUT_FILES:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for bucket, calls in data.items():     # bucket = call length group like "1-3m"
            for call in calls:
                call["_bucket"] = bucket
                if call["call_id"] in records:
                    raise ValueError("duplicate call_id requires explicit adjudication: " + call["call_id"])
                records[call["call_id"]] = call
    return records


def record_hash(record):
    # fingerprint of the transcript text; changes if anyone edits the conversation
    text = json.dumps([record["call_id"], record["conversation"]], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read_ids(path):
    with open(path) as f:
        return f.read().split()


def write_json(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    # Same-directory replace keeps interrupted writes from leaving a half-written checkpoint.
    import tempfile
    folder = os.path.dirname(path) or "."
    fd, temporary = tempfile.mkstemp(prefix=".coding-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1, allow_nan=False)
            f.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def write_manifest(path, system, version, inputs, outputs):
    # who/what/when + hashes of every input and output file, so a run can be checked later
    write_json(path, {
        "time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "system": system,
        "version": version,
        "inputs": {os.path.relpath(p, ROOT): file_hash(p) for p in inputs},
        "outputs": {os.path.relpath(p, ROOT): file_hash(p) for p in outputs},
    })
