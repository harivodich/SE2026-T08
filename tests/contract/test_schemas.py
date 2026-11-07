"""Structural Draft 2020-12 evidence; not business validation or Java parity."""

import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource, Unresolvable

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILES = (
    'business', 'extraction-result', 'export', 'compute-request',
    'compute-response', 'compute-error', 'job-message',
)


def reject_remote(uri):
    raise NoSuchResource(ref=uri)


class SharedSchemasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = {
            name: json.loads((ROOT / f'specs/contracts/{name}.schema.json').read_text(encoding='utf-8'))
            for name in SCHEMA_FILES
        }
        store = {schema['$id']: schema for schema in cls.schemas.values()}
        if len(store) != len(cls.schemas):
            raise ValueError('Duplicate schema IDs')
        registry = Registry(retrieve=reject_remote).with_resources(
            (uri, Resource.from_contents(schema)) for uri, schema in store.items())
        cls.validators = {}
        for name, schema in cls.schemas.items():
            Draft202012Validator.check_schema(schema)
            cls.validators[name] = Draft202012Validator(
                schema, format_checker=FormatChecker(), registry=registry)

    def example(self, name):
        return json.loads((ROOT / f'docs/design/v1/examples/{name}.json').read_text(encoding='utf-8'))

    def fixture(self, name):
        return json.loads((ROOT / f'tests/contract/{name}.json').read_text(encoding='utf-8'))

    def invalid(self, schema, value):
        with self.assertRaises(ValidationError):
            self.validators[schema].validate(value)

    def test_all_schema_files_are_checked(self):
        actual = {path.name.removesuffix('.schema.json')
                  for path in (ROOT / 'specs/contracts').glob('*.schema.json')}
        self.assertEqual(set(SCHEMA_FILES), actual, 'Register new contracts explicitly')

    def test_examples_and_shared_compute_fixtures(self):
        for name in ('receipt', 'invoice'):
            self.validators['business'].validate(self.example(name))
        for name in ('extraction-result', 'export'):
            self.validators[name].validate(self.example(name))
        for name in ('compute-request', 'compute-response', 'compute-error'):
            self.validators[name].validate(self.fixture(name))
        self.validators['job-message'].validate(dict(
            message_version=1, job_id='11111111-1111-4111-8111-111111111111'))

    def test_business_keys_decimal_strings_and_row_boundary(self):
        for kind in ('receipt', 'invoice'):
            original = self.example(kind)
            for mutation in ('missing', 'unknown', 'float', 'negative', 'long', 'rows', 'row-key'):
                with self.subTest(kind=kind, mutation=mutation):
                    value = copy.deepcopy(original)
                    if mutation == 'missing':
                        del value['total_amount']
                    elif mutation == 'unknown':
                        value['annotation_status'] = 'present'
                    elif mutation == 'float':
                        value['total_amount'] = 12.5
                    elif mutation == 'negative':
                        value['total_amount'] = '-1'
                    elif mutation == 'long':
                        value['total_amount'] = '1' * 33
                    elif mutation == 'rows':
                        value['items'] = [value['items'][0]] * 31
                    else:
                        value['items'][0]['extra'] = True
                    self.invalid('business', value)
            original['items'] = [original['items'][0]] * 30
            original['total_amount'] = None
            original['items'][0]['quantity'] = '0.25'
            self.validators['business'].validate(original)

    def test_request_versions_uuid_budget_and_language(self):
        original = self.fixture('compute-request')
        for key, value in (('contract_version', 2), ('job_id', 'bad'), ('attempt_id', 'bad'),
                           ('remaining_budget_ms', 0), ('remaining_budget_ms', 180001),
                           ('language', 'en'), ('schema_version', 'invoice.v1'),
                           ('input_sha256', 'ABC'), ('pipeline_manifest_id', '../escape')):
            with self.subTest(key=key, value=value):
                self.invalid('compute-request', dict(original, **{key: value}))
        invoice = dict(original, document_type='invoice', schema_version='invoice.v1')
        self.validators['compute-request'].validate(invoice)
        self.invalid('compute-request', dict(invoice, schema_version='receipt.v1'))

    def test_result_and_export_type_must_match_payload(self):
        for name in ('extraction-result', 'export'):
            receipt = self.example(name)
            self.invalid(name, dict(receipt, document_type='invoice', schema_version='invoice.v1'))
            invoice = dict(receipt, document_type='invoice', schema_version='invoice.v1',
                           payload=self.example('invoice'))
            self.validators[name].validate(invoice)
            self.invalid(name, dict(invoice, schema_version='receipt.v1'))

    def test_geometry_and_confidence_bounds(self):
        original = self.example('extraction-result')
        for mutation in ('page', 'quad', 'confidence', 'ocr-score'):
            value = copy.deepcopy(original)
            metadata = value['field_metadata'][0]
            if mutation == 'page':
                metadata['source_regions'][0]['page'] = 1
            elif mutation == 'quad':
                metadata['source_regions'][0]['quad'][0][0] = 1.01
            elif mutation == 'confidence':
                metadata['confidence'] = -0.01
            else:
                metadata['ocr_score'] = 1.01
            self.invalid('extraction-result', value)

    def test_response_and_error_bounds(self):
        original = self.fixture('compute-response')
        for mutation in ('width', 'page', 'sha', 'path', 'size', 'artifacts'):
            value = copy.deepcopy(original)
            if mutation == 'width':
                value['canonical_page']['width'] = 0
            elif mutation == 'page':
                value['canonical_page']['page'] = 1
            elif mutation == 'sha':
                value['canonical_page']['sha256'] = 'invalid'
            elif mutation == 'path':
                value['canonical_page']['asset_key'] = '../outside.png'
            elif mutation == 'size':
                value['artifacts'][0]['size_bytes'] = 0
            else:
                value['artifacts'] = []
            self.invalid('compute-response', value)
        error = self.fixture('compute-error')
        self.validators['compute-error'].validate(dict(error, attempt_id=None))
        self.invalid('compute-error', dict(error, retryable='true'))
        self.invalid('compute-error', dict(error, code='UNKNOWN'))

    def test_refs_never_fetch_network_or_files(self):
        for uri in ('https://example.invalid/schema', 'http://example.invalid/schema',
                    'file:///private/schema.json', 'urn:vietdoc:unregistered'):
            schema = {'$schema': 'https://json-schema.org/draft/2020-12/schema', '$ref': uri}
            registry = Registry(retrieve=reject_remote)
            with patch('urllib.request.urlopen', side_effect=AssertionError('Network attempted')):
                with self.assertRaises(Unresolvable):
                    Draft202012Validator(schema, registry=registry).validate({})

    def test_calendar_and_cross_record_semantics_are_not_schema_evidence(self):
        receipt = self.example('receipt')
        receipt['transaction_date'] = '2026-02-31'
        self.validators['business'].validate(receipt)
        response = self.fixture('compute-response')
        response['attempt_id'] = '44444444-4444-4444-8444-444444444444'
        self.validators['compute-response'].validate(response)
        # Domain validators must reject bad dates/correlation; schema acceptance is not parity/E2E.


if __name__ == '__main__':
    unittest.main()
