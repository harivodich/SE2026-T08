"""Label projection oracles plus real renderer path/hash/semantic boundaries."""
import copy
from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vietdoc.data.adapters.labels import VERSION, field_labels, load_training_labels
from vietdoc.data.generator.artifact_io import encoded, read_json, sha
from vietdoc.data.generator.integration import load_artifacts

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'tests/fixtures/d12/manifest.json'


class LabelProjectionTest(unittest.TestCase):
    def setUp(self):
        self.gold = read_json(ROOT / 'tests/fixtures/d11-invoice-02.gold.json')
        self.labels = read_json(ROOT / 'tests/fixtures/d11-invoice-02.labels.json')['labels']

    def test_same_null_keeps_three_distinct_statuses(self):
        result = field_labels(self.gold, self.labels)
        fields = {f.pointer: f for f in result.fields}
        self.assertEqual(result.version, VERSION)
        for pointer, status in [('/buyer_name', 'absent'), ('/items/1/quantity', 'obscured'),
                                ('/items/2/unit_price', 'unlabeled')]:
            self.assertIsNone(fields[pointer].value)
            self.assertEqual(fields[pointer].status, status)
        self.assertEqual(asdict(fields['/total_amount']),
                         dict(pointer='/total_amount', value='180500', status='present'))
        self.assertEqual(fields['/items/2/quantity'].value, '1.5')
        self.assertEqual(len(result.fields), len(self.labels))

    def test_projection_is_deterministic_and_detached(self):
        result = field_labels(self.gold, self.labels)
        self.assertEqual(result, field_labels(self.gold, dict(reversed(list(self.labels.items())))))
        self.gold['total_amount'] = '0'
        self.labels['/total_amount']['status'] = 'absent'
        self.assertIn(dict(pointer='/total_amount', value='180500', status='present'),
                      asdict(result)['fields'])

    def test_invalid_pointers_rejected(self):
        for pointer in ('buyer_name', '/items/01/quantity', '/items/-1/quantity', '/items/99/quantity',
                        '/items/1', '/items/1/unknown', '/buyer~1name'):
            with self.subTest(pointer=pointer):
                labels = copy.deepcopy(self.labels)
                labels[pointer] = labels.pop('/buyer_name')
                with self.assertRaisesRegex(ValueError, 'label pointer coverage mismatch'):
                    field_labels(self.gold, labels)
        del self.labels['/buyer_name']
        with self.assertRaisesRegex(ValueError, 'label pointer coverage mismatch'):
            field_labels(self.gold, self.labels)

    def test_invalid_status_and_null_value_consistency(self):
        for pointer, status in [('/buyer_name', 'unknown'), ('/buyer_name', 'present'),
                                ('/total_amount', 'absent'), ('/total_amount', 'obscured'),
                                ('/total_amount', 'unlabeled'), ('/buyer_name', None)]:
            with self.subTest(pointer=pointer, status=status):
                labels = copy.deepcopy(self.labels)
                labels[pointer]['status'] = status
                with self.assertRaisesRegex(ValueError, 'label status mismatch'):
                    field_labels(self.gold, labels)

    def test_invalid_annotation_shape_raw_reason_and_numeric_values(self):
        for key, value, reason in [('status', None, 'status mismatch'), ('reason', None, 'reason mismatch'),
                                   ('raw', 'invented', 'raw mismatch'), ('extra', True, 'invalid label')]:
            with self.subTest(key=key):
                labels = copy.deepcopy(self.labels)
                labels['/buyer_name'][key] = value
                with self.assertRaisesRegex(ValueError, reason):
                    field_labels(self.gold, labels)
        self.gold['total_amount'] = 180500.0
        with self.assertRaisesRegex(ValueError, 'business leaves must be strings or null'):
            field_labels(self.gold, self.labels)


class LabelFileBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.data = read_json(FIXTURE)
        self.manifest = self.base / 'manifest.json'
        # Copy the real schema and tiny fictional assets into a relocated root.
        self.root = self.base / 'root'
        (self.root / 'specs/contracts').mkdir(parents=True)
        (self.root / 'specs/contracts/business.schema.json').write_bytes(
            (ROOT / 'specs/contracts/business.schema.json').read_bytes())
        for sample in self.data['samples']:
            for suffix, asset in sample['assets'].items():
                target = self.root / (sample['sample_id'] + '.' + suffix)
                target.write_bytes((ROOT / asset['path']).read_bytes())
                asset['path'] = target.name

    def load(self):
        self.manifest.write_bytes(encoded(self.data))
        return list(load_training_labels(self.root, self.manifest))

    def test_existing_api_parity_and_no_label_reread(self):
        actual = self.load()
        legacy = list(load_artifacts(self.root, self.manifest))
        self.assertEqual([(s, g) for s, g, _ in actual], legacy)
        self.assertEqual(len(actual), 2)
        for sample, gold, result in actual:
            labels = read_json(self.root / sample['assets']['labels.json']['path'])
            self.assertEqual(result, field_labels(gold, labels))
        # If the adapter reopens labels after validation, this probe fails.
        from vietdoc.data.generator import integration
        with patch.object(integration, 'read_json', wraps=integration.read_json) as reader:
            self.load()
        reads = [Path(call.args[0]).name for call in reader.call_args_list]
        for sample, _, _ in actual:
            self.assertEqual(reads.count(sample['sample_id'] + '.labels.json'), 1)

    def test_bad_labels_hash_rejected(self):
        asset = self.data['samples'][0]['assets']['labels.json']
        (self.root / asset['path']).write_bytes(b'{}\n')
        with self.assertRaisesRegex(ValueError, 'd12-receipt-03: hash mismatch: labels.json'):
            self.load()

    def test_bad_label_pointer_or_status_with_updated_hash_rejected(self):
        asset = self.data['samples'][0]['assets']['labels.json']
        path = self.root / asset['path']
        original = read_json(path)
        for mutation, reason in [('pointer', 'pointer coverage mismatch'), ('status', 'status mismatch')]:
            with self.subTest(mutation=mutation):
                labels = copy.deepcopy(original)
                if mutation == 'pointer':
                    labels['/unknown'] = labels.pop('/total_amount')
                else:
                    labels['/total_amount']['status'] = 'unknown'
                path.write_bytes(encoded(labels))
                asset['sha256'] = sha(path)
                with self.assertRaisesRegex(ValueError, reason):
                    self.load()

    def test_path_escape_and_missing_asset_rejected(self):
        asset = self.data['samples'][0]['assets']['labels.json']
        for path, reason in [('../labels.json', 'invalid relative path'),
                             ('missing.json', 'missing asset')]:
            with self.subTest(path=path):
                asset['path'] = path
                with self.assertRaisesRegex(ValueError, reason):
                    self.load()

    def test_no_partial_results_when_later_sample_fails(self):
        self.data['samples'][1]['assets']['labels.json']['sha256'] = '0' * 64
        self.manifest.write_bytes(encoded(self.data))
        iterator = load_training_labels(self.root, self.manifest)
        with self.assertRaisesRegex(ValueError, 'd12-invoice-04: hash mismatch'):
            next(iterator)

    def test_full_set_gate_preserved(self):
        self.load()
        with self.assertRaisesRegex(ValueError, 'full D1.2 requires 20 IDs'):
            list(load_training_labels(self.root, self.manifest, full_set=True))

    def test_d22_relative_paths_and_obscured_statuses(self):
        from vietdoc.data.generator import d22, integration

        font = integration.resolve_font()
        config = dict(read_json(d22.DEFAULT_CONFIG), rows=[3], font_sha256=sha(font))
        records = [next(record for record in d22.plan(config, 2202)
                        if None in integration.leaves(d22.payload_for(record, read_json(d22.CONFIG))).values())]
        entries = []
        with patch.object(d22, 'plan', return_value=records):
            for sample, files in d22.generated(ROOT, config, 2202, font):
                entries.append(sample)
                for suffix, content in files.items():
                    (self.base / sample['assets'][suffix]['path']).write_bytes(content)
        self.manifest.write_bytes(encoded(dict(d22.provenance(ROOT, config, 2202, font), samples=entries)))
        actual = list(load_training_labels(ROOT, self.manifest))
        self.assertEqual([(s, g) for s, g, _ in actual], list(load_artifacts(ROOT, self.manifest)))
        self.assertEqual({f.status for _, _, labels in actual for f in labels.fields},
                         {'present', 'absent', 'obscured'})
        unreadable = next(labels for sample, _, labels in actual if sample['quality'] == 'unreadable')
        self.assertTrue(all(f.value is None and f.status != 'present' for f in unreadable.fields))


if __name__ == '__main__':
    unittest.main()
