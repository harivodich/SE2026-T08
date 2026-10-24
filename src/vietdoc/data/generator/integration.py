"""Bounded D1.2 integration renderer. No OCR, model, split or business persistence."""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import random

from PIL import Image, ImageDraw, ImageFont
from jsonschema import Draft202012Validator

from .values import CONFIG

VERSION = 'd1.2.v1'
FONT = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
MONEY = {'unit_price', 'line_total', 'subtotal', 'tax_amount', 'discount_amount', 'total_amount'}
LABELS = dict(merchant_name='Cửa hàng', merchant_address='Địa chỉ', transaction_date='Ngày bán',
              transaction_time='Giờ', invoice_number='Số hóa đơn', issue_date='Ngày lập',
              seller_name='Đơn vị bán', buyer_name='Đơn vị mua', subtotal='Cộng tiền hàng',
              tax_amount='Tiền thuế GTGT', discount_amount='Chiết khấu', total_amount='Tổng thanh toán')


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
    config = json.loads(CONFIG.read_text())
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
    validator = Draft202012Validator(json.loads((root / 'specs/contracts/business.schema.json').read_text()))
    ids = set()
    for sample in data['samples']:
        sid = sample['sample_id']
        assert sid not in ids, sid
        ids.add(sid)
        assets = {}
        for suffix, asset in sample['assets'].items():
            path = (root / asset['path']).resolve()
            assert path.is_relative_to(root.resolve())
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
            assert labels[pointer]['status'] == ('absent' if value is None else 'present')
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
