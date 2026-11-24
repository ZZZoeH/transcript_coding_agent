"""ASU CreateAI structured coder. Dry runs never need a key or make network calls."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from . import prompts
from .asu_api import KEY_FILE, request_json
from .io_utils import ROOT, INPUT_FILES, file_hash, load_records, read_ids, record_hash, write_json
from .labels import normalize_codes
from .novelty import attach
from .output_normalization import normalize_output
from .dev_profiles import load_profile, augment_query, normalize_labels, source_bound_schema, restrict_turn_schema, profile_contract_errors
from .schema import SCHEMA, VERSION as SCHEMA_VERSION, check_model_output

PROJECT = "ecc2a166ce994c6280373e494d39aa28"
ENDPOINT = "https://api-main.aiml.asu.edu/query"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def payload_for(record, reference, vocabulary, config):
    root = Path(ROOT)
    query = json.loads(prompts.make_query(record, reference, vocabulary,
                                        (root/"codebook.txt").read_text(),
                                        (root/"qual_sample/coding_guide.md").read_text()))
    if config.get("profile_file"):
        query = augment_query(query, record, load_profile(config["profile_file"]))
    payload = {"endpoint": "query", "request_source": "override_params",
            "project_id": config["project_id"], "model_provider": config["provider"],
            "model_name": config["model"], "enable_search": False, "enable_history": False,
            "semantic_caching": False,
            "enhance_prompt": {"time": False, "date": False},
            "model_params": {"temperature": 0, "system_prompt": prompts.SYSTEM,
                             "response_format": {"type": "json_schema", "json_schema": {
                                 "name": "calltrap_coding", "strict": True, "schema": SCHEMA}}},
            "response_format": {"type": "json"},
            "query": json.dumps(query, ensure_ascii=False)}

    if config.get("profile_file"):
        payload["model_params"]["response_format"]["json_schema"]["schema"] = source_bound_schema(SCHEMA,record)
    return payload


def post_query(payload, endpoint, timeout=55):
    return request_json(endpoint, payload, timeout)


def extract_output(response):
    if not isinstance(response, dict): raise ValueError("API response must be an object")
    wrapper = response.get("response")
    if isinstance(wrapper, dict) and "response" in wrapper:
        value = wrapper["response"]
        metadata = wrapper.get("metadata", {})
    elif "response" in response and isinstance(wrapper, (str, dict)):
        value = wrapper
        metadata = response.get("metadata", {})
    else:
        raise ValueError("expected CreateAI response envelope")
    if isinstance(value, str):
        value = value.strip()
        # Accept a complete fenced JSON block, never salvage partial/truncated text.
        if value.startswith("```json") and value.endswith("```"): value = value[7:-3].strip()
        value = json.loads(value)
    if not isinstance(value, dict): raise ValueError("model output must be a JSON object")
    return value, metadata


def finalize(output, record, reference, vocabulary=None):
    errors = check_model_output(output, record)
    if errors: raise ValueError("; ".join(errors[:20]))
    p = {"call_id": record["call_id"], "input_hash": record_hash(record), **output}
    # Unknown fields cannot silently appear confident, even if the model omits an uncertainty flag.
    def unknowns(value, path):
        if value is None: p["uncertainty"].append({"field": path, "reason": "not established from transcript"})
        elif isinstance(value, dict):
            for k, v in value.items(): unknowns(v, path + "." + k)
    for key in ["category", "subcategory"]:
        unknowns(p[key], key)
    hook = p["hook_phase"]
    for key in ["exists", "execution", "consent", "only_greeting_turns", "caller_identification"]:
        unknowns(hook[key], "hook_phase." + key)
    unknowns(hook["transfer"]["intent"], "hook_phase.transfer.intent")
    if hook["transfer"]["success"] == "no" and hook["transfer"]["failure_reason"] is None:
        p["uncertainty"].append({"field": "hook_phase.transfer.failure_reason", "reason": "failed transfer reason not established"})
    if vocabulary is not None:
        known = set(vocabulary)
        for turn in p["caller_utterances"]:
            if set(turn["requested_info"]) - known:
                p["uncertainty"].append({"field": f"caller_utterances.{turn['turn_index']}.requested_info",
                                         "reason": "label outside development vocabulary"})
    if hook["transfer"]["intent"] == "yes" and hook["transfer"]["success"] is None:
        p["uncertainty"].append({"field": "hook_phase.transfer.success", "reason": "handoff not established"})
    if hook["qualification"]["question"] and p["qualification_outcome"]["label"] is None:
        p["uncertainty"].append({"field": "qualification_outcome", "reason": "outcome missing for qualification exchange"})
    for row in p["novelty_candidates"]:
        if row["kind"] == "organization":
            evidence = " ".join(t["content"] for t in record["conversation"] if t["turn_index"] in row["turn_indices"])
            if row["term"].casefold() not in evidence.casefold():
                p["uncertainty"].append({"field": "novelty_candidates", "reason": "organization candidate not literal in cited evidence"})
    from .sensitivity import classify
    p["requested_info_tiers"] = [{"turn_index": turn["turn_index"], "tiers": classify(turn["requested_info"])}
                                 for turn in p["caller_utterances"]]
    p["observability"] = {"accent": "not_observable", "background_noise": "not_observable"}
    return attach(p, record, reference)


def chunk_request(request, indices, chunked):
    if not chunked: return request
    result = json.loads(json.dumps(request))
    query = json.loads(result["query"])
    query["target_caller_turn_indices"] = indices
    if "target_contract" in query:
        query["target_contract"]["caller_turn_indices"] = indices
        result["model_params"]["response_format"]["json_schema"]["schema"] = restrict_turn_schema(
            result["model_params"]["response_format"]["json_schema"]["schema"], indices)
    query["chunk_instructions"] = (
        "Read the COMPLETE transcript for call-level context. Emit caller_utterances ONLY for "
        "target_caller_turn_indices, in exactly that order. Produce the complete call/hook metadata "
        "and qualification outcome from the entire call. Evidence may cite any source turn. "
        "Turn-field evidence paths must correspond to the caller turns emitted in this chunk.")
    result["query"] = json.dumps(query, ensure_ascii=False)
    return result


def merge_chunks(outputs):
    result = json.loads(json.dumps(outputs[0]))
    for part in outputs[1:]:
        for field in ["category", "subcategory", "hook_phase", "qualification_outcome"]:
            if part[field] != result[field]:
                result["uncertainty"].append({"field": field, "reason": "model outputs disagree across turn chunks; first chunk retained"})
        result["caller_utterances"].extend(part["caller_utterances"])
        result["evidence"].extend(row for row in part["evidence"] if row["field"].startswith("caller_utterances."))
        result["uncertainty"].extend(part["uncertainty"])
        result["novelty_candidates"].extend(part["novelty_candidates"])
    for field in ["uncertainty", "novelty_candidates"]:
        unique = {json.dumps(row, sort_keys=True): row for row in result[field]}
        result[field] = list(unique.values())
    return result


def process_call(record, reference, vocabulary, config, output_dir, resume):
    c = record["call_id"]
    stem = hashlib.sha256(c.encode()).hexdigest()[:24]
    call_dir = output_dir/"calls"/stem
    call_dir.mkdir(parents=True, exist_ok=True)
    completed = call_dir/"prediction.json"
    if resume and completed.exists():
        p = json.loads(completed.read_text())
        if p.get("input_hash") != record_hash(record): raise ValueError("checkpoint input hash mismatch")
        return p, None
    base = payload_for(record, reference, vocabulary, config)
    write_json(str(call_dir/"request.json"), base)
    caller = [t["turn_index"] for t in record["conversation"] if t["role"] == "user"]
    size = config.get("turns_per_chunk", 32)
    chunks = [caller[start:start+size] for start in range(0, len(caller), size)] or [[]]
    outputs, metadata_rows = [], []
    call_start = time.monotonic()
    try:
        for number, indices in enumerate(chunks):
            part_dir = call_dir/f"chunk_{number:03d}"
            part_dir.mkdir(exist_ok=True)
            accepted = part_dir/"accepted.json"
            if resume and accepted.exists():
                saved = json.loads(accepted.read_text())
                outputs.append(saved["output"]); metadata_rows.extend(saved["attempt_metadata"])
                continue
            request = chunk_request(base, indices, len(chunks) > 1)
            part_metadata = []
            for repair in range(config.get("validation_repairs", 2) + 1):
                attempt = len(list(part_dir.glob("response_*.json"))) + 1
                write_json(str(part_dir/f"request_{attempt:03d}.json"), request)
                raw = post_query(request, config["endpoint"], config["timeout"])
                write_json(str(part_dir/f"response_{attempt:03d}.json"), raw)
                try:
                    output, metadata = extract_output(raw)
                    part_metadata.append(metadata)
                    alias_changes = []
                    if config.get("profile_file"):
                        output, alias_changes = normalize_labels(output, load_profile(config["profile_file"]))
                    output, normalizations = normalize_output(output)
                    normalizations = alias_changes + normalizations
                    errors = check_model_output(output, record, indices)
                    if config.get("profile_file"):
                        errors += profile_contract_errors(output, load_profile(config["profile_file"]))
                    if not errors:
                        outputs.append(output); metadata_rows.extend(part_metadata)
                        write_json(str(accepted), {"output": output, "attempt_metadata": part_metadata,
                                                   "normalizations": normalizations})
                        break
                    message = "; ".join(errors[:20])
                except (ValueError, TypeError, KeyError) as error:
                    message = str(error)[:2000]
                if repair == config.get("validation_repairs", 2):
                    raise ValueError("chunk validation failed: " + message)
                request = chunk_request(base, indices, len(chunks) > 1)
                query = json.loads(request["query"])
                query["validation_repair"] = {"errors": message,
                    "previous_output": raw.get("response"),
                    "instructions": "Return a complete corrected object. Fix only contract problems using the original transcript. Do not invent evidence. Null and empty fields have no evidence entries; all other coded fields require them."}
                request["query"] = json.dumps(query, ensure_ascii=False)
        p = finalize(merge_chunks(outputs), record, reference, vocabulary)
        p["runtime_seconds"] = round(time.monotonic() - call_start, 3)
        p["model_requested"] = config["model"]
        p["provider_metadata"] = {"attempts": metadata_rows}
        p["normalizations"] = [{"chunk": part.parent.name, **row}
                               for part in sorted(call_dir.glob("chunk_*/accepted.json"))
                               for row in json.loads(part.read_text()).get("normalizations", [])]
        p["turn_chunks"] = len(chunks)
        p["api_attempts"] = len(metadata_rows)
        write_json(str(completed), p)
        return p, None
    except (ValueError, RuntimeError, TypeError, KeyError) as error:
        failure = {"call_id": c, "input_hash": record_hash(record),
                   "reason": str(error)[:2000], "review_required": True}
        write_json(str(call_dir/"failure.json"), failure)
        return None, failure


def run(ids_file, reference_file, output_dir, config, dry_run=False, limit=None, resume=False):
    root = Path(ROOT); output_dir = Path(output_dir)
    if limit is not None and limit < 1: raise ValueError("limit must be positive")
    ids = read_ids(ids_file)
    if len(ids) != len(set(ids)): raise ValueError("duplicate IDs in requested run")
    if limit is not None: ids = ids[:limit]
    if not ids: raise ValueError("no calls requested")
    if config.get("workers", 1) < 1 or config.get("turns_per_chunk", 32) < 1:
        raise ValueError("workers and turns_per_chunk must be positive")
    reference = json.loads(Path(reference_file).read_text())
    dev = read_ids(root/"splits/dev_ids.txt"); test = read_ids(root/"splits/test_ids.txt")
    if set(dev) & set(test): raise ValueError("development/test overlap")
    if reference["source_dev_ids"] != sorted(dev) or reference["dev_ids_sha256"] != file_hash(root/"splits/dev_ids.txt"):
        raise ValueError("reference does not match the frozen development split")
    if reference["test_ids_sha256"] != file_hash(root/"splits/test_ids.txt"):
        raise ValueError("reference does not match the frozen test split")
    if set(reference["included_ids"]) & set(test): raise ValueError("test call in reference")
    records = load_records()
    if set(ids) - records.keys(): raise ValueError("unknown call IDs")
    frozen = json.loads((root/"splits/test_hashes.json").read_text())
    for c in set(ids) & set(test):
        if frozen.get(c) != record_hash(records[c]): raise ValueError("test transcript hash mismatch: " + c)
    vocabulary = sorted({label for c in reference["included_ids"]
                         for t in normalize_codes(c, records[c]["codes"])["caller_utterances"]
                         for label in t["requested_info"]})
    inputs = INPUT_FILES + [str(ids_file), str(reference_file), str(root/"codebook.txt"),
                           str(root/"qual_sample/coding_guide.md")] + [str(p) for p in sorted((root/"coding").glob("*.py"))]
    profile = None
    if config.get("profile_file"):
        profile = load_profile(config["profile_file"])
        if not set(ids) <= set(dev):
            raise ValueError("development profiles may only run on development IDs")
        if set(ids) & set(profile["fit_call_ids"]):
            raise ValueError("comparison calls must be disjoint from profile fitting calls")
        if set(profile["fit_call_ids"]) != set(reference["included_ids"]):
            raise ValueError("profile fitting IDs must match the development-only reference pool")
        if not set(profile["example_call_ids"]) <= set(profile["fit_call_ids"]):
            raise ValueError("profile examples escape the fitting pool")
        inputs.append(str(config["profile_file"]))
    fingerprints = {os.path.relpath(p, ROOT): file_hash(p) for p in inputs}
    identity = {"config": config, "ids": ids, "inputs": fingerprints, "dry_run": dry_run,
                "prompt_version": profile["version"] if profile else prompts.VERSION, "schema_version": SCHEMA_VERSION}
    run_hash = digest(identity)
    manifest_file = output_dir/"manifest.json"
    if output_dir.exists() and any(output_dir.iterdir()):
        if not resume or not manifest_file.exists(): raise ValueError("output directory exists; use a new directory or --resume")
        old = json.loads(manifest_file.read_text())
        if old["run_hash"] != run_hash: raise ValueError("cannot resume: prompt/model/reference/input configuration changed")
        for name, checksum in old.get("outputs", {}).items():
            p = output_dir/name
            if not p.exists() or file_hash(p) != checksum: raise ValueError("cannot resume: artifact hash mismatch: " + name)
    if not dry_run and (not KEY_FILE.is_file() or not config["model"] or not config["provider"]):
        raise ValueError("provide the local ASU key file and specify approved --model and --provider before a live run")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {**identity, "run_hash": run_hash, "system": "asu_createai_agent",
                "time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "status": "running", "outputs": {}}
    write_json(str(manifest_file), manifest)
    predictions, failures = {}, {}
    started = time.monotonic()
    def checkpoint():
        write_json(str(output_dir/"predictions.json"), {"system": "asu_createai_agent", "predictions": [predictions[c] for c in ids if c in predictions]})
        write_json(str(output_dir/"failures.json"), [failures[c] for c in ids if c in failures])
    try:
        if dry_run:
            for c in ids:
                call_dir = output_dir/"calls"/hashlib.sha256(c.encode()).hexdigest()[:24]
                write_json(str(call_dir/"request.json"), payload_for(records[c], reference, vocabulary, config))
        else:
            with ThreadPoolExecutor(max_workers=config.get("workers", 1)) as pool:
                tasks = {pool.submit(process_call, records[c], reference, vocabulary, config, output_dir, resume): c for c in ids}
                for task in as_completed(tasks):
                    c = tasks[task]; pred, failure = task.result()
                    if pred: predictions[c] = pred
                    if failure: failures[c] = failure
                    checkpoint()
                    print(f"{len(predictions) + len(failures)}/{len(ids)} processed; {len(failures)} failed", flush=True)
        manifest["status"] = "dry_run" if dry_run else ("complete" if not failures else "incomplete")
    finally:
        manifest["runtime_seconds_this_invocation"] = round(time.monotonic() - started, 3)
        manifest["successful_calls"] = len(predictions); manifest["failed_calls"] = len(failures)
        manifest["outputs"] = {str(p.relative_to(output_dir)): file_hash(p) for p in sorted(output_dir.rglob("*.json")) if p != manifest_file}
        write_json(str(manifest_file), manifest)
    return len(failures)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids_file"); parser.add_argument("reference_file"); parser.add_argument("output_dir")
    parser.add_argument("--dry-run", action="store_true"); parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--provider", default=os.environ.get("ASU_MODEL_PROVIDER", ""))
    parser.add_argument("--model", default=os.environ.get("ASU_MODEL_NAME", ""))
    parser.add_argument("--project-id", default=os.environ.get("ASU_PROJECT_ID", PROJECT))
    parser.add_argument("--endpoint", default=os.environ.get("ASU_API_URL", ENDPOINT))
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--turns-per-chunk", type=int, default=32)
    parser.add_argument("--validation-repairs", type=int, default=2)
    parser.add_argument("--profile-file", type=Path)
    args = parser.parse_args()
    if args.timeout <= 0: parser.error("timeout must be positive")
    config = {"provider": args.provider, "model": args.model, "project_id": args.project_id,
              "endpoint": args.endpoint, "timeout": args.timeout, "workers": args.workers,
              "turns_per_chunk": args.turns_per_chunk, "validation_repairs": args.validation_repairs}
    if args.profile_file: config["profile_file"] = str(args.profile_file.resolve())
    try:
        failures = run(args.ids_file, args.reference_file, args.output_dir, config,
                       args.dry_run, args.limit, args.resume)
    except (ValueError, OSError) as e: parser.exit(2, str(e) + "\n")
    if failures: parser.exit(1, f"{failures} calls failed; see failures.json and review queue\n")


if __name__ == "__main__": main()
