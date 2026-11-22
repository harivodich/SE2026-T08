"""Actual tiny renderer records, provenance and partial-publication regressions."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from vietdoc.data.adapters import records
from vietdoc.data.adapters.labels import field_labels
from vietdoc.data.manifest import encoded, read_json, sha

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'tests/fixtures/d12/manifest.json'


class TrainingRecordsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def test_renderer_records_replay_gold_labels_and_relative_paths(self):
        output = self.base / 'records.json'
        packet = records.export_records(ROOT, MANIFEST, output)
        self.assertEqual(packet, read_json(output))
        self.assertEqual(packet['artifact_version'], records.VERSION)
        self.assertEqual(packet['manifest']['sha256'], sha(MANIFEST))
        self.assertEqual(packet['schema']['sha256'], sha(ROOT / 'specs/contracts/business.schema.json'))
        self.assertEqual(packet['asset_base'], 'root')
        self.assertEqual(packet['counts']['document_types'], {'receipt': 1, 'invoice': 1})
        self.assertEqual(packet['counts']['samples'], 2)
        expected = {'d12-receipt-03': '178000', 'd12-invoice-04': '233000'}
        for record in packet['records']:
            sample = record['sample']
            self.assertEqual(record['gold'], read_json(ROOT / sample['assets']['gold.json']['path']))
            labels = read_json(ROOT / sample['assets']['labels.json']['path'])
            projected = field_labels(record['gold'], labels)
            fields = {field.pointer: field for field in projected.fields}
            self.assertEqual(fields['/total_amount'].value, expected[sample['sample_id']])
            self.assertEqual(record['labels']['fields'], [dict(pointer=f.pointer, value=f.value, status=f.status)
                                                        for f in projected.fields])
        self.assertNotIn(str(ROOT), output.read_text())
        self.assertEqual(packet, records.training_packet(ROOT, MANIFEST))

    def test_no_overwrite_or_output_when_later_sample_is_invalid(self):
        output = self.base / 'records.json'
        output.write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'output already exists'):
            records.export_records(ROOT, MANIFEST, output)
        self.assertEqual(output.read_bytes(), b'keep')
        bad = read_json(MANIFEST)
        bad['samples'][1]['assets']['labels.json']['sha256'] = '0' * 64
        manifest = self.base / 'bad.json'
        manifest.write_bytes(encoded(bad))
        with self.assertRaisesRegex(ValueError, 'd12-invoice-04: hash mismatch'):
            records.export_records(ROOT, manifest, self.base / 'new' / 'invalid.json')
        self.assertFalse((self.base / 'new').exists())

    def test_manifest_drift_during_validation_is_rejected(self):
        manifest = self.base / 'manifest.json'
        manifest.write_bytes(MANIFEST.read_bytes())
        original = records.load_training_labels

        def changing(*args, **kwargs):
            loaded = list(original(*args, **kwargs))
            manifest.write_bytes(manifest.read_bytes() + b'\n')
            yield from loaded

        with patch.object(records, 'load_training_labels', side_effect=changing):
            with self.assertRaisesRegex(ValueError, 'manifest changed during record export'):
                records.export_records(ROOT, manifest, self.base / 'records.json')
        self.assertFalse((self.base / 'records.json').exists())

    def test_d2_paths_use_manifest_directory(self):
        from vietdoc.data.generator import d22, integration

        font = integration.resolve_font()
        config = dict(read_json(d22.DEFAULT_CONFIG), rows=[3], font_sha256=sha(font))
        plan = [next(record for record in d22.plan(config, 2202)
                     if None in integration.leaves(d22.payload_for(record, read_json(d22.CONFIG))).values())]
        entries = []
        with patch.object(d22, 'plan', return_value=plan):
            for sample, files in d22.generated(ROOT, config, 2202, font):
                entries.append(sample)
                for suffix, content in files.items():
                    (self.base / sample['assets'][suffix]['path']).write_bytes(content)
        manifest = self.base / 'manifest.json'
        manifest.write_bytes(encoded(dict(d22.provenance(ROOT, config, 2202, font), samples=entries)))
        actual = records.training_packet(ROOT, manifest)
        self.assertEqual(actual['asset_base'], 'manifest_directory')
        self.assertEqual(set(actual['counts']['label_statuses']), {'present', 'absent', 'obscured'})
        self.assertTrue(all(field['value'] is None
                            for record in actual['records'] for field in record['labels']['fields']
                            if field['status'] == 'obscured'))

    def test_normal_and_optimized_cli_and_full_set_gate(self):
        for optimized in (False, True):
            command = [sys.executable, *(['-O'] if optimized else []), '-m',
                       'vietdoc.data.adapters.records', '--root', str(ROOT), '--manifest', str(MANIFEST),
                       '--output', str(self.base / f'{optimized}.json')]
            run = subprocess.run(command, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr.decode())
            run = subprocess.run([*command, '--full-set'], capture_output=True)
            self.assertNotEqual(run.returncode, 0)  # existing output is preserved
        with self.assertRaisesRegex(ValueError, 'full D1.2 requires 20 IDs'):
            records.export_records(ROOT, MANIFEST, self.base / 'full.json', full_set=True)
        self.assertFalse((self.base / 'full.json').exists())


if __name__ == '__main__':
    unittest.main()
