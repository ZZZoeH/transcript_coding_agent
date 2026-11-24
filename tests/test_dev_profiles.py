import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from coding.agent import payload_for,run
from coding.dev_profiles import augment_query,normalize_labels,retrieve_examples,TOPIC_ALIASES,INFO_ALIASES
from coding.output_normalization import normalize_output
from coding.schema import check_model_output
from coding.io_utils import ROOT,load_records,read_ids,file_hash
from tools.prepare_dev_alignment import stratified_sample
from test_agent import output,record


def profile():
    example={'call_id':'fit','turn_index':0,'target_text':'Do you have Medicare or Medicaid?',
             'conversation_context':[{'role':'user','turn_index':0,'content':'Do you have Medicare or Medicaid?'}],
             'released_turn_codes':{'requested_info':['possession_medicare_medicaid']},
             'features':['requested_info:possession_medicare_medicaid']}
    return {'version':'test-profile','fit_call_ids':['fit'],'example_call_ids':['fit'],
            'examples':[example],'examples_per_request':8,'rules':'test rules',
            'aliases':{'subcategory':{'house_improvement':'home_improvement'},
                       'requested_info':{'date_of_birth':'dob'},'persuasion':{},
                       'complementary_persuasion':{},'functional_states':{}}}


class ProfileTests(unittest.TestCase):
    def test_examples_and_target_must_be_disjoint(self):
        with self.assertRaises(ValueError):augment_query({},record('fit'),profile())
        target=record('target');target['codes']['sentinel']='TARGET_GOLD_MUST_STAY_LOCAL'
        q=augment_query({'untrusted_transcript':{'call_id':target['call_id'],'conversation':target['conversation']}},target,profile())
        self.assertNotIn('TARGET_GOLD_MUST_STAY_LOCAL',json.dumps(q))
        self.assertEqual(q['fitting_examples'][0]['call_id'],'fit')

    def test_aliases_do_not_merge_different_concepts_or_invent_evidence(self):
        p=output();p['subcategory']='house_improvement';p['caller_utterances'][0]['requested_info']=['date_of_birth','possession_medicare','possession_medicaid']
        q,changes=normalize_labels(p,profile())
        self.assertEqual(q['subcategory'],'home_improvement')
        self.assertEqual(q['caller_utterances'][0]['requested_info'],['dob','possession_medicaid','possession_medicare'])
        self.assertEqual(q['evidence'],p['evidence'])
        self.assertTrue(changes)
        p['subcategory']='auto_insurance';q,_=normalize_labels(p,profile());self.assertEqual(q['subcategory'],'auto_insurance')
        self.assertNotIn('auto_insurance',TOPIC_ALIASES)
        self.assertNotIn('life_insurance',TOPIC_ALIASES)

    def test_unknown_labels_are_retained(self):
        p=output();p['subcategory']='Quantum Coverage';p['caller_utterances'][0]['requested_info']=['new_credential']
        q,_=normalize_labels(p,profile())
        self.assertEqual(q['subcategory'],'quantum_coverage')
        self.assertEqual(q['caller_utterances'][0]['requested_info'],['new_credential'])

    def test_retrieval_does_not_mutate_library(self):
        ref=profile();before=copy.deepcopy(ref)
        rows=retrieve_examples(record('target'),ref)
        rows[0]['released_turn_codes']['requested_info'].append('changed')
        self.assertEqual(ref,before)

    def test_control_profile_does_not_receive_examples(self):
        q=payload_for(record('target'),{'topics':{'medicare':{}},'confirmed_organizations':[]},[],
                      {'project_id':'p','provider':'p','model':'m'})
        self.assertNotIn('fitting_examples',json.loads(q['query']))

    def test_stratification_is_repeatable_and_without_duplicates(self):
        records={str(i):{'_bucket':str(i%3)} for i in range(60)}
        a=stratified_sample(records,list(records),20,59803)
        self.assertEqual(a,stratified_sample(records,list(records),20,59803))
        self.assertEqual(len(a),len(set(a)))

    def test_source_schema_is_bounded_and_does_not_change_control(self):
        from coding.dev_profiles import source_bound_schema
        from coding.schema import SCHEMA
        rec=record('target');rec['conversation'].append({'role':'user','turn_index':4,'content':'Your date of birth?'})
        before=copy.deepcopy(SCHEMA);schema=source_bound_schema(SCHEMA,rec)
        props=schema['properties']
        self.assertEqual(props['caller_utterances']['items']['properties']['turn_index']['enum'],[0,4])
        paths=props['evidence']['items']['properties']['field']['enum']
        self.assertIn('caller_utterances.4.requested_info',paths)
        self.assertNotIn('caller_utterances.1.requested_info',paths)
        self.assertNotIn('enum',props['caller_utterances']['items']['properties']['requested_info']['items'])
        self.assertNotIn('enum',props['uncertainty']['items']['properties']['reason'])
        self.assertEqual(SCHEMA,before)

    def test_chunk_contract_and_schema_use_the_same_source_subset(self):
        from coding.dev_profiles import source_bound_schema
        from coding.schema import SCHEMA
        from coding.agent import chunk_request
        rec=record('target');rec['conversation'].append({'role':'user','turn_index':4,'content':'Your name?'})
        body={'query':json.dumps({'target_contract':{'caller_turn_indices':[0,4]}}),
              'model_params':{'response_format':{'json_schema':{'schema':source_bound_schema(SCHEMA,rec)}}}}
        part=chunk_request(body,[4],True)
        self.assertEqual(json.loads(part['query'])['target_contract']['caller_turn_indices'],[4])
        self.assertEqual(part['model_params']['response_format']['json_schema']['schema']['properties']['evidence']['items']['properties']['turn_indices']['items']['enum'],[0,1,4])
        self.assertEqual(part['model_params']['response_format']['json_schema']['schema']['properties']['caller_utterances']['items']['properties']['turn_index']['enum'],[4])

    def test_unknown_numbered_codes_require_repair_without_erasing_unknown_concepts(self):
        from coding.dev_profiles import profile_contract_errors
        ref=profile();ref['requested_info_labels']=['health_condition1','health_condition2','age']
        p=output();p['caller_utterances'][0]['requested_info']=['health_condition85','new_diagnostic_test','covid19']
        errors=profile_contract_errors(p,ref)
        self.assertEqual(len(errors),1);self.assertIn('health_condition85',errors[0])
        self.assertEqual(p['caller_utterances'][0]['requested_info'][0],'health_condition85')
        p['caller_utterances'][0]['requested_info']=['health_condition1']
        self.assertEqual(profile_contract_errors(p,ref),[])

    def test_development_guard_blocks_test_inference_before_network(self):
        root=Path(ROOT);ref=root/'runs/novelty/reference_calibrated.json'
        # The request must be rejected before it loads examples or calls the transport.
        p=profile();p['fit_call_ids']=json.loads(ref.read_text())['included_ids'];p['example_call_ids']=p['fit_call_ids'][:1]
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'profile.json';f.write_text(json.dumps(p))
            with patch('coding.agent.post_query') as api:
                with self.assertRaisesRegex(ValueError,'only run on development'):
                    run(root/'splits/test_ids.txt',ref,Path(tmp)/'run',{'profile_file':str(f)},dry_run=True,limit=1)
                api.assert_not_called()


if __name__=='__main__':unittest.main()
