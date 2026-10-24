"""D2.2 leakage, transform boundaries, reproducibility and consumer smoke."""
import copy
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from vietdoc.data.generator import d22
from vietdoc.data.generator.augmentation import augment, validate_policy
from vietdoc.data.generator.integration import load_artifacts
from vietdoc.data.generator.rendering import FONT
from vietdoc.data.generator.templates.families import catalog, render_family
from vietdoc.data.generator.values import CONFIG
from vietdoc.data.manifest import encoded, read_json, sha
from vietdoc.data.splits import assign_groups, assert_disjoint, duplicate_report
from vietdoc.data.validation import leaves

ROOT = Path(__file__).resolve().parents[2]


class GroupPolicyTest(unittest.TestCase):
    def setUp(self):
        self.config = read_json(d22.DEFAULT_CONFIG)

    def test_family_source_alias_transitive_conflict(self):
        records = [dict(base_id='a', family_id='f1', source_group='s1', split='train'),
                   dict(base_id='b', family_id='f1', source_group='s2', split='train'),
                   dict(base_id='c', family_id='f2', source_group='s2', split='final')]
        with self.assertRaisesRegex(ValueError, 'conflicting split'):
            assign_groups(records)
        records[2]['split'] = 'train'
        grouped = assign_groups(records)
        self.assertEqual(len({r['assignment_group'] for r in grouped}), 1)
        self.config['source_aliases'] = {'receipt-f00': 'same-origin', 'invoice-f09': 'same-origin'}
        with self.assertRaisesRegex(ValueError, 'conflicting split'):
            d22.plan(self.config, 2202)

    def test_assignment_before_values_and_capacity_targets(self):
        self.config['bases_per_family'] = 150
        records = d22.plan(self.config, 2202)
        self.assertEqual(len(records), 3000)
        self.assertEqual(records, d22.plan(self.config, 2202))
        self.assertEqual([(r['base_id'], r['split']) for r in records],
                         [(r['base_id'], r['split']) for r in d22.plan(self.config, 42)])
        self.assertNotEqual(records[0]['value_seed'], d22.plan(self.config, 42)[0]['value_seed'])
        assert_disjoint(records)
        for kind in ('receipt', 'invoice'):
            for partition in ('dev-tuning', 'dev-calibration'):
                self.assertEqual(sum(r['document_type'] == kind and r['dev_partition'] == partition for r in records), 150)
        self.config['bases_per_family'] = 300
        self.assertEqual(len(d22.plan(self.config, 2202)), 6000)
        self.assertTrue(all(r['dev_partition'] is None for r in d22.plan(read_json(d22.DEFAULT_CONFIG), 1)))
        self.config['source_aliases'] = {'receipt-f06': 'duplicate-dev-source', 'receipt-f07': 'duplicate-dev-source'}
        # Source aliases cannot cross the calibration/tuning subpartitions either.
        self.assertTrue(all(r['dev_partition'] is None for r in d22.plan(self.config, 1)))

    def test_family_structures_and_split_counts(self):
        for kind in ('receipt', 'invoice'):
            families = [f for f in catalog() if f['document_type'] == kind]
            self.assertEqual(len({(f['header'], f['totals'], tuple(f['columns'])) for f in families}), 10)
            self.assertEqual([sum(f['split'] == s for f in families) for s in ('train', 'dev', 'final')], [6, 2, 2])

    def test_zero_row_invoice_never_generates_negative_total(self):
        record = next(r for r in d22.plan(self.config, 2202) if r['document_type'] == 'invoice' and r['row_count'] == 0)
        vocabulary = read_json(CONFIG)
        for value_seed in range(30):
            gold = d22.payload_for(dict(record, value_seed=value_seed), vocabulary)
            self.assertGreaterEqual(Decimal(gold['total_amount']), 0)
            self.assertLessEqual(Decimal(gold['discount_amount']), Decimal(gold['subtotal']) + Decimal(gold['tax_amount']))

    def test_severity_bounds_and_invalid_configs(self):
        for key, value in [('shear', .02501), ('shear', float('nan')), ('blur', 1.001),
                           ('noise', 19), ('crop', [201, 0, 0, 0]), ('unreadable', 1)]:
            policy = dict(d22.CLEAN, **{key: value})
            with self.assertRaises(ValueError, msg=key):
                validate_policy(policy)
        with tempfile.TemporaryDirectory() as folder:
            config = dict(self.config, bases_per_family=150)
            path = Path(folder) / 'config.json'
            path.write_bytes(encoded(config))
            with self.assertRaisesRegex(ValueError, 'base limit'):
                d22.build(ROOT, Path(folder) / 'not-created', path)
            self.assertFalse((Path(folder) / 'not-created').exists())

    def test_cross_split_hash_and_content_fail_closed(self):
        samples = []
        for i, split in enumerate(('train', 'final')):
            samples.append(dict(base_id=str(i), family_id=str(i), source_group=str(i), assignment_group=str(i),
                                split=split, sample_id=str(i), quality='clean', dhash='0', content_tokens=['a'],
                                content_sha256=str(i), assets={'png': {'sha256': 'same'}}))
        with self.assertRaisesRegex(ValueError, 'exact image'):
            duplicate_report(samples)
        samples[1]['assets']['png']['sha256'] = 'different'
        samples[1]['content_sha256'] = '0'
        with self.assertRaisesRegex(ValueError, 'exact content'):
            duplicate_report(samples)
        samples[1]['content_sha256'] = '1'
        report = duplicate_report(samples)
        self.assertEqual(len(report['ambiguous']), 1)
        self.assertTrue(report['ambiguous'][0]['cross_split'])
        self.assertFalse(report['reviewed'])


