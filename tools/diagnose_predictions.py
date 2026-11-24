"""Produce numeric error diagnostics without changing labels, prompts or predictions."""
import argparse
import collections
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from coding.io_utils import load_records,read_ids,write_json,file_hash,INPUT_FILES
from coding.labels import normalize_codes
from coding.agreement import f1
from coding.evaluate import get
from coding.validate import validate


def diagnose(prediction_file,ids):
    errors=validate(prediction_file,ids)
    if errors:raise ValueError('; '.join(errors[:5]))
    records=load_records();pred={p['call_id']:p for p in json.loads(Path(prediction_file).read_text())['predictions']}
    gold={c:normalize_codes(c,records[c]['codes']) for c in ids}
    result={'calls':len(ids),'turn_fields':{},'call_field_prediction_distributions':{}}
    for field in ['persuasion','complementary_persuasion','functional_states','requested_info']:
        counts=collections.defaultdict(collections.Counter)
        for c in ids:
            proposed={t['turn_index']:set(t[field]) for t in pred[c]['caller_utterances']}
            for row in gold[c]['caller_utterances']:
                g=set(row[field]);p=proposed[row['turn_index']]
                for lab in g&p:counts[lab]['tp']+=1
                for lab in p-g:counts[lab]['fp']+=1
                for lab in g-p:counts[lab]['fn']+=1
        totals=collections.Counter()
        for row in counts.values():totals.update(row)
        precision,recall,score=f1(totals['tp'],totals['fp'],totals['fn'])
        labels=[]
        for lab,row in counts.items():
            p,r,f=f1(row['tp'],row['fp'],row['fn'])
            labels.append({'label':lab,**dict(row),'precision':p,'recall':r,'f1':f})
        result['turn_fields'][field]={'precision':precision,'recall':recall,'f1':score,
            'counts':dict(totals),'labels':sorted(labels,key=lambda r:-(r.get('tp',0)+r.get('fn',0)))}
    for field in ['category','subcategory','hook_phase.execution','hook_phase.only_greeting_turns','hook_phase.transfer.success']:
        result['call_field_prediction_distributions'][field]={
            'human':dict(collections.Counter(str(get(gold[c],field)) for c in ids)),
            'model':dict(collections.Counter(str(get(pred[c],field)) for c in ids))}
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('predictions',type=Path);parser.add_argument('ids_file',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if args.output.exists():parser.error('output already exists; choose a new path')
    result=diagnose(args.predictions,read_ids(args.ids_file));write_json(str(args.output),result)
    write_json(str(args.output.with_suffix('.manifest.json')),
       {'inputs':{str(p):file_hash(p) for p in [args.predictions,args.ids_file,Path(__file__),*map(Path,INPUT_FILES)]},
        'output_sha256':file_hash(args.output)})
    print(json.dumps({field:{k:v for k,v in value.items() if k!='labels'} for field,value in result['turn_fields'].items()},indent=2))
