"""Independent metric cross-checks and mocked protection against repeated upstream failures."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from coding import agent
from coding.evaluate import call_kappa,turn_f1,CALL_FIELDS,TURN_FIELDS
from tools.evaluate_reviewed_results import prepared_statistics,EXTRA_CALL
from tools import resume_rate_limited
from test_agent import output


class ReviewedAnalysisTests(unittest.TestCase):
    def test_compact_statistics_match_reference_metrics(self):
        gold={c:copy.deepcopy(output()) for c in ['a','b']}
        gold['b']['category']='vishing_gov';pred=copy.deepcopy(gold)
        for c in gold:
            gold[c]['caller_utterances'][0]['requested_info']=['age']
            gold[c]['hook_phase']['qualification']['question']=['age']
        pred['a']['caller_utterances'][0]['requested_info']=['age','zip_code']
        pred['b']['caller_utterances'][0]['requested_info']=[]
        pred['a']['hook_phase']['qualification']['question']=[]
        pred['b']['hook_phase']['qualification']['question']=['age','zip_code']
        stats=prepared_statistics(['a','b'],gold,pred)
        for f in CALL_FIELDS+EXTRA_CALL:self.assertEqual(stats[f](['a','b']),call_kappa(f,['a','b'],gold,pred))
        for f in TURN_FIELDS:self.assertEqual(stats[f](['a','b']),turn_f1(f,['a','b'],gold,pred))
        self.assertEqual(stats['requested_info'](['a','b']),.5)
        self.assertEqual(stats['hook_phase.qualification.question'](['a','b']),.5)

    def controller(self,effects):
        with tempfile.TemporaryDirectory() as tmp:
            exp=Path(tmp);(exp/'test_run').mkdir()
            (exp/'test_run/manifest.json').write_text(json.dumps({'config':{'workers':8}}))
            calls=[]
            def fake_run(*args,**kwargs):
                failures=0
                for _ in range(5):
                    try:calls.append(agent.post_query({},'mock'))
                    except RuntimeError:failures+=1
                return failures
            original=agent.post_query
            with patch('sys.argv',['resume_rate_limited',str(exp),'--failure-limit','2']), \
                 patch('coding.agent.post_query',side_effect=effects) as transport, \
                 patch('coding.agent.run',side_effect=fake_run):
                with self.assertRaises(SystemExit):resume_rate_limited.main()
                count=transport.call_count
            self.assertIs(agent.post_query,original)
            return count,json.loads((exp/'runtime_recovery_01.json').read_text())

    def test_circuit_prevents_further_transmissions_after_two_errors(self):
        count,audit=self.controller([RuntimeError('ASU HTTP 500'),RuntimeError('ASU HTTP 500')])
        self.assertEqual(count,2);self.assertTrue(audit['state']['circuit_open'])

    def test_success_resets_consecutive_error_counter(self):
        count,audit=self.controller([RuntimeError('ASU HTTP 500'),{},RuntimeError('ASU HTTP 500'),{},{}])
        self.assertEqual(count,5);self.assertFalse(audit['state']['circuit_open'])


if __name__=='__main__':unittest.main()