class TransformTest(unittest.TestCase):
    def test_crop_partial_field_removes_all_occurrences_and_gold(self):
        # Two occurrences of merchant_name: losing just one must obscure both.
        payload = dict(merchant_name='Hư cấu', total_amount=None, items=[])
        geometry = dict(width=400, height=400, regions=[
            dict(pointer='/merchant_name', text='Hư cấu', page=0, bbox_px=[40, 40, 180, 60]),
            dict(pointer='/merchant_name', text='Hư cấu', page=0, bbox_px=[140, 240, 280, 260])])
        image = Image.new('RGB', (400, 400), 'white')
        draw = ImageDraw.Draw(image)
        for region in geometry['regions']:
            draw.rectangle(region['bbox_px'], fill='black')
        policy = dict(d22.CLEAN, name='crop', crop=[100, 0, 0, 0])
        result, gold, labels, regions, transcript = augment(image, geometry, payload, policy, 1)
        self.assertEqual(result.size, (300, 400))
        self.assertIsNone(gold['merchant_name'])
        self.assertEqual(labels['/merchant_name']['status'], 'obscured')
        self.assertEqual(labels['/total_amount']['status'], 'absent')
        self.assertEqual(regions['regions'], [])
        self.assertEqual(transcript, '')
        self.assertEqual(payload['merchant_name'], 'Hư cấu')
        self.assertEqual(result.getextrema(), ((255, 255), (255, 255), (255, 255)))

    def test_affine_inverse_and_bounds_at_severity_limits(self):
        record = d22.plan(read_json(d22.DEFAULT_CONFIG), 2202)[4]
        gold = d22.payload_for(record, read_json(CONFIG))
        image, geometry = render_family(gold, catalog()[4], FONT)
        for shear in (-.025, .025):
            policy = dict(d22.CLEAN, name='limit', shear=shear, blur=1, noise=18, crop=[0, 0, 0, 0])
            result, transformed, labels, regions, _ = augment(image, geometry, gold, policy, 9)
            again = augment(image, geometry, gold, policy, 9)
            self.assertEqual(result.tobytes(), again[0].tobytes())
            matrix = regions['transform']['source_to_canonical']
            inverse = regions['transform']['canonical_to_source']
            for x, y in ((0, 0), (1500, 2600), (750, 1300)):
                u, v = matrix[0]*x + matrix[1]*y + matrix[2], matrix[3]*x + matrix[4]*y + matrix[5]
                self.assertAlmostEqual(inverse[0]*u + inverse[1]*v + inverse[2], x)
                self.assertAlmostEqual(inverse[3]*u + inverse[4]*v + inverse[5], y)
            for region in regions['regions']:
                x0, y0, x1, y1 = region['bbox_px']
                self.assertTrue(0 <= x0 < x1 <= result.width and 0 <= y0 < y1 <= result.height)
                if region['pointer']:
                    self.assertEqual(labels[region['pointer']]['status'], 'present')
            for pointer, value in leaves(transformed).items():
                if labels[pointer]['status'] == 'obscured':
                    self.assertIsNone(value)


class DatasetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp.name) / 'first'
        cls.manifest = d22.build(ROOT, cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_consumer_and_counts(self):
        samples = list(load_artifacts(ROOT, self.output / 'manifest.json'))
        self.assertEqual(len(samples), 80)
        report = read_json(self.output / 'report.json')
        self.assertEqual(report['counts']['base_documents']['total'], 20)
        self.assertEqual(report['counts']['base_documents']['split'], dict(dev=4, final=4, train=12))
        self.assertEqual(report['counts']['images_including_variants']['quality'],
                         {'bounded': 20, 'clean': 20, 'content-loss': 20, 'unreadable': 20})
        self.assertFalse(report['dev_support']['partition_enabled'])
        self.assertEqual(report['leakage']['exact_image_groups'], [])
        self.assertEqual(sum(c['fields'] for c in report['cross_counts']),
                         sum(report['counts']['images_including_variants']['label_statuses'].values()))
        for sample, gold in samples:
            if sample['quality'] == 'unreadable':
                self.assertTrue(all(v is None for v in leaves(gold).values()))

    def test_reproducibility_all_files_and_strict_verification(self):
        second = Path(self.temp.name) / 'second'
        self.assertEqual(self.manifest, d22.build(ROOT, second))
        self.assertEqual({p.name: sha(p) for p in self.output.iterdir()}, {p.name: sha(p) for p in second.iterdir()})
        self.assertTrue(d22.validate(ROOT, second / 'manifest.json')['valid'])
        with self.assertRaises(FileExistsError):
            d22.build(ROOT, second)
        broken = copy.deepcopy(self.manifest)
        broken['samples'][0]['split'] = 'final'
        path = second / 'manifest.json'
        path.write_bytes(encoded(broken))
        with self.assertRaisesRegex(ValueError, 'metadata/lineage'):
            d22.validate(ROOT, path)


if __name__ == '__main__':
    unittest.main()
