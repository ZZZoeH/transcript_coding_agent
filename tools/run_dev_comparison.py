"""Run the two frozen development arms with bounded total API concurrency."""
import concurrent.futures
import json
import shutil
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from coding.agent import run,PROJECT,ENDPOINT
from coding.io_utils import ROOT,read_ids,write_json,file_hash


def main():
    root=Path(ROOT);exp=Path(sys.argv[1]).resolve();ids=exp/'comparison_ids.txt'
    selected=read_ids(ids);dev=set(read_ids(root/'splits/dev_ids.txt'))
    if not set(selected)<=dev:raise ValueError('Development comparison must exclude all test IDs')
    for arm in ['control','improved']:
        if (exp/arm).exists():raise ValueError('Arm already exists; do not overwrite frozen runs')
    snapshot=exp/'benchmark_source_snapshot'
    snapshot.mkdir(exist_ok=False)
    for src in sorted((root/'coding').glob('*.py')):
        target=snapshot/'coding'/src.name;target.parent.mkdir(exist_ok=True);shutil.copy2(src,target)
    common={'provider':'openai','model':'gpt4_1','project_id':PROJECT,'endpoint':ENDPOINT,
            'timeout':180,'workers':4,'turns_per_chunk':32,'validation_repairs':2}
    configs={'control':dict(common),'improved':{**common,'profile_file':str((exp/'profile_v2.json').resolve())}}
    def execute(arm):
        folder=exp/arm;started=time.monotonic();invocations=1
        failed=run(ids,root/'runs/novelty/reference_calibrated.json',folder,configs[arm])
        if failed:
            shutil.copy2(folder/'manifest.json',folder/'manifest_before_retry_01.json');invocations+=1
            failed=run(ids,root/'runs/novelty/reference_calibrated.json',folder,configs[arm],resume=True)
        result={'arm':arm,'requested_calls':len(selected),'remaining_failures':failed,
                'invocations':invocations,'total_wall_seconds':round(time.monotonic()-started,3)}
        write_json(str(folder/'execution_summary.json'),result)
        print('ARM_FINISHED',json.dumps(result),flush=True)
        return result
    started=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(execute,['control','improved']))
    write_json(str(exp/'execution_summary.json'),{'partition':'development_only','maximum_combined_workers':8,
        'wall_seconds':round(time.monotonic()-started,3),'arms':results,
        'source_hashes':{str(p.relative_to(snapshot)):file_hash(p) for p in snapshot.rglob('*.py')}})


if __name__=='__main__':main()
