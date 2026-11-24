import io
import json
import secrets
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from coding import asu_api
from coding.agent import merge_chunks, process_call
from coding.novelty import build_reference
from coding.schema import check_model_output, coded_fields
from test_agent import record, output


class Response:
    def __init__(self, data): self.data = json.dumps(data).encode()
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): return self.data


class CredentialTests(unittest.TestCase):
    def test_each_retry_rereads_file_and_removes_echoed_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'key.text'
            first, second = secrets.token_hex(24), secrets.token_hex(24)
            p.write_text(first)
            seen = []
            class Opener:
                def open(self, request, timeout):
                    seen.append(request.get_header('Authorization'))
                    if len(seen) == 1:
                        p.write_text(second)
                        raise urllib.error.HTTPError(request.full_url, 429, 'retry', {}, io.BytesIO())
                    return Response({'response': second})
            with patch.object(asu_api, 'KEY_FILE', p), patch.object(asu_api.urllib.request, 'build_opener', return_value=Opener()), patch.object(asu_api.time, 'sleep'):
                value = asu_api.request_json('https://api-main.aiml.asu.edu/query', {'query': 'test'})
            self.assertEqual(seen, ['Bearer '+first, 'Bearer '+second])
            self.assertEqual(value, {'response': '[REDACTED]'})
            self.assertNotIn(second, json.dumps(value))

    def test_unapproved_destinations_never_read_or_send_key(self):
        for endpoint in ['http://api-main.aiml.asu.edu/query', 'https://example.com/query',
                         'https://api-main.aiml.asu.edu.evil.example/query',
                         'https://api-main.aiml.asu.edu/query?token=unsafe',
                         'https://user@api-main.aiml.asu.edu/query']:
            with patch.object(asu_api, 'read_api_key') as reader:
                with self.assertRaises(ValueError): asu_api.request_json(endpoint)
                reader.assert_not_called()

    def test_environment_key_is_not_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp)/'missing.text'
            with patch.object(asu_api, 'KEY_FILE', missing), patch.dict('os.environ', {'ASU_API_KEY': secrets.token_hex(24)}):
                with self.assertRaisesRegex(ValueError, 'local ASU key file'): asu_api.read_api_key()

    def test_http_errors_do_not_include_server_body(self):
        secret = secrets.token_hex(24)
        error = urllib.error.HTTPError('https://api-main.aiml.asu.edu/query', 401, secret, {}, io.BytesIO(secret.encode()))
        with patch.object(asu_api, 'read_api_key', return_value=secret), patch.object(asu_api.urllib.request.OpenerDirector, 'open', side_effect=error):
            with self.assertRaises(RuntimeError) as raised: asu_api.request_json('https://api-main.aiml.asu.edu/query', {})
        self.assertNotIn(secret, str(raised.exception))


def two_turn_record():
    rec = record()
    rec['conversation'].append({'role': 'user', 'turn_index': 2, 'content': 'Do you have Medicare?'})
    return rec


def partial(index):
    p = output()
    p['caller_utterances'][0]['turn_index'] = index
    p['evidence'] = [{'field': field, 'turn_indices': [index]} for field in coded_fields(p)]
    return p


