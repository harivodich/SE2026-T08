"""D2.1 reproducible generator/validator built on D1.2 values and renderer."""
import argparse
import hashlib
from collections import Counter
from io import BytesIO
from importlib.metadata import version
from pathlib import Path
import platform
import sys
import zlib

from PIL import Image, ImageFont, features

from ..manifest import ASSETS, asset_path, encoded, read_json, require, sample_id, sha
from ..validation import approval_diagnostics, leaves, supported_glyph, validate_source
from .pdf import pdf_bytes
from .rendering import FONT, raw, render
from .templates import TEMPLATE_VERSION
from .values import CONFIG, document_cases

VERSION = 'd2.1.v1'
DEFAULT_CONFIG = Path(__file__).with_name('d21.json')


def renderer_binaries():
    """Pin actual renderer builds, including Linux shaping libs with unavailable version APIs."""
    paths = {Path(Image.core.__file__), Path(ImageFont.core.__file__)}
    maps = Path('/proc/self/maps')
    if maps.is_file():
        for line in maps.read_text().splitlines():
            name = line.split()[-1]
            if name.startswith('/') and Path(name).name.startswith(
                    ('libfreetype.', 'libraqm.', 'libharfbuzz.', 'libfribidi.', 'libz.', 'libpng')):
                paths.add(Path(name))
    return {p.name: sha(p) for p in sorted(paths)}


def environment():
    return dict(python=platform.python_version(), platform=sys.platform,
                pillow=version('Pillow'), jsonschema=version('jsonschema'),
                freetype=features.version('freetype2'), raqm=features.version('raqm'),
                harfbuzz=features.version('harfbuzz'), fribidi=features.version('fribidi'),
                zlib=zlib.ZLIB_RUNTIME_VERSION, renderer_binaries=renderer_binaries())


def source_hashes():
    base = Path(__file__).parent
    paths = [base / p for p in ('d21.py', 'values.py', 'rendering.py', 'pdf.py', 'templates/__init__.py')]
    paths += [base.parent / p for p in ('manifest.py', 'validation.py')]
    return {p.relative_to(base.parent).as_posix(): sha(p) for p in paths}


def load_config(path):
    config = read_json(path)
    return validate_config(config)


def validate_config(config):
    require(isinstance(config, dict), 'config must be object')
    require(set(config) == {'version', 'rows', 'font_sha256'}, 'unknown/missing config keys')
    require(config['version'] == VERSION, 'unsupported config/generator version')
    rows = config['rows']
    require(isinstance(rows, list) and rows and all(type(n) is int and 0 <= n <= 100 for n in rows),
            'rows must be integers in [0,100]')
    require(len(set(rows)) == len(rows), 'duplicate row profiles')
    require(isinstance(config['font_sha256'], str) and len(config['font_sha256']) == 64, 'invalid font hash')
    return config


def labels_for(payload):
    return {pointer: dict(status='absent' if value is None else 'present',
                          raw=raw(pointer.rsplit('/', 1)[-1], value),
                          reason='Không in trường này.' if value is None else None)
            for pointer, value in leaves(payload).items()}


def artifacts(payload, kind, layout, schema, font):
    validate_source(payload, kind, schema, font)
    image, transcript, regions = render(payload, kind, layout, font)
    # Unicode/font checks cover the full transcript too, including static labels.
    validate_source_text(transcript, font)
    png = BytesIO()
    image.save(png, format='PNG')
    return {'png': png.getvalue(), 'pdf': pdf_bytes(image), 'gold.json': encoded(payload),
            'txt': transcript.encode('utf-8'), 'regions.json': encoded(regions),
            'labels.json': encoded(labels_for(payload))}


def validate_source_text(transcript, font):
    for char in sorted(set(transcript) - {' ', '\n'}):
        require(supported_glyph(str(font), char), f'font missing glyph: {char!r}')


