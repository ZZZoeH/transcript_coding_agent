# Cleans up the human labels so we can compare them with our system's output.
# The original data is never changed. Every fix is written to a log.

import re

# allowed labels (from codebook.txt, names as they appear in the data)
CATEGORIES = ["telemarketing", "vishing_gov", "vishing_co", "nuisance", "others"]
EXECUTION = ["action_bot", "interaction_bot", "human", "bot"]
YES_NO = ["yes", "no"]
PERSUASION = ["auth", "crc", "dis", "lsd", "sp"]
COMP_PERSUASION = ["nag", "time", "dh"]   # paper calls these NG, TIME, DSH
FUNCTIONAL = ["purpose", "qualification", "transfer", "id_check", "obscene"]
IDENTITY = ["disclosed", "none"]          # names/orgs are hidden as ***** in the data
MULTI_FIELDS = ["requested_info", "persuasion", "complementary_persuasion", "functional_states"]

# known typos / other spellings in the data
FIXES = {"ng": "nag", "dsh": "dh", "purpsoe": "purpose", "puprose": "purpose", "q": "qualification"}


class Log:
    def __init__(self):
        self.rows = []

    def add(self, call_id, field, old, new, reason):
        self.rows.append({"call_id": call_id, "field": field, "old": old, "new": new, "reason": reason})


def clean(x):
    # None -> "", trim spaces, lowercase
    if x is None:
        return ""
    return str(x).strip().lower()


def split_multi(x):
    # "auth, dis" -> ["auth", "dis"]  (sorted, no duplicates)
    if isinstance(x, list):
        parts = x
    else:
        parts = re.split(r"[,;/]", clean(x))
    labels = set()
    for p in parts:
        p = p.strip().lower().replace(" ", "_")
        if p:
            labels.add(p)
    return sorted(labels)


def keep_allowed(labels, allowed, call_id, field, log):
    # fix typos, drop labels that are not in the allowed list
    result = set()
    for label in labels:
        fixed = FIXES.get(label, label)
        if fixed != label:
            log.add(call_id, field, label, fixed, "alias/typo")
        if fixed not in allowed:
            log.add(call_id, field, label, None, "out of vocabulary, dropped")
            continue
        result.add(fixed)
    return sorted(result)


def yes_no(x, call_id, field, log):
    v = clean(x)
    if v in YES_NO:
        return v
    if v:  # something weird like "bella" or "yesno"
        log.add(call_id, field, x, None, "not yes/no, treated as missing")
    return None


def identity(x):
    # we only know if a name/org was said or not
    v = clean(x)
    if v == "":
        return None
    if v in ("none", "na", "n/a"):
        return "none"
    return "disclosed"


def normalize_codes(call_id, codes, log=None):
    # turns one call's human codes into our standard format
    # returns None if the call has no human codes (input1.json)
    if log is None:
        log = Log()
    if not codes or clean(codes.get("category")) == "":
        return None

    hook = codes.get("hook_phase") or {}
    caller_id = hook.get("caller_identification") or {}
    transfer = hook.get("transfer") or {}
    qual = hook.get("qualification") or {}

    # greeting count should be a number
    greet = hook.get("only_greeting_turns")
    try:
        greet = int(greet) if greet not in (None, "") else None
    except (TypeError, ValueError):
        log.add(call_id, "only_greeting_turns", greet, None, "not an int")
        greet = None

    # "not in service" -> "not_in_service"
    reason = clean(transfer.get("failure_reason"))
    if " " in reason:
        log.add(call_id, "transfer.failure_reason", transfer.get("failure_reason"),
                reason.replace(" ", "_"), "spaces -> underscores")
    reason = reason.replace(" ", "_") or None

    result = {
        "call_id": call_id,
        "category": clean(codes.get("category")),
        "subcategory": clean(codes.get("subcategory")) or None,
        "hook_phase": {
            "exists": yes_no(hook.get("exists"), call_id, "hook.exists", log),
            "execution": clean(hook.get("execution")) or None,
            "consent": yes_no(hook.get("consent"), call_id, "hook.consent", log),
            "only_greeting_turns": greet,
            # background_noise and accent are audio cues, so we skip them
            "caller_identification": {
                "name": identity(caller_id.get("name")),
                "organization": identity(caller_id.get("organization")),
            },
            "qualification": {"question": split_multi(qual.get("question", ""))},
            "transfer": {
                "intent": yes_no(transfer.get("intent"), call_id, "transfer.intent", log),
                "success": yes_no(transfer.get("success"), call_id, "transfer.success", log),
                "failure_reason": reason,
            },
        },
        "caller_utterances": [],
    }

    for turn in codes.get("caller_utterances", []):
        result["caller_utterances"].append({
            "turn_index": turn["turn_index"],
            "requested_info": split_multi(turn.get("requested_info", "")),
            "persuasion": keep_allowed(split_multi(turn.get("persuasion", "")),
                                       PERSUASION, call_id, "persuasion", log),
            "complementary_persuasion": keep_allowed(split_multi(turn.get("complementary_persuasion", "")),
                                                     COMP_PERSUASION, call_id, "complementary_persuasion", log),
            "functional_states": keep_allowed(split_multi(turn.get("functional_states", "")),
                                              FUNCTIONAL, call_id, "functional_states", log),
        })
    return result


def to_original_format(pred):
    # our format -> the coders' original string format (labels joined with ", ")
    hook = pred["hook_phase"]
    hidden = {"disclosed": "*****", "none": "none"}
    return {
        "category": pred["category"] or "",
        "subcategory": pred["subcategory"] or "",
        "hook_phase": {
            "exists": hook["exists"] or "",
            "execution": hook["execution"] or "",
            "consent": hook["consent"] or "",
            "only_greeting_turns": hook["only_greeting_turns"],
            "caller_identification": {
                "name": hidden.get(hook["caller_identification"]["name"], ""),
                "organization": hidden.get(hook["caller_identification"]["organization"], ""),
                "background_noise": "",
                "accent": "",
            },
            "qualification": {"question": ", ".join(hook["qualification"]["question"])},
            "transfer": {k: (v or "") for k, v in hook["transfer"].items()},
        },
        "caller_utterances": [
            {"turn_index": t["turn_index"], **{f: ", ".join(t[f]) for f in MULTI_FIELDS}}
            for t in pred["caller_utterances"]
        ],
    }
