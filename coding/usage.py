"""Summarize recorded provider usage, including failed validation attempts."""
import argparse
import collections
import json
from pathlib import Path
from .io_utils import write_json


def summarize(folder):
    folder = Path(folder)
    manifest = json.loads((folder/'manifest.json').read_text())
    totals = collections.Counter()
    models = collections.Counter()
    responses = list(folder.glob('calls/**/response_*.json'))
    for path in responses:
        raw = json.loads(path.read_text())
        wrapper = raw.get('response')
        metadata = wrapper.get('metadata', {}) if isinstance(wrapper, dict) and 'response' in wrapper else raw.get('metadata', {})
        usage = metadata.get('usage_metric', {})
        for key in ['input_token_count','output_token_count','total_token_count',
                    'input_token_cost','output_token_cost','total_token_cost']:
            if isinstance(usage.get(key), (int,float)): totals[key] += usage[key]
        details = metadata.get('model_details', {})
        models[str(details.get('inference_provider','unknown'))+'/'+str(details.get('inference_model','unknown'))] += 1
    path = folder/'predictions.json'
    preds = json.loads(path.read_text())['predictions'] if path.exists() else []
    reviewed = sum(bool(p.get('review_required')) for p in preds)
    return {'run_status':manifest['status'], 'requested_calls':len(manifest['ids']),
            'validated_calls':len(preds), 'failed_calls':manifest.get('failed_calls',0),
            'recorded_model_responses':len(responses), 'provider_models':dict(models),
            'reported_usage_all_recorded_responses':dict(totals),
            'wall_seconds_this_invocation':manifest.get('runtime_seconds_this_invocation'),
            'reviewed_calls':reviewed, 'review_fraction':reviewed/len(preds) if preds else None,
            'multi_chunk_calls':sum(p.get('turn_chunks',1)>1 for p in preds),
            'normalization_operations':sum(len(p.get('normalizations',[])) for p in preds),
            'note':'Usage includes every saved model response, including rejected validation attempts; requests that failed without a usage response may not be included.'}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_directory');parser.add_argument('output')
    args=parser.parse_args()
    if Path(args.output).exists():parser.error('output already exists; choose a new path')
    result=summarize(args.run_directory);write_json(args.output,result);print(json.dumps(result,indent=2))
