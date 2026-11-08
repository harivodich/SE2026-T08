"""D2.1 offline source checks. Approval diagnostics are not authorization."""
from datetime import date, time
from functools import lru_cache
from decimal import Decimal, localcontext
import unicodedata

from jsonschema import Draft202012Validator
from PIL import ImageFont

from .manifest import require
from .generator.templates import MONEY


def leaves(payload):
    result = {'/' + k: v for k, v in payload.items() if k != 'items'}
    for i, row in enumerate(payload['items']):
        result.update({f'/items/{i}/{k}': v for k, v in row.items()})
    return result


@lru_cache(maxsize=4096)
def supported_glyph(font_path, character):
    font = ImageFont.truetype(font_path, 23)
    return bytes(font.getmask(character)) != bytes(font.getmask('\U0010ffff'))


def validate_source(payload, kind, schema, font_path):
    require(kind in ('receipt', 'invoice'), 'unsupported document type')
    validator = Draft202012Validator({'$ref': f'#/$defs/{kind.title()}', '$defs': schema['$defs']})
    errors = sorted(validator.iter_errors(payload), key=lambda e: str(e.path))
    require(not errors, 'schema: ' + '; '.join(
        f'{list(e.path)}: {e.validator} constraint failed' for e in errors))
    for pointer, value in leaves(payload).items():
        if value is None:
            continue
        require(value and value == value.strip(), f'empty/untrimmed value: {pointer}')
        require(unicodedata.normalize('NFC', value) == value, f'Unicode NFC: {pointer}')
        require(not any(unicodedata.category(c).startswith('C') or c.isspace() and c != ' ' for c in value),
                f'Unicode control/whitespace: {pointer}')
        for character in sorted(set(value) - {' '}):
            require(supported_glyph(str(font_path), character), f'font missing glyph {character!r}: {pointer}')
        key = pointer.rsplit('/', 1)[-1]
        if key.endswith('date'):
            date.fromisoformat(value)
        elif key.endswith('time'):
            time.fromisoformat(value)
        elif key in MONEY or key == 'quantity':
            require(Decimal(value).is_finite() and Decimal(value) >= 0, f'invalid decimal: {pointer}')


def approval_diagnostics(payload):
    """Data-quality hints only; runtime guards/review/warning acknowledgements still required."""
    blockers = ['total_amount_missing'] if payload['total_amount'] is None else []
    warnings = [f'missing:{p}' for p, v in leaves(payload).items() if v is None]
    if not payload['items']:
        warnings.append('empty_items_requires_completeness_review')
    with localcontext() as context:
        context.prec = 100  # No binary floats or rounding of schema-sized operands.
        for index, row in enumerate(payload['items']):
            if all(row[k] is not None for k in ('quantity', 'unit_price', 'line_total')):
                if Decimal(row['quantity']) * Decimal(row['unit_price']) != Decimal(row['line_total']):
                    warnings.append(f'arithmetic:row:{index}')
        amounts = [row['line_total'] for row in payload['items']]
        subtotal_key = 'subtotal' if 'subtotal' in payload else 'total_amount'
        if amounts and all(v is not None for v in amounts) and payload[subtotal_key] is not None:
            if sum(map(Decimal, amounts)) != Decimal(payload[subtotal_key]):
                warnings.append('arithmetic:items_sum')
        keys = ('subtotal', 'tax_amount', 'discount_amount', 'total_amount')
        if all(payload.get(k) is not None for k in keys):
            if Decimal(payload['subtotal']) + Decimal(payload['tax_amount']) - Decimal(payload['discount_amount']) != Decimal(payload['total_amount']):
                warnings.append('arithmetic:invoice_total')
    return dict(schema_valid=True, semantic_valid=True, blockers=blockers, warnings=warnings,
                approval_valid=False, review_required=True)
