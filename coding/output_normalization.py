"""Lossless representation cleanup and documented artifact label projections."""
import copy
from .schema import SCHEMA, schema_errors, coded_fields


def normalize_output(output):
    result = copy.deepcopy(output)
    if schema_errors(result, SCHEMA): return result, []
    changes = []
    for turn in result['caller_utterances']:
        required = set()
        if set(turn['complementary_persuasion']) & {'nag', 'time'}: required.add('dis')
        if 'dh' in turn['complementary_persuasion']: required.add('crc')
        additions = required - set(turn['persuasion'])
        if additions:
            turn['persuasion'] = sorted(set(turn['persuasion']) | additions)
            path = f"caller_utterances.{turn['turn_index']}.persuasion"
            source = f"caller_utterances.{turn['turn_index']}.complementary_persuasion"
            indices = {i for row in result['evidence'] if row['field'] in (path, source) for i in row['turn_indices']}
            if indices: result['evidence'].append({'field': path, 'turn_indices': sorted(indices)})
            changes.append({'operation':'artifact_compatibility_projection', 'field':path,
                            'added_labels':sorted(additions), 'source_field':source})
    # Enumerate valid leaf paths including empty and null fields; typos remain errors.
    all_fields = {}
    def walk(value, path):
        if isinstance(value, dict):
            for key, item in value.items(): walk(item, path+'.'+key if path else key)
        else: all_fields[path] = value
    for key in ['category', 'subcategory', 'hook_phase']: walk(result[key], key)
    for turn in result['caller_utterances']:
        for key in ['requested_info','persuasion','complementary_persuasion','functional_states']:
            all_fields[f"caller_utterances.{turn['turn_index']}.{key}"] = turn[key]
    evidence = []
    locations = {}
    for row in result['evidence']:
        field = row['field']
        if field in all_fields and all_fields[field] in (None, []):
            changes.append({'operation':'remove_evidence_for_empty_field', 'field':field})
            continue
        if field in locations:
            current = evidence[locations[field]]
            current['turn_indices'] = sorted(set(current['turn_indices']) | set(row['turn_indices']))
            changes.append({'operation':'merge_duplicate_evidence', 'field':field})
        else:
            locations[field] = len(evidence); evidence.append(row)
    result['evidence'] = evidence
    return result, changes
