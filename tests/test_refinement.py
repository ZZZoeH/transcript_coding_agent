"""Contract and leakage guards for independent second passes and review triage."""
import copy
import json
import unittest
from coding.refinement import make_request, merge_refinement, mode_for, selection_mode, triage
from coding.novelty_refinement import apply, refined_detect
from coding.novelty import build_reference
from coding.schema import SCHEMA, coded_fields
from coding.io_utils import ROOT
from pathlib import Path


def fixture():
    record={'call_id':'synthetic', 'conversation':[
        {'role':'user','turn_index':2,'content':'Do you have Medicare?'},
        {'role':'assistant','turn_index':9,'content':'Yes.'}], 'codes':{'never_send':'TARGET_GOLD'}}
    p={'category':'telemarketing','subcategory':'medicare',
       'hook_phase':{'exists':'yes','execution':None,'consent':'no','only_greeting_turns':0,
          'caller_identification':{'name':'none','organization':'none'},
          'qualification':{'question':['possession_medicare']},
          'transfer':{'intent':'no','success':None,'failure_reason':None}},
       'caller_utterances':[{'turn_index':2,'requested_info':['possession_medicare'],
           'persuasion':[],'complementary_persuasion':[],'functional_states':['qualification']}],
       'evidence':[], 'uncertainty':[], 'qualification_outcome':{'label':None,'turn_indices':[]},
       'novelty_candidates':[],'review_required':True}
    p['evidence']=[{'field':f,'turn_indices':[2]} for f in coded_fields(p)]
    profile={'aliases':{'subcategory':{},'requested_info':{}},'requested_info_labels':['possession_medicare']}
    return record,p,profile


class RefinementTests(unittest.TestCase):
    def test_second_pass_cannot_change_turns_and_rejects_invented_evidence(self):
        record,base,profile=fixture();before=copy.deepcopy(base)
        out={k:copy.deepcopy(base[k]) for k in ['category','subcategory','hook_phase','qualification_outcome','novelty_candidates','evidence','uncertainty']}
        out['evidence']=[r for r in out['evidence'] if not r['field'].startswith('caller_utterances.')]
        out['evidence']={r['field']:r['turn_indices'] for r in out['evidence']}
        out['qualification_outcome']={'label':'matches_profile','turn_indices':[2,9]}
        merged,_=merge_refinement(base,out,record,profile,'global')
        self.assertEqual(base,before);self.assertEqual(merged['caller_utterances'],base['caller_utterances'])
        out['qualification_outcome']['turn_indices']=[999]
        with self.assertRaisesRegex(ValueError,'invalid candidate/outcome turn'):
            merge_refinement(base,out,record,profile,'global')

    def test_outcome_pass_owns_only_outcome_and_keeps_other_uncertainty(self):
        record,base,profile=fixture()
        base['uncertainty']=[{'field':'hook_phase.execution','reason':'unknown'}, {'field':'qualification_outcome','reason':'missing'}]
        out={'qualification_outcome':{'label':'matches_profile','turn_indices':[2,9]},'uncertainty':[]}
        merged,_=merge_refinement(base,out,record,profile,'qualification')
        self.assertEqual(merged['hook_phase'],base['hook_phase'])
        self.assertEqual(merged['uncertainty'],base['uncertainty'][:1])
        out['subcategory']='accident_claim'
        with self.assertRaises(ValueError):merge_refinement(base,out,record,profile,'qualification')

    def test_selection_uses_only_predictions_and_keeps_pipeline_abstention(self):
        _,p,_=fixture();self.assertEqual(mode_for(p),'qualification')
        p['turn_chunks']=2;self.assertEqual(mode_for(p),'global')
        p['pipeline_status']='abstained';self.assertIsNone(mode_for(p))

    def test_adopted_default_only_fills_missing_outcomes_even_for_long_calls(self):
        from inspect import signature
        from tools.refine_saved_run import run
        self.assertEqual(signature(run).parameters['scope'].default, 'gaps-only')
        _,p,_=fixture();p['turn_chunks']=2
        self.assertEqual(selection_mode(p), 'qualification')
        p['qualification_outcome']={'label':'matches_profile','turn_indices':[2,9]}
        self.assertIsNone(selection_mode(p))
        self.assertEqual(selection_mode(p,'experimental-full'), 'global')
        p['pipeline_status']='abstained'
        self.assertIsNone(selection_mode(p))

    def test_invalid_scope_is_rejected_before_loading_data_or_calling_api(self):
        from unittest.mock import patch
        from tools.refine_saved_run import run
        with self.assertRaises(ValueError):selection_mode({},'unrecognized')
        with patch('tools.refine_saved_run.load_records') as loader, patch('tools.refine_saved_run.post_query') as api:
            with self.assertRaises(ValueError):run(None,None,'dev',scope='unrecognized')
            loader.assert_not_called();api.assert_not_called()

    def test_reduced_schema_and_payload_do_not_leak_gold_or_mutate_schema(self):
        record,p,profile=fixture();ref={'topics':{'medicare':{}},'confirmed_organizations':[]}
        config={'project_id':'synthetic','provider':'test','model':'test',
                'profile_file':str(Path(ROOT)/'runs/agent/reviewed_20261126/profile_v4.json')}
        before=copy.deepcopy(SCHEMA)
        for mode in ['global','qualification']:
            request=make_request(record,ref,[],config,profile,mode)
            self.assertNotIn('TARGET_GOLD',json.dumps(request))
            props=request['model_params']['response_format']['json_schema']['schema']['properties']
            self.assertNotIn('caller_utterances',props)
            self.assertEqual(json.loads(request['query'])['untrusted_transcript'],
                {k:record[k] for k in ['call_id','conversation']})
        self.assertEqual(SCHEMA,before)

    def test_triage_does_not_claim_evidence_gaps_are_resolved(self):
        _,p,_=fixture();p['uncertainty']=[{'field':'hook_phase.execution','reason':'not established'}]
        t=triage(p);self.assertTrue(t['complete_call_review_required'])
        self.assertFalse(t['actionable_review_required']);self.assertEqual(len(t['evidence_gaps']),1)
        p['uncertainty'].append({'field':'category','reason':'ambiguous'})
        self.assertTrue(triage(p)['actionable_review_required'])

    def test_alias_match_preserves_candidates_and_does_not_hide_unknown_topics_or_organizations(self):
        record,p,_=fixture();record['codes']={'subcategory':'medicare'}
        ref=build_reference({'synthetic':record},['synthetic'],[],[])
        p['novelty_candidates']=[{'kind':'topic','term':'Medicare benefits','turn_indices':[2]},
            {'kind':'topic','term':'accident claim','turn_indices':[2]},
            {'kind':'organization','term':'Medicare benefits','turn_indices':[2]}]
        before=copy.deepcopy(p)
        result=apply(p,record,ref,{'medicare_benefits':'medicare'})
        self.assertEqual(p,before);self.assertEqual(len(result['novelty_candidates']),3)
        self.assertEqual(len(result['novelty']['known_candidate_matches']),1)
        self.assertIn('unconfirmed_topic',result['novelty']['reasons'])
        self.assertIn('unconfirmed_organization',result['novelty']['reasons'])


if __name__=='__main__':unittest.main()
