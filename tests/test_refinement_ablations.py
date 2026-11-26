"""The conservative ablation must not overwrite existing answers or unrelated coding."""
import copy
import unittest
from tools.evaluate_refinement_ablations import gaps_only


class ConservativeAblationTests(unittest.TestCase):
    def fixture(self):
        return {'hook_phase':{'qualification':{'question':['possession_medicare']},'execution':None},
            'caller_utterances':[{'turn_index':7,'requested_info':['possession_medicare']}],
            'qualification_outcome':{'label':None,'turn_indices':[]},
            'uncertainty':[{'field':'qualification_outcome','reason':'missing'},
                           {'field':'hook_phase.execution','reason':'unknown'}]}

    def test_fill_missing_outcome_keeps_all_other_fields_and_their_warnings(self):
        base=self.fixture();before=copy.deepcopy(base);refined=copy.deepcopy(base)
        refined['qualification_outcome']={'label':'matches_profile','turn_indices':[7,8]}
        refined['hook_phase']['execution']='human';refined['uncertainty']=[];refined['refinement']={'mode':'global'}
        result=gaps_only(base,refined)
        self.assertEqual(base,before);self.assertEqual(result['qualification_outcome'],refined['qualification_outcome'])
        self.assertEqual(result['hook_phase'],base['hook_phase']);self.assertEqual(result['caller_utterances'],base['caller_utterances'])
        self.assertEqual(result['uncertainty'],base['uncertainty'][1:])

    def test_no_existing_outcome_or_unqualified_case_is_overwritten(self):
        base=self.fixture();refined=copy.deepcopy(base)
        refined.update(qualification_outcome={'label':'matches_profile','turn_indices':[7,8]},refinement={'mode':'global'})
        base['qualification_outcome']={'label':'call_terminates','turn_indices':[7]}
        self.assertEqual(gaps_only(base,refined),base)
        base['qualification_outcome']={'label':None,'turn_indices':[]};base['hook_phase']['qualification']['question']=[]
        self.assertEqual(gaps_only(base,refined),base)


if __name__=='__main__':unittest.main()
