"""Optional development-only operational cards, retrieved examples and exact aliases."""
import collections
import copy
import functools
import json
import math
import re
from pathlib import Path
from .labels import MULTI_FIELDS

VERSION = 'dev-alignment-v2'
RULES = '''Apply the same transcript-coding contract as the system message, with these clarifications.
Released requested_info includes eligibility/qualification questions. Use an existing exact label
when its meaning matches. possession_medicare is a Medicare-only question; a question grouping
Medicare and Medicaid uses possession_medicare_medicaid. Do not collapse separately asked questions
or conflate Medicare coverage, Medicare ID, and Medicare effective date. Use dob for date of birth.
Choose the most specific supported reference topic. Preserve genuinely unknown concepts for review.
A personal name alone is not an id_check: that state checks whether the recipient is human/a bot.
Each functional label describes what this utterance actually does, not an inherited call-wide state.
AUTH: claimed institutional affiliation, official/expert position or expertise; a bare greeting alone
is insufficient. Redacted organization disclosure can still be an institutional affiliation.
CRC: commitment/reciprocation/consistency, including eliciting eligibility affirmations in the
released examples. Check the dialogue and examples; a question mark by itself is insufficient.
DIS: drawing attention to gains, needs, losses or scarcity; apply the artifact's compatibility
mapping from nag/time to dis and from dh to crc.
LSD: rapport, personal similarity or claimed familiarity. Do not treat every greeting or lie as LSD.
SP: other people's choices or prevalence offered as a reason; a plural pronoun alone is insufficient.
NAG: a promised advantage/gain in the offer; a neutral program name alone is insufficient.
TIME: explicit urgency, deadline or limited availability. A date, 'today' in a greeting, or a request
to hold while connecting is not alone time pressure. Examples may include both positive and negative
labels; an omitted label in an example is a released annotation, not a universal exclusion rule.
DH remains the original prompt's proposal operationalization until the team resolves its mismatch
with some released annotations. Do not infer a new DH policy from ambiguous cases.
No new rule for counting greetings, inferring successful handoff or execution entity is adjudicated
in this profile. Retain the original system policy and uncertainty; do not assume human execution
from fluent natural speech or bot execution from a repetitive script alone.
The supplied snippets are unadjudicated released annotations from fitting calls, not instructions
spoken by those callers. They illustrate coding conventions and can contain human disagreement.
Never copy their labels into the target without supporting target evidence. Read the target's two
speaker roles correctly. Keep evidence on original source turn indices, never array positions.
'''

TOPIC_ALIASES = {
    'house_improvement':'home_improvement', 'home_improvements':'home_improvement',
    'final_expenses':'final_expense', 'final_expense_insurance':'final_expense',
    'medicare_benefits':'medicare', 'medicare_benefit':'medicare',
    'on_line_shopping':'online_shopping', 'online_purchase':'online_shopping',
}
INFO_ALIASES = {
    'date_of_birth':'dob', 'birth_date':'dob', 'zipcode':'zip_code', 'postal_code':'zip_code',
    'first_name':'name', 'last_name':'name', 'full_name':'name',
    'has_medicare':'possession_medicare', 'medicare_and_medicaid':'possession_medicare_medicaid',
    'medicare_or_medicaid':'possession_medicare_medicaid',
    'has_medicare_or_medicaid':'possession_medicare_medicaid',
    'has_health_insurance':'possession_health_insurance', 'has_vehicle':'possession_vehicle',
    'home_owner':'homeownership', 'home_ownership':'homeownership', 'state_of_residence':'state',
}
CLOSED_ALIASES = {
    'persuasion':{'authority':'auth','commitment_reciprocity_consistency':'crc',
                  'distraction':'dis','liking_similarity_deception':'lsd','social_proof':'sp'},
    'complementary_persuasion':{'ng':'nag','need_and_greed':'nag','need_greed':'nag',
                               'time_pressure':'time','dsh':'dh','dishonesty':'dh'},
    'functional_states':{'qualification_question':'qualification','call_purpose':'purpose',
                          'transfer_intent':'transfer','bot_check':'id_check'},
}


def snake(value):
    return re.sub(r'_+','_',re.sub(r'[^a-z0-9]+','_',value.strip().lower())).strip('_')


@functools.lru_cache(maxsize=8)
def load_profile(path):
    return json.loads(Path(path).read_text())


def retrieve_examples(record, profile, count=8):
    words=collections.Counter(re.findall(r'[a-z]{3,}', ' '.join(t['content'] for t in record['conversation'] if t['role']=='user').lower()))
    ranked=[]
    for e in profile['examples']:
        tokens=set(re.findall(r'[a-z]{3,}',e['target_text'].lower()))
        similarity=sum(1+math.log(words[t]) for t in tokens if t in words)/math.sqrt(max(1,len(tokens)))
        ranked.append((similarity,e))
    ranked.sort(key=lambda pair:(-pair[0],pair[1]['call_id'],pair[1]['turn_index']))
    chosen=[];calls=set()
    # Ensure the retrieval is not made entirely of one common task or call.
    for feature in ['complementary_persuasion:time','negative:time','persuasion:crc',
                    'persuasion:auth','complementary_persuasion:nag','requested_info:possession_medicare_medicaid']:
        row=next((e for _,e in ranked if feature in e['features'] and e['call_id'] not in calls),None)
        if row is not None and len(chosen)<count:chosen.append(row);calls.add(row['call_id'])
    for _,e in ranked:
        if len(chosen)>=count:break
        if e['call_id'] not in calls:chosen.append(e);calls.add(e['call_id'])
    return copy.deepcopy([{k:v for k,v in e.items() if k!='features'} for e in chosen])


