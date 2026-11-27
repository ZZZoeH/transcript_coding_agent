"""Refine only prediction-selected cases, preserving frozen source, gold and turn labels."""
import argparse
import concurrent.futures
import copy
import datetime
import hashlib
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from coding.agent import post_query, digest
from coding.refinement import VERSION, selection_mode, make_request, merge_refinement, accept, extract_output, triage
from coding.io_utils import ROOT, INPUT_FILES, file_hash, record_hash, load_records, read_ids, write_json
from coding.novelty_refinement import apply
from tools.evaluate_live_run import prepare_scoring_predictions


def run(base_experiment, experiment, partition, resume=False, workers=2, retries_only=False, scope='gaps-only'):
    if scope not in {'gaps-only', 'experimental-full'}:
        raise ValueError('scope must be gaps-only or experimental-full')
    root=Path(ROOT);out=experiment/(partition+'_run');records=load_records()
    design_path=experiment/'design.json';design=json.loads(design_path.read_text())
    ids=read_ids(experiment/(partition+'_ids.txt'))
    source=base_experiment/(partition+'_run')
    manifest=json.loads((source/'manifest.json').read_text())
    if manifest['ids']!=ids:raise ValueError('base and refined denominators differ')
    profile_path=base_experiment/'profile_v4.json';profile=json.loads(profile_path.read_text())
    ref_path=root/'runs/novelty/reference_calibrated.json';reference=json.loads(ref_path.read_text())
    config=copy.deepcopy(manifest['config']);config['profile_file']=str(profile_path.resolve())
    raw=json.loads((source/'predictions.json').read_text())['predictions']
    failures=json.loads((source/'failures.json').read_text())
    bases=prepare_scoring_predictions(raw,failures,records,ids)
    paths=[source/'manifest.json',source/'predictions.json',source/'failures.json',profile_path,ref_path,design_path,
           experiment/(partition+'_ids.txt'),root/'codebook.txt',root/'qual_sample/coding_guide.md',Path(__file__),
           *[Path(p) for p in INPUT_FILES],*sorted((root/'coding').glob('*.py'))]
    policy_path=experiment/'novelty_policy.json'
    if partition=='test':
        if not policy_path.exists():raise ValueError('Freeze the development-selected novelty policy before test inference')
        paths.append(policy_path)
    fingerprints={str(p.relative_to(root)):file_hash(p) for p in paths}
    identity=digest({'inputs':fingerprints,'version':VERSION,'partition':partition,'scope':scope})
    if out.exists() and not resume:raise ValueError('output exists; explicit resume required')
    out.mkdir(parents=True,exist_ok=True)
    existing=out/'manifest.json'
    if existing.exists():
        previous=json.loads(existing.read_text())
        if previous['identity']!=identity:raise ValueError('resume inputs or implementation changed')
        for path,h in previous.get('outputs',{}).items():
            if not (out/path).exists() or file_hash(out/path)!=h:raise ValueError('resume output fingerprint mismatch')
    else: previous={}
    started=time.monotonic()
    m={'version':VERSION,'status':'running','identity':identity,'ids':ids,'partition':partition,
       'exploratory':True,'scope':scope,'config':config,'inputs':fingerprints,'workers_this_invocation':workers,
       'started_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
       'previous_invocations':previous.get('previous_invocations',[])+([{'runtime_seconds':previous.get('runtime_seconds_this_invocation'),'status':previous['status']}] if previous else [])}
    write_json(str(existing),m)
    policy=(json.loads(policy_path.read_text())['selected'] if partition=='test' else {'minimum':None,'margin':0.0})
    def finish(p):
        p=apply(p,records[p['call_id']],reference,profile['aliases']['subcategory'],**policy)
        p['review_triage']=triage(p)
        return p
    def process(base):
        c=base['call_id'];record=records[c];mode=selection_mode(base,scope)
        if base['input_hash']!=record_hash(record):raise ValueError('base transcript hash mismatch')
        if mode is None:return finish(base),None
        folder=out/'calls'/hashlib.sha256(c.encode()).hexdigest()[:24];folder.mkdir(parents=True,exist_ok=True)
        saved=folder/'prediction.json';failed=folder/'failure.json'
        if saved.exists():return finish(json.loads(saved.read_text())),None
        if failed.exists() and not retries_only:
            return finish(base),json.loads(failed.read_text())
        request=make_request(record,reference,profile['requested_info_labels'],config,profile,mode)
        try:
            for repair in range(3):
                n=len(list(folder.glob('request_*.json')))+1
                write_json(str(folder/f'request_{n:03d}.json'),request)
                response=post_query(request,config['endpoint'],config['timeout'])
                write_json(str(folder/f'response_{n:03d}.json'),response)
                try:
                    output,metadata=extract_output(response)
                    schema=request['model_params']['response_format']['json_schema']['schema']
                    from coding.schema import schema_errors
                    errors=schema_errors(output,schema)
                    if errors:raise ValueError('; '.join(errors[:20]))
                    p=accept(base,output,record,reference,profile['requested_info_labels'],profile,mode)
                    p['refinement']['provider_metadata']=metadata
                    write_json(str(saved),p)
                    return finish(p),None
                except (ValueError,KeyError,TypeError) as error:
                    if repair==2:raise
                    query=json.loads(request['query'])
                    query['validation_repair']={'errors':str(error)[:1800],'previous_output':output if 'output' in locals() else None,
                        'instructions':'Correct only the output contract using the original target evidence. Do not invent evidence.'}
                    request['query']=json.dumps(query,ensure_ascii=False)
        except (ValueError,RuntimeError,KeyError,TypeError) as error:
            failure={'call_id':c,'mode':mode,'reason':str(error)[:1800],'base_prediction_retained':True}
            write_json(str(failed),failure)
            return finish(base),failure
    predictions={};pass_failures=[]
    selected=[p for p in bases if selection_mode(p,scope)]
    print('SELECTED',partition,len(selected),'of',len(ids),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(process,p):p['call_id'] for p in bases}
        for future in concurrent.futures.as_completed(futures):
            p,failure=future.result();predictions[p['call_id']]=p
            if failure:pass_failures.append(failure)
            write_json(str(out/'predictions.json'),{'predictions':[predictions[c] for c in ids if c in predictions]})
            write_json(str(out/'refinement_failures.json'),pass_failures)
            if p.get('refinement') or failure:print('REFINED',partition,p['call_id'],p.get('refinement',{}).get('mode'), 'fallback' if failure else 'accepted',flush=True)
    write_json(str(out/'failures.json'),[]) # All base failures remain explicit abstention objects in predictions.
    m.update(status='complete',selected_calls=len(selected),refinement_failures=len(pass_failures),
             base_pipeline_abstentions=len(failures),runtime_seconds_this_invocation=round(time.monotonic()-started,3))
    m['outputs']={str(p.relative_to(out)):file_hash(p) for p in out.rglob('*.json') if p!=existing}
    write_json(str(existing),m)
    print('COMPLETE',partition,len(predictions),'refinement_failures',len(pass_failures),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('base',type=Path);p.add_argument('experiment',type=Path)
    p.add_argument('partition',choices=['dev','test']);p.add_argument('--resume',action='store_true');p.add_argument('--retry-failures',action='store_true');p.add_argument('--workers',type=int,default=2)
    p.add_argument('--scope',choices=['gaps-only','experimental-full'],default='gaps-only',
        help='Fill missing qualification outcomes by default; full global recoding is experimental.')
    a=p.parse_args();run(a.base.resolve(),a.experiment.resolve(),a.partition,a.resume,a.workers,a.retry_failures,a.scope)
