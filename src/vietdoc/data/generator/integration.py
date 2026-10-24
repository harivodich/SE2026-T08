"""Bounded D1.2 integration renderer and versioned artifact smoke loader."""
import argparse
from collections import Counter
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import random
import re

from PIL import Image, ImageDraw, ImageFont
from jsonschema import Draft202012Validator

from .artifact_io import asset_path, encoded, read_json, require, sample_id, sha
from .render_environment import environment
from .values import CONFIG

VERSION = 'd1.2.v2'
D1_VERSIONS = ('d1.2.v1', VERSION)
ASSETS = {'png', 'gold.json', 'txt', 'regions.json', 'labels.json'}
FONT = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
MONEY = {'unit_price', 'line_total', 'subtotal', 'tax_amount', 'discount_amount', 'total_amount'}
LABELS = dict(merchant_name='Cửa hàng', merchant_address='Địa chỉ', transaction_date='Ngày bán',
              transaction_time='Giờ', invoice_number='Số hóa đơn', issue_date='Ngày lập',
              seller_name='Đơn vị bán', buyer_name='Đơn vị mua', subtotal='Cộng tiền hàng',
              tax_amount='Tiền thuế GTGT', discount_amount='Chiết khấu', total_amount='Tổng thanh toán')


def dump(path, value):
    with path.open('xb') as stream:
        stream.write(encoded(value))


def leaves(payload):
    result = {'/' + k: v for k, v in payload.items() if k != 'items'}
    for i, row in enumerate(payload['items']):
        result.update({f'/items/{i}/{k}': v for k, v in row.items()})
    return result


def raw(key, value):
    if value is None:
        return None
    if key in MONEY:
        integer, dot, fraction = value.partition('.')
        return f'{int(integer):,}'.replace(',', '.') + (',' + fraction if dot else '') + ' đ'
    if key.endswith('date'):
        return '/'.join(reversed(value.split('-')))
    return value.replace('.', ',') if key == 'quantity' else value