class ChunkTests(unittest.TestCase):
    def test_merge_preserves_exact_source_turn_indices(self):
        rec = two_turn_record()
        a, b = partial(0), partial(2)
        self.assertEqual(check_model_output(a, rec, [0]), [])
        self.assertEqual(check_model_output(b, rec, [2]), [])
        self.assertEqual(check_model_output(merge_chunks([a,b]), rec), [])
        b['category'] = 'vishing_co'
        merged = merge_chunks([a,b])
        self.assertEqual(merged['category'], a['category'])
        self.assertTrue(any('disagree' in row['reason'] for row in merged['uncertainty']))

    def test_greeting_count_uses_whole_call_not_chunk_size(self):
        rec=two_turn_record()
        rec['conversation'].extend([{'role':'assistant','turn_index':3,'content':'Hello'},
                                    {'role':'user','turn_index':4,'content':'Do you have Medicare?'}])
        p=partial(4);p['hook_phase']['only_greeting_turns']=2
        for row in p['evidence']:
            if row['field']=='hook_phase.only_greeting_turns':row['turn_indices']=[0,2]
        self.assertEqual(check_model_output(p,rec,[4]),[])

    def test_validation_repair_retains_both_api_attempts(self):
        rec = record(); ref = build_reference({'dev':rec}, ['dev'], [], [])
        config = {'provider':'test', 'model':'test', 'project_id':'test', 'endpoint':'https://example.invalid', 'timeout':1}
        replies = [{'response':{}, 'metadata':{'usage_metric':{'total_token_count':11}}},
                   {'response':output(), 'metadata':{'usage_metric':{'total_token_count':12}}}]
        with tempfile.TemporaryDirectory() as tmp, patch('coding.agent.post_query', side_effect=replies) as api:
            pred, failure = process_call(rec, ref, [], config, Path(tmp), False)
            self.assertIsNone(failure)
            self.assertEqual(pred['api_attempts'], 2)
            self.assertEqual(api.call_count, 2)
            self.assertEqual(len(list(Path(tmp).glob('calls/*/chunk_*/response_*.json'))), 2)

    def test_resume_skips_accepted_chunk_of_failed_call(self):
        rec = two_turn_record(); ref = build_reference({'dev':rec}, ['dev'], [], [])
        config = {'provider':'test', 'model':'test', 'project_id':'test', 'endpoint':'https://example.invalid', 'timeout':1, 'turns_per_chunk':1}
        with tempfile.TemporaryDirectory() as tmp:
            with patch('coding.agent.post_query', side_effect=[{'response':partial(0)}, RuntimeError('network failure')]):
                pred, failure = process_call(rec, ref, [], config, Path(tmp), False)
                self.assertIsNone(pred); self.assertIsNotNone(failure)
            with patch('coding.agent.post_query', return_value={'response':partial(2)}) as api:
                pred, failure = process_call(rec, ref, [], config, Path(tmp), True)
                self.assertIsNone(failure); self.assertEqual(api.call_count, 1)
                self.assertEqual([t['turn_index'] for t in pred['caller_utterances']], [0,2])


class NormalizationTests(unittest.TestCase):
    def test_empty_and_duplicate_evidence_are_safe_to_canonicalize(self):
        from coding.output_normalization import normalize_output
        p = output(); p['evidence'].append({'field':'caller_utterances.0.persuasion','turn_indices':[0]})
        p['evidence'].append(dict(p['evidence'][0]))
        canonical, changes = normalize_output(p)
        self.assertEqual(check_model_output(canonical, record()), [])
        self.assertEqual(len(changes), 2)
        self.assertNotEqual(p, canonical)

    def test_compatibility_projection_keeps_evidence_and_missing_evidence_fails(self):
        from coding.output_normalization import normalize_output
        p = output(); p['caller_utterances'][0]['complementary_persuasion'] = ['nag','dh']
        p['evidence'].append({'field':'caller_utterances.0.complementary_persuasion','turn_indices':[0]})
        canonical, changes = normalize_output(p)
        self.assertEqual(canonical['caller_utterances'][0]['persuasion'], ['crc','dis'])
        self.assertEqual(check_model_output(canonical, record()), [])
        canonical['evidence'] = [row for row in canonical['evidence'] if row['field'] != 'category']
        canonical, changes = normalize_output(canonical)
        self.assertIn('missing evidence: category', check_model_output(canonical, record()))

    def test_organization_flags_do_not_inflate_topic_recall(self):
        from coding.novelty import detect
        rec=record(); ref=build_reference({'dev':rec},['dev'],[],[])
        pred={'subcategory':'medicare','novelty_candidates':[{'kind':'organization','term':'Acme','turn_indices':[0]}]}
        result=detect(rec,ref,pred)
        self.assertTrue(result['flagged']); self.assertTrue(result['organization_flagged'])
        self.assertFalse(result['topic_flagged'])


if __name__ == '__main__': unittest.main()