def build(root, output, seed=2101, config_path=DEFAULT_CONFIG, font=FONT, requested_version=VERSION):
    require(requested_version == VERSION, 'unsupported generator version')
    require(type(seed) is int and 0 <= seed < 2**63, 'seed must be integer in [0,2^63)')
    config = load_config(config_path)
    require(sha(font) == config['font_sha256'], 'font hash does not match pinned config')
    schema_path = root / 'specs/contracts/business.schema.json'
    schema = read_json(schema_path)
    vocabulary = read_json(CONFIG)
    # Exclusive directory creation: previous output is never overwritten.
    output.mkdir(parents=True, exist_ok=False)
    entries, rejected, ids = [], [], set()
    for sid, kind, layout, payload in document_cases(seed, config, vocabulary):
        sample_id(sid)
        require(sid not in ids, f'duplicate ID: {sid}')
        ids.add(sid)
        try:
            files = artifacts(payload, kind, layout, schema, font)
        except ValueError as error:
            rejected.append(dict(sample_id=sid, document_type=kind, row_count=len(payload['items']),
                                 status='rejected', reason=str(error)))
            continue
        assets = {}
        for suffix, data in files.items():
            path = output / f'{sid}.{suffix}'
            with path.open('xb') as stream:
                stream.write(data)
            assets[suffix] = dict(path=path.name, sha256=sha(path))
        entries.append(dict(sample_id=sid, base_id=sid, family_id=f'{kind}-layout-{layout}',
                            template_id=f'{kind}-layout-{layout}-{TEMPLATE_VERSION}', layout=layout,
                            document_type=kind, schema_id=schema['$id'], seed=seed, generator_version=VERSION,
                            row_count=len(payload['items']),
                            label_statuses=dict(Counter(x['status'] for x in labels_for(payload).values())),
                            validation=approval_diagnostics(payload), assets=assets))
    report = dict(rejected=rejected, excluded=[], accepted_count=len(entries), rejected_count=len(rejected))
    report_path = output / 'rejections.json'
    report_path.write_bytes(encoded(report))
    manifest = dict(version=VERSION, seed=seed, config=config, config_sha256=hashlib.sha256(encoded(config)).hexdigest(),
                    vocabulary_sha256=sha(CONFIG), schema_sha256=sha(schema_path),
                    schema_id=schema['$id'], font_sha256=sha(font), template_version=TEMPLATE_VERSION,
                    environment=environment(), source_sha256=source_hashes(),
                    purpose='synthetic integration/boundary QA; no split or untouched holdout claim',
                    report=dict(path=report_path.name, sha256=sha(report_path)), samples=entries)
    (output / 'manifest.json').write_bytes(encoded(manifest))
    return manifest