def samples(seed=1202):
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    rng = random.Random(seed)
    for kind in ('receipt', 'invoice'):
        for i in range(10):
            count = [1, 3, 5, 12, 30][i // 2]
            rows = [dict(rng.choice(config['products'])) for _ in range(count)]
            if i >= 2:
                rows[0]['description'] = 'Bộ giấy gói hư cấu họa tiết lá và hoa dành cho quầy trưng bày mùa thu'
            subtotal = sum((Decimal(r['line_total']) for r in rows), Decimal(0))
            if kind == 'receipt':
                payload = dict(merchant_name=config['merchants'][i % 2],
                               merchant_address=None if i % 3 == 0 else config['addresses'][0],
                               transaction_date=f'2026-10-{i+1:02}',
                               transaction_time=None if i % 3 == 0 else f'{8+i:02}:05',
                               total_amount=str(subtotal), items=rows)
            else:
                tax, discount = ('10000', '5000') if i % 2 else ('0', '0')
                payload = dict(invoice_number=f'GIẢ-LẬP-{seed}-{i+1:02}', issue_date=f'2026-10-{i+1:02}',
                               seller_name=config['sellers'][i % 2], buyer_name=None if i % 3 == 0 else config['buyers'][0],
                               subtotal=str(subtotal), tax_amount=tax, discount_amount=discount,
                               total_amount=str(subtotal + Decimal(tax) - Decimal(discount)), items=rows)
            yield f'd12-{kind}-{i+1:02}', kind, i % 2, payload


def render(payload, kind, layout, font_path=FONT):
    width, height = 1500, 2600
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path), 23)
    title_font = ImageFont.truetype(str(font_path), 32)
    regions, transcript = [], []
    y = 35

    def text(value, x, top, pointer=None, title=False):
        face = title_font if title else font
        box = list(draw.textbbox((x, top), value, font=face))
        if not (0 <= box[0] < box[2] < width and 0 <= box[1] < box[3] < height):
            raise ValueError(f'Clipping: {value}: {box}')
        draw.text((x, top), value, font=face, fill='black')
        transcript.append(value)
        regions.append(dict(text=value, pointer=pointer, page=0, bbox_px=box))

    text('HÓA ĐƠN BÁN HÀNG' if kind == 'invoice' else 'PHIẾU THANH TOÁN', 45, y, title=True)
    y += 55
    text('DỮ LIỆU HƯ CẤU — KHÔNG CÓ GIÁ TRỊ GIAO DỊCH', 45, y)
    y += 45
    for key, value in payload.items():
        if key == 'items' or key in MONEY or value is None:
            continue
        text(LABELS[key] + ': ' + raw(key, value), 45 if layout == 0 else 180, y, '/' + key)
        y += 36
    y += 15
    columns = [('description', 'Tên hàng', 45, 650), ('quantity', 'SL', 720, 100),
               ('unit', 'ĐVT', 850, 100), ('unit_price', 'Đơn giá', 1000, 190),
               ('line_total', 'Thành tiền', 1240, 210)]
    if layout:
        columns = [columns[0], columns[2], columns[1], columns[3], columns[4]]
        columns = [(k, label, x, w) for (k, label, _, w), x in zip(columns, [45, 720, 850, 1000, 1240])]
    for _, label, x, _ in columns:
        text(label, x, y)
    y += 38
    for index, row in enumerate(payload['items']):
        max_lines = 1
        for key, _, x, max_width in columns:
            value = raw(key, row[key])
            lines, line = [], ''
            for word in value.split():
                candidate = (line + ' ' + word).strip()
                if draw.textlength(candidate, font=font) > max_width:
                    if not line:
                        raise ValueError('Word exceeds column')
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
            for offset, fragment in enumerate(lines):
                text(fragment, x, y + offset * 29, f'/items/{index}/{key}')
            max_lines = max(max_lines, len(lines))
        y += max_lines * 29 + 8
        if layout:
            draw.line((40, y - 3, 1460, y - 3), fill='#bbbbbb')
    y += 20
    for key in payload:
        if key in MONEY:
            text(LABELS[key] + ': ' + raw(key, payload[key]), 650 if layout == 0 else 45, y, '/' + key)
            y += 36
    text('Số tiền ghi lại: ' + raw('total_amount', payload['total_amount']), 45, y + 10, '/total_amount')
    return image, '\n'.join(transcript) + '\n', dict(
        convention='renderer-local-v1; not approved shared geometry', page=0,
        width=width, height=height, origin='top-left', units='pixels',
        transform='identity; PNG is the rendered page', regions=regions)


def resolve_font(font_path=None):
    """Explicit CLI/env font wins; OS discovery is a portable, noncanonical fallback."""
    requested = font_path or os.environ.get('VIETDOC_DATA_FONT')
    candidates = [requested] if requested else [FONT, 'DejaVuSans.ttf',
                  Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/arial.ttf']
    for candidate in candidates:
        try:
            face = ImageFont.truetype(str(candidate), 23)
            path = Path(face.path).resolve()
            require(path.is_file(), 'font must resolve to a local file')
            # Check Vietnamese coverage, including labels, before accepting fallback.
            missing = bytes(face.getmask('\U0010ffff'))
            for char in set('HÓA ĐƠN ăâđêôơư ắằẳẵặ ấầẩẫậ ếềểễệ ốồổỗộ ớờởỡợ ứừửữự') - {' '}:
                require(bytes(face.getmask(char)) != missing, f'font missing Vietnamese glyph: {char}')
            return path
        except (OSError, ValueError):
            if requested:
                break
    raise ValueError('No usable Vietnamese font. Pass --font PATH or set VIETDOC_DATA_FONT to a licensed local TTF.')


def build(root, output, manifest, seed=1202, font_path=None, tiny=False):
    root, output, manifest = root.resolve(), output.resolve(), manifest.resolve()
    require(output.is_relative_to(root) and manifest.is_relative_to(root), 'output/manifest must be beneath root')
    require(type(seed) is int and 0 <= seed < 2**63, 'seed must be integer in [0,2^63)')
    font_path = resolve_font(font_path)
    schema = read_json(root / 'specs/contracts/business.schema.json')
    selected = list(samples(seed))
    if tiny:
        selected = [s for s in selected if s[0] in {'d12-receipt-03', 'd12-invoice-04'}]
    destinations = [output / f'{sid}.{suffix}' for sid, *_ in selected for suffix in ASSETS]
    for path in destinations + [manifest]:
        if path.exists():
            raise FileExistsError(path)
    output.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    for sid, kind, layout, payload in selected:
        Draft202012Validator({'$ref': f'#/$defs/{kind.title()}', '$defs': schema['$defs']}).validate(payload)
        image, transcript, regions = render(payload, kind, layout, font_path)
        labels = {p: dict(status='absent' if v is None else 'present',
                         raw=raw(p.rsplit('/', 1)[-1], v),
                         reason='Không in trường này.' if v is None else None)
                  for p, v in leaves(payload).items()}
        image.save(output / f'{sid}.png')
        with (output / f'{sid}.txt').open('xb') as stream:
            stream.write(transcript.encode('utf-8'))
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
                        font_sha256=sha(font_path), config_sha256=sha(CONFIG),
                        environment=environment(), samples=entries))


