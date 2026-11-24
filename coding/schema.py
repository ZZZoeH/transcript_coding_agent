"""Versioned model contract and a dependency-free validator for its schema subset."""
from .labels import CATEGORIES, EXECUTION, PERSUASION, COMP_PERSUASION, FUNCTIONAL

VERSION = "calltrap-text-v1"
OUTCOMES = ["matches_profile", "mismatch_call_continues", "call_terminates"]


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


def array(items):
    return {"type": "array", "items": items}


def enum(values, nullable=True):
    return {"enum": list(values) + ([None] if nullable else [])}


TEXT = {"type": "string", "minLength": 1}
MAYBE_TEXT = {"type": ["string", "null"], "minLength": 1}
INDEX = {"type": "integer", "minimum": 0}
STRINGS = array(TEXT)
INDICES = array(INDEX)
YN = enum(["yes", "no"])
HOOK = obj({
    "exists": YN, "execution": enum(EXECUTION), "consent": YN,
    "only_greeting_turns": {"type": ["integer", "null"], "minimum": 0},
    "caller_identification": obj({"name": enum(["disclosed", "none"]),
                                   "organization": enum(["disclosed", "none"])}),
    "qualification": obj({"question": STRINGS}),
    "transfer": obj({"intent": YN, "success": YN, "failure_reason": MAYBE_TEXT}),
})
TURN = obj({"turn_index": INDEX, "requested_info": STRINGS,
            "persuasion": array(enum(PERSUASION, False)),
            "complementary_persuasion": array(enum(COMP_PERSUASION, False)),
            "functional_states": array(enum(FUNCTIONAL, False))})
SCHEMA = obj({
    "category": enum(CATEGORIES), "subcategory": MAYBE_TEXT, "hook_phase": HOOK,
    "caller_utterances": array(TURN),
    "evidence": array(obj({"field": TEXT, "turn_indices": INDICES})),
    "uncertainty": array(obj({"field": TEXT, "reason": TEXT})),
    "qualification_outcome": obj({"label": enum(OUTCOMES), "turn_indices": INDICES}),
    "novelty_candidates": array(obj({"kind": enum(["topic", "organization"], False),
                                      "term": TEXT, "turn_indices": INDICES})),
})
PREDICTION_SCHEMA = obj({"call_id": TEXT, "input_hash": TEXT,
                        **{k: SCHEMA["properties"][k] for k in
                           ["category", "subcategory", "hook_phase", "caller_utterances"]}})


def schema_errors(value, schema, path="$"):
    """Validate only the explicit JSON Schema keywords used above. Never coerces."""
    errors = []
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value outside vocabulary")
    types = schema.get("type")
    checks = {"object": lambda x: isinstance(x, dict), "array": lambda x: isinstance(x, list),
              "string": lambda x: isinstance(x, str), "integer": lambda x: type(x) is int,
              "null": lambda x: x is None}
    if types:
        types = types if isinstance(types, list) else [types]
        if not any(checks[t](value) for t in types):
            return errors + [f"{path}: expected {'/'.join(types)}"]
    if isinstance(value, dict):
        props = schema.get("properties", {})
        errors += [f"{path}.{k}: missing" for k in schema.get("required", []) if k not in value]
        if schema.get("additionalProperties") is False:
            errors += [f"{path}.{k}: unexpected" for k in value if k not in props]
        for k in value.keys() & props.keys():
            errors += schema_errors(value[k], props[k], path + "." + k)
    if isinstance(value, list):
        for i, item in enumerate(value):
            errors += schema_errors(item, schema.get("items", {}), f"{path}[{i}]")
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        errors.append(f"{path}: empty string")
    if type(value) is int and value < schema.get("minimum", value):
        errors.append(f"{path}: below minimum")
    return errors


def coded_fields(pred):
    """Leaf paths requiring evidence; empty lists and unknowns need no invented evidence."""
    result = {}
    def walk(value, path):
        if isinstance(value, dict):
            for key, item in value.items(): walk(item, path + "." + key if path else key)
        elif value is not None and value != []:
            result[path] = value
    for key in ["category", "subcategory", "hook_phase"]:
        walk(pred[key], key)
    for turn in pred["caller_utterances"]:
        for key in ["requested_info", "persuasion", "complementary_persuasion", "functional_states"]:
            if turn[key]: result[f"caller_utterances.{turn['turn_index']}.{key}"] = turn[key]
    return result


def check_model_output(pred, record, caller_turn_indices=None):
    errors = schema_errors(pred, SCHEMA)
    if errors: return errors
    caller = [t["turn_index"] for t in record["conversation"] if t["role"] == "user"]
    total_caller_turns = len(caller)
    if caller_turn_indices is not None: caller = list(caller_turn_indices)
    valid = {t["turn_index"] for t in record["conversation"]}
    if [t["turn_index"] for t in pred["caller_utterances"]] != caller:
        errors.append("caller turns must match the source exactly in order")
    for turn in pred["caller_utterances"]:
        for key in ["requested_info", "persuasion", "complementary_persuasion", "functional_states"]:
            if len(set(turn[key])) != len(turn[key]): errors.append(f"duplicate labels: {key}")
    fields = coded_fields(pred)
    seen = set()
    for row in pred["evidence"]:
        field, indices = row["field"], row["turn_indices"]
        if field not in fields: errors.append(f"evidence references unknown or empty field: {field}")
        if field in seen: errors.append(f"duplicate evidence field: {field}")
        seen.add(field)
        if not indices or not set(indices) <= valid: errors.append(f"invalid evidence turns: {field}")
        if field.startswith("caller_utterances."):
            index = int(field.split(".")[1]) if field in fields else None
            if index not in indices: errors.append(f"turn label must cite its own turn: {field}")
    errors += [f"missing evidence: {field}" for field in fields.keys() - seen]
    for row in pred["novelty_candidates"]:
        if not row["turn_indices"]: errors.append("novelty candidate needs evidence")
    for row in pred["novelty_candidates"] + [pred["qualification_outcome"]]:
        if not set(row["turn_indices"]) <= valid: errors.append("invalid candidate/outcome turn")
    outcome = pred["qualification_outcome"]
    if outcome["label"] is not None and not outcome["turn_indices"]:
        errors.append("qualification outcome needs evidence")
    hook = pred["hook_phase"]
    if hook["only_greeting_turns"] is not None and hook["only_greeting_turns"] > total_caller_turns:
        errors.append("greeting count exceeds caller turns")
    if hook["transfer"]["intent"] == "no" and any(hook["transfer"][k] is not None for k in ["success", "failure_reason"]):
        errors.append("no transfer intent requires null success and failure_reason")
    if hook["transfer"]["success"] == "yes" and hook["transfer"]["failure_reason"] is not None:
        errors.append("successful transfer cannot have a failure reason")
    return errors
