"""Compare control, exact-alias ablation and aligned examples on development only."""
import argparse
import ast
import collections
import csv
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from coding.io_utils import ROOT,load_records,read_ids,file_hash,write_json
from coding.evaluate import evaluate
from coding.compare import compare
from coding.baseline import code_call
from coding.dev_profiles import normalize_labels
from coding.usage import summarize
from tools.evaluate_live_run import prepare_scoring_predictions
from tools.diagnose_predictions import diagnose


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('experiment',type=Path)
    p.add_argument('--candidate-directory',type=Path);p.add_argument('--output-directory',type=Path)
    p.add_argument('--exploratory-retune',action='store_true')
    a=p.parse_args();exp=a.experiment;root=Path(ROOT);out=a.output_directory or exp/'comparison'
    candidate=a.candidate_directory or exp/'improved'
    if out.exists() and any(out.iterdir()):p.error('comparison output exists; choose a new experiment')
    ids=read_ids(exp/'comparison_ids.txt');dev=set(read_ids(root/'splits/dev_ids.txt'))
    if not set(ids)<=dev:p.error('development IDs only')
    improved_manifest=json.loads((candidate/'manifest.json').read_text())
    profile_path=Path(improved_manifest['config']['profile_file'])
    profile=json.loads(profile_path.read_text());design=json.loads((exp/'design.json').read_text())
    if set(ids)&set(profile['fit_call_ids']):p.error('fitting/comparison overlap')
    records=load_records();out.mkdir(parents=True,exist_ok=True);paths={};meta={}
    for arm in ['control','improved']:
        folder=candidate if arm=='improved' else exp/arm;manifest=json.loads((folder/'manifest.json').read_text())
        if manifest['status'] not in ['complete','incomplete']:raise ValueError('inference has not finished')
        if manifest['ids']!=ids:raise ValueError('run IDs do not match design')
        raw=json.loads((folder/'predictions.json').read_text())['predictions'];failed=json.loads((folder/'failures.json').read_text())
        scored=prepare_scoring_predictions(raw,failed,records,ids)
        paths[arm]=out/(arm+'_scoring.json');write_json(str(paths[arm]),{'predictions':scored})
        meta[arm]={'valid_model_outputs':len(raw),'explicit_abstentions':len(failed),'usage':summarize(folder),
                   'prompt_version':manifest['prompt_version'],
                   'execution':json.loads((folder/'execution_summary.json').read_text())}
    paths['rule_baseline']=out/'rule_baseline_scoring.json'
    write_json(str(paths['rule_baseline']),{'predictions':[code_call(records[c]) for c in ids]})
    control=json.loads(paths['control'].read_text())['predictions'];canonical=[];changes=[]
    for pred in control:
        row,ops=normalize_labels(pred,profile);canonical.append(row)
        changes.extend({'call_id':pred['call_id'],**op} for op in ops)
    paths['control_alias_only']=out/'control_alias_only_scoring.json'
    write_json(str(paths['control_alias_only']),{'predictions':canonical,'normalizations':changes,
        'review_status_note':'Scoring ablation only; original uncertainty flags retained, no claim of recalibrated review decisions.'})
    tables={}
    for arm,path in paths.items():
        rows=[]
        for line in evaluate(path,ids,extended=True).splitlines()[2:]:
            field,score,ci=[x.strip() for x in line.strip('|').split('|')]
            rows.append({'metric':field,'score':None if score=='undefined' else float(score),'ci95':ast.literal_eval(ci)})
        tables[arm]=rows
        write_json(str(out/(arm+'_diagnostics.json')),diagnose(path,ids))
        print('SCORED',arm,flush=True)
    paired=compare(paths['control'],paths['improved'],ids)
    paired.update({'comparison':'original v2 versus aligned examples+aliases','partition':'development_only'})
    write_json(str(out/'paired_comparison.json'),paired)
    write_json(str(out/'alias_only_comparison.json'),compare(paths['control'],paths['control_alias_only'],ids))
    protected_changed=[name for name,wanted in design['protected_files'].items() if file_hash(root/name)!=wanted]
    if protected_changed:raise ValueError('protected files changed: '+str(protected_changed))
    summary={'calls':len(ids),'partition':'development_comparison_not_final_test','seed':59803,
        'examples_from_disjoint_fitting_pool':True,'example_snippets':len(profile['examples']),
        'pending_human_cases':(json.loads((exp/'team_review_cases_all.json').read_text())['case_count'] if (exp/'team_review_cases_all.json').exists() else design['team_cases']),'profile_version':profile['version'],'test_inference_performed':False,'same_development_ids_used_for_retuning':a.exploratory_retune,
        'documentation_and_original_splits_unchanged':True,'arms':meta,'metrics':tables,
        'alias_only_operations':len(changes),'unresolved_policies':profile['unresolved_decisions']}
    write_json(str(out/'summary.json'),summary)
    with (out/'metric_comparison.csv').open('w',newline='') as f:
        w=csv.writer(f);order=['rule_baseline','control','control_alias_only','improved'];w.writerow(['metric']+order)
        for i,row in enumerate(tables['control']):w.writerow([row['metric']]+[tables[k][i]['score'] for k in order])
    inputs=[profile_path,exp/'design.json',exp/'comparison_ids.txt',Path(__file__)]
    for folder in [exp/'control',candidate]:inputs.extend([folder/'manifest.json',folder/'predictions.json',folder/'failures.json'])
    write_json(str(out/'manifest.json'),{'inputs':{str(p):file_hash(p) for p in inputs},
         'outputs':{p.name:file_hash(p) for p in out.iterdir() if p.is_file() and p.name!='manifest.json'}})
    print('SUMMARY',json.dumps({k:v for k,v in summary.items() if k!='metrics'}),flush=True)


if __name__=='__main__':main()
