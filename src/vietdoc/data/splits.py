"""Offline, pre-value assignment and leakage checks for grouped datasets."""
from collections import defaultdict
import hashlib

from .manifest import encoded, require


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def assign_groups(records):
    """Join transitive family/source/base aliases; conflicting requested splits fail closed.

    Records contain identifiers only, never generated values or predictions. A source
    group identifies duplicate origins, not merely a shared generator or merchant name.
    """
    parent = {}

    def find(key):
        parent.setdefault(key, key)
        if parent[key] != key:
            parent[key] = find(parent[key])
        return parent[key]

    for record in records:
        require(record['split'] in ('train', 'dev', 'final'), 'invalid requested split')
        keys = [(field, record[field]) for field in ('family_id', 'source_group', 'base_id')]
        for key in keys[1:]:
            parent[find(key)] = find(keys[0])
    components = defaultdict(list)
    for record in records:
        components[find(('base_id', record['base_id']))].append(record)
    for group in components.values():
        require(len({r['split'] for r in group}) == 1,
                'conflicting split requests in connected family/source/base group')
    require(len({r['base_id'] for r in records}) == len(records), 'duplicate base ID in plan')
    return [dict(r, assignment_group=digest(sorted(x['base_id'] for x in
                 components[find(('base_id', r['base_id']))]))) for r in records]


def assert_disjoint(samples):
    for field in ('base_id', 'family_id', 'source_group', 'assignment_group'):
        seen = {}
        for sample in samples:
            value = sample[field]
            require(value not in seen or seen[value] == sample['split'], f'cross-split {field}: {value}')
            seen[value] = sample['split']


def duplicate_report(samples):
    """Exact hashes + content groups + coarse 64-bit dHash candidate review.

    dHash is a screening heuristic on sparse pages, not proof of independence.
    Never auto-resolve ambiguous pairs or consult model predictions.
    """
    assert_disjoint(samples)
    exact, content = defaultdict(list), defaultdict(list)
    bases = {}
    for sample in samples:
        exact[sample['assets']['png']['sha256']].append(sample)
        if sample['quality'] == 'clean':
            content[sample['content_sha256']].append(sample)
            bases[sample['base_id']] = sample
    groups = lambda index: [[s['sample_id'] for s in group] for group in index.values() if len(group) > 1]
    for group in exact.values():
        require(len({s['split'] for s in group}) <= 1, 'exact image duplicate across splits')
    for group in content.values():
        require(len({s['split'] for s in group}) <= 1, 'exact content duplicate across splits')
    ambiguous = []
    values = list(bases.values())
    for i, left in enumerate(values):
        for right in values[i + 1:]:
            distance = (int(left['dhash'], 16) ^ int(right['dhash'], 16)).bit_count()
            a, b = set(left['content_tokens']), set(right['content_tokens'])
            similarity = len(a & b) / max(1, len(a | b))
            if distance <= 8 or similarity >= .85:
                ambiguous.append(dict(base_ids=[left['base_id'], right['base_id']],
                                      cross_split=left['split'] != right['split'],
                                      dhash_distance=distance, content_jaccard=round(similarity, 4),
                                      disposition='pending human review; not proven duplicate'))
    return dict(exact_image_groups=groups(exact), exact_content_groups=groups(content),
                ambiguous=ambiguous, near_duplicate_policy='clean bases only; dHash<=8 OR content token Jaccard>=0.85',
                reviewed=False)
