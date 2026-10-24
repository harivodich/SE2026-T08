"""D2.2 grouped synthetic dataset builder; smoke by default, no freeze authority."""
import argparse
import copy
import hashlib
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import random

from PIL import Image

from ..manifest import ASSETS, asset_path, encoded, read_json, require, sha, sample_id
from ..splits import assign_groups, digest, duplicate_report
from ..validation import leaves, validate_source
from .augmentation import augment, validate_policy
from .d21 import environment, validate_source_text, source_hashes as d21_sources
from .pdf import pdf_bytes
from .rendering import FONT
from .templates.families import VERSION as FAMILY_VERSION, catalog, render_family
from .values import CONFIG, integration_samples

VERSION = 'd2.2.v1'
DEFAULT_CONFIG = Path(__file__).with_name('d22.json')


def source_hashes():
    base = Path(__file__).parent
    return dict(d21_sources(), **{p.relative_to(base.parent).as_posix(): sha(p) for p in
                [base / 'd22.py', base / 'augmentation.py', base / 'templates/families.py', base.parent / 'splits.py']})


def validate_config(config):
    require(set(config) == {'version', 'dataset_version', 'bases_per_family', 'rows', 'font_sha256',
                            'augmentations', 'dev_min_clean_per_type', 'source_aliases'}, 'config keys')
    require(config['version'] == VERSION, 'unsupported generator/config version')
    require(isinstance(config['dataset_version'], str), 'dataset version must be string')
    sample_id(config['dataset_version'].replace('.', '-'))
    require(type(config['bases_per_family']) is int and 1 <= config['bases_per_family'] <= 300,
            'bases_per_family must be in [1,300] (20 families => up to 6000 clean bases)')
    require(isinstance(config['rows'], list) and config['rows'] and
            all(type(n) is int and 0 <= n <= 30 for n in config['rows']), 'rows bound [0,30]')
    require(type(config['dev_min_clean_per_type']) is int and config['dev_min_clean_per_type'] >= 1,
            'dev support threshold must be positive')
    require(isinstance(config['augmentations'], list) and len(config['augmentations']) <= 8, 'augmentation count bound')
    names = ['clean']
    for policy in config['augmentations']:
        validate_policy(policy)
        sample_id(policy['name'])
        names.append(policy['name'])
    require(len(set(names)) == len(names), 'duplicate variant name')
    aliases = config['source_aliases']
    require(isinstance(aliases, dict) and set(aliases) <= {f['family_id'] for f in catalog()}, 'unknown source alias family')
    for value in aliases.values():
        sample_id(value)
    return config


def plan(config, seed):
    """Complete assignment before calling any value factory, including dev subpartitions."""
    require(type(seed) is int and 0 <= seed < 2**63, 'seed range')
    records = []
    for family in catalog():
        for index in range(config['bases_per_family']):
            base = f"{config['dataset_version'].replace('.', '-')}-{family['family_id']}-b{index:04}"
            records.append(dict(base_id=base, family_id=family['family_id'], document_type=family['document_type'],
                                source_group=config['source_aliases'].get(family['family_id'], 'synthetic-' + family['family_id']),
                                split=family['split'], value_seed=int(digest([seed, base])[:15], 16),
                                row_count=config['rows'][(family['index'] + index) % len(config['rows'])]))
    records = assign_groups(records)
    # Reserve whole dev families for a subpartition, avoiding family crossover too.
    dev_groups = {}
    for record in records:
        if record['split'] == 'dev':
            group = record['assignment_group']
            dev_groups[group] = min(dev_groups.get(group, record['family_id']), record['family_id'])
    for record in records:
        record['dev_partition'] = (('dev-tuning' if dev_groups[record['assignment_group']].endswith('06') else 'dev-calibration')
                                   if record['split'] == 'dev' else None)
    sufficient = all(sum(r['document_type'] == kind and r['dev_partition'] == part for r in records)
                     >= config['dev_min_clean_per_type'] for kind in ('receipt', 'invoice')
                     for part in ('dev-tuning', 'dev-calibration'))
    if not sufficient:
        for record in records:
            record['dev_partition'] = None
    return records


