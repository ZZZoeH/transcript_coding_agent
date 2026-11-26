"""Reviewed conventions and symmetric scoring projections; source gold is never edited."""
import copy
import json
import re

VERSION = 'reviewed-conventions-v1'
POLICY_ADDENDUM = '''The following reviewed conventions override conflicting earlier operational definitions.
They are dataset conventions confirmed on November 26, 2026, not claims about universal terminology.
Execution: an explicit keypad/button response to continue or connect is interaction_bot.
Automated speech/dialogue without such an action request is bot when automation is actually
established by text. Never infer automation solely from fluency or a repetitive script.
Use action_bot only for textually established one-way automated call-to-action behavior that
does not meet the keypad-continuation rule. Otherwise use null with uncertainty.
Greetings: count caller turns that only greet or check recipient availability/connection,
including repeated Hello?, Are you there?, and Can you hear me? turns. Count each turn once.
Turns also carrying identity, offer details, or a substantive question do not count as greeting-only.
DH follows the appendix's dishonesty/illegal-act leverage concept: using alleged dishonest or
illegal activity to create dependence or inhibit seeking help. A bare mention of illegality is
insufficient. DH is not limited to explicit instructions to lie.
The released topic convention merges auto_insurance into auto_warranty. This is a dataset label
alias, not a claim that insurance and warranty are substantively the same product.
All legacy health_conditionN information labels are represented as health_condition. Do not
invent numbered health labels. Named conditions can remain distinct if separately requested.
For an exact repeated caller question/utterance after case/whitespace/punctuation normalization,
assign turn-level information, persuasion, complementary, and functional labels at its FIRST
occurrence only. Emit the later caller turns as required, with empty repeated-label arrays.
Qualification question summaries still collect unique questions before the first transfer.
TIME still requires temporal pressure/availability framing in context, not every occurrence of
today or a greeting. Five fitting cases retain their released TIME labels under reviewer judgment;
that case-level decision does not establish a rule that every temporal word is TIME.
Apply the supplied qualification-outcome guide unchanged. Independent test human answers are
never examples or instructions. Every target label needs target-source evidence.
'''

SYSTEM_REPLACEMENTS = {
    'Greeting count counts only initial\ncaller turns containing greetings and no identity or purpose.':
        'Greeting count follows the reviewed convention specified below.',
    'Execution: action_bot prompts keypad action;\ninteraction_bot converses automatically; human or bot only with textual evidence. Ambiguous\nexecution is null with uncertainty.':
        'Execution follows the reviewed convention specified below; unsupported execution is null with uncertainty.',
    'dh=instructing false answers.': 'dh=reviewed dishonesty/illegal-act leverage as specified below.'}


def effective_system(base, profile):
    result = base
    for old, new in profile.get('system_replacements', {}).items():
        if old not in result:
            raise ValueError('Reviewed system replacement no longer matches the base prompt')
        result = result.replace(old, new)
    if profile.get('system_addendum'):
        result += '\n\n' + profile['system_addendum']
    return result


def evidence_indices(value):
    """Parse submitted JSON or adjacent bracket groups without changing human source files."""
    value = value.strip()
    if not value:
        return [], None
    try:
        result = json.loads(value)
        change = None
    except ValueError:
        if not re.fullmatch(r'(?:\s*\[\s*\d+\s*\]\s*)+', value):
            raise ValueError('Unsupported evidence-index format') from None
        result = [int(x) for x in re.findall(r'\d+', value)]
        change = 'adjacent_bracket_groups_to_json_array'
    if not isinstance(result, list) or any(type(i) is not int for i in result):
        raise ValueError('Evidence indices must be integer arrays')
    if len(result) != len(set(result)):
        raise ValueError('Duplicate evidence indices')
    return result, change


def information_label(label):
    return 'health_condition' if re.fullmatch(r'health_condition_?\d+', label) else label


def utterance_key(text):
    return re.sub(r'[^a-z0-9]+', '', text.casefold())


def project_for_scoring(prediction, record):
    """Derived, coarser comparison on BOTH gold and predictions; never primary raw scoring."""
    result = copy.deepcopy(prediction)
    if result['subcategory'] == 'auto_insurance':
        result['subcategory'] = 'auto_warranty'
    questions = result['hook_phase']['qualification']['question']
    result['hook_phase']['qualification']['question'] = sorted({information_label(x) for x in questions})
    canonical, seen = {}, {}
    for turn in record['conversation']:
        if turn['role'] != 'user':
            continue
        key = utterance_key(turn['content'])
        # Empty/non-Latin utterances are not silently collapsed into one group.
        token = key if key else ('source_turn', turn['turn_index'])
        canonical[turn['turn_index']] = seen.setdefault(token, turn['turn_index'])
    grouped = {}
    for turn in result['caller_utterances']:
        first = canonical[turn['turn_index']]
        row = grouped.setdefault(first, {'turn_index': first, 'requested_info': set(),
                                        'persuasion': set(), 'complementary_persuasion': set(),
                                        'functional_states': set()})
        for field in ['requested_info', 'persuasion', 'complementary_persuasion', 'functional_states']:
            values = turn[field]
            row[field].update(information_label(x) if field == 'requested_info' else x for x in values)
    result['caller_utterances'] = [
        {k: sorted(v) if isinstance(v, set) else v for k, v in row.items()}
        for row in sorted(grouped.values(), key=lambda r: r['turn_index'])]
    return result