def validate(root, manifest_path, font=FONT, assets_root=None):
    """Strict current-version validator, including re-rendered pixel/label/PDF comparison.

    Paths resolve beneath the manifest directory; hash checks are integrity checks,
    not authentication of an untrusted manifest. No assertions disabled by python -O.
    """
    manifest = read_json(manifest_path)
    base = manifest_path.parent if assets_root is None else assets_root.resolve()
    require(manifest['version'] == VERSION, 'unsupported manifest version')
    validate_config(manifest['config'])
    require(type(manifest['seed']) is int and 0 <= manifest['seed'] < 2**63, 'invalid seed')
    require(manifest['template_version'] == TEMPLATE_VERSION, 'template version mismatch')
    require(manifest['environment'] == environment(), 'renderer environment differs; use pinned environment')
    require(manifest['source_sha256'] == source_hashes(), 'generator source changed; regenerate with version bump')
    require(manifest['font_sha256'] == sha(font) == manifest['config']['font_sha256'], 'font hash mismatch')
    require(manifest['config_sha256'] == hashlib.sha256(encoded(manifest['config'])).hexdigest(), 'config hash mismatch')
    require(manifest['vocabulary_sha256'] == sha(CONFIG), 'vocabulary hash mismatch')
    schema_path = root / 'specs/contracts/business.schema.json'
    require(manifest['schema_sha256'] == sha(schema_path), 'schema hash mismatch')
    schema = read_json(schema_path)
    require(manifest['schema_id'] == schema['$id'], 'schema ID mismatch')
    # Reconstruct the complete source set: detect omitted samples and false rejections.
    expected = {sid: (kind, layout, payload) for sid, kind, layout, payload in
                document_cases(manifest['seed'], manifest['config'], read_json(CONFIG))}
    ids, paths, image_hashes = set(), set(), set()
    for sample in manifest['samples']:
        sid = sample_id(sample['sample_id'])
        require(sid not in ids, f'duplicate ID: {sid}')
        ids.add(sid)
        require(sid in expected, f'unknown sample: {sid}')
        kind, layout, payload = expected[sid]
        require(sample['document_type'] == kind and sample['layout'] == layout, f'type/layout mismatch: {sid}')
        require(sample['seed'] == manifest['seed'] and sample['generator_version'] == VERSION, f'version/seed mismatch: {sid}')
        require(sample['schema_id'] == schema['$id'] and sample['base_id'] == sid and
                sample['family_id'] == f'{kind}-layout-{layout}' and
                sample['template_id'] == f'{kind}-layout-{layout}-{TEMPLATE_VERSION}', f'lineage mismatch: {sid}')
        require(set(sample['assets']) == set(ASSETS), f'missing/unknown asset: {sid}')
        actual = {}
        for suffix, asset in sample['assets'].items():
            path = asset_path(base, asset['path'])
            require(path not in paths, f'duplicate asset reference: {sid}')
            paths.add(path)
            require(sha(path) == asset['sha256'], f'hash mismatch: {sid}/{suffix}')
            actual[suffix] = path
        require(sample['assets']['png']['sha256'] not in image_hashes, f'duplicate image: {sid}')
        image_hashes.add(sample['assets']['png']['sha256'])
        with Image.open(actual['png']) as image:
            image.load()
            require(image.format == 'PNG' and image.mode == 'RGB' and image.size == (1500, 2600), f'image dimensions/format: {sid}')
        gold = read_json(actual['gold.json'])
        require(gold == payload, f'gold/source mismatch: {sid}')
        require(sample['row_count'] == len(gold['items']), f'row count mismatch: {sid}')
        regenerated = artifacts(gold, kind, layout, schema, font)
        for suffix in ASSETS:
            require(actual[suffix].read_bytes() == regenerated[suffix], f'render/evidence mismatch: {sid}/{suffix}')
        require(sample['validation'] == approval_diagnostics(gold), f'approval diagnostics mismatch: {sid}')
        require(sample['label_statuses'] == dict(Counter(x['status'] for x in labels_for(gold).values())), f'label status counts: {sid}')
    report_path = asset_path(base, manifest['report']['path'])
    require(report_path not in paths, 'report aliases sample asset')
    require(sha(report_path) == manifest['report']['sha256'], 'report hash mismatch')
    report = read_json(report_path)
    require(report['excluded'] == [] and report['accepted_count'] == len(ids), 'report counts/exclusions mismatch')
    require(report['rejected_count'] == len(report['rejected']), 'rejected count mismatch')
    for rejected in report['rejected']:
        sid = sample_id(rejected['sample_id'])
        require(sid not in ids and sid in expected, f'duplicate/unknown rejected ID: {sid}')
        ids.add(sid)
        kind, layout, payload = expected[sid]
        require(rejected['document_type'] == kind and rejected['row_count'] == len(payload['items']) and rejected['status'] == 'rejected', f'rejected metadata: {sid}')
        try:
            artifacts(payload, kind, layout, schema, font)
        except ValueError as error:
            require(rejected['reason'] == str(error), f'rejection reason mismatch: {sid}')
        else:
            raise ValueError(f'false rejection: {sid}')
    require(ids == set(expected), 'missing samples in manifest/report')
    return dict(accepted=len(manifest['samples']), rejected=len(report['rejected']), valid=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path)
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--seed', type=int, default=2101)
    parser.add_argument('--version', default=VERSION)
    parser.add_argument('--font', type=Path, default=FONT)
    parser.add_argument('--verify', type=Path, metavar='MANIFEST')
    parser.add_argument('--assets-root', type=Path, help='explicit asset directory for a relocated manifest snapshot')
    args = parser.parse_args()
    try:
        if args.verify:
            require(args.output is None, '--verify and --output are mutually exclusive')
            result = validate(args.root.resolve(), args.verify.resolve(), args.font, args.assets_root)
        else:
            require(args.assets_root is None, '--assets-root requires --verify')
            require(args.output is not None, '--output is required for generation')
            build(args.root.resolve(), args.output.resolve(), args.seed, args.config, args.font, args.version)
            result = validate(args.root.resolve(), args.output.resolve() / 'manifest.json', args.font)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, f'Validation failed: {error}\n')
    print(encoded(result).decode(), end='')


if __name__ == '__main__':
    main()
