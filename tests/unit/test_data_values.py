"""Focused D1.1 checks: real schema plus semantic/annotation invariants."""
from datetime import date, time
from decimal import Decimal
import json
from pathlib import Path
import re
import unicodedata
import unittest

from jsonschema import Draft202012Validator
from vietdoc.data.generator.values import generate

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / 'specs/contracts/business.schema.json').read_text(encoding='utf-8'))
FIXTURES = ROOT / 'tests/fixtures'
DECIMAL = re.compile(r'^(0|[1-9][0-9]*)(\.[0-9]+)?$')


class DataValuesTest(unittest.TestCase):
    def test_committed_gold_matches_generator(self):
        for sample_id, payload, labels in generate():
            for suffix, expected in (('gold', payload), ('labels', labels)):
                actual = json.loads((FIXTURES / f'{sample_id}.{suffix}.json').read_text(encoding='utf-8'))
                self.assertEqual(actual, expected)

    def test_schema_semantics_and_annotation_coverage(self):
        Draft202012Validator.check_schema(SCHEMA)
        validator = Draft202012Validator(SCHEMA)
        statuses, quantities, units, totals = set(), set(), set(), set()
        for sample_id, payload, annotation in generate():
            with self.subTest(sample=sample_id):
                validator.validate(payload)
                kind = annotation['document_type'].title()
                self.assertEqual(set(payload), set(SCHEMA['$defs'][kind]['required']))
                leaves = {'/' + k: v for k, v in payload.items() if k != 'items'}
                for index, row in enumerate(payload['items']):
                    self.assertEqual(set(row), set(SCHEMA['$defs']['LineItem']['required']))
                    leaves.update({f'/items/{index}/{k}': v for k, v in row.items()})
                    quantities.add(row['quantity'])
                    units.add(row['unit'])
                self.assertEqual(set(leaves), set(annotation['labels']))
                for pointer, value in leaves.items():
                    label = annotation['labels'][pointer]
                    statuses.add(label['status'])
                    self.assertEqual(value is None, label['status'] != 'present')
                    if value is None:
                        self.assertTrue(label['reason'])
                        if label['status'] in ('absent', 'unlabeled'):
                            self.assertIsNone(label['raw'])
                        continue
                    self.assertIsInstance(value, str)
                    self.assertEqual(value, unicodedata.normalize('NFC', value))
                    key = pointer.rsplit('/', 1)[-1]
                    if key.endswith('date'):
                        date.fromisoformat(value)
                    elif key.endswith('time'):
                        time.fromisoformat(value)
                    elif key in {'quantity', 'unit_price', 'line_total', 'subtotal', 'tax_amount', 'discount_amount', 'total_amount'}:
                        self.assertRegex(value, DECIMAL)
                        self.assertGreaterEqual(Decimal(value), 0)
                self.assertIn('Hư Cấu', payload.get('merchant_name', payload.get('seller_name')))
                self.assertGreaterEqual(len(payload['items']), 2)
                totals.add(payload['total_amount'])
        self.assertEqual(statuses, {'present', 'absent', 'obscured', 'unlabeled'})
        self.assertIn('1.5', quantities)
        self.assertIn('2', quantities)
        self.assertGreater(len(units - {None}), 1)
        self.assertGreater(len(totals), 1)

    def test_many_seeds_valid_and_different(self):
        validator = Draft202012Validator(SCHEMA)
        self.assertEqual(generate(1101), generate(1101))
        self.assertNotEqual(generate(1101), generate(1102))
        for seed in range(100):
            for _, payload, _ in generate(seed):
                validator.validate(payload)
                date.fromisoformat(payload.get('issue_date', payload.get('transaction_date')))
                if payload.get('transaction_time'):
                    time.fromisoformat(payload['transaction_time'])

    def test_fully_labeled_arithmetic(self):
        for _, payload, labels in generate():
            if labels['sample_id'].endswith('02'):
                continue
            subtotal = sum((Decimal(row['line_total']) for row in payload['items']), Decimal(0))
            for row in payload['items']:
                self.assertEqual(Decimal(row['quantity']) * Decimal(row['unit_price']), Decimal(row['line_total']))
            self.assertEqual(Decimal(payload['total_amount']), subtotal)

    def test_missing_fields_do_not_infer_zero_or_one(self):
        samples = {sample_id: (payload, labels) for sample_id, payload, labels in generate()}
        invoice, labels = samples['d11-invoice-02']
        self.assertIsNone(invoice['buyer_name'])
        self.assertIsNone(invoice['tax_amount'])
        self.assertIsNone(invoice['discount_amount'])
        self.assertEqual(Decimal(invoice['total_amount']) - Decimal(invoice['subtotal']), Decimal('5000'))
        self.assertIsNone(invoice['items'][1]['quantity'])
        self.assertEqual(labels['labels']['/items/1/quantity']['status'], 'obscured')
        receipt, _ = samples['d11-receipt-02']
        self.assertIsNone(receipt['merchant_address'])
        self.assertIsNone(receipt['transaction_time'])

    def test_schema_rejects_missing_unknown_keys_and_numeric_money(self):
        validator = Draft202012Validator(SCHEMA)
        for _, payload, _ in generate():
            for mutation in ('missing', 'unknown', 'float'):
                broken = dict(payload)
                if mutation == 'missing':
                    del broken['items']
                elif mutation == 'unknown':
                    broken['label_status'] = 'present'
                else:
                    broken['total_amount'] = 123.5
                self.assertFalse(validator.is_valid(broken))


if __name__ == '__main__':
    unittest.main()
