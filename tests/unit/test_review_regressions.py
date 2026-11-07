"""Strict-review boundary regressions using actual generated artifacts, never model scores."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from vietdoc.data.generator import d21, d22, integration
from vietdoc.data.manifest import encoded, read_json, sha
from vietdoc.evaluation import scalar_ocr, extended
from vietdoc.evaluation.evidence import iou, polygon, evaluate_evidence
from test_evaluation import artifact, sample
from test_evaluation_tables import geometry_sample

ROOT = Path(__file__).resolve().parents[2]


class ReviewRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / 'datasets/processed')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.base = Path(cls.temp.name)
        cls.font = integration.resolve_font()
        cls.d1 = cls.base / 'd1.json'
        integration.build(ROOT, cls.base / 'd1', cls.d1, font_path=cls.font, tiny=True)
        config = dict(read_json(d21.DEFAULT_CONFIG), font_sha256=sha(cls.font))
        path = cls.base / 'd21-config.json'
        path.write_bytes(encoded(config))
        cls.d21 = cls.base / 'd21/manifest.json'
        d21.build(ROOT, cls.d21.parent, config_path=path, font=cls.font)
        config = dict(read_json(d22.DEFAULT_CONFIG), font_sha256=sha(cls.font))
        # Bounded real render: both types, standard/alternate headers and every variant.
        records = d22.plan(config, 2202)
        cls.d22 = cls.base / 'd22/manifest.json'
        cls.d22.parent.mkdir()
        entries = []
        with patch.object(d22, 'plan', return_value=[records[i] for i in (0, 1, 6, 11, 16)]):
            for entry, files in d22.generated(ROOT, config, 2202, cls.font):
                entries.append(entry)
                for suffix, data in files.items():
                    (cls.d22.parent / entry['assets'][suffix]['path']).write_bytes(data)
        cls.d22.write_bytes(encoded(dict(d22.provenance(ROOT, config, 2202, cls.font),
                                         report={'path': 'report.json', 'sha256': '0'*64}, samples=entries)))

    def test_actual_producers_scope_paths_and_version_provenance(self):
        for path, count in ((self.d1, 2), (self.d21, 14), (self.d22, 20)):
            with self.subTest(manifest=path):
                self.assertEqual(len(list(integration.load_artifacts(ROOT, path))), count)
                manifest, samples, _ = scalar_ocr.load_gold(ROOT, path)
                self.assertTrue(all(s['transcript_scope'] == 'full_page' and
                                    s['transcript_order'] == 'renderer-draw-call-v1' for s in samples))
                data = dict(artifact(), dataset_manifest_sha256=sha(path),
                            dataset_version=manifest.get('dataset_version', manifest['version']))
                predictions = self.base / 'empty-predictions.json'
                predictions.write_bytes(encoded(data))
                scalar = scalar_ocr.evaluate_files(ROOT, path, predictions)
                bundle = extended.evaluate_files(ROOT, path, {'empty': predictions})
                report = bundle['reports']['empty']
                self.assertEqual(report['ocr']['all']['cer']['support'], count)
                self.assertEqual(report['ocr']['all']['counts']['missing_or_failed_ocr'], count)
                for result in (scalar['inputs'], report['inputs'], bundle['freeze_record'], *report['correctness_labels']):
                    self.assertEqual(result['dataset_version'], data['dataset_version'])
                    self.assertEqual(result['manifest_format_version'], manifest['version'])
                if path == self.d22:
                    self.assertNotEqual(data['dataset_version'], manifest['version'])
                    output = self.base / 'bundle'
                    extended.write_bundle(bundle, output)
                    labels = [json.loads(line) for line in (output/'empty/correctness-labels.jsonl').read_text(encoding='utf-8').splitlines()]
                    self.assertTrue(all(e['dataset_version'] == data['dataset_version'] for e in labels))

    def test_historical_scope_adapter_and_unknown_scope_exclusion(self):
        original = read_json(self.d1)
        for version in ('d1.2.v1', 'd1.2.v2', 'unknown-format'):
            data = copy.deepcopy(original)
            data['version'] = version
            for entry in data['samples']:
                entry['generator_version'] = version
            if version == 'd1.2.v1':
                data.pop('environment')
            data.pop('transcript_scope')
            data.pop('transcript_order')
            path = self.base / 'historical.json'
            path.write_bytes(encoded(data))
            _, samples, _ = scalar_ocr.load_gold(ROOT, path,
                gold_mode='annotated' if version == 'unknown-format' else 'renderer')
            report = scalar_ocr.evaluate(samples, artifact())
            self.assertEqual(report['ocr']['all']['cer']['support'], 0 if version == 'unknown-format' else 2)
        data['transcript_scope'] = 'qa_answers'
        path.write_bytes(encoded(data))
        _, samples, _ = scalar_ocr.load_gold(ROOT, path, gold_mode='annotated')
        self.assertEqual(scalar_ocr.evaluate(samples, artifact())['ocr']['all']['cer']['support'], 0)

    def test_d2_consumer_corruptions_normal_and_optimized(self):
        code = ('from pathlib import Path; import sys; '
                'from vietdoc.data.generator.integration import load_artifacts; '
                'list(load_artifacts(Path(sys.argv[1]), Path(sys.argv[2])))')
        for original in (self.d21, self.d22):
            baseline = read_json(original)
            for case in ('valid', 'hash', 'duplicate', 'type', 'schema', 'version', 'rows', 'statuses', 'lineage',
                         'wrong-total', 'wrong-repeat', 'wrong-line', 'transcript', 'bounds', 'path'):
                data = copy.deepcopy(baseline)
                entry = next(e for e in data['samples'] if read_json(original.parent / e['assets']['gold.json']['path'])['total_amount'] not in ('0', None))
                changed = {}
                def save(suffix, value):
                    path = original.parent / entry['assets'][suffix]['path']
                    changed[path] = path.read_bytes()
                    path.write_bytes(value if isinstance(value, bytes) else encoded(value))
                    entry['assets'][suffix]['sha256'] = sha(path)
                if case == 'hash':
                    entry['assets']['png']['sha256'] = '0'*64
                elif case == 'duplicate':
                    data['samples'].append(copy.deepcopy(entry))
                elif case in ('type', 'schema', 'version', 'rows', 'statuses', 'lineage'):
                    key, value = {'type': ('document_type', 'invoice'), 'schema': ('schema_id', 'wrong'),
                        'version': ('generator_version', 'wrong'), 'rows': ('row_count', 777),
                        'statuses': ('label_statuses', {'present': 1}), 'lineage': ('template_id', 'wrong')}[case]
                    entry[key] = value
                elif case == 'wrong-total':
                    gold = read_json(original.parent / entry['assets']['gold.json']['path'])
                    labels = read_json(original.parent / entry['assets']['labels.json']['path'])
                    gold['total_amount'] = '0'
                    labels['/total_amount']['raw'] = '0 đ'
                    save('gold.json', gold)
                    save('labels.json', labels)
                elif case in ('wrong-repeat', 'wrong-line', 'bounds'):
                    geometry = read_json(original.parent / entry['assets']['regions.json']['path'])
                    if case == 'bounds':
                        geometry['regions'][0]['bbox_px'][0] = -1
                    else:
                        region = next(r for r in geometry['regions'] if r['pointer'] == '/total_amount')
                        if case == 'wrong-repeat':
                            geometry['regions'].append(dict(region, text='Số tiền ghi lại: 999 đ'))
                        else:
                            region['text'] = 'Tổng thanh toán: 999 đ'
                    save('regions.json', geometry)
                    save('txt', ''.join(r['text']+'\n' for r in geometry['regions']).encode('utf-8'))
                elif case == 'transcript':
                    save('txt', b'drift\n')
                elif case == 'path':
                    entry['assets']['png']['path'] = '../outside.png'
                path = original.parent / 'consumer-case.json'
                path.write_bytes(encoded(data))
                try:
                    for optimized in (False, True):
                        with self.subTest(version=data['version'], case=case, optimized=optimized):
                            run = subprocess.run([sys.executable, *(['-O'] if optimized else []), '-c', code, str(ROOT), str(path)],
                                env=dict(os.environ, PYTHONPATH=str(ROOT/'src')), capture_output=True)
                            self.assertEqual(run.returncode == 0, case == 'valid', run.stderr.decode('utf-8'))
                            if case != 'valid':
                                self.assertIn(entry['sample_id'].encode(), run.stderr)
                                reasons = {'hash': 'hash mismatch', 'duplicate': 'duplicate sample_id',
                                    'type': 'D2.1 lineage mismatch' if original == self.d21 else 'D2 family/type mismatch',
                                    'schema': 'schema_id mismatch', 'version': 'generator version mismatch',
                                    'rows': 'invalid row_count', 'statuses': 'label status counts mismatch',
                                    'lineage': 'lineage mismatch', 'wrong-total': 'exact occurrence mismatch',
                                    'wrong-repeat': 'exact occurrence mismatch',
                                    'wrong-line': 'exact occurrence mismatch', 'transcript': 'transcript drift',
                                    'bounds': 'bbox outside image', 'path': 'invalid relative path'}
                                self.assertIn(reasons[case].encode(), run.stderr)
                finally:
                    for path, value in changed.items():
                        path.write_bytes(value)

    def test_labels_boundary_and_partial_annotation(self):
        for labels in ({'version': 'd1.1', 'labels': {}}, {'/merchnat_name': {'status': 'present'}},
                       {'/items/99/description': {'status': 'present'}}, {'/merchant_name': 'present'},
                       {'/merchant_name': {'status': 'typo'}}):
            s = sample()
            s['labels'] = labels
            for evaluator in (scalar_ocr.evaluate, extended.evaluate):
                reason = ('unsupported label pointer/format' if any(
                    p not in ('/merchant_name',) for p in labels) else 'invalid label')
                with self.subTest(labels=labels, evaluator=evaluator.__module__), self.assertRaisesRegex(ValueError, reason):
                    evaluator([s], artifact())
        s = sample()
        s['labels'] = {'/merchant_name': {'status': 'obscured'}}
        result = extended.evaluate([s], artifact())
        self.assertEqual(result['scalar']['all']['counts']['obscured'], 1)
        self.assertEqual(result['scalar']['all']['counts']['unlabeled'], 4)
        self.assertEqual(result['scalar']['all']['counts']['absent'], 0)
        # The file boundary must reject before either scoring or slice construction.
        data = read_json(self.d1)
        entry = data['samples'][0]
        path = self.base / 'envelope.json'
        path.write_bytes(encoded({'version': 'd1.1', 'labels': {}}))
        entry['assets']['labels.json'] = {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path)}
        manifest = self.base / 'bad-labels.json'
        manifest.write_bytes(encoded(data))
        for loader in (scalar_ocr.load_gold, extended.load_gold):
            with self.assertRaisesRegex(ValueError, 'unsupported label pointer/format'):
                loader(ROOT, manifest)

    def test_strict_validators_reject_corrupt_assets_under_optimization(self):
        for module, manifest in (('d21', self.d21), ('d22', self.d22)):
            entry = read_json(manifest)['samples'][0]
            image = manifest.parent / entry['assets']['png']['path']
            original = image.read_bytes()
            image.write_bytes(b'corrupt')
            code = (f'from vietdoc.data.generator.{module} import validate; from pathlib import Path; '
                    'import sys; validate(Path(sys.argv[1]), Path(sys.argv[2]), font=Path(sys.argv[3]))')
            try:
                for optimized in (False, True):
                    with self.subTest(module=module, optimized=optimized):
                        run = subprocess.run([sys.executable, *(['-O'] if optimized else []), '-c', code,
                            str(ROOT), str(manifest), str(self.font)], env=dict(os.environ, PYTHONPATH=str(ROOT/'src')),
                            capture_output=True)
                        self.assertNotEqual(run.returncode, 0)
                        self.assertIn(b'hash mismatch' if module == 'd21' else b'asset drift', run.stderr)
            finally:
                image.write_bytes(original)

    def test_evaluator_reads_with_cp1252_default_and_writes_lf(self):
        native = Path.read_text
        def cp1252(path, encoding=None, errors=None):
            return native(path, encoding=encoding or 'cp1252', errors=errors)
        path = self.base / 'locale-predictions.json'
        path.write_bytes(encoded(dict(artifact(), dataset_manifest_sha256=sha(self.d1))))
        with patch.object(Path, 'read_text', cp1252):
            report = scalar_ocr.evaluate_files(ROOT, self.d1, path)
            bundle = extended.evaluate_files(ROOT, self.d1, {'empty': path})
        self.assertEqual(report['scalar']['all']['counts']['present'], 12)
        output = self.base / 'locale-bundle'
        extended.write_bundle(bundle, output)
        for path in output.rglob('*'):
            if path.is_file():
                self.assertNotIn(b'\r\n', path.read_bytes())
                path.read_bytes().decode('utf-8')

    def test_tiny_and_degenerate_geometry(self):
        tiny = [[1-1e-12, 1-1e-12], [1, 1-1e-12], [1, 1], [1-1e-12, 1]]
        self.assertIsNotNone(polygon(tiny))
        self.assertEqual(iou(tiny, tiny), 1)
        for q in (tiny, [[0, 0], [1, 0], [1, 1e-12], [0, 1e-12]],
                  [[0, 0], [1e-200, 0], [1e-200, 1e-200], [0, 1e-200]], [[1, 1]]*4):
            s, p = geometry_sample()
            p['field_metadata'][0]['source_regions'][0]['quad'] = q
            result = evaluate_evidence(s, p, {'matches': []})
            self.assertEqual(len(result['details']), 1)
            if polygon(q) is None:
                self.assertIsNone(iou(q, q))
                self.assertEqual(result['counts']['invalid_region_fields'], 1)


if __name__ == '__main__':
    unittest.main()
