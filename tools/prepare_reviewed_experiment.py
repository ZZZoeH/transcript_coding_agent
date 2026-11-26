"""Freeze reviewed fitting conventions and the next exploratory evaluation design."""
import copy
import csv
import json
import shutil
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coding.io_utils import ROOT, file_hash, read_ids, load_records, write_json
from coding.reviewed_policies import POLICY_ADDENDUM, SYSTEM_REPLACEMENTS, evidence_indices


def main():
    root = Path(ROOT); out = Path(sys.argv[1]); old = root/'runs/agent/dev_alignment_20261123'
    if out.exists():raise ValueError('Choose a new immutable experiment directory')
    profile = copy.deepcopy(json.loads((old/'profile_v3.json').read_text()))
    with (old/'team_decisions_all.csv').open(encoding='utf-8-sig', newline='') as f:rows=list(csv.DictReader(f))
    packet = json.loads((old/'team_review_cases_all.json').read_text())
    cases = {c['case_id']:c for c in packet['cases']}; normalized=[]
    for row in rows:
        case=cases[row['case_id']]
        if row['decision'] not in case['decision_options'] or not row['reviewer'].strip():
            raise ValueError('Incomplete reviewed policy decision')
        indices, conversion = evidence_indices(row['supporting_turn_indices'])
        if not set(indices)<={t['turn_index'] for t in case['conversation']}:
            raise ValueError('Evidence outside original fitting source')
        normalized.append({**row,'supporting_turn_indices':indices,'format_conversion':conversion,
                           'evidence_supplied':bool(indices)})
    if len(normalized)!=32 or len({r['case_id'] for r in normalized})!=32:raise ValueError('Expected 32 unique reviews')
    profile['version']='reviewed-profile-v4-20261126'
    profile['system_replacements']=SYSTEM_REPLACEMENTS;profile['system_addendum']=POLICY_ADDENDUM
    profile['rules']=profile['rules'].split('DH remains')[0]+'\n'+POLICY_ADDENDUM
    profile['aliases']['subcategory']['auto_insurance']='auto_warranty'
    for label in profile['requested_info_labels']:
        if label.startswith('health_condition') and label.removeprefix('health_condition').lstrip('_').isdigit():
            profile['aliases']['requested_info'][label]='health_condition'
    profile['unresolved_decisions']=['case_specific_TIME_semantics_not_global_adjudicated_gold',
                                    'reviewer_conventions_differ_from_original_proposal']
    profile['execution_override_user_confirmed']='keypad continuation is interaction_bot'
    # Keep the same fitting examples; update only their label representation under the reviewed alias.
    from coding.reviewed_policies import information_label
    for ex in profile['examples']:
        ex['released_turn_codes']['requested_info']=sorted({information_label(x) for x in ex['released_turn_codes']['requested_info']})
        if ex['topic']=='auto_insurance':ex['topic']='auto_warranty'
        ex['annotation_status']='released_fitting_annotation_with_reviewed_representation_aliases'
    out.mkdir(parents=True)
    write_json(str(out/'profile_v4.json'),profile)
    write_json(str(out/'reviewed_decisions.json'),{'rows':normalized,'source_sha256':file_hash(old/'team_decisions_all.csv'),
        'source_unchanged':True,'missing_evidence_is_not_fabricated':True,
        'keypad_label_confirmation':'User explicitly selected interaction_bot on November 26, 2026'})
    for src,dest in [('comparison_ids.txt','dev_ids.txt'),('pilot_ids.txt','pilot_ids.txt')]:shutil.copy2(old/src,out/dest)
    shutil.copy2(root/'splits/test_ids.txt',out/'test_ids.txt')
    write_json(str(out/'design.json'),{'version':profile['version'],'dev_calls':80,'test_calls':583,
        'fitting_calls':len(profile['fit_call_ids']),'examples':len(profile['examples']),
        'profile_sha256':file_hash(out/'profile_v4.json'),'development_is_reused':True,
        'test_is_previously_inspected_exploratory':True,'primary':'unchanged released-label metrics',
        'secondary':'symmetric topic/health aliases and exact repeated-utterance union; coarser scoring unit',
        'qualification':'independently completed A/B/C 50-call outcome labels; no examples from these calls',
        'source_reviews_sha256':file_hash(old/'team_decisions_all.csv'),
        'source_transcripts_sha256':{str(p.relative_to(root)):file_hash(p) for p in (root/'transcript_inputs').glob('input*.json')}})
    print(json.dumps({'output':str(out),'profile':profile['version'],'reviewed_rows':32}))

if __name__=='__main__':main()
