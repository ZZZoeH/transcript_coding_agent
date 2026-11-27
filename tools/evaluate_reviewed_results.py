"""Aggregate original and coarser reviewed metrics without modifying source gold or past runs."""
import argparse
import collections
import copy
import csv
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from coding.io_utils import ROOT,load_records,read_ids,write_json,file_hash
from coding.labels import normalize_codes
from coding.evaluate import get,CALL_FIELDS,TURN_FIELDS
from coding.agreement import bootstrap_ci,kappa,f1
from coding.reviewed_policies import project_for_scoring
from coding.qualification_eval import score as qualification_score
from coding.novelty_eval import evaluate_novelty
from coding.usage import summarize
from coding.validate import validate
from tools.evaluate_live_run import prepare_scoring_predictions

EXTRA_CALL=['hook_phase.exists','hook_phase.caller_identification.name',
            'hook_phase.caller_identification.organization','hook_phase.transfer.failure_reason']
FIELDS=CALL_FIELDS+EXTRA_CALL+TURN_FIELDS+['hook_phase.qualification.question']


def prepared_statistics(ids,gold,pred):
    stats={}
    for field in FIELDS:
        if field in CALL_FIELDS+EXTRA_CALL:
            pairs={c:(get(gold[c],field),get(pred[c],field)) if get(gold[c],field) is not None else None for c in ids}
            def statistic(sample,pairs=pairs):
                rows=[pairs[c] for c in sample if pairs[c] is not None]
                return kappa([g for g,_ in rows],[p for _,p in rows])
        else:
            counts={}
            for c in ids:
                tp=fp=fn=0
                if field=='hook_phase.qualification.question':
                    pairs=[(set(get(gold[c],field)),set(get(pred[c],field)))]
                else:
                    guessed={u['turn_index']:set(u[field]) for u in pred[c]['caller_utterances']}
                    pairs=[(set(u[field]),guessed[u['turn_index']]) for u in gold[c]['caller_utterances']]
                for g,p in pairs:tp+=len(g&p);fp+=len(p-g);fn+=len(g-p)
                counts[c]=(tp,fp,fn)
            def statistic(sample,counts=counts):
                tp=fp=fn=0
                for c in sample:
                    row=counts[c];tp+=row[0];fp+=row[1];fn+=row[2]
                return f1(tp,fp,fn)[2]
        stats[field]=statistic
    return stats


def summarize_stats(ids,stats):
    return [{'field':f,'metric':'kappa' if f in CALL_FIELDS+EXTRA_CALL else 'micro_f1',
             'score':stats[f](ids),'ci95':bootstrap_ci(ids,stats[f])} for f in FIELDS]


