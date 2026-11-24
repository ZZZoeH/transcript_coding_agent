"""Prepare frozen, disjoint development examples, comparison IDs, and human cases."""
import argparse
import collections
import csv
import hashlib
import json
import random
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from coding.io_utils import ROOT,load_records,read_ids,record_hash,file_hash,write_json
from coding.labels import normalize_codes,MULTI_FIELDS
from coding.dev_profiles import VERSION,RULES,TOPIC_ALIASES,INFO_ALIASES,CLOSED_ALIASES

PRESSURE=re.compile(r'expir|deadline|limited time|last chance|final courtesy|close.{0,25}file|end.{0,15}enroll',re.I)


def stratified_sample(records,ids,n,seed):
    groups=collections.defaultdict(list)
    for c in ids:groups[records[c]['_bucket']].append(c)
    allocations={k:int(n*len(v)/len(ids)) for k,v in groups.items()}
    remainder=n-sum(allocations.values())
    order=sorted(groups,key=lambda k: (-(n*len(groups[k])/len(ids)-allocations[k]),k))
    for k in order[:remainder]:allocations[k]+=1
    selected=[];rng=random.Random(seed)
    for k in sorted(groups):
        candidates=sorted(groups[k]);rng.shuffle(candidates);selected.extend(candidates[:allocations[k]])
    return sorted(selected)


def make_cases(records,fit):
    categories=collections.defaultdict(list)
    for c in sorted(fit):
        rec=records[c];codes=normalize_codes(c,rec['codes']);conv=rec['conversation'];by={t['turn_index']:t for t in conv}
        for t in codes['caller_utterances']:
            text=by[t['turn_index']]['content'];kind=None;question=None;options=None
            if 'dh' in t['complementary_persuasion']:
                kind='dh_definition';question='Should DH follow the proposal definition (instructing false answers) or the original paper definition (illegal activity or being under another person\'s control)? Could this annotation be incorrect?';options=['proposal_definition','paper_definition','annotation_error','insufficient_evidence']
            elif 'time' in t['complementary_persuasion'] and not PRESSURE.search(text):
                kind='time_without_explicit_pressure';question='Which utterance provides evidence of time pressure for this TIME annotation? Should the label be retained, moved to another turn, or corrected?';options=['keep_with_evidence','move_to_other_turn','annotation_error','insufficient_evidence']
            if kind:categories[kind].append((c,t['turn_index'],question,options))
        text=' '.join(t['content'] for t in conv if t['role']=='user')
        if codes['subcategory']=='auto_warranty' and re.search('auto insurance|car insurance',text,re.I) and not re.search('warranty',text,re.I):
            categories['topic_boundary'].append((c,None,'Is this call about auto_warranty or auto_insurance? Please clarify the topic boundary and the appropriate label.',['keep_released_topic','different_topic','insufficient_evidence']))
        if codes['hook_phase']['execution']=='interaction_bot':
            categories['execution_observability'].append((c,None,'What textual evidence is sufficient to assign interaction_bot? Is audio or other metadata required?',['text_supports_label','requires_audio_or_metadata','insufficient_evidence']))
        if codes['hook_phase']['only_greeting_turns'] not in [None,0]:
            categories['greeting_definition'].append((c,None,'Which turns count as greetings: only consecutive opening greeting-only turns, all greeting-only turns, or turns that also include self-identification?',['initial_greeting_only','all_greeting_only','includes_identification','needs_other_rule']))
        seen={}
        for t in codes['caller_utterances']:
            key=re.sub(r'[^a-z0-9]','',by[t['turn_index']]['content'].lower())
            if len(key)<15:continue
            labels={f:t[f] for f in MULTI_FIELDS}
            if key in seen and labels!=seen[key][1]:
                categories['repeated_turn_annotation'].append((c,t['turn_index'],'The same question appears repeatedly with different annotations. Should each occurrence be labeled, only the first occurrence, or should the label depend on context?',['label_each_occurrence','label_first_only','context_dependent','annotation_error']))
                break
            seen[key]=(t['turn_index'],labels)
    result=[];used=set()
    order=['dh_definition','time_without_explicit_pressure','topic_boundary','execution_observability','greeting_definition','repeated_turn_annotation']
    for kind in order:
        chosen=0
        for c,index,question,options in categories[kind]:
            if c in used:continue
            rec=records[c];codes=normalize_codes(c,rec['codes'])
            result.append({'case_id':f'DEV-{len(result)+1:03d}','issue':kind,'call_id':c,'input_hash':record_hash(rec),
                'target_turn_index':index,'question':question,'decision_options':options,
                'conversation':rec['conversation'],'released_codes':codes,
                'model_predictions_included':False,'status':'pending_human_decision'})
            used.add(c);chosen+=1
            if chosen>=5:break
    for case in result:
        conv=case['conversation'];index=case['target_turn_index']
        if index is None:case['focused_context']=conv[:12]
        else:
            pos=next(i for i,t in enumerate(conv) if t['turn_index']==index)
            case['focused_context']=conv[max(0,pos-2):pos+3]
    return result


