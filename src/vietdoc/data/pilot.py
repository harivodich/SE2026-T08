"""Plan model-neutral train/dev membership; never rewrites datasets or grants approval."""
import argparse
from collections import defaultdict
from pathlib import Path

from .duplicate_review import candidate_id, validate_review
from .manifest import encoded, read_json, require, sample_id, sha
from .splits import digest

VERSION = 'vietdoc.pilot-plan.v1'


class _Union:
    def __init__(self, values):
        self.parent = {value: value for value in values}

    def find(self, value):
        root = value
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[value] != value:
            previous = self.parent[value]
            self.parent[value] = root
            value = previous
        return root

    def join(self, left, right):
        left, right = self.find(left), self.find(right)
        self.parent[max(left, right)] = min(left, right)

    def groups(self):
        result = defaultdict(list)
        for value in sorted(self.parent):
            result[self.find(value)].append(value)
        return sorted(result.values())


def _counts(samples):
    return dict(base_documents=len({s['base_id'] for s in samples}), samples_including_variants=len(samples),
                bases_by_type_split={kind: {split: len({s['base_id'] for s in samples
                    if s['document_type'] == kind and s['split'] == split})
                    for split in ('train', 'dev', 'final')} for kind in ('receipt', 'invoice')},
                samples_by_type_split={kind: {split: sum(s['document_type'] == kind and s['split'] == split
                    for s in samples) for split in ('train', 'dev', 'final')} for kind in ('receipt', 'invoice')})


