"""D1.1 fictional content only; no rendering, inference or business state."""
import argparse
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
            with path.open('x', encoding='utf-8', newline='\n') as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.write('\n')


if __name__ == '__main__':
    main()