def check_manifest(data):
    require(isinstance(data, dict), 'manifest must be an object')
    require(data.get('version') in D1_VERSIONS, 'unsupported manifest version')
    require(isinstance(data.get('samples'), list), 'manifest samples must be an array')
    for key in ('font_sha256',):
        require(isinstance(data.get(key), str) and re.fullmatch('[0-9a-f]{64}', data[key]), f'invalid {key}')
    if data['version'] in D1_VERSIONS:
        keys = {'version', 'purpose', 'font_sha256', 'config_sha256', 'samples'}
        require(data.get('purpose') == 'shared integration set; not untouched holdout', 'D1 purpose mismatch')
        if data['version'] == VERSION:
            keys.add('environment')
            env = data.get('environment')
            require(isinstance(env, dict) and set(env) == {'python', 'platform', 'pillow', 'jsonschema', 'zlib',
                    'freetype', 'raqm', 'harfbuzz', 'fribidi', 'renderer_binaries'} and
                    all(isinstance(env.get(k), str) and env[k] for k in
                    ('python', 'platform', 'pillow', 'jsonschema', 'zlib')) and
                    all(env[k] is None or isinstance(env[k], str) for k in
                    ('freetype', 'raqm', 'harfbuzz', 'fribidi')), 'invalid renderer environment')
            binaries = env['renderer_binaries']
            require(isinstance(binaries, dict) and binaries and
                    all(isinstance(name, str) and '/' not in name and '\\' not in name and
                        isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest)
                        for name, digest in binaries.items()), 'invalid renderer binary hashes')
        require(set(data) == keys, 'missing/unknown D1 manifest keys')
        require(data['config_sha256'] == sha(CONFIG), 'D1 vocabulary hash mismatch')