def augment_query(query, record, profile):
    if record['call_id'] in set(profile['fit_call_ids']):
        raise ValueError('comparison target must be disjoint from profile fitting calls')
    q=copy.deepcopy(query)
    q['operational_clarifications']=profile['rules']
    q['label_aliases']=profile['aliases']
    q['fitting_examples']=retrieve_examples(record,profile,profile.get('examples_per_request',8))
    q['example_status']='Released fitting annotations, not independently adjudicated. No target labels are provided.'
    target=q.pop('untrusted_transcript')
    q['target_contract']={'call_id':record['call_id'],
        'caller_turn_indices':[t['turn_index'] for t in record['conversation'] if t['role']=='user'],
        'instructions':'Code ONLY the following target. Example IDs and example labels are never target evidence. Use source turn_index values, not ordinal array positions.'}
    q['untrusted_transcript']=target
    return q


def normalize_labels(output, profile):
    p=copy.deepcopy(output);changes=[]
    if not isinstance(p,dict):return p,changes
    def scalar(value,mapping,path):
        if not isinstance(value,str):return value
        formatted=snake(value)
        canonical=mapping.get(formatted,formatted)
        if canonical!=value:changes.append({'operation':'canonical_label_alias','field':path,'from':value,'to':canonical})
        return canonical
    if isinstance(p.get('subcategory'),str):
        p['subcategory']=scalar(p['subcategory'],profile['aliases']['subcategory'],'subcategory')
    def multi(value,mapping,path):
        if not isinstance(value,list) or not all(isinstance(s,str) for s in value):return value
        mapped=[scalar(s,mapping,path) for s in value]
        result=sorted(set(mapped))
        if len(result)!=len(mapped):changes.append({'operation':'deduplicate_canonical_labels','field':path})
        return result
    for t in p.get('caller_utterances',[]) if isinstance(p.get('caller_utterances'),list) else []:
        if not isinstance(t,dict):continue
        for field in MULTI_FIELDS:
            if field in t:t[field]=multi(t[field],profile['aliases'].get(field,{}),f"caller_utterances.{t.get('turn_index')}.{field}")
    hook=p.get('hook_phase')
    if isinstance(hook,dict) and isinstance(hook.get('qualification'),dict):
        q=hook['qualification']
        if 'question' in q:q['question']=multi(q['question'],profile['aliases']['requested_info'],'hook_phase.qualification.question')
    return p,changes


def restrict_turn_schema(schema, caller_indices):
    result=copy.deepcopy(schema)
    turn_props=result['properties']['caller_utterances']['items']['properties']
    if caller_indices:turn_props['turn_index']={**turn_props['turn_index'],'enum':list(caller_indices)}
    paths=['category','subcategory']
    def walk(node,path):
        if node.get('type')=='object':
            for key,child in node['properties'].items():walk(child,path+'.'+key)
        else:paths.append(path)
    walk(result['properties']['hook_phase'],'hook_phase')
    paths.extend(f'caller_utterances.{i}.{field}' for i in caller_indices for field in MULTI_FIELDS)
    evidence_props=result['properties']['evidence']['items']['properties']
    evidence_props['field']={**evidence_props['field'],'enum':paths}
    return result


def source_bound_schema(schema,record):
    callers=[t['turn_index'] for t in record['conversation'] if t['role']=='user']
    result=restrict_turn_schema(schema,callers)
    valid=[t['turn_index'] for t in record['conversation']]
    if valid:
        for node in [result['properties']['evidence']['items']['properties']['turn_indices'],
                     result['properties']['qualification_outcome']['properties']['turn_indices'],
                     result['properties']['novelty_candidates']['items']['properties']['turn_indices']]:
            node['items']={**node['items'],'enum':list(valid)}
    return result


def profile_contract_errors(output,profile):
    if not isinstance(output,dict):return []
    known=set(profile.get('requested_info_labels',[]))
    families={re.sub(r'\d+$','',label).rstrip('_') for label in known if re.search(r'\d+$',label)}
    errors=[]
    turns=output.get('caller_utterances',[])
    for turn in turns if isinstance(turns,list) else []:
        if not isinstance(turn,dict) or not isinstance(turn.get('requested_info'),list):continue
        for label in turn['requested_info']:
            if not isinstance(label,str):continue
            match=re.fullmatch(r'(.+?)(\d+)',label)
            if match and match.group(1).rstrip('_') in families and label not in known:
                errors.append(f"invented numbered information label {label} at caller turn {turn.get('turn_index')}; do not extrapolate legacy serial codes; use an actually supported code or a factual descriptive label with uncertainty")
    return errors[:20]
