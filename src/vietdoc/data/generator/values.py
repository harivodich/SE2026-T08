"""D1.1 fictional content only; no rendering, inference or business state."""
import argparse
import copy
from datetime import date, time, timedelta
from decimal import Decimal
import json
from pathlib import Path
import random

CONFIG = Path(__file__).with_name('fake-values.json')


def generate(seed=1101):
    """Return four (sample ID, payload, annotation) tuples, deterministic per seed."""
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    rng = random.Random(seed)
    samples = []
    for kind in ('receipt', 'invoice'):
        for variant in range(2):
            items = [dict(row) for row in rng.sample(config['products'], 3)]
            subtotal = sum((Decimal(row['line_total']) for row in items), Decimal('0'))
            adjustment = config['adjustments'][variant]
            total = subtotal + Decimal(adjustment['tax']) - Decimal(adjustment['discount'])
            day = date(2026, 1, 1) + timedelta(days=rng.randrange(365))
            if kind == 'receipt':
                payload = dict(merchant_name=rng.choice(config['merchants']),
                               merchant_address=rng.choice(config['addresses']),
                               transaction_date=day.isoformat(),
                               transaction_time=time(rng.randrange(24), rng.randrange(60)).isoformat(timespec='minutes'),
                               total_amount=str(subtotal), items=items)
            else:
                payload = dict(invoice_number=f'GIẢ-LẬP-{seed}-{variant + 1:02}',
                               issue_date=day.isoformat(), seller_name=rng.choice(config['sellers']),
                               buyer_name=rng.choice(config['buyers']), subtotal=str(subtotal),
                               tax_amount=adjustment['tax'], discount_amount=adjustment['discount'],
                               total_amount=str(total), items=items)
            labels = {}
            def annotate(path, value):
                raw = value
                if path.endswith(('date',)):
                    raw = date.fromisoformat(value).strftime('%d/%m/%Y')
                elif path.endswith(('unit_price', 'line_total', 'total_amount', 'subtotal', 'tax_amount', 'discount_amount')):
                    raw = f'{int(value):,}'.replace(',', '.') + ' đ'
                elif path.endswith('quantity'):
                    raw = value.replace('.', ',')
                labels[path] = dict(status='present', raw=raw, reason=None)
            for key, value in payload.items():
                if key != 'items':
                    annotate('/' + key, value)
            for index, row in enumerate(items):
                for key, value in row.items():
                    annotate(f'/items/{index}/{key}', value)
            if variant:
                missing = ('merchant_address', 'transaction_time') if kind == 'receipt' else ('buyer_name', 'tax_amount', 'discount_amount')
                for key in missing:
                    payload[key] = None
                    labels['/' + key] = dict(status='absent', raw=None, reason='Không in trường này trong kịch bản hư cấu.')
                # Synthetic ambiguity and partial annotation cases; never invent a value.
                for row_index, key, status, raw, reason in (
                    (0, 'unit', 'absent', None, 'Không in đơn vị.'),
                    (1, 'quantity', 'obscured', '?,?', 'Kịch bản che quantity, không đọc chắc chắn.'),
                    (2, 'unit_price', 'unlabeled', None, 'Cố ý chưa annotate đơn giá.')):
                    items[row_index][key] = None
                    labels[f'/items/{row_index}/{key}'] = dict(status=status, raw=raw, reason=reason)
            sample_id = f'd11-{kind}-{variant + 1:02}'
            samples.append((sample_id, payload, dict(sample_id=sample_id, document_type=kind,
                schema_id='urn:vietdoc:business:v1', generator_version=config['version'], seed=seed,
                notice=config['notice'], stage='content-only; not rendered or image-audited', labels=labels)))
    return samples


def integration_samples(seed=1202, config=None):
    config = json.loads(CONFIG.read_text(encoding='utf-8')) if config is None else config
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


def document_cases(seed, config, vocabulary):
    """D2.1 boundary profiles use the existing D1.2 value source, never truncate rows."""
    bases = [s for s in integration_samples(seed, vocabulary) if s[0].endswith(('03', '04'))]
    for _, kind, layout, base in bases:
        for count in config['rows']:
            payload = copy.deepcopy(base)
            payload['items'] = [copy.deepcopy(base['items'][i % len(base['items'])]) for i in range(count)]
            subtotal = sum((Decimal(r['line_total']) for r in payload['items']), Decimal(0))
            payload['total_amount'] = str(subtotal)
            if kind == 'invoice':
                payload['subtotal'] = str(subtotal)
                payload['tax_amount'] = payload['discount_amount'] = '0'
            yield f'd21-{kind}-l{layout}-r{count}', kind, layout, payload
        if layout == 0:
            payload = copy.deepcopy(base)
            payload['total_amount'] = None
            yield f'd21-{kind}-missing-total', kind, layout, payload
            payload = copy.deepcopy(base)
            payload['items'] = [copy.deepcopy(base['items'][0]) for _ in range(30)]
            for row in payload['items']:
                row['description'] = ('Hàng hóa hư cấu mô tả dài ' * 18).strip()
            yield f'd21-{kind}-overflow', kind, layout, payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=1101)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for sample_id, payload, annotation in generate(args.seed):
        for suffix, value in (('gold', payload), ('labels', annotation)):
            path = args.output / f'{sample_id}.{suffix}.json'
            # Exclusive creation protects existing user files; regenerate into a fresh directory.
            with path.open('x', encoding='utf-8') as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.write('\n')


if __name__ == '__main__':
    main()
