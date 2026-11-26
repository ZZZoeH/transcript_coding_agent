"""Optional fitting-only topic aliases and lexical support for candidate descriptions."""
import copy
import re
from .novelty import detect, tokens, vector, cosine


def key(text): return re.sub('[^a-z0-9]', '', text.casefold())


def refined_detect(record, reference, prediction, aliases, minimum=None, margin=0.0):
    p = copy.deepcopy(prediction)
    known = {key(k):k for k in reference['topics']}
    known.update({key(a):b for a,b in aliases.items() if b in reference['topics']})
    audit = []
    candidates = []
    for row in p.get('novelty_candidates', []):
        canonical = known.get(key(row['term'])) if row['kind']=='topic' else None
        reason = 'known_canonical_topic_or_existing_alias' if canonical else None
        if not canonical and row['kind']=='topic' and minimum is not None:
            v=vector(tokens(row['term']), reference['idf'])
            scores=sorted(((cosine(v,c),t) for t,c in reference['topics'].items()), reverse=True)
            if len(scores)>1 and scores[0][0]>=minimum and scores[0][0]-scores[1][0]>=margin:
                if scores[0][1] == p.get('subcategory') and len(set(tokens(row['term'])))>=2:
                    canonical=scores[0][1]; reason='fitting_centroid_support_agrees_with_predicted_known_topic'
        if canonical:
            audit.append({'term':row['term'],'canonical':canonical,'reason':reason})
        else: candidates.append(row)
    p['novelty_candidates']=candidates
    result=detect(record, reference, p)
    result['known_candidate_matches']=audit
    result['candidate_policy']={'minimum':minimum,'margin':margin,'aliases_source':'frozen fitting/reviewer profile'}
    return result


def apply(prediction, record, reference, aliases, minimum=None, margin=0.0):
    p=copy.deepcopy(prediction)
    p['novelty']=refined_detect(record,reference,p,aliases,minimum,margin)
    p['uncertainty']=[r for r in p.get('uncertainty',[]) if r['field']!='novelty']
    if p['novelty']['flagged']:
        p['uncertainty'].append({'field':'novelty','reason':', '.join(p['novelty']['reasons'])})
    p['review_required']=bool(p['uncertainty'])
    return p
