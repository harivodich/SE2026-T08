"""Offline scoring proposal; never imports or changes production normalization."""
from datetime import date
from decimal import Decimal
import re
import unicodedata

VERSION = 'd31-canonical-nfc-v1-proposed'
FIELDS = {
    'receipt': ('merchant_name', 'merchant_address', 'transaction_date',
                'transaction_time', 'total_amount'),
    'invoice': ('invoice_number', 'issue_date', 'seller_name', 'buyer_name',
                'subtotal', 'tax_amount', 'discount_amount', 'total_amount'),
}
MONEY = {'subtotal', 'tax_amount', 'discount_amount', 'total_amount'}
POLICY = {
    'version': VERSION,
    'status': 'proposed; AI-1/AI-2 review required',
    'unicode': 'NFC; preserve Vietnamese diacritics; Python Unicode ' + unicodedata.unidata_version,
    'text': 'collapse Unicode whitespace, trim; case-sensitive; empty is missing',
    'money': 'canonical nonnegative decimal strings only; Decimal equality; no locale/currency parsing',
    'date': 'valid YYYY-MM-DD only; no guessing raw dates',
    'time': 'valid HH:MM or HH:MM:SS, compared literally',
    'ocr': 'NFC + whitespace collapse; case-sensitive; CER Unicode codepoints including spaces; WER split on spaces',
    'obscured': 'excluded, like unlabeled; no inferred gold',
    'zero_denominator': 'null, including empty-reference CER/WER; edit numerator retained',
    'failures': 'missing/failed/duplicate/invalid records score as empty predictions; never select duplicate winner',
    'ocr_scope': 'full_page only; d1.2.v1 renderer txt is known full_page; other manifests must declare transcript_scope',
}


def text(value):
    return ' '.join(unicodedata.normalize('NFC', value).split())


def normalize(field, value):
    """Return canonical value or raise ValueError; invalid is never equal to invalid."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('scalar must be string or null')
    value = text(value)
    if not value:
        return None
    if field in MONEY:
        if not re.fullmatch(r'(0|[1-9][0-9]*)(\.[0-9]+)?', value) or len(value) > 32:
            raise ValueError('not canonical money')
        return Decimal(value)
    if field.endswith('date'):
        if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
            raise ValueError('not canonical date')
        date.fromisoformat(value)
    if field.endswith('time'):
        if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9])?', value):
            raise ValueError('not canonical time')
    return value
