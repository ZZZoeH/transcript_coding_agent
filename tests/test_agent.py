"""Offline tests: synthetic transcripts, mocked transport, and real split boundaries."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coding.agent import extract_output, finalize, payload_for, run
from coding.agreement import bootstrap_ci, kappa
from coding.io_utils import ROOT, load_records, read_ids, record_hash, file_hash
from coding.novelty import attach, build_reference, detect
from coding.novelty_eval import evaluate_novelty
from coding.review import queue_rows
from coding.schema import SCHEMA, coded_fields, check_model_output, schema_errors
from coding.time_savings import estimate
from coding.validate import check_call, validate


def record(call_id='dev', topic='medicare', text='Medicare coverage enrollment'):
    return {'call_id': call_id, 'conversation': [
        {'role': 'user', 'turn_index': 0, 'content': text},
        {'role': 'assistant', 'turn_index': 1, 'content': 'Yes, I have Medicare.'}],
        'codes': {'category': 'telemarketing', 'subcategory': topic, 'hook_phase': {}, 'caller_utterances': []}}


def output():
    p = {'category': 'telemarketing', 'subcategory': 'medicare',
         'hook_phase': {'exists': 'yes', 'execution': None, 'consent': 'no', 'only_greeting_turns': 0,
                        'caller_identification': {'name': 'none', 'organization': 'none'},
                        'qualification': {'question': ['possession_medicare']},
                        'transfer': {'intent': 'no', 'success': None, 'failure_reason': None}},
         'caller_utterances': [{'turn_index': 0, 'requested_info': ['possession_medicare'],
                                'persuasion': [], 'complementary_persuasion': [], 'functional_states': ['qualification']}],
         'evidence': [], 'uncertainty': [],
         'qualification_outcome': {'label': 'matches_profile', 'turn_indices': [0, 1]},
         'novelty_candidates': []}
    p['evidence'] = [{'field': path, 'turn_indices': [0]} for path in coded_fields(p)]
    return p


class ContractTests(unittest.TestCase):
    def test_valid_output_and_unknown_execution_review(self):
        rec = record(); ref = build_reference({'dev': rec}, ['dev'], [], [])
        self.assertEqual(check_model_output(output(), rec), [])
        p = finalize(output(), rec, ref)
        self.assertTrue(p['review_required'])
        self.assertEqual(p['observability']['accent'], 'not_observable')
        self.assertEqual(check_call(p, rec, strict=True), [])
        missing = output(); missing['hook_phase']['transfer']['intent'] = None
        missing['evidence'] = [row for row in missing['evidence'] if row['field'] != 'hook_phase.transfer.intent']
        revised = finalize(missing, rec, ref, vocabulary=[])
        fields = {row['field'] for row in revised['uncertainty']}
        self.assertIn('hook_phase.transfer.intent', fields)
        self.assertIn('caller_utterances.0.requested_info', fields)

    def test_schema_rejects_bad_types_and_extra_fields(self):
        for key, value in [('hook_phase', []), ('caller_utterances', None), ('category', 'invented')]:
            p = output(); p[key] = value
            self.assertTrue(check_model_output(p, record()))
        p = output(); p['secret'] = 'extra'
        self.assertTrue(schema_errors(p, SCHEMA))
        p = output(); p['hook_phase']['only_greeting_turns'] = True
        self.assertTrue(check_model_output(p, record()))
        self.assertTrue(check_call([], record()))

    def test_turn_completeness_evidence_and_transfer(self):
        for mutate in [lambda p: p['caller_utterances'].clear(),
                       lambda p: p['evidence'].pop(),
                       lambda p: p['evidence'][0].update(turn_indices=[999]),
                       lambda p: p['hook_phase']['transfer'].update(success='yes'),
                       lambda p: p['novelty_candidates'].append({'kind': 'organization', 'term': 'Acme', 'turn_indices': []})]:
            p = output(); mutate(p)
            self.assertTrue(check_model_output(p, record()))

    def test_input_tampering(self):
        rec = record(); ref = build_reference({'dev': rec}, ['dev'], [], [])
        p = finalize(output(), rec, ref)
        rec['conversation'][0]['content'] += ' changed'
        self.assertIn('transcript was changed', check_call(p, rec))

    def test_api_envelope(self):
        p = output()
        self.assertEqual(extract_output({'response': {'response': json.dumps(p)}})[0], p)
        self.assertEqual(extract_output({'response': {'response': p, 'metadata': {'model': 'test'}}})[0], p)
        self.assertEqual(extract_output({'response': json.dumps(p), 'metadata': {'model': 'test'}})[0], p)
        self.assertEqual(extract_output({'response': p, 'metadata': {}})[0], p)
        for bad in [{'response': {'response': '{broken'}}, {'error': 'denied'}, []]:
            with self.assertRaises(ValueError): extract_output(bad)


class NoveltyTests(unittest.TestCase):
    def setUp(self):
        self.records = {'a': record('a'), 'b': record('b', 'accident_claim', 'collision injury accident compensation'),
                        'test': record('test', 'accident_claim', 'collision injury accident compensation')}
        self.ref = build_reference(self.records, ['a', 'b'], ['test'], ['accident_claim'])

    def test_withheld_documents_excluded_and_no_test_leakage(self):
        self.assertEqual(self.ref['included_ids'], ['a'])
        self.assertNotIn('accident_claim', self.ref['topics'])
        self.assertNotIn('collision', self.ref['idf'])
        with self.assertRaises(ValueError): build_reference(self.records, ['a', 'test'], ['test'], [])

    def test_known_unknown_and_redactions(self):
        self.assertFalse(detect(self.records['a'], self.ref)['flagged'])
        self.assertTrue(detect(self.records['test'], self.ref)['flagged'])
        p = {'subcategory': 'medicare', 'novelty_candidates': [{'kind': 'organization', 'term': '*****', 'turn_indices': [0]}]}
        self.assertFalse(detect(self.records['a'], self.ref, p)['flagged'])
        p['novelty_candidates'][0]['term'] = 'Acme'
        self.assertTrue(detect(self.records['a'], self.ref, p)['flagged'])
        original = copy.deepcopy(self.ref); attach(p, self.records['a'], self.ref)
        self.assertEqual(original, self.ref)

    def test_eval_requires_complete_predictions_and_distinct_groups(self):
        result = evaluate_novelty(self.records, ['test'], self.ref)
        self.assertEqual(result['metrics']['withheld_recall']['rate'], 1)
        self.assertIsNone(result['metrics']['known_false_positive_rate']['rate'])
        with self.assertRaises(ValueError): evaluate_novelty(self.records, ['test'], self.ref, [])
        with self.assertRaises(ValueError): evaluate_novelty(self.records, ['a'], self.ref)

    def test_gold_and_withheld_metadata_do_not_reach_prompt(self):
        ref = copy.deepcopy(self.ref); ref['withheld_topics'] = ['DO_NOT_DISCLOSE_TARGET']
        rec = copy.deepcopy(self.records['a']); rec['codes']['secret'] = 'DO_NOT_DISCLOSE_GOLD'
        config = {'project_id': 'p', 'provider': 'test', 'model': 'test'}
        body = json.dumps(payload_for(rec, ref, [], config))
        self.assertNotIn('DO_NOT_DISCLOSE', body)
        self.assertIn('untrusted_transcript', body)
        self.assertIn('untrusted evidence', body)


class StatisticsTests(unittest.TestCase):
    def test_degenerate_and_empty_agreement(self):
        self.assertIsNone(kappa([], []))
        self.assertIsNone(kappa(['a'], ['a']))
        self.assertEqual(kappa(list('aaab'), list('aabb')), 0.5)
        with self.assertRaises(ValueError): kappa(['a'], [])
        self.assertIsNone(bootstrap_ci([], lambda s: 0))
        self.assertIsNone(bootstrap_ci(['a'], lambda s: None))

    def test_time_savings(self):
        p = estimate(100, 10, 5, 0.2, 60)
        self.assertEqual(p['assisted_labor_hours'], 160/60)
        self.assertAlmostEqual(p['fraction_labor_saved'], 0.84)
        with self.assertRaises(ValueError): estimate(0, 10, 5, 0.2)

    def test_queue_contains_failures_and_unknowns(self):
        rows = queue_rows([{'call_id': 'a', 'input_hash': 'h', 'uncertainty': [{'field': 'x', 'reason': 'unknown'}]}],
                          [{'call_id': 'b', 'input_hash': 'h2', 'reason': 'invalid output'}])
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r['status'] == 'pending' and r['review_seconds'] == '' for r in rows))


class RunnerTests(unittest.TestCase):
    def test_dry_run_mocked_live_failure_and_resume(self):
        records = load_records(); root = Path(ROOT)
        dev = read_ids(root/'splits/dev_ids.txt'); test = read_ids(root/'splits/test_ids.txt')
        ref = build_reference(records, dev, test)
        ref.update(dev_ids_sha256=file_hash(root/'splits/dev_ids.txt'), test_ids_sha256=file_hash(root/'splits/test_ids.txt'))
        config = {'project_id': 'test', 'provider': 'test', 'model': 'test', 'endpoint': 'https://example.invalid', 'timeout': 1}
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); ref_file = folder/'reference.json'; ref_file.write_text(json.dumps(ref))
            ids_file = folder/'ids.txt'; ids_file.write_text(dev[0]+'\n')
            with patch('coding.agent.post_query') as transport:
                run(ids_file, ref_file, folder/'dry', config, dry_run=True)
                transport.assert_not_called()
            self.assertFalse((folder/'dry/predictions.json').exists())
            with patch('coding.agent.KEY_FILE', ref_file):
                with patch('coding.agent.post_query', return_value={'response': {'response': {}}}):
                    failures = run(ids_file, ref_file, folder/'live', config)
                self.assertEqual(failures, 1)
                manifest = json.loads((folder/'live/manifest.json').read_text())
                self.assertEqual(manifest['status'], 'incomplete')
                self.assertNotIn('TEST_TOKEN_DO_NOT_LOG', json.dumps(manifest))
                # A valid model object for all real caller turns; semantic correctness is not asserted here.
                p = output(); p['caller_utterances'] = []
                for turn in records[dev[0]]['conversation']:
                    if turn['role'] == 'user':
                        p['caller_utterances'].append({'turn_index': turn['turn_index'], 'requested_info': [],
                                                      'persuasion': [], 'complementary_persuasion': [], 'functional_states': []})
                p['evidence'] = [{'field': key, 'turn_indices': [0]} for key in coded_fields(p)]
                with patch('coding.agent.post_query', return_value={'response': {'response': p}}) as transport:
                    self.assertEqual(run(ids_file, ref_file, folder/'live', config, resume=True), 0)
                    self.assertEqual(transport.call_count, 1)
                with patch('coding.agent.post_query') as transport:
                    self.assertEqual(run(ids_file, ref_file, folder/'live', config, resume=True), 0)
                    transport.assert_not_called()
                self.assertEqual(validate(folder/'live/predictions.json', [dev[0]], strict=True), [])
                checkpoint = next((folder/'live/calls').glob('*/prediction.json'))
                checkpoint.write_text('{}')
                with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                    run(ids_file, ref_file, folder/'live', config, resume=True)


if __name__ == '__main__': unittest.main()