def qualification(predictions,human):
    result=qualification_score(predictions,human)
    by={p['call_id']:p.get('qualification_outcome',{}).get('label') for p in predictions}
    labels=['matches_profile','mismatch_call_continues','call_terminates']
    matrix={g:{p:0 for p in labels+['abstain']} for g in labels}
    for c,g in human.items():matrix[g][by[c] if by[c] in labels else 'abstain']+=1
    answered=[c for c in human if by[c] in labels]
    result.update({'coverage':len(answered)/len(human),
        'answered_accuracy':sum(by[c]==human[c] for c in answered)/len(answered) if answered else None,
        'all_errors_are_abstentions':len(result['disagreements'])==result['model_abstentions'],
        'confusion_rows_human_columns_model':matrix,
        'always_matches_profile_accuracy':sum(g=='matches_profile' for g in human.values())/len(human),
        'note':'Abstentions remain errors in full-denominator accuracy and kappa. Answered accuracy is conditional; not evidence of superhuman reliability.'})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('experiment',type=Path);parser.add_argument('partition',choices=['dev','test'])
    args=parser.parse_args();exp=args.experiment;part=args.partition;root=Path(ROOT)
    out=exp/(part+'_analysis');run=exp/(part+'_run')
    if out.exists():parser.error('Use a new output directory rather than overwrite analysis')
    ids=read_ids(exp/(part+'_ids.txt'));records=load_records();profile=json.loads((exp/'profile_v4.json').read_text())
    manifest=json.loads((run/'manifest.json').read_text())
    if manifest['ids']!=ids or manifest['status'] not in ['complete','incomplete']:raise ValueError('Run not finished or IDs differ')
    raw=json.loads((run/'predictions.json').read_text())['predictions'];failed=json.loads((run/'failures.json').read_text())
    reviewed=prepare_scoring_predictions(raw,failed,records,ids)
    if part=='dev':
        control=root/'runs/agent/dev_alignment_20261123/comparison/control_scoring.json'
        v3=root/'runs/agent/dev_alignment_20261123/comparison_v3/improved_scoring.json'
        baseline=root/'runs/agent/dev_alignment_20261123/comparison/rule_baseline_scoring.json'
    else:
        control=root/'runs/agent/test_gpt41_20261123_w8/analysis/scoring_predictions.json'
        baseline=root/'runs/baseline/test_predictions.json';v3=None
    paths={'rule_baseline':baseline,'original_model':control}
    if v3:paths['profile_v3']=v3
    arms={k:json.loads(p.read_text())['predictions'] for k,p in paths.items()};arms['reviewed_v4']=reviewed
    for name,path in paths.items():
        errors=validate(path,ids)
        if errors:raise ValueError(name+': '+str(errors[:2]))
    if any({p['call_id'] for p in rows}!=set(ids) for rows in arms.values()):raise ValueError('Unequal call denominators')
    out.mkdir(parents=True);write_json(str(out/'reviewed_scoring.json'),{'predictions':reviewed})
    gold={c:normalize_codes(c,records[c]['codes']) for c in ids};results={};functions={}
    for view in ['original_labels','reviewed_projection']:
        g=gold if view=='original_labels' else {c:project_for_scoring(gold[c],records[c]) for c in ids}
        results[view]={};functions[view]={}
        for name,rows in arms.items():
            p={row['call_id']:row for row in rows}
            if view!='original_labels':p={c:project_for_scoring(p[c],records[c]) for c in ids}
            functions[view][name]=prepared_statistics(ids,g,p)
            results[view][name]=summarize_stats(ids,functions[view][name])
            print('SCORED',part,view,name,flush=True)
    paired={}
    for view in results:
        paired[view]={}
        for comparison in ['rule_baseline','original_model']:
            rows=[]
            for field in FIELDS:
                a=functions[view][comparison][field];b=functions[view]['reviewed_v4'][field]
                def difference(sample,a=a,b=b):
                    x,y=a(sample),b(sample)
                    return None if x is None or y is None else y-x
                rows.append({'field':field,'difference':difference(ids),'ci95':bootstrap_ci(ids,difference)})
            paired[view]['reviewed_v4_minus_'+comparison]=rows
    usage=summarize(run)
    for previous in run.glob('manifest_before_retry_*.json'):
        usage['wall_seconds_this_invocation']+=json.loads(previous.read_text()).get('runtime_seconds_this_invocation',0)
    summary={'calls':len(ids),'partition':part,'profile_version':profile['version'],
        'exploratory':True,'reused_development' :part=='dev','previously_inspected_test':part=='test',
        'valid_outputs':len(raw),'explicit_abstentions':len(failed),'metrics':results,'paired_differences':paired,
        'usage':usage,'review_queue_calls':sum(bool(p.get('review_required')) for p in reviewed),
        'projection_note':'Secondary view maps auto_insurance and numbered health labels symmetrically, then unions exact repeated utterances within calls. It changes label granularity and scoring unit; it does not replace original-label metrics.'}
    if part=='test':
        from coding.qual_kit import read_sheet
        human=read_sheet(root/'runs/agent/qualification_review/adjudicated_after_C_v1/adjudicated_sheet.csv')
        summary['qualification']={name:qualification(rows,human) for name,rows in arms.items() if name!='rule_baseline'}
        reference=json.loads((root/'runs/novelty/reference_calibrated.json').read_text())
        summary['novelty']={}
        for name in ['original_model','reviewed_v4']:
            value=evaluate_novelty(records,ids,reference,arms[name]);value.pop('calls_detail',None)
            summary['novelty'][name]=value
    write_json(str(out/'summary.json'),summary)
    for view in results:
        with (out/(view+'_metrics.csv')).open('w',newline='') as f:
            names=list(arms);writer=csv.writer(f,lineterminator='\n');writer.writerow(['field','metric']+names)
            for index,field in enumerate(FIELDS):writer.writerow([field,results[view][names[0]][index]['metric']]+[results[view][name][index]['score'] for name in names])
    inputs=[exp/'design.json',exp/'profile_v4.json',run/'manifest.json',run/'predictions.json',run/'failures.json',Path(__file__),*paths.values()]
    if part=='test':inputs.append(root/'runs/agent/qualification_review/adjudicated_after_C_v1/adjudicated_sheet.csv')
    write_json(str(out/'manifest.json'),{'inputs':{str(p):file_hash(p) for p in inputs},
               'outputs':{p.name:file_hash(p) for p in out.iterdir() if p.is_file()}})
    print('COMPLETE',part,len(ids),flush=True)


if __name__=='__main__':main()
