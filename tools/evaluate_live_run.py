"""Score every requested call; keep model failures visible as explicit abstentions."""
import argparse
import ast
import collections
import csv
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coding.io_utils import ROOT, load_records, read_ids, record_hash, write_json, file_hash
from coding.validate import validate, check_call
from coding.evaluate import evaluate
from coding.compare import compare
from coding.novelty_eval import evaluate_novelty
from coding.review import queue_rows
from coding.usage import summarize


def abstention(record, failure):
    return {'call_id':record['call_id'], 'input_hash':record_hash(record),
        'category':None, 'subcategory':None,
        'hook_phase':{'exists':None, 'execution':None, 'consent':None, 'only_greeting_turns':None,
                      'caller_identification':{'name':None,'organization':None},
                      'qualification':{'question':[]},
                      'transfer':{'intent':None,'success':None,'failure_reason':None}},
        'caller_utterances':[{'turn_index':t['turn_index'], 'requested_info':[], 'persuasion':[],
                              'complementary_persuasion':[], 'functional_states':[]}
                             for t in record['conversation'] if t['role']=='user'],
        'evidence':[], 'uncertainty':[{'field':'pipeline','reason':failure['reason']}],
        'qualification_outcome':{'label':None,'turn_indices':[]}, 'novelty_candidates':[],
        'review_required':True, 'pipeline_status':'abstained_after_invalid_or_failed_model_response'}


def prepare_scoring_predictions(raw, failures, records, ids):
    pred={p['call_id']:p for p in raw}; failed={p['call_id']:p for p in failures}
    if len(pred)!=len(raw) or len(failed)!=len(failures) or pred.keys() & failed.keys():
        raise ValueError('duplicate/overlapping prediction and failure IDs')
    if pred.keys() | failed.keys() != set(ids):
        raise ValueError('run is incomplete; every requested call must finish first')
    result=[]
    for c in ids:
        p=pred[c] if c in pred else abstention(records[c],failed[c])
        errors=check_call(p,records[c],strict=True)
        if errors:raise ValueError('invalid scoring record: '+c+': '+'; '.join(errors[:5]))
        result.append(p)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_directory',type=Path)
    parser.add_argument('--output-directory',type=Path)
    parser.add_argument('--ids-file',type=Path,default=Path(ROOT)/'splits/test_ids.txt')
    parser.add_argument('--reference',type=Path,default=Path(ROOT)/'runs/novelty/reference_calibrated.json')
    args=parser.parse_args();run=args.run_directory.resolve();out=args.output_directory or run/'analysis'
    if out.exists() and any(out.iterdir()):parser.error('analysis output exists; choose a new directory')
    manifest=json.loads((run/'manifest.json').read_text())
    if manifest['status'] not in ['complete','incomplete']:parser.error('inference has not finished')
    ids=read_ids(args.ids_file);records=load_records()
    raw=json.loads((run/'predictions.json').read_text())['predictions']
    failures=json.loads((run/'failures.json').read_text())
    preds=prepare_scoring_predictions(raw,failures,records,ids)
    out.mkdir(parents=True,exist_ok=True)
    scoring_file=out/'scoring_predictions.json'
    write_json(str(scoring_file),{'system':'asu_createai_agent_full_denominator',
         'requested_calls':len(ids),'valid_model_outputs':len(raw),'explicit_abstentions':len(failures),
         'scoring_note':'Failed model calls receive null categories and empty label sets; they count as disagreement/missed labels, not successful model output.',
         'predictions':preds})
    errors=validate(scoring_file,ids,strict=True)
    if errors:raise ValueError('; '.join(errors[:5]))
    print('SCORING_CONTRACT_VALID',len(preds),'calls;',len(failures),'explicit abstentions',flush=True)
    rows=[]
    for line in evaluate(scoring_file,ids,extended=True).splitlines()[2:]:
        field,score,interval=[cell.strip() for cell in line.strip('|').split('|')]
        rows.append({'field_metric':field,'score':None if score=='undefined' else float(score),
                     'ci95':ast.literal_eval(interval)})
    write_json(str(out/'scores.json'),{'calls':len(ids),'valid_model_outputs':len(raw),
         'explicit_abstentions':len(failures),'bootstrap_unit':'call','bootstrap_rounds':1000,'seed':598,'metrics':rows})
    print('SCORES',json.dumps(rows),flush=True)
    paired=compare(Path(ROOT)/'runs/baseline/test_predictions.json',scoring_file,ids)
    write_json(str(out/'comparison.json'),paired)
    print('PAIRED_COMPARISON_COMPLETE',flush=True)
    ref=json.loads(args.reference.read_text())
    novelty=evaluate_novelty(records,ids,ref,preds)
    write_json(str(out/'novelty.json'),novelty)
    write_json(str(out/'reference_only_novelty.json'),evaluate_novelty(records,ids,ref))
    print('NOVELTY',json.dumps({k:v for k,v in novelty.items() if k!='calls_detail'}),flush=True)
    usage=summarize(run)
    prior_seconds=0
    continuation=run/'continuation.json'
    if continuation.exists(): prior_seconds+=json.loads(continuation.read_text()).get('parent_elapsed_seconds',0)
    for prior in run.glob('manifest_before_retry_*.json'):
        prior_seconds+=json.loads(prior.read_text()).get('runtime_seconds_this_invocation',0)
    usage['total_recorded_active_wall_seconds']=prior_seconds+(usage.get('wall_seconds_this_invocation') or 0)
    write_json(str(out/'usage.json'),usage)
    print('USAGE',json.dumps(usage),flush=True)
    queue=queue_rows(raw,failures)
    with (out/'review_queue.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['call_id','input_hash','reasons','candidates','status','review_seconds','reviewer','notes'])
        writer.writeheader();writer.writerows(queue)
    reasons=collections.Counter(row['field'] for p in raw for row in p.get('uncertainty',[]))
    quality={'requested_calls':len(ids),'valid_model_outputs':len(raw),'failed_model_calls':len(failures),
         'raw_model_completion_rate':len(raw)/len(ids),'scoring_calls_including_abstentions':len(preds),
         'scoring_caller_turns':sum(len(p['caller_utterances']) for p in preds),
         'scoring_contract_errors':0,'review_calls':len(queue),'review_fraction':len(queue)/len(ids),
         'uncertainty_fields':dict(reasons.most_common()),
         'qualification_human_sheets':{name:sum(bool(row['outcome'].strip()) for row in csv.DictReader((Path(ROOT)/f'qual_sample/sheet_{name}.csv').open())) for name in ['A','B']}}
    write_json(str(out/'quality.json'),quality)
    inputs=[run/'manifest.json',run/'predictions.json',run/'failures.json',args.ids_file,args.reference,Path(__file__)]
    write_json(str(out/'analysis_manifest.json'),{'inputs':{str(p):file_hash(p) for p in inputs},
          'outputs':{p.name:file_hash(p) for p in out.iterdir() if p.is_file() and p.name!='analysis_manifest.json'}})
    print('QUALITY',json.dumps(quality),flush=True)


if __name__=='__main__':main()