def check_metadata(sample, data, schema):
    sid = sample_id(sample['sample_id'])
    kind = sample.get('document_type')
    require(kind in ('receipt', 'invoice'), 'unsupported document_type')
    require(sample.get('schema_id') == schema['$id'], 'schema_id mismatch')
    require(sample.get('generator_version') == data['version'], 'generator version mismatch')
    seed_key = 'seed'
    require(type(sample.get(seed_key)) is int and 0 <= sample[seed_key] < 2**63, f'invalid {seed_key}')
    require(type(sample.get('row_count')) is int and 0 <= sample['row_count'] <= 30, 'invalid row_count')
    counts = sample.get('label_statuses')
    require(isinstance(counts, dict) and set(counts) <= {'present', 'absent', 'obscured', 'unlabeled'} and
            all(type(n) is int and n > 0 for n in counts.values()), 'invalid label_statuses')
    if data['version'] in D1_VERSIONS:
        require(set(sample) == {'sample_id', 'base_id', 'family_id', 'template_id', 'document_type', 'schema_id',
                                'seed', 'generator_version', 'row_count', 'label_statuses', 'assets'},
                'missing/unknown D1 sample metadata')
        match = re.fullmatch(f'd12-{kind}-(0[1-9]|10)', sid)
        require(match is not None, 'sample_id/type mismatch')
        index = int(match[1]) - 1
        layout = index % 2
        require(sample['base_id'] == sid and sample['family_id'] == f'{kind}-layout-{layout}' and
                sample['template_id'] == f'{kind}-layout-{layout}-v1', 'lineage mismatch')
        require(sample['row_count'] == [1, 3, 5, 12, 30][index // 2], 'D1 row profile mismatch')
    return kind


def occurrences(regions, pointer):
    """Exact v1 adapter: strip known label prefixes, group ordered wrap fragments.

    Scalar prefixes start occurrences, so repeated amounts are checked separately.
    A table cell has a single occurrence; its adjacent fragments are layout wraps.
    This compares sidecars, not pixels. No OCR or runtime evidence is inferred.
    """
    if pointer.startswith('/items/'):
        groups, previous = [], None
        for region in regions:
            if region['pointer'] == pointer:
                if previous != pointer:
                    groups.append([])
                groups[-1].append(region['text'])
            previous = region['pointer']
        return [' '.join(group) for group in groups]
    prefix = LABELS[pointer[1:]] + ': '
    prefixes = [prefix] + (['Số tiền ghi lại: '] if pointer == '/total_amount' else [])
    groups, previous = [], None
    for region in regions:
        if region['pointer'] == pointer:
            text = region['text']
            start = next((p for p in prefixes if text.startswith(p)), None)
            if start:
                groups.append([text[len(start):]])
            else:
                require(previous == pointer and groups, f'missing scalar label prefix: {pointer}')
                groups[-1].append(text)
        previous = region['pointer']
    return [' '.join(group) for group in groups]


def check_sample(root, manifest, sample, data, schema):
    kind = check_metadata(sample, data, schema)
    base = root
    expected_assets = ASSETS
    require(isinstance(sample['assets'], dict) and set(sample['assets']) == expected_assets, 'missing/unknown asset')
    assets, paths = {}, set()
    for suffix, asset in sample['assets'].items():
        require(isinstance(asset, dict) and set(asset) == {'path', 'sha256'}, f'invalid asset: {suffix}')
        path = asset_path(base, asset['path'])
        require(path not in paths, f'duplicate asset path: {suffix}')
        paths.add(path)
        require(sha(path) == asset['sha256'], f'hash mismatch: {suffix}/{asset["path"]}')
        assets[suffix] = path
    with Image.open(assets['png']) as image:
        image.load()
        require(image.format == 'PNG' and image.mode == 'RGB', 'invalid image format/mode')
        size = image.size
    gold = read_json(assets['gold.json'])
    errors = list(Draft202012Validator({'$ref': f'#/$defs/{kind.title()}', '$defs': schema['$defs']}).iter_errors(gold))
    require(not errors, f'business schema/type mismatch: {kind}')
    require(sample['row_count'] == len(gold['items']), 'row_count/gold mismatch')
    labels, geometry = read_json(assets['labels.json']), read_json(assets['regions.json'])
    require(isinstance(geometry, dict) and geometry.get('page') == 0 and
            size == (geometry.get('width'), geometry.get('height')), 'geometry dimensions/page mismatch')
    require(geometry.get('convention') == 'renderer-local-v1; not approved shared geometry' and
            geometry.get('origin') == 'top-left' and geometry.get('units') == 'pixels', 'unsupported geometry convention')
    regions = geometry['regions']
    require(isinstance(regions, list), 'regions must be an array')
    values = leaves(gold)
    for region in regions:
        require(isinstance(region, dict) and isinstance(region.get('text'), str) and region['text'] and
                region.get('page') == 0 and 'pointer' in region, 'invalid region')
        require(region['pointer'] is None or region['pointer'] in values, 'unknown region pointer')
        box = region.get('bbox_px')
        require(isinstance(box, list) and len(box) == 4 and
                all(type(v) in (int, float) and math.isfinite(v) for v in box), 'invalid bbox')
        x0, y0, x1, y1 = box
        require(0 <= x0 < x1 <= size[0] and 0 <= y0 < y1 <= size[1], 'bbox outside image')
    require(assets['txt'].read_bytes() == ''.join(r['text'] + '\n' for r in regions).encode('utf-8'), 'transcript drift')
    require(isinstance(labels, dict) and set(labels) == set(values), 'label pointer coverage mismatch')
    for pointer, value in values.items():
        label = labels[pointer]
        require(isinstance(label, dict) and set(label) == {'status', 'raw', 'reason'}, f'invalid label: {pointer}')
        status = label['status']
        allowed = ('present', 'absent')
        require(status in allowed and (status == 'present') == (value is not None), f'label status mismatch: {pointer}')
        require(label['raw'] == raw(pointer.rsplit('/', 1)[-1], value), f'label raw mismatch: {pointer}')
        require(label['reason'] is None if status == 'present' else isinstance(label['reason'], str) and bool(label['reason']),
                f'label reason mismatch: {pointer}')
        hits = occurrences(regions, pointer)
        if value is None:
            require(not hits, f'null field has evidence: {pointer}')
        else:
            require(hits and all(hit == label['raw'] for hit in hits), f'exact occurrence mismatch: {pointer}')
            if data['version'] in D1_VERSIONS:
                require(len(hits) == (2 if pointer == '/total_amount' else 1), f'occurrence count mismatch: {pointer}')
    require(sample['label_statuses'] == dict(Counter(v['status'] for v in labels.values())), 'label status counts mismatch')
    return gold


def load_artifacts(root, manifest, *, full_set=False):
    """Smoke consumer. Explicit integrity checks also run under python -O.

    Supports legacy D1 v1 and current D1 v2. Does not
    certify pixel/text alignment, renderer provenance, or consumer approval.
    """
    root, manifest = root.resolve(), manifest.resolve()
    data = read_json(manifest)
    check_manifest(data)
    schema = read_json(root / 'specs/contracts/business.schema.json')
    ids, loaded = set(), []
    for sample in data['samples']:
        sid = sample.get('sample_id', '<missing>') if isinstance(sample, dict) else '<invalid>'
        try:
            require(isinstance(sample, dict), 'sample must be an object')
            require(sid not in ids, 'duplicate sample_id')
            gold = check_sample(root, manifest, sample, data, schema)
            ids.add(sid)
            loaded.append((sample, gold))
        except (ValueError, OSError, KeyError, TypeError) as error:
            raise ValueError(f'{sid}: {error}') from error
    if full_set:
        require(data['version'] in D1_VERSIONS, 'full_set requires D1.2 manifest')
        expected = {sid for sid, *_ in samples()}
        require(ids == expected, f'full D1.2 requires 20 IDs; missing={sorted(expected-ids)}, extra={sorted(ids-expected)}')
        require(len({s['seed'] for s, _ in loaded}) == 1, 'full D1.2 seed mismatch')
        require(Counter((s['document_type'], s['family_id']) for s, _ in loaded) ==
                Counter({(k, f'{k}-layout-{i}'): 5 for k in ('receipt', 'invoice') for i in (0, 1)}),
                'full D1.2 type/layout counts mismatch')
    yield from loaded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path, default=Path('datasets/processed/d12-integration-v2'))
    parser.add_argument('--manifest', type=Path, default=Path('datasets/manifests/d12-integration-v2.json'))
    parser.add_argument('--seed', type=int, default=1202)
    parser.add_argument('--font', type=Path, help='local Vietnamese TTF; alternatively VIETDOC_DATA_FONT')
    parser.add_argument('--tiny', action='store_true')
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--full-set', action='store_true', help='require all 20 D1.2 IDs and type/layout/row profiles')
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = root / args.manifest
    try:
        if not args.verify:
            build(root, root / args.output, manifest, args.seed, args.font, args.tiny)
        loaded = list(load_artifacts(root, manifest, full_set=args.full_set or (not args.verify and not args.tiny)))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, f'Validation failed: {error}\n')
    print(encoded(dict(samples=len(loaded), types=dict(Counter(s['document_type'] for s, _ in loaded)))).decode('utf-8'), end='')


if __name__ == '__main__':
    main()
