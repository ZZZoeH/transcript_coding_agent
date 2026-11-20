# Simple rule-based coder: keyword lists from the codebook (tuned on dev only).
import re
import sys

from .io_utils import INPUT_FILES, load_records, read_ids, record_hash, write_json, write_manifest

TOPICS = {
    "accident_claim": ["accident", "injur", "compensation"],
    "auto_warranty": ["vehicle", "auto insurance", "car insurance", "protection plan", "your car"],
    "final_expense": ["final expense", "funeral", "burial", "cremation", "life insurance"],
    "medical_device": ["brace", "back pain", "diabetic", "medical alert"],
    "home_improvement": ["roof", "window", "home improvement", "solar"],
    "online_shopping": ["amazon", "your order"],
    "subsidy": ["subsid", "spending card", "grocery"],
    "health_insurance": ["health insurance", "marketplace"],
    "medicare": ["medicare", "part a"],
}
ASKS = {
    "age": ["how old", "your age", "age of", "ages of", "are you between"],
    "possession_medicare": ["part a and", "parts a and", "have medicare"],
    "possession_medicare_medicaid": ["medicaid or medicare", "medicare or medicaid", "like medicaid"],
    "name": ["first name", "last name", "your name"],
    "dob": ["date of birth"],
    "zip_code": ["zip"],
    "decision_making": ["decision"],
    "car_accident": ["involved in", "accident within"],
    "homeownership": ["homeowner"],
}
GAINS = ["cash back", "$", "dollars", "free", "dental", "vision", "to cover", "benefit", "save", "expenses"]
PERSUASION = {
    "auth": [" from *", " with *", "specialist", "supervisor", "licensed", "government", "eligible"],
    "crc": ["to let you know", "calling to", "enrollment", "recently", "newly", "you qualify"],
    "dis": GAINS,
    "lsd": ["how's your day", "day going", "beautiful", "god bless"],
    "sp": ["many people", "millions", "everyone"],
}
COMPLEMENTARY = {"nag": GAINS, "time": ["limited time", "expire", "deadline", "close your file"], "dh": ["illegal"]}
STATES = {
    "purpose": ["calling to", "calling about", "reaching out", "reason of my call", "to let you know",
                "to inform you", "enrollment", "i'm calling"],
    "transfer": ["transfer", "connect you", "connecting", "please hold", "stay on the line", "supervisor",
                 "verification officer"],
    "id_check": ["real person", "are you a robot", "are you a machine", "are you a bot"],
    "obscene": ["fuck", "shit", "bitch"],
}
CONSENT = ["is that okay", "is it okay", "would that be okay", "are you interested", "would you like"]
GREETING = re.compile(r"^\W*((hello|hi|hey|yes|good morning|can you hear me|how are you( doing)?( today)?)\W*)*$", re.I)


def labels(text, keyword_lists):
    # every label whose keywords appear in the text
    return sorted(label for label, words in keyword_lists.items() if any(w in text for w in words))


def code_turn(turn):
    t = turn["content"].lower()
    asks = labels(t, ASKS)
    states = labels(t, STATES) + (["qualification"] if asks else [])
    return {"turn_index": turn["turn_index"], "requested_info": asks, "persuasion": labels(t, PERSUASION),
            "complementary_persuasion": labels(t, COMPLEMENTARY), "functional_states": sorted(states)}


def code_call(record):
    caller = [t for t in record["conversation"] if t["role"] == "user"]
    turns = [code_turn(t) for t in caller]
    text = " ".join(t["content"] for t in caller).lower()

    # topic = most keyword hits; category follows the topic
    hits = {topic: sum(text.count(w) for w in words) for topic, words in TOPICS.items()}
    topic = max(hits, key=hits.get) if max(hits.values()) > 0 else None
    category = {"subsidy": "vishing_gov", "online_shopping": "vishing_co"}.get(topic, "telemarketing")

    # greeting-only turns at the start (a 1-2 word first turn is usually a garbled "hello")
    greetings = 0
    for i, t in enumerate(caller):
        if not (GREETING.match(t["content"]) or (i == 0 and len(t["content"].split()) <= 2)):
            break
        greetings += 1

    # "press 1" = action bot, long call = human, otherwise a talking bot
    if re.search(r"press (\d|one)", text):
        execution = "action_bot"
    else:
        execution = "human" if len(caller) >= 7 else "interaction_bot"

    # transfer: tried? did the call go on after it?
    tries = [u["turn_index"] for u in turns if "transfer" in u["functional_states"]]
    if not tries:
        transfer = {"intent": "no", "success": None, "failure_reason": None}
    elif caller[-1]["turn_index"] > tries[0]:
        transfer = {"intent": "yes", "success": "yes", "failure_reason": None}
    else:
        transfer = {"intent": "yes", "success": "no", "failure_reason": None}

    # qualification questions = things asked before the first transfer
    stop = tries[0] if tries else 10**9
    questions = sorted({a for u in turns if u["turn_index"] <= stop for a in u["requested_info"]})

    return {
        "call_id": record["call_id"],
        "input_hash": record_hash(record),
        "category": category,
        "subcategory": topic,
        "hook_phase": {
            "exists": "yes" if greetings < len(caller) else "no",
            "execution": execution,
            "consent": "yes" if any(w in text for w in CONSENT) else "no",
            "only_greeting_turns": greetings,
            "caller_identification": {"name": "disclosed" if "*****" in text else "none",
                                      "organization": "disclosed" if re.search(r"(from|with) (the )?\*", text) else "none"},
            "qualification": {"question": questions},
            "transfer": transfer,
        },
        "caller_utterances": turns,
        "evidence": {"transfer": tries},
        "uncertainty": [] if topic else [{"field": "subcategory", "reason": "no topic keyword"}],
    }


if __name__ == "__main__":
    ids_file, out_file = sys.argv[1], sys.argv[2]
    records = load_records()
    preds = [code_call(records[c]) for c in read_ids(ids_file)]
    write_json(out_file, {"system": "rule_based_baseline", "predictions": preds})
    write_manifest(out_file.replace(".json", "_manifest.json"), "rule_based_baseline", "0.1",
                   INPUT_FILES + [ids_file], [out_file])
    print(f"coded {len(preds)} calls -> {out_file}")