def export_decisions(output,cases):
    path=Path(output)/'team_decisions.csv'
    existing={}
    if path.exists():
        with path.open(encoding='utf-8-sig',newline='') as f:existing={r['case_id']:r for r in csv.DictReader(f)}
    fields=['case_id','issue','call_id','question','decision_options','released_value','focused_transcript',
            'decision','supporting_turn_indices','reviewer','notes']
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for c in cases:
            codes=c['released_codes'];kind=c['issue']
            if kind=='execution_observability':value=codes['hook_phase']['execution']
            elif kind=='greeting_definition':value=codes['hook_phase']['only_greeting_turns']
            elif kind=='topic_boundary':value=codes['subcategory']
            else:value=next((t for t in codes['caller_utterances'] if t['turn_index']==c['target_turn_index']),None)
            row={k:existing.get(c['case_id'],{}).get(k,'') for k in fields}
            row.update({k:c[k] for k in ['case_id','issue','call_id','question']})
            row['decision_options']=' | '.join(c['decision_options'])
            row['released_value']=json.dumps(value,ensure_ascii=False)
            row['focused_transcript']='\n'.join(f"[{t['turn_index']}] {'CALLER' if t['role']=='user' else 'CALLEE'}: {t['content']}" for t in c['focused_context'])
            w.writerow(row)


def make_examples(records,fit,case_calls,n=72):
    candidates=[];topic_counts=collections.Counter(normalize_codes(c,records[c]['codes'])['subcategory'] for c in fit)
    for c in sorted(set(fit)-case_calls):
        rec=records[c];gold=normalize_codes(c,rec['codes']);conv=rec['conversation'];positions={t['turn_index']:i for i,t in enumerate(conv)}
        for t in gold['caller_utterances']:
            pos=positions[t['turn_index']];source=conv[pos];text=source['content'];words=len(text.split())
            if not (1<=words<=110):continue
            if 'dh' in t['complementary_persuasion']:continue
            if 'time' in t['complementary_persuasion'] and not PRESSURE.search(text):continue
            context=conv[max(0,pos-2):min(len(conv),pos+3)]
            if sum(len(x['content'].split()) for x in context)>350:continue
            features={f+':'+lab for f in MULTI_FIELDS for lab in t[f]}
            if topic_counts[gold['subcategory']]>=5:features.add('topic:'+gold['subcategory'])
            if not t['complementary_persuasion'] and re.search(r'\btoday\b|good morning|how are you',text,re.I):features.add('negative:time')
            if all(not t[f] for f in MULTI_FIELDS):features.add('negative:all')
            if not features:continue
            candidates.append({'call_id':c,'turn_index':t['turn_index'],'input_hash':record_hash(rec),
                 'topic':gold['subcategory'],'target_text':text,'conversation_context':context,
                 'released_turn_codes':{f:t[f] for f in MULTI_FIELDS},'features':sorted(features),
                 'annotation_status':'released_annotation_not_independently_adjudicated'})
    desired={f for e in candidates for f in e['features'] if not f.startswith('requested_info:')}
    common=collections.Counter(lab for e in candidates for lab in e['released_turn_codes']['requested_info'])
    desired|={'requested_info:'+lab for lab,_ in common.most_common(22)}
    selected=[];covered=collections.Counter();per_call=collections.Counter()
    def gain(e):
        return sum((4 if f.startswith(('persuasion:','complementary_persuasion:','negative:')) else 1)/(1+covered[f]) for f in e['features'] if f in desired)
    remaining=list(candidates)
    while remaining and len(selected)<n:
        eligible=[e for e in remaining if per_call[e['call_id']]<2]
        if not eligible:break
        best=max(eligible,key=lambda e:(gain(e),-len(e['target_text']),e['call_id'],e['turn_index']))
        selected.append(best);covered.update(best['features']);per_call[best['call_id']]+=1;remaining.remove(best)
    return selected