def payload_for(record, vocabulary):
    rng = random.Random(record['value_seed'])
    kind = record['document_type']
    payload = copy.deepcopy(next(p for sid, k, _, p in integration_samples(record['value_seed'], vocabulary)
                                 if k == kind and sid.endswith('03')))
    day = (date(2026, 1, 1) + timedelta(days=rng.randrange(365))).isoformat()
    payload['transaction_date' if kind == 'receipt' else 'issue_date'] = day
    payload['items'] = []
    for _ in range(record['row_count']):
        row = dict(rng.choice(vocabulary['products']))
        row['quantity'] = rng.choice(['0.5', '1', '2', '3', '5'])
        row['unit_price'] = str(rng.randrange(1, 1000) * 1000)
        row['line_total'] = str(Decimal(row['quantity']) * Decimal(row['unit_price']))
        payload['items'].append(row)
    subtotal = sum((Decimal(r['line_total']) for r in payload['items']), Decimal(0))
    payload['total_amount'] = str(subtotal)
    if kind == 'receipt':
        payload['merchant_name'] = rng.choice(vocabulary['merchants'])
        payload['merchant_address'] = rng.choice(vocabulary['addresses']) if rng.randrange(3) else None
        payload['transaction_time'] = f'{rng.randrange(24):02}:{rng.randrange(60):02}' if rng.randrange(3) else None
    else:
        payload['seller_name'] = rng.choice(vocabulary['sellers'])
        payload['buyer_name'] = rng.choice(vocabulary['buyers']) if rng.randrange(3) else None
        payload['invoice_number'] = f"GIẢ-LẬP-{record['value_seed']}"
        payload['subtotal'] = str(subtotal)
        payload['tax_amount'], payload['discount_amount'] = rng.choice([('0', '0'), ('10000', '5000'), ('0', '1000')])
        payload['discount_amount'] = str(min(Decimal(payload['discount_amount']), subtotal + Decimal(payload['tax_amount'])))
        payload['total_amount'] = str(subtotal + Decimal(payload['tax_amount']) - Decimal(payload['discount_amount']))
    return payload


CLEAN = dict(name='clean', shear=0, blur=0, noise=0, crop=[0, 0, 0, 0], unreadable=False)


def generated(root, config, seed, font):
    assignments = plan(config, seed)  # Deliberately materialized before any values.
    schema = read_json(root / 'specs/contracts/business.schema.json')
    vocabulary = read_json(CONFIG)
    families = {f['family_id']: f for f in catalog()}
    for record in assignments:
        payload = payload_for(record, vocabulary)
        kind = record['document_type']
        validate_source(payload, kind, schema, font)
        image, geometry = render_family(payload, families[record['family_id']], font)
        content = {p: v for p, v in leaves(payload).items() if p != '/invoice_number'}
        for policy in [CLEAN] + config['augmentations']:
            variant_seed = int(digest([record['value_seed'], policy['name']])[:15], 16)
            raster, gold, labels, regions, transcript = augment(image, geometry, payload, policy, variant_seed)
            validate_source(gold, kind, schema, font)
            validate_source_text(transcript, font)
            stream = BytesIO()
            raster.save(stream, format='PNG')
            small = raster.convert('L').resize((9, 8), Image.Resampling.LANCZOS)
            pixels = list(small.getdata())
            bits = ''.join('1' if pixels[y*9+x] > pixels[y*9+x+1] else '0' for y in range(8) for x in range(8))
            quality = ('unreadable' if policy['unreadable'] else 'clean' if policy['name'] == 'clean'
                       else 'content-loss' if any(l['status'] == 'obscured' for l in labels.values()) else 'bounded')
            sid = record['base_id'] + '-' + policy['name']
            sample_id(sid)
            files = dict(png=stream.getvalue(), pdf=pdf_bytes(raster),
                         **{'gold.json': encoded(gold), 'labels.json': encoded(labels),
                            'regions.json': encoded(regions), 'txt': transcript.encode('utf-8')})
            entry = dict(record, sample_id=sid, template_id=record['family_id'] + '-' + FAMILY_VERSION,
                         schema_id=schema['$id'], generator_version=VERSION, augmentation=policy,
                         augmentation_seed=variant_seed, quality=quality,
                         source_gold_sha256=digest(payload), content_sha256=digest(content),
                         content_tokens=(sorted({digest(str(v)) for v in content.values() if v is not None})
                                         if quality == 'clean' else []),
                         dhash=f'{int(bits, 2):016x}', label_statuses=dict(Counter(l['status'] for l in labels.values())),
                         assets={suffix: dict(path=f'{sid}.{suffix}', sha256=hashlib.sha256(data).hexdigest())
                                 for suffix, data in files.items()})
            yield entry, files


