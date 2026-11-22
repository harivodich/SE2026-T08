"""Versioned offline duplicate dispositions; never changes grouping or splits."""
import argparse
from collections import Counter
from pathlib import Path

from .manifest import encoded, read_json, require, sha
from .splits import digest, duplicate_report

VERSION = 'duplicate-review-v1'
DISPOSITIONS = {'pending', 'distinct', 'duplicate', 'ambiguous'}


def candidate_id(base_ids):
    require(isinstance(base_ids, list) and len(base_ids) == 2 and
            all(isinstance(x, str) and x for x in base_ids) and
            base_ids[0] != base_ids[1], 'invalid candidate base IDs')
    return 'pair-' + digest(sorted(base_ids))


def candidates(manifest_path, report_path):
    """Bind the historical report to its manifest and recompute its screening."""
    manifest, report = read_json(manifest_path), read_json(report_path)
    require(sha(report_path) == manifest['report']['sha256'], 'report hash drift')
    require(report['leakage'] == duplicate_report(manifest['samples']),
            'candidate report drift from manifest')
    result = {}
    for pair in report['leakage']['ambiguous']:
        key = candidate_id(pair['base_ids'])
        require(key not in result, 'duplicate candidate pair')
        result[key] = pair
    return result


def validate_review(review, manifest_path, report_path):
    """Pending is valid accounting, never a completed visual/content review.

    Reviewer is an attributed identity, not authenticated approval. Completion
    here records review coverage only; AI peer/Lead approval remains external.
    """
    require(isinstance(review, dict) and set(review) == {
        'version', 'manifest', 'report', 'dispositions'}, 'review keys')
    require(review['version'] == VERSION, 'unsupported review version')
    for field, path in [('manifest', manifest_path), ('report', report_path)]:
        require(review[field] == {'name': Path(path).name, 'sha256': sha(path)},
                f'{field} reference/hash drift')
    expected = candidates(manifest_path, report_path)
    require(isinstance(review['dispositions'], list), 'dispositions must be a list')
    seen, counts, cross = set(), Counter(), Counter()
    for entry in review['dispositions']:
        require(isinstance(entry, dict) and set(entry) == {
            'candidate_id', 'base_ids', 'disposition', 'reason', 'reviewer', 'evidence'},
            'disposition keys')
        key = entry['candidate_id']
        require(isinstance(key, str) and key in expected, 'unknown candidate ID')
        require(key not in seen, 'duplicate disposition')
        seen.add(key)
        require(candidate_id(entry['base_ids']) == key, 'candidate base IDs mismatch')
        require(isinstance(entry['disposition'], str) and entry['disposition'] in DISPOSITIONS,
                'unknown disposition')
        for field in ('reason', 'reviewer'):
            require(isinstance(entry[field], str) and entry[field].strip(), f'missing {field}')
        evidence = entry['evidence']
        require(isinstance(evidence, dict) and set(evidence) == {'image', 'content', 'lineage'} and
                all(type(value) is bool for value in evidence.values()), 'invalid review evidence')
        require(entry['disposition'] == 'pending' or all(evidence.values()),
                'non-pending disposition requires image/content/lineage review')
        counts[entry['disposition']] += 1
        if expected[key]['cross_split']:
            cross[entry['disposition']] += 1
    require(seen == set(expected), 'missing dispositions')
    return dict(version=VERSION, candidates=len(expected), dispositions=dict(counts),
                cross_split=dict(cross), review_complete=not counts['pending'],
                unresolved=counts['pending'] + counts['ambiguous'],
                approval='AI1/AI2 peer review and Lead grouping/split approval required before pilot/freeze')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--review', type=Path, required=True)
    args = parser.parse_args()
    print(encoded(validate_review(read_json(args.review), args.manifest, args.report)).decode(), end='')


if __name__ == '__main__':
    main()
