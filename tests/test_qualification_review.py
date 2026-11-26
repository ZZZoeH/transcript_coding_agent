"""Synthetic human-label fixtures only; no model requests or test-set scoring."""
import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coding.qual_kit import read_sheet
from coding.qualification_review import (DECISION_FIELDS, agreement_statistics, finalize,
                                          prepare, read_labels, write_csv)


class QualificationReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.ids = ['one', 'two', 'three', 'four']
        self.records = {c: {'call_id': c, 'conversation': [
            {'role': 'user', 'turn_index': 2, 'content': 'Do you meet the stated criterion?',
             'annotation_sentinel': 'DO_NOT_EXPORT_SOURCE_ANNOTATIONS'},
            {'role': 'assistant', 'turn_index': 5, 'content': 'Yes.'}],
            'codes': {'secret': 'DO_NOT_EXPORT_GOLD'},
            'model_prediction': 'DO_NOT_EXPORT_MODEL'} for c in self.ids}
        self.a = self.root / 'A.csv'
        self.b = self.root / 'B.csv'
        self.packet = self.root / 'packet.md'
        self.packet.write_text(''.join('## ' + c + '\n' for c in self.ids))
        self.guide = self.root / 'guide.md'
        self.guide.write_text('Use only the last qualification exchange before the first transfer.')
        self.labels_a = ['matches_profile'] * 3 + ['call_terminates']
        self.labels_b = ['matches_profile'] * 2 + ['call_terminates'] * 2
        self.labels(self.a, self.labels_a)
        self.labels(self.b, self.labels_b)

    def labels(self, path, labels):
        write_csv(path, ['call_id', 'outcome'],
                  [{'call_id': c, 'outcome': label} for c, label in zip(self.ids, labels)])

    def prepare(self, name='bundle'):
        out = self.root / name
        result = prepare(self.a, self.b, out, self.packet, self.guide,
                         records=self.records, rounds=80)
        return out, result

    def complete_decisions(self, bundle, **overrides):
        path = bundle / 'reviewer/decisions.csv'
        with path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            row.update(outcome='mismatch_call_continues', supporting_turn_indices='[5]',
                       reviewer='Coder C', independent_review='yes',
                       rationale='The answer contradicts the criterion, but the caller continues.')
            row.update(overrides)
        write_csv(path, DECISION_FIELDS, rows)
        return path

    def test_incomplete_sheets_never_compute_partial_agreement(self):
        self.labels(self.b, ['matches_profile', 'matches_profile', '', ''])
        with patch('coding.qualification_review.agreement_statistics') as statistics:
            out, status = self.prepare()
        statistics.assert_not_called()
        self.assertFalse(status['agreement_computed'])
        self.assertEqual(status['coder_B_completed'], 2)
        self.assertFalse((out / 'reviewer').exists())
        self.assertFalse((out / 'private/agreement.json').exists())
        with self.assertRaisesRegex(ValueError, 'completed A/B'):
            finalize(out, self.root / 'final', records=self.records)
        self.assertFalse((self.root / 'final').exists())

    def test_legacy_compare_also_blocks_incomplete_agreement(self):
        from coding.qual_kit import compare
        self.labels(self.b, ['matches_profile', '', '', ''])
        with patch('coding.qual_kit.kappa') as statistic, patch('builtins.print'):
            compare(self.a, self.b)
        statistic.assert_not_called()

    def test_legacy_csv_reader_accepts_excel_bom(self):
        self.assertEqual(read_sheet(self.a), read_labels(self.a))

    def test_statistics_known_answer_and_repeatable_bootstrap(self):
        a, b = read_labels(self.a), read_labels(self.b)
        first = agreement_statistics(a, b, self.ids, rounds=80)
        self.assertEqual(first['kappa'], .5)
        self.assertEqual(first['observed_agreement'], .75)
        self.assertEqual(first['disagreement_calls'], 1)
        self.assertEqual(first['confusion_matrix_rows_A_columns_B']['matches_profile']['call_terminates'], 1)
        self.assertEqual(first, agreement_statistics(a, b, self.ids, rounds=80))
        self.assertEqual(first['bootstrap']['kappa_defined_replicates'] +
                         first['bootstrap']['kappa_undefined_replicates'], 80)

    def test_single_category_kappa_is_explicitly_undefined(self):
        a = dict.fromkeys(self.ids, 'matches_profile')
        result = agreement_statistics(a, a, self.ids, rounds=40)
        self.assertIsNone(result['kappa'])
        self.assertIsNone(result['kappa_ci95'])
        self.assertEqual(result['observed_agreement'], 1)
        self.assertEqual(result['bootstrap']['kappa_undefined_replicates'], 40)

    def test_blinded_packet_has_only_source_and_no_coder_choices(self):
        out, status = self.prepare()
        self.assertTrue(status['agreement_computed'])
        packet = json.loads((out / 'reviewer/packet.json').read_text())
        self.assertEqual([c['call_id'] for c in packet['cases']], ['three'])
        case = packet['cases'][0]
        self.assertEqual(set(case), {'case_id', 'call_id', 'input_hash', 'conversation'})
        for turn in case['conversation']:
            self.assertEqual(set(turn), {'role', 'turn_index', 'content'})
        serialized = json.dumps(packet)
        self.assertNotIn('DO_NOT_EXPORT', serialized)
        self.assertNotIn('outcome_A', serialized)
        self.assertNotIn('outcome_B', serialized)
        with (out / 'reviewer/decisions.csv').open(encoding='utf-8-sig', newline='') as stream:
            row = next(csv.DictReader(stream))
        self.assertEqual(row['outcome'], '')
        self.assertEqual(row['reviewer'], '')

    def test_finalize_preserves_consensus_and_allows_a_third_outcome(self):
        before_a, before_b = self.a.read_bytes(), self.b.read_bytes()
        out, _ = self.prepare()
        self.complete_decisions(out)
        result = finalize(out, self.root / 'final', records=self.records)
        self.assertEqual(result['consensus_calls'], 3)
        self.assertEqual(result['third_reviewer_calls'], 1)
        merged = read_sheet(self.root / 'final/adjudicated_sheet.csv')
        self.assertEqual(merged['three'], 'mismatch_call_continues')
        self.assertEqual(merged['four'], 'call_terminates')
        self.assertEqual(merged['one'], 'matches_profile')
        provenance = json.loads((self.root / 'final/provenance.json').read_text())
        self.assertEqual(provenance['agreement_statistics']['kappa'], .5)
        self.assertEqual(provenance['agreement_statistics_phase'], 'before_adjudication')
        self.assertEqual(self.a.read_bytes(), before_a)
        self.assertEqual(self.b.read_bytes(), before_b)

    def test_blank_decisions_do_not_create_final_output(self):
        out, _ = self.prepare()
        with self.assertRaisesRegex(ValueError, 'valid third-reviewer outcome'):
            finalize(out, self.root / 'final', records=self.records)
        self.assertFalse((self.root / 'final').exists())

    def test_invalid_evidence_and_independence_are_rejected(self):
        out, _ = self.prepare()
        invalid = [({'supporting_turn_indices': '[0]'}, 'source turn'),
                   ({'supporting_turn_indices': '[true]'}, 'source turn'),
                   ({'supporting_turn_indices': '[]'}, 'source turn'),
                   ({'supporting_turn_indices': '[2, 2]'}, 'source turn'),
                   ({'supporting_turn_indices': 'not JSON'}, 'JSON integer'),
                   ({'independent_review': 'no'}, 'attest'),
                   ({'reviewer': 'A'}, 'third person'),
                   ({'rationale': ''}, 'rationale')]
        for overrides, message in invalid:
            with self.subTest(overrides=overrides):
                self.complete_decisions(out, **overrides)
                with self.assertRaisesRegex(ValueError, message):
                    finalize(out, self.root / 'final', records=self.records)
                self.assertFalse((self.root / 'final').exists())

    def test_missing_duplicate_and_extra_decisions_are_rejected(self):
        out, _ = self.prepare()
        path = self.complete_decisions(out)
        with path.open(encoding='utf-8-sig', newline='') as stream:
            valid = list(csv.DictReader(stream))
        for rows in [[], valid + valid, [{**valid[0], 'call_id': 'one'}],
                     [{**valid[0], 'case_id': 'WRONG'}]]:
            with self.subTest(rows=rows):
                write_csv(path, DECISION_FIELDS, rows)
                with self.assertRaises(ValueError):
                    finalize(out, self.root / 'final', records=self.records)
                self.assertFalse((self.root / 'final').exists())

    def test_original_input_and_packet_changes_are_detected(self):
        out, _ = self.prepare()
        self.complete_decisions(out)
        before = self.a.read_bytes()
        self.labels(self.a, ['call_terminates'] * 4)
        with self.assertRaisesRegex(ValueError, 'original input changed'):
            finalize(out, self.root / 'final', records=self.records)
        self.a.write_bytes(before)
        p = out / 'reviewer/packet.json'
        p.write_text(p.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'immutable'):
            finalize(out, self.root / 'final', records=self.records)

    def test_source_tampering_and_output_overwrite_are_rejected(self):
        out, _ = self.prepare()
        self.complete_decisions(out)
        changed = copy.deepcopy(self.records)
        changed['three']['conversation'][0]['content'] = 'Altered source'
        with self.assertRaisesRegex(ValueError, 'transcript changed'):
            finalize(out, self.root / 'final', records=changed)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.prepare()
        finalize(out, self.root / 'final', records=self.records)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            finalize(out, self.root / 'final', records=self.records)

    def test_unanimous_sheets_need_no_fabricated_third_review(self):
        self.labels(self.b, self.labels_a)
        out, result = self.prepare()
        self.assertEqual(result['disagreement_calls'], 0)
        self.assertEqual(json.loads((out / 'reviewer/packet.json').read_text())['cases'], [])
        result = finalize(out, self.root / 'final', records=self.records)
        self.assertEqual(result['third_reviewer_calls'], 0)
        self.assertEqual(read_sheet(self.root / 'final/adjudicated_sheet.csv'), read_labels(self.a))

    def test_bad_sheet_labels_headers_duplicates_and_sample_ids_are_rejected(self):
        for text in ['call_id,outcome\none,unsupported\n',
                     'call_id,outcome\none,matches_profile\none,call_terminates\n',
                     'call_id,outcome\none,matches_profile,extra\n',
                     'call_id,outcome\none\n',
                     'wrong,outcome\none,matches_profile\n']:
            with self.subTest(text=text):
                self.b.write_text(text)
                with self.assertRaises(ValueError):
                    self.prepare()
                self.assertFalse((self.root / 'bundle').exists())
        self.labels(self.b, self.labels_b[:-1])
        with self.assertRaisesRegex(ValueError, 'exactly the frozen sample'):
            self.prepare()
        with self.assertRaisesRegex(ValueError, 'positive integer'):
            agreement_statistics(read_labels(self.a), read_labels(self.a), self.ids, rounds=0)


if __name__ == '__main__':
    unittest.main()