def report_for(samples, config):
    clean = [s for s in samples if s['quality'] == 'clean']
    counts = {}
    for label, subset in (('base_documents', clean), ('images_including_variants', samples)):
        counts[label] = dict(total=len(subset))
        for key in ('document_type', 'family_id', 'source_group', 'split', 'quality', 'row_count', 'dev_partition'):
            counts[label][key] = dict(sorted(Counter(str(s[key]) for s in subset).items()))
        counts[label]['label_statuses'] = dict(sum((Counter(s['label_statuses']) for s in subset), Counter()))
    cells = Counter((s['document_type'], s['family_id'], s['split'], s['quality'], s['row_count'], status)
                    for s in samples for status in s['label_statuses'])
    fields = Counter()
    image_counts = Counter(s['base_id'] for s in samples)
    for sample in samples:
        for status, count in sample['label_statuses'].items():
            fields[(sample['document_type'], sample['family_id'], sample['split'], sample['quality'],
                    sample['row_count'], status)] += count
    support = {kind: {part: sum(s['document_type'] == kind and s['dev_partition'] == part for s in clean)
                      for part in ('dev-tuning', 'dev-calibration')} for kind in ('receipt', 'invoice')}
    return dict(counts=counts, bases=[dict(base_id=s['base_id'], document_type=s['document_type'],
                                         family_id=s['family_id'], split=s['split'], clean_documents=1,
                                         images=image_counts[s['base_id']]) for s in clean],
                cross_counts=[dict(document_type=k[0], family_id=k[1], split=k[2], quality=k[3],
                                   rows=k[4], status=k[5], images=v, fields=fields[k]) for k, v in sorted(cells.items())],
                leakage=duplicate_report(samples), dev_support=dict(clean_base_counts=support,
                unpartitioned_dev_bases={kind: sum(s['document_type'] == kind and s['split'] == 'dev' and
                                                  s['dev_partition'] is None for s in clean) for kind in ('receipt', 'invoice')},
                configured_minimum_per_type=config['dev_min_clean_per_type'],
                partition_enabled=all(v >= config['dev_min_clean_per_type'] for c in support.values() for v in c.values()),
                calibration_sufficiency='not established; correctness labels, class/field coverage and Lead review still required'),
                planning_targets=dict(families_per_type=10, family_splits='6 train / 2 dev / 2 final',
                                      clean_bases_total=[3000, 6000], bases_per_family=[150, 300],
                                      approved_capacity=False, final_frozen=False),
                exclusions=[], readiness='smoke/review only; ambiguous findings require review before pilot/freeze')


def provenance(root, config, seed, font):
    return dict(version=VERSION, dataset_version=config['dataset_version'], config=config, config_sha256=digest(config),
                seed=seed, assignments=plan(config, seed), assignment_sha256=digest(plan(config, seed)),
                families=catalog(), template_version=FAMILY_VERSION, source_sha256=source_hashes(),
                vocabulary_sha256=sha(CONFIG), schema_sha256=sha(root / 'specs/contracts/business.schema.json'),
                font_sha256=sha(font), environment=environment(), asset_paths='relative to manifest directory',
                source_kind='fictional synthetic', language='vi', license='project-generated fictional data; distribution terms pending Lead decision',
                final_frozen=False, capacity_decision='pending Lead/G0; this manifest grants no capacity approval')


