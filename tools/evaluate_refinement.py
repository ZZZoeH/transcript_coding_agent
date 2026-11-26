"""Paired exploratory comparison of frozen refinements, with unchanged full denominators."""
import argparse
import collections
import copy
import csv
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from coding.io_utils import ROOT, file_hash, load_records, read_ids, write_json
from coding.labels import normalize_codes
from coding.agreement import bootstrap_ci
from coding.reviewed_policies import project_for_scoring
from coding.novelty_refinement import apply
from coding.novelty import detect
from coding.refinement import triage
from coding.usage import summarize
from coding.validate import check_call
from tools.evaluate_live_run import prepare_scoring_predictions
from tools.evaluate_reviewed_results import FIELDS, prepared_statistics, summarize_stats, qualification, get, CALL_FIELDS, EXTRA_CALL


def novelty_rows(rows, records, reference):
    result=[]
    for p in rows:
        c=p['call_id'];topic=str(records[c]['codes'].get('subcategory') or '').strip().lower()
        group='withheld' if topic in reference['withheld_topics'] else ('known' if topic in reference['topics'] else 'naturally_unseen')
        result.append({'call_id':c,'group':group,'topic':topic,**p.get('novelty',detect(records[c],reference,p))})
    return result


def novelty_summary(rows):
    groups={}
    for group in ['known','withheld','naturally_unseen']:
        subset={r['call_id']:r['topic_flagged'] for r in rows if r['group']==group};n=len(subset)
        groups[group]={'n':n,'flagged':sum(subset.values()),'rate':sum(subset.values())/n if n else None,
            'ci95':bootstrap_ci(list(subset),lambda s:sum(subset[c] for c in s)/len(s)) if n else None}
    return {'groups':groups,'topic_flagged':sum(r['topic_flagged'] for r in rows),
            'organization_flagged':sum(r['organization_flagged'] for r in rows),
            'all_flagged':sum(r['flagged'] for r in rows),
            'candidate_alias_matches':sum(len(r.get('known_candidate_matches',[])) for r in rows)}


def choose_policy(exp, rows, base, records, reference, aliases):
    design=json.loads((exp/'design.json').read_text())
    baseline=novelty_summary(novelty_rows(base,records,reference))
    baseline_hits=baseline['groups']['withheld']['flagged']
    variants=[]
    for policy in design['novelty_candidates']:
        ps=[apply(p,records[p['call_id']],reference,aliases,**policy) for p in rows]
        stats=novelty_summary(novelty_rows(ps,records,reference))
        variants.append({'policy':policy,'metrics':stats,
            'eligible':(stats['groups']['withheld']['flagged']>=baseline_hits and
                (policy['minimum'] is None or baseline['groups']['withheld']['n']>0)),
            'lexical_overrides':sum(r['reason'].startswith('fitting_centroid') for p in ps for r in p['novelty']['known_candidate_matches'])})
    eligible=[v for v in variants if v['eligible']]
    selected=min(eligible,key=lambda v:(v['metrics']['groups']['known']['flagged'],v['lexical_overrides'],
        -(v['policy']['minimum'] or 1.0),-v['policy']['margin'])) if eligible else variants[0]
    result={'selected':selected['policy'],'selection_partition':'development_only',
        'baseline':baseline,'variants':variants,
        'development_withheld_calls':baseline['groups']['withheld']['n'],
        'unknown_recall_validated_in_this_development_comparison':baseline['groups']['withheld']['n']>0,
        'selection_guard':'Without unknown-topic development examples, accept canonical existing aliases only; do not select a lexical threshold from known negatives alone.',
        'inputs':{str(p):file_hash(p) for p in [exp/'dev_run/predictions.json',exp/'design.json',Path(__file__)]},
        'note':'Uses existing released development topic labels, not new human annotations. No qualification test answers enter selection. Small reused development sample; uncertainty remains.'}
    path=exp/'novelty_policy.json'
    if path.exists():
        if json.loads(path.read_text())!=result:raise ValueError('frozen novelty policy differs; use a new experiment')
    else:write_json(str(path),result)
    return result['selected']