def prepare(output,n=80):
    root=Path(ROOT);output=Path(output)
    if output.exists() and any(output.iterdir()):raise ValueError('output exists; choose a new experiment directory')
    records=load_records();dev=set(read_ids(root/'splits/dev_ids.txt'));test=set(read_ids(root/'splits/test_ids.txt'))
    ref_path=root/'runs/novelty/reference_calibrated.json';ref=json.loads(ref_path.read_text())
    fit=ref['included_ids'];cal=ref['calibration_ids']
    if set(fit)&set(cal) or not set(fit+cal)<=dev or set(fit+cal)&test:raise ValueError('development boundary violated')
    if not 1<=n<=len(cal)-4:raise ValueError('invalid comparison size')
    comparison=stratified_sample(records,cal,n,59803)
    pilot=[c for c in sorted(set(cal)-set(comparison)) if sum(t['role']=='user' for t in records[c]['conversation'])<=16][:4]
    cases=make_cases(records,fit);case_calls={c['call_id'] for c in cases}
    examples=make_examples(records,fit,case_calls)
    info=sorted({lab for c in fit for t in normalize_codes(c,records[c]['codes'])['caller_utterances'] for lab in t['requested_info']})
    aliases={'subcategory':{k:v for k,v in TOPIC_ALIASES.items() if v in ref['topics']},
             'requested_info':{k:v for k,v in INFO_ALIASES.items() if v in info},**CLOSED_ALIASES}
    profile={'version':VERSION,'rules':RULES,'fit_call_ids':sorted(fit),'example_call_ids':sorted({e['call_id'] for e in examples}),
         'examples':examples,'examples_per_request':8,'aliases':aliases,'known_topics':sorted(ref['topics']),
         'requested_info_labels':info,'excluded_case_call_ids':sorted(case_calls),
         'unresolved_decisions':['dh_definition','time_without_explicit_pressure','topic_boundary','execution_observability','greeting_definition','repeated_turn_annotation']}
    output.mkdir(parents=True,exist_ok=True)
    write_json(str(output/'profile.json'),profile)
    write_json(str(output/'team_review_cases.json'),{'case_count':len(cases),'model_blind':True,'role_legend':{'user':'caller','assistant':'callee'},'cases':cases})
    export_decisions(output,cases)
    for name,ids in [('comparison',comparison),('pilot',pilot),('fit',sorted(fit))]:
        (output/f'{name}_ids.txt').write_text('\n'.join(ids)+'\n')
    protected=[root/'README.md',root/'.gitignore',*sorted((root/'docs').rglob('*')),*sorted((root/'deliverables').rglob('*')),
               *sorted((root/'splits').rglob('*')),*sorted((root/'qual_sample').rglob('*'))]
    write_json(str(output/'design.json'),{'version':VERSION,'seed':59803,'comparison_calls':len(comparison),'pilot_calls':len(pilot),
        'fit_calls':len(fit),'examples':len(examples),'example_calls':len(profile['example_call_ids']),'team_cases':len(cases),
        'comparison_buckets':dict(collections.Counter(records[c]['_bucket'] for c in comparison)),
        'reference_sha256':file_hash(ref_path),'source_dev_ids_sha256':file_hash(root/'splits/dev_ids.txt'),
        'comparison_input_hashes':{c:record_hash(records[c]) for c in comparison},
        'protected_files':{str(p.relative_to(root)):file_hash(p) for p in protected if p.is_file()},
        'fitting_and_comparison_disjoint':not bool(set(fit)&set(comparison)),
        'test_ids_excluded':not bool(set(fit+comparison+pilot)&test)})
    return {'comparison_calls':len(comparison),'pilot_calls':len(pilot),'example_snippets':len(examples),'team_cases':len(cases)}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output');p.add_argument('--calls',type=int,default=80)
    a=p.parse_args();print(json.dumps(prepare(a.output,a.calls),ensure_ascii=False))
