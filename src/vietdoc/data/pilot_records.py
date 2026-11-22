"""Prepare selected records from a recomputed pilot plan; no approval or archive claim."""
import argparse
from collections import Counter
from pathlib import Path

from .adapters.records import training_packet
from .manifest import encoded, read_json, require, sha
from .pilot import plan_files

VERSION = 'vietdoc.pilot-records-preparation.v1'


def prepare(root, manifest, report, review, plan, asset_manifest):
    paths = [Path(p) for p in (manifest, report, review, plan, asset_manifest)]
    hashes = [sha(p) for p in paths]
    expected = plan_files(*paths[:3])
    require(read_json(paths[3]) == expected, 'pilot plan drift from current manifest/report/review')
    require(expected['status'] == 'prepared_not_approved' and not expected['missing_type_split_support'],
            'pilot has no complete receipt/invoice train/dev support')
    require(hashes[0] == hashes[4], 'asset manifest differs from pinned pilot manifest')
    source = training_packet(root, paths[4])  # Validate all source members before selecting any.
    require(source['manifest']['sha256'] == hashes[0], 'asset manifest changed during selection')
    selected = {sid for members in expected['members'].values() for sid in members}
    records = [r for r in source['records'] if r['sample']['sample_id'] in selected]
    require({r['sample']['sample_id'] for r in records} == selected, 'selected records missing from validated source')
    require(all(r['sample']['split'] in ('train', 'dev') for r in records), 'selected final member')
    # Keep the records.v1 shape and semantics, with counts for the selected population.
    packet = dict(source, records=records, counts=dict(samples=len(records),
                  document_types=dict(Counter(r['sample']['document_type'] for r in records)),
                  label_statuses=dict(Counter(f['status'] for r in records for f in r['labels']['fields']))))
    require(all(sha(p) == h for p, h in zip(paths, hashes)), 'selection inputs changed')
    return dict(artifact_version=VERSION, status='prepared_not_approved',
                scope='selected records preparation only; original assets still required; no archive, pixel QA, membership approval or consumer ACK',
                inputs={key: dict(name=p.name, sha256=h) for key, p, h in
                        zip(('manifest', 'report', 'review', 'plan', 'asset_manifest'), paths, hashes)},
                selection=dict(members=expected['members'], counts=expected['counts']['after'],
                               decisions=[d for d in expected['decisions'] if d['sample_id'] in selected]),
                prerequisites=expected['prerequisites'], training_records=packet)


def export(root, manifest, report, review, plan, asset_manifest, output):
    output = Path(output)
    require(not output.exists(), 'output already exists')
    result = prepare(root, manifest, report, review, plan, asset_manifest)
    content = encoded(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(content)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('root', 'manifest', 'report', 'review', 'plan', 'asset-manifest', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    result = export(args.root, args.manifest, args.report, args.review, args.plan, args.asset_manifest, args.output)
    print(encoded(dict(status=result['status'], counts=result['selection']['counts'])).decode(), end='')


if __name__ == '__main__':
    main()