def audit(rows, gold):
    total=len(rows);by_field={}
    for field in CALL_FIELDS+EXTRA_CALL:
        eligible=[p for p in rows if get(gold[p['call_id']],field) is not None]
        accepted=[p for p in eligible if get(p,field) is not None and not any(
            r['field']==field or field.startswith(r['field']+'.') or r['field'].startswith(field+'.') or r['field']=='pipeline'
            for r in p.get('uncertainty',[]))]
        differences=sum(get(p,field)!=get(gold[p['call_id']],field) for p in accepted)
        by_field[field]={'reference_annotated_calls':len(eligible),'accepted_calls':len(accepted),
            'coverage':len(accepted)/len(eligible) if eligible else None,
            'accepted_reference_disagreements':differences,
            'accepted_reference_disagreement_rate':differences/len(accepted) if accepted else None}
    return {'calls':total,'complete_call_review_required':sum(p.get('review_required',False) for p in rows),
        'actionable_review_calls':sum(triage(p)['actionable_review_required'] for p in rows),
        'evidence_gap_calls':sum(bool(triage(p)['evidence_gaps']) for p in rows),
        'evidence_gap_only_calls':sum(bool(triage(p)['evidence_gaps']) and not triage(p)['actionable_review_required'] for p in rows),
        'fully_unflagged_calls':sum(not p.get('review_required',False) for p in rows),
        'uncertainty_call_counts':dict(collections.Counter(f for p in rows for f in {r['field'] for r in p.get('uncertainty',[])})),
        'field_acceptance_audit':by_field,
        'note':'Acceptance means no emitted uncertainty on that field, not correctness. Reference disagreement is not independently adjudicated error. Evidence-gap-only calls still require review for complete-call coding.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('experiment',type=Path);parser.add_argument('partition',choices=['dev','test'])
    args=parser.parse_args();exp=args.experiment;part=args.partition;root=Path(ROOT)
    design=json.loads((exp/'design.json').read_text());base=root/design['base_experiment'];run=exp/(part+'_run');out=exp/(part+'_analysis')
    if out.exists():raise ValueError('analysis output already exists')
    ids=read_ids(exp/(part+'_ids.txt'));records=load_records()
    raw=json.loads((base/(part+'_run')/'predictions.json').read_text())['predictions']
    failed=json.loads((base/(part+'_run')/'failures.json').read_text())
    old=prepare_scoring_predictions(raw,failed,records,ids)
    new=json.loads((run/'predictions.json').read_text())['predictions']
    if [p['call_id'] for p in new]!=ids:raise ValueError('mismatched denominator or order')
    reference=json.loads((root/'runs/novelty/reference_calibrated.json').read_text());profile=json.loads((base/'profile_v4.json').read_text())
    if part=='dev':policy=choose_policy(exp,new,old,records,reference,profile['aliases']['subcategory'])
    else:policy=json.loads((exp/'novelty_policy.json').read_text())['selected']
    new=[apply(p,records[p['call_id']],reference,profile['aliases']['subcategory'],**policy) for p in new]
    for p,q in zip(old,new):
        if p['caller_utterances']!=q['caller_utterances']:raise ValueError('turn labels changed')
        if p['input_hash']!=q['input_hash']:raise ValueError('source identity changed')
        errors=check_call(q,records[q['call_id']],strict=True)
        if errors:raise ValueError(str(errors[:5]))
        q['review_triage']=triage(q)
    out.mkdir();write_json(str(out/'refined_scoring.json'),{'predictions':new})
    gold={c:normalize_codes(c,records[c]['codes']) for c in ids}
    results={};paired={}
    for view in ['original_labels','reviewed_projection']:
        g=gold if view=='original_labels' else {c:project_for_scoring(gold[c],records[c]) for c in ids}
        funcs={};results[view]={}
        for name,rows in [('reviewed_v4',old),('refined_v5',new)]:
            p={r['call_id']:r for r in rows}
            if view!='original_labels':p={c:project_for_scoring(p[c],records[c]) for c in ids}
            funcs[name]=prepared_statistics(ids,g,p);results[view][name]=summarize_stats(ids,funcs[name])
        paired[view]=[]
        for field in FIELDS:
            a=funcs['reviewed_v4'][field];b=funcs['refined_v5'][field]
            def diff(sample,a=a,b=b):
                x,y=a(sample),b(sample);return None if x is None or y is None else y-x
            paired[view].append({'field':field,'difference':diff(ids),'ci95':bootstrap_ci(ids,diff)})
        print('SCORED',part,view,flush=True)
    novelty={name:novelty_summary(novelty_rows(rows,records,reference)) for name,rows in [('reviewed_v4',old),('refined_v5',new)]}
    usage=summarize(run)
    usage['validated_calls']=len(new)-len(failed)
    usage['failed_calls']=len(failed)
    usage['retained_base_pipeline_abstentions']=len(failed)
    summary={'partition':part,'calls':len(ids),'exploratory':True,'new_human_annotations':0,
        'preserved_turn_predictions':True,'base_pipeline_abstentions':len(failed),
        'valid_refinement_calls':sum(bool(p.get('refinement')) for p in new),
        'refinement_fallbacks':json.loads((run/'refinement_failures.json').read_text()),
        'metrics':results,'paired_refined_minus_v4':paired,'novelty':novelty,
        'review':{'reviewed_v4':audit(old,gold),'refined_v5':audit(new,gold)},
        'qualification_outcome_nulls':{name:sum(p['qualification_outcome']['label'] is None for p in rows) for name,rows in [('reviewed_v4',old),('refined_v5',new)]},
        'new_api_usage_only':usage,'novelty_policy':policy,
        'cost_note':'Incremental refinement cost only, excludes the reused v4 run. Provider-reported saved responses, not complete billing.'}
    if part=='test':
        from coding.qual_kit import read_sheet
        human=read_sheet(root/'runs/agent/qualification_review/adjudicated_after_C_v1/adjudicated_sheet.csv')
        summary['qualification']={name:qualification(rows,human) for name,rows in [('reviewed_v4',old),('refined_v5',new)]}
    write_json(str(out/'summary.json'),summary)
    with (out/'original_label_metrics.csv').open('w',newline='') as f:
        writer=csv.writer(f,lineterminator='\n');writer.writerow(['field','metric','reviewed_v4','refined_v5','difference','ci95_difference'])
        for a,b,d in zip(results['original_labels']['reviewed_v4'],results['original_labels']['refined_v5'],paired['original_labels']):
            writer.writerow([a['field'],a['metric'],a['score'],b['score'],d['difference'],json.dumps(d['ci95'])])
    with (out/'review_triage.csv').open('w',newline='') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(['call_id','complete_call_review_required','actionable_review_required','evidence_gaps','actionable_issues'])
        for p in new:
            t=triage(p);w.writerow([p['call_id'],t['complete_call_review_required'],t['actionable_review_required'],json.dumps(t['evidence_gaps']),json.dumps(t['actionable_issues'])])
    paths=[run/'manifest.json',run/'predictions.json',exp/'design.json',exp/'novelty_policy.json',Path(__file__)]
    if part=='test':paths.append(root/'runs/agent/qualification_review/adjudicated_after_C_v1/adjudicated_sheet.csv')
    write_json(str(out/'manifest.json'),{'inputs':{str(p):file_hash(p) for p in paths},'outputs':{p.name:file_hash(p) for p in out.iterdir() if p.is_file()}})
    print('COMPLETE',part,len(ids),flush=True)


if __name__=='__main__':main()
