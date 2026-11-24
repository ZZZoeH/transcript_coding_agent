"""Append fitting-only numbering questions to the model-blind human decision packet."""
import json
import re
import shutil
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from coding.io_utils import load_records,record_hash,write_json,read_ids,ROOT
from coding.labels import normalize_codes
from tools.prepare_dev_alignment import export_decisions


def main():
    exp=Path(sys.argv[1]);profile=json.loads((exp/'profile_v3.json').read_text())
    original=json.loads((exp/'team_review_cases.json').read_text());cases=list(original['cases'])
    output=exp/'team_review_cases_all.json'
    if output.exists():raise ValueError('case packet already exists; preserve decisions')
    excluded=set(profile['example_call_ids'])|{c['call_id'] for c in cases}
    records=load_records();added=0
    for c in profile['fit_call_ids']:
        if c in excluded:continue
        rec=records[c];gold=normalize_codes(c,rec['codes']);source={t['turn_index']:t for t in rec['conversation']}
        numbered=[]
        for t in gold['caller_utterances']:
            labels=[lab for lab in t['requested_info'] if re.fullmatch(r'health_condition_?\d+',lab)]
            if labels:numbered.append({'turn_index':t['turn_index'],'labels':labels,'text':source[t['turn_index']]['content']})
        if len({lab for row in numbered for lab in row['labels']})<2:continue
        indices={row['turn_index'] for row in numbered[:3]}
        positions={i for i,t in enumerate(rec['conversation']) if t['turn_index'] in indices}
        focus_positions={j for i in positions for j in range(max(0,i-1),min(len(rec['conversation']),i+2))}
        cases.append({'case_id':f'DEV-{len(cases)+1:03d}','issue':'numbered_health_information',
            'call_id':c,'input_hash':record_hash(rec),'target_turn_index':numbered[0]['turn_index'],
            'question':'Do health_condition1, health_condition2, and similar labels refer to a fixed condition dictionary or to question order within each call? How should these labels be assigned consistently across calls?',
            'decision_options':['fixed_global_taxonomy','call_local_question_order','needs_explicit_code_dictionary','annotation_error'],
            'conversation':rec['conversation'],'focused_context':[rec['conversation'][i] for i in sorted(focus_positions)],
            'released_codes':gold,'numbered_label_examples':numbered[:6],
            'model_predictions_included':False,'status':'pending_human_decision'})
        added+=1
        if added==3:break
    if added!=3:raise ValueError('not enough disjoint fitting cases')
    dev=set(read_ids(Path(ROOT)/'splits/dev_ids.txt'))
    assert {c['call_id'] for c in cases}<=dev
    write_json(str(output),{'case_count':len(cases),'initial_cases':len(original['cases']),'supplemental_numbering_cases':added,
        'purpose':'coding_convention_decisions_not_independent_reliability_sample','model_blind':True,
        'role_legend':{'user':'caller','assistant':'callee'},'cases':cases})
    # Reuse the export function without changing the initial packet or any existing responses.
    staging=exp/'numbering_case_export';staging.mkdir(exist_ok=False)
    shutil.copy2(exp/'team_decisions.csv',staging/'team_decisions.csv')
    export_decisions(staging,cases)
    shutil.move(str(staging/'team_decisions.csv'),str(exp/'team_decisions_all.csv'));staging.rmdir()
    print(json.dumps({'total_cases':len(cases),'added_numbering_cases':added}))


if __name__=='__main__':main()
