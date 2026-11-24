"""Development-only topic reference, immutable during inference. No API required."""
import argparse
import collections
import copy
import math
import re
import random
from pathlib import Path

from .io_utils import ROOT, INPUT_FILES, file_hash, load_records, read_ids, write_json, write_manifest

VERSION = "tfidf-reference-v2-dev-calibrated"
# Fixed before test scoring. Sensitivity must be assessed on development data only.
THRESHOLD = 0.25
STOP = set("a an the i you your we our us me my it is are was were be been to of and or in on at for from with that this these those have has had do does did can could would will should just now then so yes no okay ok hello hi hey thank thanks please how what who when where why all any some about there here im its thats dont not right know like today calling call line phone number recorded name good morning afternoon really well also very let get got go going want need sure said tell more out up as by if but they them their am may one two much still actually alright oh uh um yeah qualify qualified eligible benefit benefits information question questions speaking sir maam help people time back give great perfect awesome correct confirm currently already talking little understand hear sorry hold second minute something anything because see take make say next before after again insurance agent specialist supervisor transfer connect connection coverage plan parts part new enrollment percent dollars free address zip code age old live years year month day born first last states united unitedstates america american california florida medicaremedicaid".split())


def tokens(text):
    return [w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in STOP]


def caller_text(record):
    return " ".join(t["content"] for t in record["conversation"] if t["role"] == "user")


def vector(words, idf):
    c = collections.Counter(words)
    return {w: (1 + math.log(n)) * idf.get(w, 1.0) for w, n in c.items()}


def cosine(a, b):
    den = math.sqrt(sum(x*x for x in a.values()) * sum(x*x for x in b.values()))
    return sum(v*b.get(k, 0) for k, v in a.items()) / den if den else 0.0


def build_reference(records, dev_ids, test_ids, withheld=("accident_claim",)):
    if len(dev_ids) != len(set(dev_ids)) or set(dev_ids) & set(test_ids):
        raise ValueError("development IDs must be unique and disjoint from test")
    withheld = set(withheld)
    documents, groups, included, excluded = [], collections.defaultdict(list), [], []
    by_topic = collections.defaultdict(list)
    for c in dev_ids:
        topic = str(records[c].get("codes", {}).get("subcategory") or "").strip().lower()
        if not topic or topic in withheld: excluded.append(c)
        else: by_topic[topic].append(c)
    # Disjoint development calibration calls never contribute words/IDF/centroids.
    calibration_ids = []
    rng = random.Random(598)
    for topic in sorted(by_topic):
        candidates = sorted(by_topic[topic]); rng.shuffle(candidates)
        n_calibration = max(1, round(len(candidates)*0.2)) if len(candidates) >= 5 else 0
        calibration_ids.extend(candidates[:n_calibration])
        for c in candidates[n_calibration:]:
            words = tokens(caller_text(records[c]))
            documents.append(words); groups[topic].extend(words); included.append(c)
    if not documents: raise ValueError("no development documents available")
    if not withheld <= {str(records[c].get("codes", {}).get("subcategory", "")).lower().strip() for c in dev_ids}:
        raise ValueError("withheld topics must exist in development labels")
    df = collections.Counter(w for words in documents for w in set(words))
    idf = {w: math.log((1 + len(documents))/(1 + n)) + 1 for w, n in df.items()}
    # Maximum 80 salient words per topic; weights are transparent and reviewable.
    centers = {topic: dict(sorted(vector(words, idf).items(), key=lambda x: (-x[1], x[0]))[:80])
               for topic, words in groups.items()}
    ref = {"version": VERSION, "threshold": THRESHOLD, "withheld_topics": sorted(withheld),
           "source_dev_ids": sorted(dev_ids), "included_ids": sorted(included), "excluded_ids": sorted(excluded),
           "calibration_ids": sorted(calibration_ids), "topics": centers, "idf": idf,
           "confirmed_organizations": [],
           "organization_note": "Names are redacted; no original organization novelty claim is possible."}
    scores = sorted(detect(records[c], ref)["similarity"] for c in calibration_ids)
    if len(scores) >= 20:
        ref["threshold"] = scores[int(0.05*len(scores))]
    ref["calibration"] = {"method": "fifth percentile of known-topic development similarities",
                          "target_known_false_positive_rate": 0.05, "calls": len(scores), "seed": 598,
                          "note": "Initial fixed-threshold test was inspected; revised test results are exploratory."}
    return ref



def detect(record, reference, prediction=None):
    words = tokens(caller_text(record)); v = vector(words, reference["idf"])
    sims = {topic: cosine(v, center) for topic, center in reference["topics"].items()}
    nearest = max(sims, key=sims.get) if sims else None
    similarity = sims.get(nearest, 0.0)
    reasons = []
    if similarity < reference["threshold"]:
        reasons.append("low_topic_similarity")
    if prediction and prediction.get("subcategory") and prediction["subcategory"] not in reference["topics"]:
        reasons.append("topic_outside_reference")
    candidates = []
    for row in (prediction or {}).get("novelty_candidates", []):
        term = row["term"].strip()
        if not re.search(r"[A-Za-z]", term) or term.lower() in {"redacted", "unknown", "none"}: continue
        known = reference["confirmed_organizations"] if row["kind"] == "organization" else reference["topics"]
        normalized = re.sub(r"[^a-z0-9]", "", term.lower())
        if normalized not in {re.sub(r"[^a-z0-9]", "", k.lower()) for k in known}:
            candidates.append(row); reasons.append("unconfirmed_" + row["kind"])
    return {"flagged": bool(reasons),
            "topic_flagged": any(reason != "unconfirmed_organization" for reason in reasons),
            "organization_flagged": "unconfirmed_organization" in reasons,
            "reasons": sorted(set(reasons)),
            "nearest_topic": nearest, "similarity": round(similarity, 6),
            "threshold": reference["threshold"], "candidates": candidates,
            "unmatched_terms": [w for w, _ in collections.Counter(words).most_common() if w not in reference["idf"]][:10]}


def attach(prediction, record, reference):
    p = copy.deepcopy(prediction)
    p["novelty"] = detect(record, reference, p)
    p.setdefault("uncertainty", [])
    if p["novelty"]["flagged"]:
        p["uncertainty"].append({"field": "novelty", "reason": ", ".join(p["novelty"]["reasons"])})
    p["review_required"] = bool(p["uncertainty"])
    return p


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--withhold", nargs="+", default=["accident_claim"])
    args = parser.parse_args()
    if args.output.exists(): parser.error("reference already exists; use a new path to create a new experiment")
    dev = Path(ROOT)/"splits/dev_ids.txt"; test = Path(ROOT)/"splits/test_ids.txt"
    ref = build_reference(load_records(), read_ids(dev), read_ids(test), args.withhold)
    ref["dev_ids_sha256"] = file_hash(dev); ref["test_ids_sha256"] = file_hash(test)
    write_json(str(args.output), ref)
    write_manifest(str(args.output.with_suffix(".manifest.json")), "topic_reference", VERSION,
                   INPUT_FILES + [str(dev), str(test), __file__], [str(args.output)])
    print(f"Frozen reference: {len(ref['topics'])} topics, {len(ref['included_ids'])} dev calls -> {args.output}")


if __name__ == "__main__": main()
