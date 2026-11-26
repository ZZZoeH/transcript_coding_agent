"""Offline human agreement and blinded adjudication; never loads model predictions."""
import argparse
import csv
import json
import random
import re
from pathlib import Path

from .agreement import kappa
from .io_utils import INPUT_FILES, ROOT, file_hash, load_records, record_hash, write_json
from .qual_kit import OUTCOMES

VERSION = 'qualification-review-v1'
ROOT_PATH = Path(ROOT)
DECISION_FIELDS = ['case_id', 'call_id', 'outcome', 'supporting_turn_indices',
                   'reviewer', 'independent_review', 'rationale']
REVIEW_INSTRUCTIONS = (
    'A third person who supplied neither original coding sheet must review these calls independently. '
    'Use the frozen coding guide and verbatim source turns. Do not consult either original coder\'s '
    'labels or model predictions before submitting decisions. Choose any supported allowed outcome; '
    'you are not restricted to the original coders\' choices. Enter supporting_turn_indices as a '
    'nonempty JSON integer array, provide an English rationale and your reviewer name, and set '
    'independent_review to yes to attest that this was an independent assessment. '
    'Share only the reviewer directory with the reviewer; keep the private directory separate.'
)


def read_csv(path, fields):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != fields:
            raise ValueError('Unexpected CSV header; required columns: ' + ', '.join(fields))
        rows = list(reader)
    if any(set(row) != set(fields) or any(value is None for value in row.values()) for row in rows):
        raise ValueError('Malformed CSV row or unexpected extra columns')
    return rows


def read_labels(path):
    result = {}
    for row in read_csv(path, ['call_id', 'outcome']):
        call_id = row['call_id']
        if not call_id or call_id != call_id.strip() or call_id in result:
            raise ValueError('Empty, padded, or duplicate call_id in coding sheet')
        outcome = row['outcome'].strip()
        if outcome and outcome not in OUTCOMES:
            raise ValueError('Unsupported outcome for call ' + call_id)
        result[call_id] = outcome
    return result


