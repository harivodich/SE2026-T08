"""D2.1 source, renderer, manifest and deliberate corruption boundaries."""
import copy
import shutil
import subprocess
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageChops

from vietdoc.data.generator import d21
from vietdoc.data.generator.rendering import FONT, render
from vietdoc.data.generator.values import CONFIG, document_cases
from vietdoc.data.manifest import encoded, read_json, sha
from vietdoc.data.validation import approval_diagnostics, validate_source

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = read_json(ROOT / 'specs/contracts/business.schema.json')


class D21Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.output = cls.base / 'a'
        cls.first = d21.build(ROOT, cls.output)
        cls.manifest = cls.output / 'manifest.json'
        cls.cases = list(document_cases(2101, d21.load_config(d21.DEFAULT_CONFIG), read_json(CONFIG)))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_fresh_runs_all_bytes_and_non_overwrite(self):
        second_dir = self.base / 'b'
        second = d21.build(ROOT, second_dir)
        self.assertEqual(self.first, second)
        self.assertEqual(d21.validate(ROOT, self.manifest), dict(accepted=14, rejected=6, valid=True))
        self.assertEqual(d21.validate(ROOT, second_dir / 'manifest.json'), dict(accepted=14, rejected=6, valid=True))
        first_files = {p.name: sha(p) for p in self.output.iterdir()}
        self.assertEqual(first_files, {p.name: sha(p) for p in second_dir.iterdir()})
        with self.assertRaises(FileExistsError):
            d21.build(ROOT, self.output)

    @unittest.skipUnless(all(shutil.which(p) for p in ('pdfinfo', 'pdfimages', 'pdftoppm')),
                         'optional Poppler tools unavailable')
    def test_pdf_independent_parser_render_and_lossless_image(self):
        qa = self.base / 'pdfqa'
        qa.mkdir()
        for pdf in self.output.glob('*.pdf'):
            with self.subTest(pdf=pdf.name):
                info = subprocess.run(['pdfinfo', str(pdf)], capture_output=True, text=True, check=True).stdout
                self.assertIn('Pages:           1', info)
                prefix = qa / pdf.stem
                subprocess.run(['pdftoppm', '-r', '72', '-singlefile', '-png', str(pdf), str(prefix)],
                               capture_output=True, check=True)
                subprocess.run(['pdfimages', '-png', str(pdf), str(prefix) + '-embedded'],
                               capture_output=True, check=True)
                with Image.open(str(prefix) + '.png') as rendered:
                    self.assertEqual(rendered.size, (1500, 2600))
                with Image.open(str(prefix) + '-embedded-000.png') as embedded, Image.open(pdf.with_suffix('.png')) as expected:
                    self.assertIsNone(ImageChops.difference(embedded.convert('RGB'), expected.convert('RGB')).getbbox())

    def test_boundaries_report_and_approval(self):
        self.assertEqual({s['row_count'] for s in self.first['samples']}, {0, 1, 3, 30})
        report = read_json(self.output / 'rejections.json')
        self.assertEqual(len(report['rejected']), 6)
        for rejection in report['rejected']:
            self.assertTrue(rejection['reason'])
            if rejection['sample_id'].endswith('overflow'):
                self.assertIn('Clipping', rejection['reason'])
                source = next(c for c in self.cases if c[0] == rejection['sample_id'])
                validate_source(source[3], source[1], SCHEMA, FONT)  # schema-valid, render-invalid
            else:
                self.assertEqual(rejection['row_count'], 31)
                self.assertIn('schema', rejection['reason'])
            self.assertFalse(list(self.output.glob(rejection['sample_id'] + '.*')))
        for sample in self.first['samples']:
            self.assertTrue(sample['validation']['schema_valid'])
            self.assertFalse(sample['validation']['approval_valid'])
            if sample['sample_id'].endswith('missing-total'):
                self.assertEqual(sample['validation']['blockers'], ['total_amount_missing'])
                self.assertEqual(read_json(self.output / sample['assets']['labels.json']['path'])['/total_amount']['status'], 'absent')
            if sample['row_count'] == 0:
                self.assertIn('empty_items_requires_completeness_review', sample['validation']['warnings'])

    def test_source_semantics_unicode_font_and_missing(self):
        _, kind, layout, original = self.cases[1]
        cases = [('transaction_date', '2026-02-30'), ('transaction_time', '25:70'),
                 ('total_amount', 1.5), ('total_amount', '-1'), ('total_amount', '01'),
                 ('merchant_name', ''), ('merchant_name', 'Cafe\u0301'),
                 ('merchant_name', 'Hư Cấu\n'), ('merchant_name', '\U0010ffff')]
        for key, value in cases:
            payload = copy.deepcopy(original)
            payload[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_source(payload, kind, SCHEMA, FONT)
        for key in ('transaction_date', 'transaction_time', 'total_amount', 'merchant_name'):
            payload = copy.deepcopy(original)
            payload[key] = None
            validate_source(payload, kind, SCHEMA, FONT)
            labels = d21.labels_for(payload)
            self.assertEqual(labels['/' + key]['status'], 'absent')
            self.assertIsNone(labels['/' + key]['raw'])
        payload = copy.deepcopy(original)
        payload['total_amount'] = '1'
        self.assertIn('arithmetic:items_sum', approval_diagnostics(payload)['warnings'])
        # Arithmetic differences remain source values, never rewritten by validation.
        self.assertEqual(payload['total_amount'], '1')
        missing_cell = copy.deepcopy(original)
        missing_cell['items'][0]['quantity'] = None
        validate_source(missing_cell, kind, SCHEMA, FONT)
        image, transcript, geometry = render(missing_cell, kind, layout)
        self.assertEqual(d21.labels_for(missing_cell)['/items/0/quantity']['status'], 'absent')
        self.assertFalse(any(r['pointer'] == '/items/0/quantity' for r in geometry['regions']))
        for value in ('0', '1.5', '99999999999999999999999999999999'):
            payload['total_amount'] = value
            validate_source(payload, kind, SCHEMA, FONT)
        with self.assertRaises(ValueError):
            validate_source(original, 'other', SCHEMA, FONT)
        with self.assertRaises(OSError):
            validate_source(original, kind, SCHEMA, Path('/no/such/font.ttf'))
        payload = copy.deepcopy(original)
        payload['items'][0]['description'] = 'X' * 500
        with self.assertRaisesRegex(ValueError, 'Word exceeds column'):
            render(payload, kind, layout)

    def test_config_version_seed_and_font(self):
        for key, value in [('version', 'future'), ('rows', [1, 1]), ('rows', [-1]), ('rows', [True]), ('rows', [101])]:
            config = read_json(d21.DEFAULT_CONFIG)
            config[key] = value
            path = self.base / 'bad-config.json'
            path.write_bytes(encoded(config))
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                d21.load_config(path)
        with self.assertRaisesRegex(ValueError, 'version'):
            d21.build(ROOT, self.base / 'bad-version', requested_version='d0')
        with self.assertRaisesRegex(ValueError, 'seed'):
            d21.build(ROOT, self.base / 'bad-seed', seed=-1)
        wrong_font = self.base / 'wrong-font.ttf'
        wrong_font.write_bytes(b'not a font')
        with self.assertRaisesRegex(ValueError, 'font hash'):
            d21.build(ROOT, self.base / 'bad-font', font=wrong_font)
        self.assertNotEqual(list(document_cases(2101, d21.load_config(d21.DEFAULT_CONFIG), read_json(CONFIG))),
                            list(document_cases(2102, d21.load_config(d21.DEFAULT_CONFIG), read_json(CONFIG))))

    def test_manifest_tampering(self):
        # Modify one file at a time, restoring it even when a check fails.
        original_manifest = self.manifest.read_bytes()
        original_report = (self.output / 'rejections.json').read_bytes()
        first_sample = self.first['samples'][0]
        image_path = self.output / first_sample['assets']['png']['path']
        original_image = image_path.read_bytes()
        for case in ('hash', 'corrupt', 'dimensions', 'absolute', 'traversal', 'missing', 'symlink',
                     'invalid_id', 'duplicate_id', 'duplicate_image', 'duplicate_path', 'missing_asset', 'row_count',
                     'regions', 'transcript', 'status', 'gold', 'pdf', 'report', 'omitted', 'environment'):
            changes = {}
            data = copy.deepcopy(self.first)
            sample = data['samples'][0]
            try:
                if case in ('hash', 'corrupt', 'dimensions'):
                    changes[image_path] = original_image
                    if case == 'dimensions':
                        Image.new('RGB', (10, 10)).save(image_path)
                    else:
                        image_path.write_bytes(b'not an image')
                    if case != 'hash':
                        sample['assets']['png']['sha256'] = sha(image_path)
                elif case in ('absolute', 'traversal', 'missing', 'symlink'):
                    if case == 'symlink':
                        target = self.base / 'outside.png'
                        target.write_bytes(original_image)
                        link = self.output / 'escape.png'
                        if not link.exists():
                            link.symlink_to(target)
                        name = link.name
                    else:
                        name = {'absolute': str(image_path), 'traversal': '../outside.png', 'missing': 'missing.png'}[case]
                    sample['assets']['png']['path'] = name
                elif case == 'invalid_id':
                    sample['sample_id'] = '../escape'
                elif case == 'duplicate_id':
                    data['samples'].append(copy.deepcopy(sample))
                elif case == 'duplicate_image':
                    other = data['samples'][1]['assets']['png']
                    target = self.output / other['path']
                    changes[target] = target.read_bytes()
                    target.write_bytes(original_image)
                    other['sha256'] = sha(target)
                elif case == 'duplicate_path':
                    sample['assets']['pdf'] = copy.deepcopy(sample['assets']['png'])
                elif case == 'missing_asset':
                    del sample['assets']['pdf']
                elif case == 'row_count':
                    sample['row_count'] += 1
                elif case in ('regions', 'transcript', 'status', 'gold', 'pdf'):
                    suffix = {'regions': 'regions.json', 'transcript': 'txt', 'status': 'labels.json', 'gold': 'gold.json', 'pdf': 'pdf'}[case]
                    asset = sample['assets'][suffix]
                    path = self.output / asset['path']
                    changes[path] = path.read_bytes()
                    if case == 'regions':
                        geometry = read_json(path)
                        geometry['regions'][0]['bbox_px'][2] = 9999
                        path.write_bytes(encoded(geometry))
                    elif case == 'status':
                        labels = read_json(path)
                        labels['/merchant_address']['status'] = 'unlabeled'
                        path.write_bytes(encoded(labels))
                    elif case == 'gold':
                        gold = read_json(path)
                        gold['total_amount'] = '999'
                        path.write_bytes(encoded(gold))
                    else:
                        path.write_bytes(b'tampered')
                    asset['sha256'] = sha(path)
                elif case == 'report':
                    path = self.output / 'rejections.json'
                    changes[path] = original_report
                    report = read_json(path)
                    report['rejected'][0]['reason'] = 'made up'
                    path.write_bytes(encoded(report))
                    data['report']['sha256'] = sha(path)
                elif case == 'omitted':
                    data['samples'].pop()
                elif case == 'environment':
                    data['environment']['pillow'] = 'other'
                self.manifest.write_bytes(encoded(data))
                with self.subTest(case=case), self.assertRaises((ValueError, OSError)):
                    d21.validate(ROOT, self.manifest)
            finally:
                self.manifest.write_bytes(original_manifest)
                for path, content in changes.items():
                    path.write_bytes(content)


if __name__ == '__main__':
    unittest.main()
