"""Gold file-boundary regressions; predictions are deliberately synthetic controls."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from vietdoc.data.manifest import encoded, read_json, sha
from vietdoc.evaluation import scalar_ocr, extended
from test_evaluation import artifact

ROOT = Path(__file__).resolve().parents[2]


class GoldBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'specs/contracts').mkdir(parents=True)
        shutil.copyfile(ROOT / 'specs/contracts/business.schema.json',
                        self.root / 'specs/contracts/business.schema.json')
        self.data = read_json(ROOT / 'tests/fixtures/d12/manifest.json')
        for entry in self.data['samples']:
            for suffix, asset in entry['assets'].items():
                name = entry['sample_id'] + '.' + suffix
                shutil.copyfile(ROOT / asset['path'], self.root / name)
                asset['path'] = name
        self.manifest = self.root / 'manifest.json'
        self.predictions = self.root / 'predictions.json'
        self.save()

    def save(self):
        self.manifest.write_bytes(encoded(self.data))
        self.predictions.write_bytes(encoded(dict(artifact(), dataset_manifest_sha256=sha(self.manifest))))

    def evaluate_both(self, **options):
        return (scalar_ocr.evaluate_files(self.root, self.manifest, self.predictions, **options),
                extended.evaluate_files(self.root, self.manifest, {'control': self.predictions}, **options)
                ['reports']['control'])

    def test_valid_controls_and_versioned_validation_provenance(self):
        for report in self.evaluate_both():
            validation = report['inputs']['gold_validation']
            self.assertEqual(validation['status'], 'validated')
            self.assertEqual(validation['manifest_sha256'], sha(self.manifest))
            self.assertEqual(len(validation['assets']), 10)
            self.assertEqual(validation['schema_sha256'], sha(self.root / 'specs/contracts/business.schema.json'))
            self.assertIn('generator/integration.py', validation['validator_sources'])
            self.assertEqual(report['accounting']['outcomes'], {'missing': 2})

    def test_coordinated_wrong_gold_is_rejected_by_both_apis_and_cli(self):
        entry = self.data['samples'][0]
        for suffix in ('gold.json', 'labels.json'):
            path = self.root / entry['assets'][suffix]['path']
            value = read_json(path)
            if suffix == 'gold.json':
                self.assertEqual(value['total_amount'], '178000')
                value['total_amount'] = '0'
            else:
                value['/total_amount']['raw'] = '0 đ'
            path.write_bytes(encoded(value))
            entry['assets'][suffix]['sha256'] = sha(path)
        self.save()
        for evaluator, args in ((scalar_ocr.evaluate_files, self.predictions),
                                (extended.evaluate_files, {'control': self.predictions})):
            with self.subTest(evaluator=evaluator.__module__), self.assertRaisesRegex(
                    ValueError, 'd12-receipt-03: exact occurrence mismatch: /total_amount'):
                evaluator(self.root, self.manifest, args)
        for optimized in (False, True):
            for flag, value in (('--predictions', str(self.predictions)),
                                ('--candidate', 'control=' + str(self.predictions))):
                with self.subTest(optimized=optimized, flag=flag):
                    out = self.root / ('output-' + str(optimized) + flag)
                    run = subprocess.run([sys.executable, *(['-O'] if optimized else []), '-m',
                        'vietdoc.evaluation', '--root', str(self.root), '--manifest', str(self.manifest),
                        flag, value, '--output', str(out)], capture_output=True,
                        env=dict(os.environ, PYTHONPATH=str(ROOT / 'src')))
                    self.assertNotEqual(run.returncode, 0)
                    self.assertIn(b'exact occurrence mismatch: /total_amount', run.stderr)
                    self.assertFalse(out.exists())

    def test_metadata_schema_type_and_image_hash_fail_before_scoring(self):
        original = deepcopy(self.data)
        for key, value, reason in (('schema_id', 'bad', 'unsupported business schema'),
                                   ('row_count', 20, 'D1 row profile mismatch'),
                                   ('document_type', 'invoice', 'unsupported label pointer/format')):
            self.data = deepcopy(original)
            self.data['samples'][0][key] = value
            self.save()
            for evaluator, args in ((scalar_ocr.evaluate_files, self.predictions),
                                    (extended.evaluate_files, {'control': self.predictions})):
                with self.subTest(key=key, evaluator=evaluator.__module__), self.assertRaisesRegex(ValueError, reason):
                    evaluator(self.root, self.manifest, args)
        self.data = original
        self.data['samples'][0]['assets']['png']['sha256'] = '0' * 64
        self.save()
        with self.assertRaisesRegex(ValueError, 'hash mismatch: png'):
            scalar_ocr.load_gold(self.root, self.manifest)

    def test_explicit_annotated_mode_cannot_bypass_known_renderer(self):
        with self.assertRaisesRegex(ValueError, 'gold mode mismatch'):
            self.evaluate_both(gold_mode='annotated')
        self.data['version'] = 'manual-annotations.v1'
        self.save()
        with self.assertRaisesRegex(ValueError, 'gold mode mismatch'):
            self.evaluate_both()
        for report in self.evaluate_both(gold_mode='annotated'):
            self.assertEqual(report['inputs']['gold_validation']['status'], 'unvalidated')
        code = ('import sys; sys.path.insert(0, sys.argv[1]); '
                'from vietdoc.evaluation.scalar_ocr import evaluate_files; from pathlib import Path; '
                'r=Path(sys.argv[2]); evaluate_files(r,r/"manifest.json",r/"predictions.json",gold_mode="annotated"); '
                'assert "PIL" not in sys.modules and "jsonschema" not in sys.modules')
        run = subprocess.run([sys.executable, '-I', '-S', '-c', code, str(ROOT / 'src'), str(self.root)],
                             capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr.decode())

    def test_wrong_gold_types_and_unknown_keys_reject_even_with_new_hashes(self):
        entry = self.data['samples'][0]
        path = self.root / entry['assets']['gold.json']['path']
        original = path.read_bytes()
        for key, value in (('total_amount', 178000.0), ('unexpected', 'value')):
            gold = json.loads(original)
            gold[key] = value
            path.write_bytes(encoded(gold))
            entry['assets']['gold.json']['sha256'] = sha(path)
            self.save()
            for evaluator, args in ((scalar_ocr.evaluate_files, self.predictions),
                                    (extended.evaluate_files, {'control': self.predictions})):
                with self.subTest(key=key, evaluator=evaluator.__module__), self.assertRaisesRegex(
                        ValueError, 'business schema/type mismatch'):
                    evaluator(self.root, self.manifest, args)

    def test_validation_runs_once_for_multiple_candidates(self):
        from vietdoc.data.generator import integration
        with patch.object(integration, 'check_sample', wraps=integration.check_sample) as check:
            extended.evaluate_files(self.root, self.manifest,
                                    {'a': self.predictions, 'b': self.predictions})
        self.assertEqual(check.call_count, 2)

    def test_manifest_drift_during_validation_is_rejected(self):
        from vietdoc.data.generator import integration
        original = integration.check_sample
        def change_manifest(*args):
            result = original(*args)
            self.manifest.write_bytes(self.manifest.read_bytes() + b'\n')
            return result
        with patch.object(integration, 'check_sample', side_effect=change_manifest):
            with self.assertRaisesRegex(ValueError, 'manifest changed during validation'):
                scalar_ocr.evaluate_files(self.root, self.manifest, self.predictions)


if __name__ == '__main__':
    unittest.main()
