"""Resume an immutable run with fewer simultaneous HTTP calls and an upstream circuit breaker."""
import argparse
import json
import sys
import threading
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from coding import agent
from coding.io_utils import ROOT,write_json,file_hash


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('experiment',type=Path)
    p.add_argument('--concurrency',type=int,default=2);p.add_argument('--failure-limit',type=int,default=6)
    p.add_argument('--audit-name',default='runtime_recovery_01.json');a=p.parse_args()
    if a.concurrency<1 or a.failure_limit<1:p.error('limits must be positive')
    exp=a.experiment;folder=exp/'test_run';saved=json.loads((folder/'manifest.json').read_text());root=Path(ROOT)
    # Preserve immutable config and source identity; only HTTP dispatch is throttled externally.
    gate=threading.Semaphore(a.concurrency);lock=threading.Lock();state={'requests':0,'upstream_errors':0,'consecutive':0,'circuit_open':False}
    original=agent.post_query
    def request(*args,**kwargs):
        with gate:
            with lock:
                if state['circuit_open']:raise RuntimeError('Deferred without transmission after repeated upstream errors; resume after recovery')
                state['requests']+=1
            try:result=original(*args,**kwargs)
            except RuntimeError as error:
                if any(code in str(error) for code in ['HTTP 500','HTTP 502','HTTP 503','HTTP 504','HTTP 429']):
                    with lock:
                        state['upstream_errors']+=1;state['consecutive']+=1
                        if state['consecutive']>=a.failure_limit:state['circuit_open']=True
                raise
            with lock:state['consecutive']=0
            return result
    agent.post_query=request;started=time.monotonic()
    try:
        failures=agent.run(exp/'test_ids.txt',root/'runs/novelty/reference_calibrated.json',folder,saved['config'],resume=True)
    finally:
        agent.post_query=original
        write_json(str(exp/a.audit_name),{'effective_HTTP_concurrency':a.concurrency,'thread_workers_in_frozen_config':saved['config']['workers'],
            'failure_limit':a.failure_limit,'state':state,'wall_seconds':round(time.monotonic()-started,3),
            'source_and_prompt_unchanged':True,'wrapper_sha256':file_hash(Path(__file__))})
    raise SystemExit(1 if failures else 0)


if __name__=='__main__':main()
