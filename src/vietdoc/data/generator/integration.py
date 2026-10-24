"""Bounded D1.2 integration renderer. No OCR, model, split or business persistence."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from PIL import Image
from jsonschema import Draft202012Validator

from .values import CONFIG, integration_samples as samples
from .rendering import render, raw

VERSION = 'd1.2.v1'
FONT = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')


def dump(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def leaves(payload):
    result = {'/' + k: v for k, v in payload.items() if k != 'items'}
    for i, row in enumerate(payload['items']):
        result.update({f'/items/{i}/{k}': v for k, v in row.items()})
    return result


def build(root, output, manifest, seed=1202, font_path=FONT, tiny=False):
    schema = json.loads((root / 'specs/contracts/business.schema.json').read_text())
    validator = Draft202012Validator(schema)
    selected = list(samples(seed))
    if tiny:
        selected = [s for s in selected if s[0] in {'d12-receipt-03', 'd12-invoice-04'}]
    # Preflight every destination before writing, never overwrite artifacts.
    destinations = [output / f'{sid}.{suffix}' for sid, *_ in selected
                    for suffix in ('png', 'gold.json', 'txt', 'regions.json', 'labels.json')]
    for path in destinations + [manifest]:
        if path.exists():
            raise FileExistsError(path)
    output.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    for sid, kind, layout, payload in selected:
        validator.validate(payload)
        image, transcript, regions = render(payload, kind, layout, font_path)
        labels = {p: dict(status='absent' if v is None else 'present',
                         raw=raw(p.rsplit('/', 1)[-1], v),
                         reason='Không in trường này.' if v is None else None)
                  for p, v in leaves(payload).items()}
        image.save(output / f'{sid}.png')
        (output / f'{sid}.txt').write_text(transcript, encoding='utf-8')
        for suffix, value in [('gold', payload), ('regions', regions), ('labels', labels)]:
            dump(output / f'{sid}.{suffix}.json', value)
        assets = {}
        for suffix in ('png', 'gold.json', 'txt', 'regions.json', 'labels.json'):
            path = output / f'{sid}.{suffix}'
            assets[suffix] = dict(path=path.relative_to(root).as_posix(), sha256=sha(path))
        entries.append(dict(sample_id=sid, base_id=sid, family_id=f'{kind}-layout-{layout}',
                            template_id=f'{kind}-layout-{layout}-v1', document_type=kind,
                            schema_id=schema['$id'], seed=seed, generator_version=VERSION,
                            row_count=len(payload['items']), label_statuses=dict(Counter(x['status'] for x in labels.values())),
                            assets=assets))
    dump(manifest, dict(version=VERSION, purpose='shared integration set; not untouched holdout',
                        font_sha256=sha(font_path), config_sha256=sha(CONFIG), samples=entries))


def load_artifacts(root, manifest):
    """Consumer smoke loader: validate hashes, decodability, schema and evidence coverage."""
    data = json.loads(manifest.read_text())
    asset_root = manifest.parent if data.get('asset_paths') == 'relative to manifest directory' else root
    validator = Draft202012Validator(json.loads((root / 'specs/contracts/business.schema.json').read_text()))
    ids = set()
    for sample in data['samples']:
        sid = sample['sample_id']
        assert sid not in ids, sid
        ids.add(sid)
        assets = {}
        for suffix, asset in sample['assets'].items():
            path = (asset_root / asset['path']).resolve()
            assert path.is_relative_to(asset_root.resolve())
            assert sha(path) == asset['sha256'], path
            assets[suffix] = path
        with Image.open(assets['png']) as image:
            image.load()
            size = image.size
        gold = json.loads(assets['gold.json'].read_text())
        validator.validate(gold)
        labels = json.loads(assets['labels.json'].read_text())
        geometry = json.loads(assets['regions.json'].read_text())
        assert size == (geometry['width'], geometry['height'])
        regions = geometry['regions']
        assert assets['txt'].read_text() == ''.join(r['text'] + '\n' for r in regions)
        assert set(labels) == set(leaves(gold))
        for pointer, value in leaves(gold).items():
            hits = [r['text'] for r in regions if r['pointer'] == pointer]
            status = labels[pointer]['status']
            assert status in ('present', 'absent', 'obscured', 'unlabeled')
            assert (status == 'present') == (value is not None)
            assert labels[pointer]['raw'] == raw(pointer.rsplit('/', 1)[-1], value)
            if value is None:
                assert not hits, pointer
            else:
                expected = labels[pointer]['raw']
                assert any(expected in hit for hit in hits) or ' '.join(hits) == expected, pointer
        for region in regions:
            x0, y0, x1, y1 = region['bbox_px']
            assert 0 <= x0 < x1 <= size[0] and 0 <= y0 < y1 <= size[1]
        yield sample, gold


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path, default=Path('datasets/processed/d12-integration-v1'))
    parser.add_argument('--manifest', type=Path, default=Path('datasets/manifests/d12-integration-v1.json'))
    parser.add_argument('--seed', type=int, default=1202)
    parser.add_argument('--font', type=Path, default=FONT)
    parser.add_argument('--tiny', action='store_true')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = root / args.manifest
    if not args.verify:
        build(root, root / args.output, manifest, args.seed, args.font, args.tiny)
    loaded = list(load_artifacts(root, manifest))
    print(json.dumps(dict(samples=len(loaded), types=dict(Counter(s['document_type'] for s, _ in loaded))), ensure_ascii=False))


if __name__ == '__main__':
    main()
