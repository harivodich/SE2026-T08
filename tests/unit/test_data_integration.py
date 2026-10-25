"""D1.2 portable semantics, exact occurrences and normal/-O integrity checks."""
from collections import Counter
import copy
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from vietdoc.data.generator.integration import build, load_artifacts, samples, resolve_font, environment
from vietdoc.data.generator.artifact_io import encoded, read_json, sha

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'tests/fixtures/d12/manifest.json'


class IntegrationDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / 'datasets/processed')
        cls.base = Path(cls.temp.name)
        cls.output = cls.base / 'original'
        cls.manifest = cls.base / 'manifest.json'
        cls.font = resolve_font()
        build(ROOT, cls.output, cls.manifest, tiny=True, font_path=cls.font)
        cls.data = read_json(cls.manifest)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def scratch(self):
        temp = tempfile.TemporaryDirectory(dir=ROOT / 'datasets/processed')
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        data = copy.deepcopy(self.data)
        for sample in data['samples']:
            for asset in sample['assets'].values():
                source = ROOT / asset['path']
                path = base / source.name
                shutil.copyfile(source, path)
                asset['path'] = path.relative_to(ROOT).as_posix()
        manifest = base / 'manifest.json'
        manifest.write_bytes(encoded(data))
        return data, manifest

    def save_asset(self, sample, suffix, value):
        asset = sample['assets'][suffix]
        path = ROOT / asset['path']
        path.write_bytes(value if isinstance(value, bytes) else encoded(value))
        asset['sha256'] = sha(path)

    def rejects(self, data, manifest, reason):
        manifest.write_bytes(encoded(data))
        with self.assertRaisesRegex(ValueError, reason):
            list(load_artifacts(ROOT, manifest))

    def test_set_coverage_and_full_loader(self):
        data = list(samples())
        self.assertEqual(len({s[0] for s in data}), 20)
        self.assertEqual(Counter(s[1] for s in data), {'receipt': 10, 'invoice': 10})
        self.assertEqual(Counter((s[1], s[2]) for s in data),
                         {(k, n): 5 for k in ('receipt', 'invoice') for n in (0, 1)})
        self.assertEqual(Counter(len(s[3]['items']) for s in data), {n: 4 for n in (1, 3, 5, 12, 30)})
        self.assertEqual(data, list(samples()))
        self.assertNotEqual(data, list(samples(1203)))
        output, manifest = self.base / 'full', self.base / 'full.json'
        build(ROOT, output, manifest, font_path=self.font)
        self.assertEqual(len(list(load_artifacts(ROOT, manifest, full_set=True))), 20)
        for broken in [dict(self.data, samples=[]), self.data]:
            scratch = self.base / 'incomplete.json'
            scratch.write_bytes(encoded(broken))
            with self.assertRaisesRegex(ValueError, 'requires 20 IDs'):
                list(load_artifacts(ROOT, scratch, full_set=True))

    def test_portable_tiny_semantics_and_same_environment_reproduction(self):
        original = list(load_artifacts(ROOT, FIXTURE))
        actual = list(load_artifacts(ROOT, self.manifest))
        self.assertEqual([g for _, g in original], [g for _, g in actual])
        second = self.base / 'second'
        build(ROOT, second, second / 'manifest.json', tiny=True, font_path=self.font)
        reproduced = list(load_artifacts(ROOT, second / 'manifest.json'))
        for (first, _), (again, _), (reference, _) in zip(actual, reproduced, original):
            self.assertEqual({k: a['sha256'] for k, a in first['assets'].items()},
                             {k: a['sha256'] for k, a in again['assets'].items()})
            for suffix in ('gold.json', 'labels.json'):
                self.assertEqual(first['assets'][suffix]['sha256'], reference['assets'][suffix]['sha256'])
        with self.assertRaises(FileExistsError):
            build(ROOT, self.output, self.manifest, tiny=True, font_path=self.font)
        self.assertEqual(self.data['environment'], environment())

    @unittest.skipUnless(os.environ.get('VIETDOC_CANONICAL_BYTES') == '1',
                         'opt-in canonical bytes: set VIETDOC_CANONICAL_BYTES=1 in declared render environment')
    def test_canonical_reference_bytes(self):
        pin = read_json(FIXTURE.parent / 'canonical-environment.json')
        self.assertEqual(environment(), pin['environment'], 'canonical renderer environment differs')
        self.assertEqual(sha(self.font), pin['font_sha256'], 'canonical font differs')
        for (reference, _), (actual, _) in zip(load_artifacts(ROOT, FIXTURE), load_artifacts(ROOT, self.manifest)):
            for suffix in reference['assets']:
                self.assertEqual(reference['assets'][suffix]['sha256'], actual['assets'][suffix]['sha256'])

    def test_exact_amount_occurrences_wrap_and_duplicates(self):
        # Image/text remain unchanged: coordinated gold+raw+hash changes must fail.
        for replacement in ('0', '80', '500'):
            with self.subTest(replacement=replacement):
                data, manifest = self.scratch()
                sample = data['samples'][0]
                gold = read_json(ROOT / sample['assets']['gold.json']['path'])
                labels = read_json(ROOT / sample['assets']['labels.json']['path'])
                gold['total_amount'] = replacement
                labels['/total_amount']['raw'] = replacement + ' đ'
                self.save_asset(sample, 'gold.json', gold)
                self.save_asset(sample, 'labels.json', labels)
                self.rejects(data, manifest, 'd12-receipt-03: exact occurrence mismatch: /total_amount')
        # Exact review reproduction: the actual first PNG says 37.500, gold says 0.
        output, manifest = self.base / 'r03-full', self.base / 'r03-full.json'
        build(ROOT, output, manifest, font_path=self.font)
        data = read_json(manifest)
        sample = data['samples'][0]
        gold = read_json(ROOT / sample['assets']['gold.json']['path'])
        self.assertEqual(gold['total_amount'], '37500')
        labels = read_json(ROOT / sample['assets']['labels.json']['path'])
        gold['total_amount'], labels['/total_amount']['raw'] = '0', '0 đ'
        self.save_asset(sample, 'gold.json', gold)
        self.save_asset(sample, 'labels.json', labels)
        self.rejects(data, manifest, 'd12-receipt-01: exact occurrence mismatch: /total_amount')
        # 180.000 on pixels/raw cannot supervise gold 80.000 (suffix collision).
        source = next(s for s in samples() if s[0] == 'd12-receipt-03')
        source[3]['items'][0]['unit_price'] = '180000'
        output, manifest = self.base / 'r03-suffix', self.base / 'r03-suffix.json'
        with patch('vietdoc.data.generator.integration.samples', return_value=[source]):
            build(ROOT, output, manifest, font_path=self.font, tiny=True)
        data = read_json(manifest)
        sample = data['samples'][0]
        gold = read_json(ROOT / sample['assets']['gold.json']['path'])
        labels = read_json(ROOT / sample['assets']['labels.json']['path'])
        gold['items'][0]['unit_price'] = '80000'
        labels['/items/0/unit_price']['raw'] = '80.000 đ'
        self.save_asset(sample, 'gold.json', gold)
        self.save_asset(sample, 'labels.json', labels)
        self.rejects(data, manifest, 'exact occurrence mismatch: /items/0/unit_price')
        data, manifest = self.scratch()
        sample = data['samples'][0]
        geometry = read_json(ROOT / sample['assets']['regions.json']['path'])
        totals = [r for r in geometry['regions'] if r['pointer'] == '/total_amount']
        totals[-1]['text'] = 'Số tiền ghi lại: 180.000 đ'  # first occurrence remains correct
        self.save_asset(sample, 'regions.json', geometry)
        self.save_asset(sample, 'txt', ''.join(r['text']+'\n' for r in geometry['regions']).encode('utf-8'))
        self.rejects(data, manifest, 'exact occurrence mismatch: /total_amount')
        # A true suffix pair reproduces R03 precisely; neither 0 nor 80.000 is 180.000.
        from vietdoc.data.generator.integration import occurrences
        region = dict(pointer='/total_amount', text='Tổng thanh toán: 180.000 đ')
        self.assertEqual(occurrences([region], '/total_amount'), ['180.000 đ'])
        self.assertNotIn('80.000 đ', occurrences([region], '/total_amount'))

    def test_metadata_type_schema_counts_lineage_and_assets(self):
        for key, value, reason in [
            ('document_type', 'invoice', 'sample_id/type'), ('schema_id', 'wrong', 'schema_id'),
            ('row_count', 999, 'row_count'), ('row_count', 5, 'row profile'),
            ('label_statuses', {'present': 1}, 'status counts'), ('seed', '1202', 'seed'),
            ('family_id', 'wrong', 'lineage'), ('template_id', 'wrong', 'lineage'),
            ('generator_version', 'wrong', 'version')]:
            with self.subTest(key=key, value=value):
                data, manifest = self.scratch()
                data['samples'][0][key] = value
                self.rejects(data, manifest, 'd12-receipt-03: .*' + reason)
        data, manifest = self.scratch()
        del data['samples'][0]['assets']['png']
        self.rejects(data, manifest, 'd12-receipt-03: missing/unknown asset')
        data, manifest = self.scratch()
        data['samples'][0]['document_type'] = 'invoice'
        data['samples'][0]['sample_id'] = data['samples'][0]['base_id'] = 'd12-invoice-03'
        data['samples'][0]['family_id'] = 'invoice-layout-0'
        data['samples'][0]['template_id'] = 'invoice-layout-0-v1'
        self.rejects(data, manifest, 'd12-invoice-03: business schema/type mismatch: invoice')  # receipt gold must fail Invoice branch
        data, manifest = self.scratch()
        data['version'] = 'unknown'
        self.rejects(data, manifest, 'unsupported manifest version')

    def test_corruption_in_normal_and_optimized_interpreters(self):
        code = 'from pathlib import Path; from vietdoc.data.generator.integration import load_artifacts; import sys; print(len(list(load_artifacts(Path(sys.argv[1]), Path(sys.argv[2])))))'
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
        for case in ('valid', 'hash', 'path', 'duplicate', 'transcript', 'bbox', 'missing-file'):
            data, manifest = self.scratch()
            sample = data['samples'][0]
            if case == 'hash':
                sample['assets']['png']['sha256'] = '0'*64
            elif case == 'path':
                sample['assets']['png']['path'] = '../outside.png'
            elif case == 'duplicate':
                data['samples'].append(copy.deepcopy(sample))
            elif case == 'transcript':
                self.save_asset(sample, 'txt', b'drift\n')
            elif case == 'bbox':
                geometry = read_json(ROOT / sample['assets']['regions.json']['path'])
                geometry['regions'][0]['bbox_px'][0] = -1
                self.save_asset(sample, 'regions.json', geometry)
            elif case == 'missing-file':
                sample['assets']['png']['path'] = 'datasets/processed/no-such-file.png'
            manifest.write_bytes(encoded(data))
            for optimized in (False, True):
                with self.subTest(case=case, optimized=optimized):
                    result = subprocess.run([sys.executable, *(['-O'] if optimized else []), '-c', code,
                                             str(ROOT), str(manifest)], env=env, capture_output=True)
                    self.assertEqual(result.returncode == 0, case == 'valid', result.stderr.decode('utf-8'))
                    if case != 'valid':
                        self.assertIn(b'd12-receipt-03', result.stderr)

    def test_utf8_reads_with_cp1252_default(self):
        native = Path.read_text
        def cp1252(path, encoding=None, errors=None):
            return native(path, encoding=encoding or 'cp1252', errors=errors)
        with patch.object(Path, 'read_text', cp1252):
            self.assertEqual(len(list(load_artifacts(ROOT, FIXTURE))), 2)
            self.assertIn('Hư Cấu', list(samples())[0][3]['merchant_name'])
        for path in self.output.iterdir():
            if path.suffix != '.png':
                self.assertNotIn(b'\r\n', path.read_bytes())

    def test_font_override_and_failure(self):
        with patch.dict(os.environ, {'VIETDOC_DATA_FONT': str(self.font)}):
            self.assertEqual(resolve_font(), self.font)
        with self.assertRaisesRegex(ValueError, 'No usable Vietnamese font'):
            resolve_font(self.base / 'missing.ttf')


if __name__ == '__main__':
    unittest.main()