def _plan(samples, dispositions):
    """Pure component calculation; the public file boundary validates review coverage."""
    require(isinstance(samples, list) and samples, 'nonempty sample inventory required')
    bases, ids = defaultdict(list), set()
    for sample in samples:
        sid = sample_id(sample['sample_id'])
        require(sid not in ids, 'duplicate sample ID')
        ids.add(sid)
        sample_id(sample['base_id'])
        require(sample['document_type'] in ('receipt', 'invoice') and
                sample['split'] in ('train', 'dev', 'final'), 'invalid type/split')
        for field in ('family_id', 'source_group', 'assignment_group'):
            require(isinstance(sample[field], str) and sample[field], 'missing lineage: ' + field)
        bases[sample['base_id']].append(sample)
    require(all(len({s['document_type'] for s in rows}) == 1 for rows in bases.values()),
            'mixed document types in one base')
    known = _Union(bases)
    unions = []

    def join(left, right, relation, evidence):
        if left != right:
            known.join(left, right)
            unions.append(dict(base_ids=sorted([left, right]), relation=relation, evidence=evidence))

    # Preserve every source/family/assignment alias and every variant's base.
    for field in ('family_id', 'source_group', 'assignment_group'):
        seen = {}
        for sample in sorted(samples, key=lambda s: s['sample_id']):
            value = sample[field]
            if value in seen:
                join(seen[value], sample['base_id'], field, value)
            else:
                seen[value] = sample['base_id']
    # Exact bytes and exact clean content are separate relations, not dHash guesses.
    for relation in ('exact_png', 'exact_clean_content'):
        seen = {}
        for sample in sorted(samples, key=lambda s: s['sample_id']):
            if relation == 'exact_clean_content' and sample['quality'] != 'clean':
                continue
            value = (sample['assets']['png']['sha256'] if relation == 'exact_png'
                     else sample['content_sha256'])
            if value in seen:
                join(seen[value], sample['base_id'], relation, value)
            else:
                seen[value] = sample['base_id']
    for entry in sorted(dispositions, key=lambda e: e['candidate_id']):
        left, right = entry['base_ids']
        require(left in bases and right in bases and
                candidate_id(entry['base_ids']) == entry['candidate_id'], 'invalid disposition base binding')
        if entry['disposition'] == 'duplicate':
            join(left, right, 'review_duplicate', entry['candidate_id'])

    # Risk connectivity is distinct from confirmed leakage grouping. Unresolved
    # edges propagate quarantine through the already connected known groups.
    risk = _Union(bases)
    for group in known.groups():
        for base in group[1:]:
            risk.join(group[0], base)
    unresolved = [e for e in dispositions if e['disposition'] in ('pending', 'ambiguous')]
    for entry in unresolved:
        risk.join(*entry['base_ids'])
    pending_by_component = defaultdict(list)
    for entry in unresolved:
        pending_by_component[risk.find(entry['base_ids'][0])].append(entry['candidate_id'])
    risk_groups = []
    component_of = {}
    for members in risk.groups():
        component = 'risk-' + digest(members)
        pending = sorted(pending_by_component[risk.find(members[0])])
        risk_groups.append(dict(component_id=component, base_ids=members, unresolved_candidate_ids=pending))
        for base in members:
            component_of[base] = (component, pending)
    known_groups, group_of = [], {}
    for members in known.groups():
        group = 'group-' + digest(members)
        splits = sorted({s['split'] for base in members for s in bases[base]})
        reasons = []
        if len(splits) > 1:
            reasons.append('confirmed_group_cross_split')
        if 'final' in splits:
            reasons.append('historical_final_not_train_dev')
        known_groups.append(dict(group_id=group, base_ids=members, source_splits=splits,
                                 reasons=reasons))
        for base in members:
            group_of[base] = (group, reasons)
    members, excluded, decisions = {'train': [], 'dev': []}, [], []
    for base in sorted(bases):
        group, reasons = group_of[base]
        component, pending = component_of[base]
        reasons = reasons + (['unresolved_component'] if pending else [])
        for sample in sorted(bases[base], key=lambda s: s['sample_id']):
            decision = dict(sample_id=sample['sample_id'], base_id=base, document_type=sample['document_type'],
                            source_split=sample['split'], group_id=group, component_id=component,
                            reasons=reasons)
            decisions.append(decision)
            if reasons:
                excluded.append(decision)
            else:
                members[sample['split']].append(sample['sample_id'])
    selected = {sid for values in members.values() for sid in values}
    after = _counts([sample for sample in samples if sample['sample_id'] in selected])
    missing = [f'{kind}/{split}' for kind, counts in after['bases_by_type_split'].items()
               for split in ('train', 'dev') if counts[split] == 0]
    return dict(version=VERSION, status='blocked_membership' if missing else 'prepared_not_approved',
                scope='metadata/review planning only; not asset/gold/pixel QA, consumer ACK or training acceptance',
                confirmed_groups=known_groups,
                union_reasons=sorted(unions, key=lambda e: (e['base_ids'], e['relation'], e['evidence'])),
                risk_components=risk_groups, decisions=decisions, members=members, excluded=excluded,
                counts=dict(before=_counts(samples), after=after), missing_type_split_support=missing,
                unresolved_candidates=len(unresolved),
                prerequisites=['asset/gold/status QA and archive verification', 'peer/Lead grouping acceptance',
                               'AI1 OCR cache and AI2 actual reader/ACK'],
                capacity='model-neutral preparation needs no G0/final host; model-specific size/serialization pending AI2')


def plan_files(manifest_path, report_path, review_path):
    paths = [Path(path) for path in (manifest_path, report_path, review_path)]
    hashes = [sha(path) for path in paths]
    manifest, review = read_json(paths[0]), read_json(paths[2])
    require(manifest.get('version') == 'd2.2.v1' and manifest.get('final_frozen') is False,
            'planner requires exposed, non-frozen D2.2 smoke snapshot')
    review_summary = validate_review(review, paths[0], paths[1])
    result = _plan(manifest['samples'], review['dispositions'])
    require(all(sha(path) == digest for path, digest in zip(paths, hashes)), 'planning inputs changed')
    result.update(inputs={key: dict(name=path.name, sha256=digest)
                          for key, path, digest in zip(('manifest', 'report', 'review'), paths, hashes)},
                  review=review_summary)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest', 'report', 'review', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'output already exists')
    result = plan_files(args.manifest, args.report, args.review)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('xb') as stream:
        stream.write(encoded(result))
    print(encoded(dict(status=result['status'], counts=result['counts'],
                       unresolved_candidates=result['unresolved_candidates'])).decode(), end='')


if __name__ == '__main__':
    main()