def build(root, output, config_path=DEFAULT_CONFIG, seed=2202, font=FONT, base_limit=40):
    config = validate_config(read_json(config_path))
    require(20 * config['bases_per_family'] <= base_limit, 'clean base limit exceeded; use reviewed capacity before raising --base-limit')
    require(sha(font) == config['font_sha256'], 'font hash mismatch')
    metadata = provenance(root, config, seed, font)
    output.mkdir(parents=True, exist_ok=False)
    samples, image_hashes, excluded = [], set(), []
    for entry, files in generated(root, config, seed, font):
        image_hash = entry['assets']['png']['sha256']
        # Identical variants add no evidence. Across bases fail rather than invent
        # a clean independent document or silently alter the preassigned split.
        if image_hash in image_hashes:
            previous = next(s for s in samples if s['assets']['png']['sha256'] == image_hash)
            require(previous['base_id'] == entry['base_id'], 'duplicate image across bases; revise/group source before generation')
            excluded.append(dict(sample_id=entry['sample_id'], reason='redundant exact image variant', duplicate_of=previous['sample_id']))
            continue
        image_hashes.add(image_hash)
        for suffix, data in files.items():
            with (output / entry['assets'][suffix]['path']).open('xb') as stream:
                stream.write(data)
        samples.append(entry)
    report = report_for(samples, config)
    report['exclusions'] = excluded
    (output / 'report.json').write_bytes(encoded(report))
    manifest = dict(metadata, report=dict(path='report.json', sha256=sha(output / 'report.json')), samples=samples)
    (output / 'manifest.json').write_bytes(encoded(manifest))
    (output / 'manifest.sha256').write_text(sha(output / 'manifest.json') + '  manifest.json\n')
    return manifest


def validate(root, manifest_path, font=FONT, assets_root=None):
    manifest = read_json(manifest_path)
    config = validate_config(manifest['config'])
    require(sha(font) == config['font_sha256'], 'font hash mismatch')
    metadata = provenance(root, config, manifest['seed'], font)
    require({k: manifest[k] for k in metadata} == metadata, 'manifest provenance/assignment/environment drift')
    require(set(manifest) == set(metadata) | {'report', 'samples'}, 'unknown manifest keys')
    base = manifest_path.parent if assets_root is None else assets_root.resolve()
    expected, excluded, images, paths = [], [], {}, set()
    for entry, files in generated(root, config, manifest['seed'], font):
        image_hash = entry['assets']['png']['sha256']
        if image_hash in images:
            require(images[image_hash]['base_id'] == entry['base_id'], 'duplicate image across bases')
            excluded.append(dict(sample_id=entry['sample_id'], reason='redundant exact image variant', duplicate_of=images[image_hash]['sample_id']))
            continue
        images[image_hash] = entry
        expected.append(entry)
        require(len(manifest['samples']) >= len(expected) and manifest['samples'][len(expected) - 1] == entry,
                'sample omission/order/metadata/lineage drift')
        require(set(files) == set(ASSETS), 'asset set mismatch')
        for suffix, data in files.items():
            path = asset_path(base, entry['assets'][suffix]['path'])
            require(path not in paths and path.read_bytes() == data, f'asset drift: {entry["sample_id"]}/{suffix}')
            paths.add(path)
    require(manifest['samples'] == expected, 'sample omission/order/metadata/lineage drift')
    report = report_for(expected, config)
    report['exclusions'] = excluded
    require(manifest['report']['path'] == 'report.json', 'report path mismatch')
    path = asset_path(base, manifest['report']['path'])
    require(sha(path) == manifest['report']['sha256'] and read_json(path) == report, 'report drift')
    return dict(valid=True, base_documents=report['counts']['base_documents']['total'], samples=len(expected),
                ambiguous_pairs=len(report['leakage']['ambiguous']), final_frozen=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path)
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--seed', type=int, default=2202)
    parser.add_argument('--font', type=Path, default=FONT)
    parser.add_argument('--base-limit', type=int, default=40)
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--assets-root', type=Path)
    args = parser.parse_args()
    try:
        if args.verify:
            require(args.output is None, '--output incompatible with --verify')
            result = validate(args.root.resolve(), args.verify.resolve(), args.font, args.assets_root)
        else:
            require(args.output is not None and args.assets_root is None, '--output required; --assets-root only with --verify')
            build(args.root.resolve(), args.output.resolve(), args.config, args.seed, args.font, args.base_limit)
            result = validate(args.root.resolve(), args.output.resolve() / 'manifest.json', args.font)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, f'Validation failed: {error}\n')
    print(encoded(result).decode(), end='')


if __name__ == '__main__':
    main()
