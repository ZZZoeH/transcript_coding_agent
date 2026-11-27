"""Offline checks of reviewed rules, unchanged gold, and explicit exploratory opt-in."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from coding.io_utils import ROOT
from coding.reviewed_policies import (POLICY_ADDENDUM, SYSTEM_REPLACEMENTS, effective_system,
                                      evidence_indices, information_label, project_for_scoring)
from coding.prompts import SYSTEM
from coding.agent import run


class ReviewedPolicyTests(unittest.TestCase):
    def test_reviewed_prompt_replaces_conflicting_definitions_without_changing_control(self):
        result=effective_system(SYSTEM,{'system_replacements':SYSTEM_REPLACEMENTS,'system_addendum':POLICY_ADDENDUM})
        self.assertNotIn('action_bot prompts keypad action',result)
        self.assertNotIn('dh=instructing false answers.',result)
        self.assertIn('keypad/button response to continue or connect is interaction_bot',result)
        self.assertIn('action_bot prompts keypad action',SYSTEM)
        self.assertEqual(effective_system(SYSTEM,{}),SYSTEM)

    def test_projection_groups_repeats_and_maps_both_views_without_editing_inputs(self):
        record={'conversation':[{'role':'user','turn_index':2,'content':'Health conditions?'},
                                {'role':'assistant','turn_index':4,'content':'Yes'},
                                {'role':'user','turn_index':8,'content':'HEALTH conditions!'}]}
        p={'subcategory':'auto_insurance','hook_phase':{'qualification':{'question':['health_condition2']}},
           'caller_utterances':[{'turn_index':2,'requested_info':['health_condition1'],'persuasion':['auth'],
                                 'complementary_persuasion':[],'functional_states':['qualification']},
                                {'turn_index':8,'requested_info':['health_condition2'],'persuasion':['crc'],
                                 'complementary_persuasion':[],'functional_states':[]}]}
        before=copy.deepcopy(p);q=project_for_scoring(p,record)
        self.assertEqual(p,before)
        self.assertEqual(q['subcategory'],'auto_warranty')
        self.assertEqual(len(q['caller_utterances']),1)
        self.assertEqual(q['caller_utterances'][0]['requested_info'],['health_condition'])
        self.assertEqual(q['caller_utterances'][0]['persuasion'],['auth','crc'])
        self.assertEqual(q['hook_phase']['qualification']['question'],['health_condition'])
        self.assertEqual(information_label('diabetes'),'diabetes')
        # If the released annotation covers only the later repetition, compare at the first source occurrence.
        p['caller_utterances']=p['caller_utterances'][1:]
        self.assertEqual(project_for_scoring(p,record)['caller_utterances'][0]['turn_index'],2)

    def test_adjacent_evidence_groups_are_converted_with_trace(self):
        self.assertEqual(evidence_indices('[8][10]'),([8,10],'adjacent_bracket_groups_to_json_array'))
        self.assertEqual(evidence_indices('[0, 2]'),([0,2],None))
        self.assertEqual(evidence_indices(''),([],None))
        for value in ['[0][bad]','[true]','[0,0]']:
            with self.assertRaises(ValueError):evidence_indices(value)

    def test_reviewed_profile_test_inference_requires_explicit_opt_in(self):
        root=Path(ROOT);ref=root/'runs/novelty/reference_calibrated.json'
        fitting=json.loads(ref.read_text())['included_ids']
        profile={'version':'synthetic-reviewed-test','fit_call_ids':fitting,'example_call_ids':[],
                 'examples':[],'rules':'Synthetic test rules','aliases':{'subcategory':{},'requested_info':{}}}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'profile.json';p.write_text(json.dumps(profile))
            config={'profile_file':str(p),'provider':'test','model':'test','project_id':'test'}
            with patch('coding.agent.post_query') as api:
                with self.assertRaisesRegex(ValueError,'only run on development'):
                    run(root/'splits/test_ids.txt',ref,Path(tmp)/'blocked',config,dry_run=True,limit=1)
                config['allow_exploratory_test']=True
                run(root/'splits/test_ids.txt',ref,Path(tmp)/'explicit',config,dry_run=True,limit=1)
                api.assert_not_called()
            manifest=json.loads((Path(tmp)/'explicit/manifest.json').read_text())
            self.assertTrue(manifest['config']['allow_exploratory_test'])
            self.assertEqual(manifest['status'],'dry_run')


if __name__=='__main__':unittest.main()
