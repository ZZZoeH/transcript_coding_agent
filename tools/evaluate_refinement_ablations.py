"""Compare predefined additive refinements; never choose per-call answers from gold."""
import argparse
import copy
import csv
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from coding.io_utils import ROOT, file_hash, load_records, read_ids, write_json
from coding.schema import SCHEMA, check_model_output
from coding.labels import normalize_codes
from coding.novelty_refinement import apply
from coding.refinement import triage
from coding.agreement import bootstrap_ci
from coding.reviewed_policies import project_for_scoring
from tools.evaluate_live_run import prepare_scoring_predictions
from tools.evaluate_reviewed_results import FIELDS, prepared_statistics, summarize_stats, qualification
from tools.evaluate_refinement import audit, novelty_rows, novelty_summary


def gaps_only(base, refined):
    result=copy.deepcopy(base)
    if (base['qualification_outcome']['label'] is None
            and base['hook_phase']['qualification']['question']
            and refined['qualification_outcome']['label'] is not None
            and refined.get('refinement')):
        result['qualification_outcome']=copy.deepcopy(refined['qualification_outcome'])
        result['uncertainty']=[r for r in result.get('uncertainty',[]) if not r['field'].startswith('qualification_outcome')]
        result['uncertainty'].extend(copy.deepcopy([r for r in refined['uncertainty'] if r['field'].startswith('qualification_outcome')]))
        result['refinement']={'version':'gaps-only-v1','mode':'missing_qualification_outcome_only',
            'previous_outcome':copy.deepcopy(base['qualification_outcome']),
            'source_refinement_mode':refined['refinement']['mode'],'preserved_all_other_coding_fields':True}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('experiment',type=Path);parser.add_argument('partition',choices=['dev','test'])
    a=parser.parse_args();exp=a.experiment;part=a.partition;root=Path(ROOT)
    base=root/json.loads((exp/'design.json').read_text())['base_experiment'];records=load_records();ids=read_ids(exp/(part+'_ids.txt'))
    design=exp/'ablation_design.json'
    if not design.exists():raise ValueError('Predefined ablation design missing')
    out=exp/(part+'_ablations')
    if out.exists():raise ValueError('Use a new output directory')
    old=prepare_scoring_predictions(json.loads((base/(part+'_run')/'predictions.json').read_text())['predictions'],
        json.loads((base/(part+'_run')/'failures.json').read_text()),records,ids)
    full=json.loads((exp/(part+'_analysis')/'refined_scoring.json').read_text())['predictions']
    profile=json.loads((base/'profile_v4.json').read_text());ref=json.loads((root/'runs/novelty/reference_calibrated.json').read_text())
    aliases=profile['aliases']['subcategory'];policy=json.loads((exp/'novelty_policy.json').read_text())['selected']
    arms={'reviewed_v4':old,'alias_only':[apply(p,records[p['call_id']],ref,aliases,**policy) for p in old],
        'gaps_only':[apply(gaps_only(p,q),records[p['call_id']],ref,aliases,**policy) for p,q in zip(old,full)],'full_refinement':full}
    out.mkdir();gold={c:normalize_codes(c,records[c]['codes']) for c in ids};metrics={};paired={}
    for name,rows in arms.items():
        for p,q in zip(old,rows):
            if p['caller_utterances']!=q['caller_utterances']:raise ValueError('turn predictions changed')
            e=check_model_output({k:copy.deepcopy(q[k]) for k in SCHEMA['properties']},records[q['call_id']])
            if e:raise ValueError('; '.join(e[:5]))
            q['review_triage']=triage(q)
        if name!='reviewed_v4':write_json(str(out/(name+'_predictions.json')),{'predictions':rows})
    for view in ['original_labels','reviewed_projection']:
        g=gold if view=='original_labels' else {c:project_for_scoring(gold[c],records[c]) for c in ids}
        funcs={};metrics[view]={};paired[view]={}
        for name,rows in arms.items():
            p={q['call_id']:q for q in rows}
            if view!='original_labels':p={c:project_for_scoring(p[c],records[c]) for c in ids}
            funcs[name]=prepared_statistics(ids,g,p)
            metrics[view][name]=[{'field':f,'score':funcs[name][f](ids)} for f in FIELDS]
        for name in ['alias_only','gaps_only','full_refinement']:
            paired[view][name]=[]
            for field in FIELDS:
                fa=funcs['reviewed_v4'][field];fb=funcs[name][field]
                def diff(s,fa=fa,fb=fb):
                    x,y=fa(s),fb(s);return None if x is None or y is None else y-x
                paired[view][name].append({'field':field,'difference':diff(ids),'ci95':bootstrap_ci(ids,diff)})
        print('SCORED_ABLATIONS',part,view,flush=True)
    summary={'calls':len(ids),'partition':part,'exploratory':True,'new_human_labels':0,'predeclared_design_sha256':file_hash(design),
        'metrics':metrics,'paired_minus_v4':paired,
        'novelty':{n:novelty_summary(novelty_rows(p,records,ref)) for n,p in arms.items()},
        'review':{n:audit(p,gold) for n,p in arms.items()},
        'qualification_outcome_nulls':{n:sum(q['qualification_outcome']['label'] is None for q in p) for n,p in arms.items()},
        'gaps_filled':sum(bool(q.get('refinement')) for q in arms['gaps_only']),
        'note':'No per-call selection against reference answers. Gaps-only preserves all original call/turn codes apart from eligible missing qualification outcomes. Full refinement is experimental after mixed development results.'}
    if part=='test':
        from coding.qual_kit import read_sheet
        human=read_sheet(root/'runs/agent/qualification_review/adjudicated_after_C_v1/adjudicated_sheet.csv')
        summary['qualification']={n:qualification(rows,human) for n,rows in arms.items()}
        original=root/'runs/agent/reviewed_20261126/test_analysis/summary.json'
        summary['original_pre_v4_qualification']=json.loads(original.read_text())['qualification']['original_model']
        pair=[]
        by={n:{p['call_id']:p['qualification_outcome']['label'] for p in rows} for n,rows in arms.items()}
        for name in ['gaps_only','full_refinement']:
            def difference(sample,name=name):return sum((by[name][c]==human[c])-(by['reviewed_v4'][c]==human[c]) for c in sample)/len(sample)
            pair.append({'arm':name,'accuracy_difference':difference(list(human)),'ci95':bootstrap_ci(list(human),difference)})
        summary['qualification_paired_accuracy_minus_v4']=pair
    write_json(str(out/'summary.json'),summary)
    with (out/'comparison.csv').open('w',newline='') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(['field']+list(arms))
        for i,field in enumerate(FIELDS):w.writerow([field]+[metrics['original_labels'][n][i]['score'] for n in arms])
    with (out/'gaps_only_review_triage.csv').open('w',newline='') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(['call_id','complete_call_review_required','actionable_review_required','evidence_gaps','actionable_issues'])
        for p in arms['gaps_only']:
            t=triage(p);w.writerow([p['call_id'],t['complete_call_review_required'],t['actionable_review_required'],json.dumps(t['evidence_gaps']),json.dumps(t['actionable_issues'])])
    inputs=[design,exp/'novelty_policy.json',exp/(part+'_analysis')/'refined_scoring.json',base/(part+'_run')/'predictions.json',Path(__file__)]
    if part=='test':inputs.append(root/'runs/agent/qualification_review/adjudicated_after_C_v1/adjudicated_sheet.csv')
    write_json(str(out/'manifest.json'),{'inputs':{str(p):file_hash(p) for p in inputs},'outputs':{p.name:file_hash(p) for p in out.iterdir() if p.is_file()}})
    print('COMPLETE_ABLATIONS',part,flush=True)


if __name__=='__main__':main()