def write_csv(path, fields, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def sample_ids(packet):
    ids = re.findall(r'^## ([A-Za-z0-9_:-]+)\s*$', Path(packet).read_text(encoding='utf-8-sig'), re.M)
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('Sample packet must contain unique call headings')
    return ids


def source_records(ids, records=None):
    supplied = records is not None
    records = load_records() if records is None else records
    if set(ids) - records.keys():
        raise ValueError('Sample contains an unknown source call')
    for call_id in ids:
        rec = records[call_id]
        turns = rec['conversation']
        indices = [turn['turn_index'] for turn in turns]
        if rec['call_id'] != call_id or len(indices) != len(set(indices)):
            raise ValueError('Source call ID or turn indices are inconsistent')
        if any(type(index) is not int for index in indices):
            raise ValueError('Source turn indices must be integers')
    if not supplied:
        frozen = json.loads((ROOT_PATH / 'splits/test_hashes.json').read_text())
        if any(frozen.get(c) != record_hash(records[c]) for c in ids):
            raise ValueError('Qualification sample does not match the frozen source transcripts')
    return records


def percentile(values, probability):
    values = sorted(values)
    position = probability * (len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return round(values[lower] + (values[upper] - values[lower]) * (position - lower), 6)


def agreement_statistics(a, b, ids, rounds=1000, seed=598):
    if not ids or any(a[c] not in OUTCOMES or b[c] not in OUTCOMES for c in ids):
        raise ValueError('Both independent sheets must be complete before computing agreement')
    if type(rounds) is not int or rounds < 1:
        raise ValueError('Bootstrap rounds must be a positive integer')
    confusion = {x: {y: 0 for y in OUTCOMES} for x in OUTCOMES}
    for c in ids:
        confusion[a[c]][b[c]] += 1
    observed = sum(a[c] == b[c] for c in ids) / len(ids)
    value = kappa([a[c] for c in ids], [b[c] for c in ids])
    rng = random.Random(seed)
    kappas, agreements = [], []
    for _ in range(rounds):
        sample = rng.choices(ids, k=len(ids))
        result = kappa([a[c] for c in sample], [b[c] for c in sample])
        if result is not None:
            kappas.append(result)
        agreements.append(sum(a[c] == b[c] for c in sample) / len(sample))
    interval = lambda values: [percentile(values, .025), percentile(values, .975)] if values else None
    return {
        'calls': len(ids), 'metric': 'unweighted_nominal_cohens_kappa',
        'observed_agreement': observed, 'observed_agreement_ci95': interval(agreements),
        'kappa': value, 'kappa_ci95': interval(kappas) if value is not None else None,
        'kappa_status': 'defined' if value is not None else 'undefined_single_shared_category',
        'confusion_matrix_rows_A_columns_B': confusion,
        'coder_A_label_counts': {label: sum(a[c] == label for c in ids) for label in OUTCOMES},
        'coder_B_label_counts': {label: sum(b[c] == label for c in ids) for label in OUTCOMES},
        'disagreement_calls': sum(a[c] != b[c] for c in ids),
        'bootstrap': {'unit': 'call', 'rounds': rounds, 'seed': seed,
                      'kappa_defined_replicates': len(kappas),
                      'kappa_undefined_replicates': rounds - len(kappas),
                      'method': 'paired percentile bootstrap; kappa interval uses defined replicates only'},
        'interpretation': 'Pre-adjudication human agreement, not model performance. Undefined kappa is not zero.'}


def input_entry(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': file_hash(path)}


def new_output(path):
    path = Path(path).resolve()
    if path.exists():
        raise ValueError('Output already exists; choose a new directory to preserve previous work')
    path.mkdir(parents=True)
    return path


def prepare(sheet_a, sheet_b, output_dir, packet=None, guide=None, records=None, rounds=1000, seed=598):
    packet = Path(packet or ROOT_PATH / 'qual_sample/packet.md')
    guide = Path(guide or ROOT_PATH / 'qual_sample/coding_guide.md')
    a, b = read_labels(sheet_a), read_labels(sheet_b)
    ids = sample_ids(packet)
    if set(a) != set(ids) or set(b) != set(ids):
        raise ValueError('Both coding sheets must contain exactly the frozen sample call IDs')
    if type(rounds) is not int or rounds < 1:
        raise ValueError('Bootstrap rounds must be a positive integer')
    entries = {'sheet_A': input_entry(sheet_a), 'sheet_B': input_entry(sheet_b),
               'sample_packet': input_entry(packet), 'coding_guide': input_entry(guide)}
    supplied = records is not None
    records = source_records(ids, records)
    if not supplied:
        for i, path in enumerate(INPUT_FILES):
            entries['source_file_' + str(i)] = input_entry(path)
        entries['frozen_test_hashes'] = input_entry(ROOT_PATH / 'splits/test_hashes.json')
    complete_a = sum(bool(a[c]) for c in ids)
    complete_b = sum(bool(b[c]) for c in ids)
    ready = complete_a == complete_b == len(ids)
    status = {'status': 'ready_for_adjudication' if ready else 'waiting_for_independent_coding',
              'sample_calls': len(ids), 'coder_A_completed': complete_a, 'coder_B_completed': complete_b,
              'coder_A_missing_call_ids': [c for c in ids if not a[c]],
              'coder_B_missing_call_ids': [c for c in ids if not b[c]],
              'agreement_computed': ready, 'model_predictions_accessed': False,
              'test_inference_or_model_scoring_performed': False}
    # Build all source-dependent artifacts before creating any output directory.
    disagreements = [c for c in ids if ready and a[c] != b[c]]
    analysis = agreement_statistics(a, b, ids, rounds, seed) if ready else None
    cases = [{'case_id': f'QREV-{i:03d}', 'call_id': c, 'input_hash': record_hash(records[c]),
              'conversation': [{'role': t['role'], 'turn_index': t['turn_index'], 'content': t['content']}
                               for t in records[c]['conversation']]}
             for i, c in enumerate(disagreements, 1)]
    reviewer_packet = {'instructions': REVIEW_INSTRUCTIONS, 'allowed_outcomes': list(OUTCOMES),
                       'role_legend': {'user': 'caller', 'assistant': 'callee'},
                       'coding_guide': guide.read_text(encoding='utf-8-sig'),
                       'source_evidence': 'Verbatim transcript text; original language preserved.', 'cases': cases}
    out = new_output(output_dir)
    write_json(str(out / 'status.json'), status)
    if ready:
        write_json(str(out / 'private/agreement.json'), analysis)
        write_csv(out / 'private/paired_labels.csv', ['call_id', 'outcome_A', 'outcome_B'],
                  [{'call_id': c, 'outcome_A': a[c], 'outcome_B': b[c]} for c in ids])
        write_json(str(out / 'reviewer/packet.json'), reviewer_packet)
        write_csv(out / 'reviewer/decisions.csv', DECISION_FIELDS,
                  [{**dict.fromkeys(DECISION_FIELDS, ''), 'case_id': c['case_id'], 'call_id': c['call_id']}
                   for c in cases])
        status['disagreement_calls'] = len(disagreements)
        write_json(str(out / 'status.json'), status)
    immutable = {str(p.relative_to(out)): file_hash(p) for p in out.rglob('*')
                 if p.is_file() and p != out / 'reviewer/decisions.csv'}
    write_json(str(out / 'private/manifest.json'), {
        'version': VERSION, 'status': status['status'], 'inputs': entries,
        'sample_ids': ids, 'disagreement_ids': disagreements,
        'source_call_hashes': {c: record_hash(records[c]) for c in ids},
        'immutable_outputs': immutable,
        'editable_output': 'reviewer/decisions.csv' if ready else None,
        'model_predictions_accessed': False})
    return status


def verified_bundle(bundle):
    bundle = Path(bundle).resolve()
    manifest = json.loads((bundle / 'private/manifest.json').read_text())
    if manifest['version'] != VERSION or manifest['status'] != 'ready_for_adjudication':
        raise ValueError('A completed A/B analysis bundle is required before finalizing')
    for entry in manifest['inputs'].values():
        if file_hash(entry['path']) != entry['sha256']:
            raise ValueError('An original input changed after preparation; create a fresh bundle')
    for name, wanted in manifest['immutable_outputs'].items():
        if file_hash(bundle / name) != wanted:
            raise ValueError('An immutable analysis or reviewer packet changed after preparation')
    return bundle, manifest


def finalize(bundle, output_dir, decisions=None, records=None):
    bundle, manifest = verified_bundle(bundle)
    ids = manifest['sample_ids']
    records = source_records(ids, records)
    if any(record_hash(records[c]) != manifest['source_call_hashes'][c] for c in ids):
        raise ValueError('Source transcript changed after preparation')
    a = read_labels(manifest['inputs']['sheet_A']['path'])
    b = read_labels(manifest['inputs']['sheet_B']['path'])
    if set(a) != set(ids) or set(b) != set(ids) or any(not a[c] or not b[c] for c in ids):
        raise ValueError('The frozen independent coding sheets are not complete')
    disagreements = [c for c in ids if a[c] != b[c]]
    if disagreements != manifest['disagreement_ids']:
        raise ValueError('Disagreement IDs do not match the frozen independent sheets')
    packet = json.loads((bundle / 'reviewer/packet.json').read_text())
    expected = {case['call_id']: case['case_id'] for case in packet['cases']}
    if set(expected) != set(disagreements):
        raise ValueError('Reviewer packet does not match the disagreement set')
    decisions = Path(decisions) if decisions else bundle / 'reviewer/decisions.csv'
    rows = read_csv(decisions, DECISION_FIELDS)
    by_call = {}
    for row in rows:
        c = row['call_id']
        if c in by_call or c not in expected or row['case_id'] != expected[c]:
            raise ValueError('Duplicate, extra, or mismatched adjudication case')
        if row['outcome'].strip() not in OUTCOMES:
            raise ValueError('Every disagreement requires a valid third-reviewer outcome')
        if not row['reviewer'].strip() or not row['rationale'].strip():
            raise ValueError('Every decision requires a reviewer name and an English rationale')
        if row['independent_review'].strip().lower() != 'yes':
            raise ValueError('The third reviewer must attest independent_review=yes')
        if row['reviewer'].strip().lower() in {'a', 'b', 'coder a', 'coder b', 'coder_a', 'coder_b'}:
            raise ValueError('The adjudicator must be a third person, not coder A or B')
        try:
            indices = json.loads(row['supporting_turn_indices'])
        except (ValueError, TypeError):
            raise ValueError('Supporting turn indices must be a nonempty JSON integer array') from None
        valid = {t['turn_index'] for t in records[c]['conversation']}
        if (not isinstance(indices, list) or not indices or any(type(i) is not int for i in indices)
                or len(set(indices)) != len(indices) or not set(indices) <= valid):
            raise ValueError('Supporting evidence must cite distinct original source turn indices')
        by_call[c] = {**row, 'outcome': row['outcome'].strip(), 'supporting_turn_indices': indices}
    if set(by_call) != set(disagreements):
        raise ValueError('All and only the disagreement cases must be adjudicated')
    final_rows, provenance = [], []
    for c in ids:
        decision = by_call.get(c)
        final_rows.append({'call_id': c, 'outcome': decision['outcome'] if decision else a[c]})
        provenance.append({'call_id': c, 'outcome_A': a[c], 'outcome_B': b[c],
                           'outcome': final_rows[-1]['outcome'],
                           'decision_source': 'third_reviewer' if decision else 'coder_agreement',
                           'input_hash': record_hash(records[c]), 'adjudication': decision})
    out = new_output(output_dir)
    write_csv(out / 'adjudicated_sheet.csv', ['call_id', 'outcome'], final_rows)
    write_json(str(out / 'provenance.json'), {'version': VERSION, 'calls': provenance,
               'agreement_statistics': json.loads((bundle / 'private/agreement.json').read_text()),
               'agreement_statistics_phase': 'before_adjudication',
               'independence_note': 'Reviewer independence is self-attested; software cannot verify it.'})
    result = {'status': 'complete', 'calls': len(ids), 'consensus_calls': len(ids) - len(disagreements),
              'third_reviewer_calls': len(disagreements), 'model_predictions_accessed': False,
              'test_inference_or_model_scoring_performed': False}
    write_json(str(out / 'manifest.json'), {**result, 'version': VERSION,
               'inputs': {'bundle_manifest': input_entry(bundle / 'private/manifest.json'),
                          'decisions': input_entry(decisions)},
               'outputs': {p.name: file_hash(p) for p in out.iterdir() if p.is_file()}})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare', help='Check completion; analyze only after both sheets are complete')
    prep.add_argument('--sheet-a', type=Path, default=ROOT_PATH / 'qual_sample/sheet_A.csv')
    prep.add_argument('--sheet-b', type=Path, default=ROOT_PATH / 'qual_sample/sheet_B.csv')
    prep.add_argument('--packet', type=Path, default=ROOT_PATH / 'qual_sample/packet.md')
    prep.add_argument('--guide', type=Path, default=ROOT_PATH / 'qual_sample/coding_guide.md')
    prep.add_argument('--bootstrap-rounds', type=int, default=1000)
    prep.add_argument('--seed', type=int, default=598)
    prep.add_argument('--output-dir', type=Path, required=True)
    finish = commands.add_parser('finalize', help='Validate third-reviewer decisions and merge human labels only')
    finish.add_argument('--bundle', type=Path, required=True)
    finish.add_argument('--decisions', type=Path, help='Defaults to BUNDLE/reviewer/decisions.csv')
    finish.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            result = prepare(args.sheet_a, args.sheet_b, args.output_dir, args.packet, args.guide,
                             rounds=args.bootstrap_rounds, seed=args.seed)
        else:
            result = finalize(args.bundle, args.output_dir, args.decisions)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
