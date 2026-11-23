"""Export verified Data records for consumer inspection; no training/loss policy."""
import argparse
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from .labels import VERSION as LABEL_VERSION, load_training_labels
from ..manifest import asset_path, encoded, read_json, require, sha

VERSION = 'vietdoc.training-records.v1'


def training_packet(root, manifest, *, full_set=False):
    """Keep gold and four-state labels from the same validated renderer snapshot.

    Paths retain their declared base. The packet is a Data handoff, not a model
    batch or evidence that a consumer implements masking correctly. Consumers
    must verify the referenced manifest/assets again before using mutable files.
    """
    root, manifest = Path(root).resolve(), Path(manifest).resolve()
    manifest_hash = sha(manifest)
    schema_path = root / 'specs/contracts/business.schema.json'
    schema_hash = sha(schema_path)
    schema = read_json(schema_path)
    data = read_json(manifest)
    loaded = list(load_training_labels(root, manifest, full_set=full_set))
    require(data['samples'] == [sample for sample, _, _ in loaded],
            'manifest changed during record export')
    base = manifest.parent if data['version'].startswith('d2.') else root
    records, counts = [], Counter()
    for sample, gold, labels in loaded:
        for name, asset in sample['assets'].items():
            require(sha(asset_path(base, asset['path'])) == asset['sha256'],
                    f'{sample["sample_id"]}: asset changed during record export: {name}')
        counts.update(field.status for field in labels.fields)
        records.append(dict(sample=sample, gold=gold,
                            labels=dict(version=labels.version, fields=[asdict(f) for f in labels.fields])))
    require(sha(manifest) == manifest_hash, 'manifest changed during record export')
    require(sha(schema_path) == schema_hash, 'schema changed during record export')
    return dict(artifact_version=VERSION, label_adapter_version=LABEL_VERSION,
                manifest=dict(name=manifest.name, version=data['version'], sha256=manifest_hash),
                schema=dict(id=schema['$id'], sha256=schema_hash),
                asset_base='manifest_directory' if data['version'].startswith('d2.') else 'root',
                counts=dict(samples=len(records), document_types=dict(Counter(
                    sample['document_type'] for sample, _, _ in loaded)), label_statuses=dict(counts)),
                scope='validated Data records; consumer target/mask/loss policy and ACK remain required',
                records=records)


def export_records(root, manifest, output, *, full_set=False):
    output = Path(output)
    require(not output.exists(), 'output already exists')
    packet = training_packet(root, manifest, full_set=full_set)
    # Do not publish even a partial packet when a later sample fails validation.
    content = encoded(packet)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(content)
    return packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='root containing the business schema')
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--full-set', action='store_true', help='require the complete D1.2 integration set')
    parser.add_argument('--output', type=Path, required=True, help='new JSON file; never overwritten')
    args = parser.parse_args()
    packet = export_records(args.root, args.manifest, args.output, full_set=args.full_set)
    print(encoded(dict(artifact_version=VERSION, manifest=packet['manifest'],
                       counts=packet['counts'], sha256=sha(args.output))).decode(), end='')


if __name__ == '__main__':
    main()
