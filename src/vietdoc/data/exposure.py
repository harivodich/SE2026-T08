"""Conservative exposure inventory and metadata-only untouched-holdout preflight."""
import argparse
from pathlib import Path
import re

from .adapters.records import training_packet
from .manifest import encoded, read_json, require, sample_id, sha

VERSION = 'vietdoc.exposure-ledger.v1'
IDENTITIES = ('sample_id', 'base_id', 'family_id', 'source_group', 'assignment_group')
HASHES = ('png_sha256', 'gold_sha256', 'content_sha256', 'source_gold_sha256')


def identity(sample):
    result = {key: sample.get(key) for key in IDENTITIES}
    for key in ('sample_id', 'base_id', 'family_id'):
        sample_id(result[key])
    result.update(png_sha256=sample['assets']['png']['sha256'],
                  gold_sha256=sample['assets']['gold.json']['sha256'],
                  content_sha256=sample.get('content_sha256'),
                  source_gold_sha256=sample.get('source_gold_sha256'))
    validate_identity(result)
    return result


def validate_identity(entry):
    require(isinstance(entry, dict) and set(entry) == set(IDENTITIES + HASHES), 'exposure identity keys')
    for key in IDENTITIES:
        value = entry[key]
        require((key in ('source_group', 'assignment_group') and value is None) or
                isinstance(value, str) and bool(value), 'invalid exposure identity: ' + key)
    for key in HASHES:
        value = entry[key]
        require((key in ('content_sha256', 'source_gold_sha256') and value is None) or
                isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'invalid exposure hash: ' + key)


def record(root, manifest, reference):
    require(isinstance(reference, str) and reference.strip(), 'exposure reference required')
    packet = training_packet(root, manifest)
    return dict(version=VERSION, classification='exposed_integration', reference=reference,
                scope='conservative exclusion from untouched final; not an authenticated per-person access log',
                manifest=packet['manifest'], schema=packet['schema'],
                entries=[identity(r['sample']) for r in packet['records']])


def check(ledgers, samples):
    """Only compare metadata; no final image/gold/model IO or acceptance authority."""
    require(isinstance(ledgers, list) and ledgers, 'at least one exposure ledger required')
    index = {key: set() for key in IDENTITIES + HASHES}
    for ledger in ledgers:
        require(isinstance(ledger, dict) and ledger.get('version') == VERSION and
                ledger.get('classification') == 'exposed_integration' and
                isinstance(ledger.get('reference'), str) and ledger['reference'].strip(), 'unsupported exposure ledger')
        require(isinstance(ledger.get('entries'), list) and ledger['entries'], 'nonempty exposure entries required')
        seen = set()
        for entry in ledger['entries']:
            validate_identity(entry)
            require(entry['sample_id'] not in seen, 'duplicate sample ID in exposure ledger')
            seen.add(entry['sample_id'])
            for key in index:
                if entry[key] is not None:
                    index[key].add(entry[key])
    require(isinstance(samples, list) and samples, 'nonempty candidate metadata required')
    seen, conflicts = set(), []
    for sample in samples:
        entry = identity(sample)
        sid = entry['sample_id']
        require(sid not in seen, 'duplicate candidate sample ID')
        seen.add(sid)
        overlaps = [key for key in index if entry[key] is not None and entry[key] in index[key]]
        if overlaps:
            conflicts.append(dict(sample_id=sid, overlapping_keys=overlaps))
    require(not conflicts, 'exposed candidate metadata: ' + repr(conflicts))
    return dict(status='no_known_exposure_overlap', samples=len(samples),
                scope='metadata-only preflight; not asset validation, structural independence, split approval or final-open permission')


def publish(output, result):
    output = Path(output)
    require(not output.exists(), 'output already exists')
    content = encoded(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(content)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    capture = commands.add_parser('record')
    capture.add_argument('--root', type=Path, required=True)
    capture.add_argument('--reference', required=True)
    preflight = commands.add_parser('check')
    preflight.add_argument('--ledger', type=Path, action='append', required=True)
    for command in (capture, preflight):
        command.add_argument('--manifest', type=Path, required=True)
        command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'output already exists')
    inputs = [args.manifest, *getattr(args, 'ledger', [])]
    hashes = [sha(p) for p in inputs]
    if args.command == 'record':
        result = record(args.root, args.manifest, args.reference)
    else:
        result = check([read_json(p) for p in args.ledger], read_json(args.manifest)['samples'])
    require(all(sha(p) == h for p, h in zip(inputs, hashes)), 'exposure inputs changed')
    publish(args.output, result)
    print(encoded(dict(status=result.get('status', 'recorded_exposed_integration'),
                       samples=result.get('samples', len(result.get('entries', []))))).decode(), end='')


if __name__ == '__main__':
    main()
