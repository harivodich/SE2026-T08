"""Prepare pinned duplicate-inspection queues; never infer or approve dispositions."""
import argparse
from collections import Counter
from pathlib import Path

from .adapters.records import training_packet
from .duplicate_review import candidates, validate_review
from .generator.templates.families import catalog
from .manifest import encoded, read_json, require, sha

VERSION = 'vietdoc.duplicate-batches.v1'


def prepare(root, manifest, report, review, asset_manifest, *, batch_size=10):
    require(type(batch_size) is int and 1 <= batch_size <= 20, 'batch size must be in [1,20]')
    paths = [Path(p) for p in (manifest, report, review, asset_manifest)]
    hashes = [sha(p) for p in paths]
    data, reviewed = read_json(paths[0]), read_json(paths[2])
    require(data.get('version') == 'd2.2.v1' and data.get('final_frozen') is False,
            'batch preparation requires exposed non-frozen D2.2 snapshot')
    summary = validate_review(reviewed, paths[0], paths[1])
    require(hashes[0] == hashes[3], 'asset manifest differs from pinned review manifest')
    packet = training_packet(root, paths[3])  # Existing whole-manifest semantic/hash boundary.
    require(packet['manifest']['sha256'] == hashes[0], 'asset manifest changed during preparation')
    clean = {r['sample']['base_id']: r for r in packet['records'] if r['sample']['quality'] == 'clean'}
    families = {f['family_id']: f for f in catalog()}
    sample_catalog = {}
    for base, record in sorted(clean.items()):
        sample = record['sample']
        sample_catalog[base] = dict(
            lineage={k: sample[k] for k in ('sample_id', 'base_id', 'document_type', 'family_id',
                'source_group', 'assignment_group', 'split', 'value_seed', 'source_gold_sha256',
                'content_sha256', 'row_count')},
            assets=sample['assets'], family=families[sample['family_id']],
            field_count=len(record['labels']['fields']), label_statuses=sample['label_statuses'])
    screening = candidates(paths[0], paths[1])
    batches = []
    for cross in (True, False):
        entries = sorted((e for e in reviewed['dispositions']
                          if e['disposition'] in ('pending', 'ambiguous') and
                          screening[e['candidate_id']]['cross_split'] == cross), key=lambda e: e['candidate_id'])
        for offset in range(0, len(entries), batch_size):
            pairs = []
            for entry in entries[offset:offset + batch_size]:
                left, right = [clean[base] for base in entry['base_ids']]
                pairs.append(dict(candidate_id=entry['candidate_id'], base_ids=entry['base_ids'],
                    current_disposition=entry['disposition'],
                    screening=screening[entry['candidate_id']],
                    mechanical_comparison=dict(same_document_type=left['sample']['document_type'] == right['sample']['document_type'],
                        same_gold=left['gold'] == right['gold'],
                        row_counts=[len(r['gold']['items']) for r in (left, right)]),
                    inspection=dict(image=False, content=False, lineage=False, reviewer=None, verdict=None)))
            batches.append(dict(batch_id=f'{"cross" if cross else "same"}-split-{offset // batch_size + 1:02}',
                                cross_split=cross, pairs=pairs))
    require(all(sha(p) == h for p, h in zip(paths, hashes)), 'batch inputs changed')
    return dict(version=VERSION, status='prepared_for_review',
                scope='machine-prepared references only; image/content/lineage inspection and peer verdict still required',
                inputs={key: dict(name=p.name, sha256=h) for key, p, h in
                        zip(('manifest', 'report', 'review', 'asset_manifest'), paths, hashes)},
                review=summary, validated_source_counts=packet['counts'],
                queued_pairs=sum(len(b['pairs']) for b in batches),
                queued_by_split=dict(Counter('cross' if b['cross_split'] else 'same'
                                            for b in batches for _ in b['pairs'])),
                sample_catalog=sample_catalog, batches=batches)


def export(root, manifest, report, review, asset_manifest, output, *, batch_size=10):
    output = Path(output)
    require(not output.exists(), 'output already exists')
    result = prepare(root, manifest, report, review, asset_manifest, batch_size=batch_size)
    content = encoded(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(content)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('root', 'manifest', 'report', 'review', 'asset-manifest', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--batch-size', type=int, default=10)
    args = parser.parse_args()
    result = export(args.root, args.manifest, args.report, args.review, args.asset_manifest,
                    args.output, batch_size=args.batch_size)
    print(encoded(dict(status=result['status'], queued_pairs=result['queued_pairs'],
                       queued_by_split=result['queued_by_split'])).decode(), end='')


if __name__ == '__main__':
    main()
