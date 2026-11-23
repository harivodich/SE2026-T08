"""Real bounded renderer selection, provenance, negatives and publication safety."""
from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from vietdoc.data import pilot_records, pilot
from vietdoc.data.adapters.labels import field_labels
from vietdoc.data.duplicate_review import VERSION, candidate_id
from vietdoc.data.generator import d22, integration
from vietdoc.data.manifest import encoded, read_json, sha

ROOT = Path(__file__).resolve().parents[2]


class PilotRecordsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.template = Path(cls.tmp.name)
        font = integration.resolve_font()
        config = dict(read_json(d22.DEFAULT_CONFIG), rows=[1], font_sha256=sha(font))
        config['augmentations'] = config['augmentations'][:1]
        # Four type/split cells plus an exposed historical final, for boundary
        # tests only. Test dispositions never establish real pilot acceptance.
        planned = [r for r in d22.plan(config, 2202) if r['family_id'] in
                   {'receipt-f00', 'receipt-f06', 'invoice-f00', 'invoice-f06', 'receipt-f08'}]
        entries = []
        with patch.object(d22, 'plan', return_value=planned):
            for entry, files in d22.generated(ROOT, config, 2202, font):
                entries.append(entry)
                for suffix, content in files.items():
                    (cls.template / entry['assets'][suffix]['path']).write_bytes(content)
        report = d22.report_for(entries, config)
        (cls.template / 'report.json').write_bytes(encoded(report))
        manifest = dict(d22.provenance(ROOT, config, 2202, font), samples=entries,
                        report=dict(path='report.json', sha256=sha(cls.template / 'report.json')))
        (cls.template / 'manifest.json').write_bytes(encoded(manifest))
        review = dict(version=VERSION,
                      manifest=dict(name='manifest.json', sha256=sha(cls.template / 'manifest.json')),
                      report=dict(name='report.json', sha256=sha(cls.template / 'report.json')),
                      dispositions=[dict(candidate_id=candidate_id(p['base_ids']), base_ids=p['base_ids'],
                          disposition='distinct', reason='Fictional test disposition; no actual acceptance',
                          reviewer='unit-test fixture', evidence=dict(image=True, content=True, lineage=True))
                          for p in report['leakage']['ambiguous']])
        (cls.template / 'review.json').write_bytes(encoded(review))
        (cls.template / 'plan.json').write_bytes(encoded(pilot.plan_files(
            cls.template / 'manifest.json', cls.template / 'report.json', cls.template / 'review.json')))

    def setUp(self):
        self.tmp_case = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_case.cleanup)
        self.base = Path(self.tmp_case.name)
        self.source = self.base / 'source'
        shutil.copytree(self.template, self.source)
        self.paths = [self.source / name for name in ('manifest.json', 'report.json', 'review.json', 'plan.json')]
        self.output = self.base / 'new/records.json'

    def export(self):
        return pilot_records.export(ROOT, *self.paths, self.paths[0], self.output)

    def test_selected_records_preserve_all_variants_gold_statuses_and_source_manifest(self):
        before = [sha(p) for p in self.paths]
        result = self.export()
        self.assertEqual(result, read_json(self.output))
        self.assertEqual(result['status'], 'prepared_not_approved')
        packet = result['training_records']
        self.assertEqual(packet['artifact_version'], 'vietdoc.training-records.v1')
        self.assertEqual(packet['counts']['samples'], 8)
        self.assertEqual(packet['counts']['document_types'], dict(receipt=4, invoice=4))
        self.assertEqual(result['selection']['counts']['base_documents'], 4)
        selected = {sid for members in result['selection']['members'].values() for sid in members}
        self.assertEqual(selected, {r['sample']['sample_id'] for r in packet['records']})
        for record in packet['records']:
            sample = record['sample']
            self.assertIn(sample['split'], ('train', 'dev'))
            self.assertEqual(record['gold'], read_json(self.source / sample['assets']['gold.json']['path']))
            labels = field_labels(record['gold'], read_json(self.source / sample['assets']['labels.json']['path']))
            self.assertEqual(record['labels']['fields'], [dict(pointer=f.pointer, value=f.value, status=f.status)
                                                        for f in labels.fields])
        self.assertEqual(before, [sha(p) for p in self.paths])
        self.assertNotIn(str(ROOT), self.output.read_text(encoding='utf-8'))

    def test_tampered_missing_unknown_duplicate_or_cross_split_members_rejected(self):
        original = read_json(self.paths[3])
        for case in ('missing', 'unknown', 'duplicate', 'cross_split'):
            with self.subTest(case=case):
                plan = deepcopy(original)
                members = plan['members']['train']
                if case == 'missing': members.pop()
                elif case == 'unknown': members.append('unknown-alias')
                elif case == 'duplicate': members.append(members[0])
                else: plan['members']['dev'].append(members.pop())
                self.paths[3].write_bytes(encoded(plan))
                with self.assertRaisesRegex(ValueError, 'pilot plan drift'):
                    self.export()
                self.assertFalse(self.output.parent.exists())

    def test_invalid_excluded_source_member_still_blocks_publication(self):
        # Final is not exported, but whole-source validation must not be skipped.
        final = next(s for s in read_json(self.paths[0])['samples'] if s['split'] == 'final')
        path = self.source / final['assets']['gold.json']['path']
        path.write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            self.export()
        self.assertFalse(self.output.parent.exists())

    def test_rebound_source_cannot_hide_asset_escape_or_aliased_sample_id(self):
        from vietdoc.data.splits import duplicate_report
        for case in ('path_escape', 'aliased_id'):
            with self.subTest(case=case):
                source = self.base / case
                shutil.copytree(self.template, source)
                manifest_path, report_path, review_path, plan_path = [source / name for name in
                    ('manifest.json', 'report.json', 'review.json', 'plan.json')]
                manifest, report, review = [read_json(p) for p in (manifest_path, report_path, review_path)]
                sample = manifest['samples'][0]
                if case == 'path_escape':
                    original = source / sample['assets']['png']['path']
                    (self.base / 'escape.png').write_bytes(original.read_bytes())
                    sample['assets']['png']['path'] = '../escape.png'
                    expected = 'invalid relative path'
                else:
                    sample['sample_id'] += '-alias'
                    expected = 'D2 variant lineage mismatch'
                report['leakage'] = duplicate_report(manifest['samples'])
                report_path.write_bytes(encoded(report))
                manifest['report']['sha256'] = sha(report_path)
                manifest_path.write_bytes(encoded(manifest))
                review['manifest']['sha256'] = sha(manifest_path)
                review['report']['sha256'] = sha(report_path)
                review_path.write_bytes(encoded(review))
                plan_path.write_bytes(encoded(pilot.plan_files(manifest_path, report_path, review_path)))
                with self.assertRaisesRegex(ValueError, expected):
                    pilot_records.export(ROOT, manifest_path, report_path, review_path, plan_path,
                                         manifest_path, self.output)
                self.assertFalse(self.output.parent.exists())

    def test_asset_manifest_or_plan_drift_and_no_overwrite(self):
        other = self.source / 'other.json'
        other.write_bytes(self.paths[0].read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'asset manifest differs'):
            pilot_records.export(ROOT, *self.paths, other, self.output)
        self.assertFalse(self.output.parent.exists())
        original = pilot_records.training_packet
        def changing(*args):
            result = original(*args)
            self.paths[3].write_bytes(self.paths[3].read_bytes() + b'\n')
            return result
        with patch.object(pilot_records, 'training_packet', side_effect=changing):
            with self.assertRaisesRegex(ValueError, 'selection inputs changed'):
                self.export()
        self.assertFalse(self.output.parent.exists())
        self.output.parent.mkdir()
        self.output.write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'output already exists'):
            self.export()
        self.assertEqual(self.output.read_bytes(), b'keep')

    def test_normal_optimized_cli_and_real_zero_support_snapshot(self):
        for optimized in (False, True):
            command = [sys.executable, *(['-O'] if optimized else []), '-m', 'vietdoc.data.pilot_records', '--root', str(ROOT)]
            for key, path in zip(('manifest', 'report', 'review', 'plan'), self.paths):
                command += ['--' + key, str(path)]
            output = self.base / f'{optimized}.json'
            run = subprocess.run([*command, '--asset-manifest', str(self.paths[0]), '--output', str(output)], capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr.decode())
            self.assertEqual(read_json(output)['training_records']['counts']['samples'], 8)
            manifests = ROOT / 'datasets/manifests'
            command = [sys.executable, *(['-O'] if optimized else []), '-m', 'vietdoc.data.pilot_records', '--root', str(ROOT)]
            for key, name in [('manifest', 'd22-smoke-v01.json'), ('report', 'd22-report-v01.json'),
                              ('review', 'd22-duplicate-review-20261122-batch01.json'), ('plan', 'd22-pilot-plan-20261122.json')]:
                command += ['--' + key, str(manifests / name)]
            run = subprocess.run([*command, '--asset-manifest', str(manifests / 'd22-smoke-v01.json'),
                                  '--output', str(self.output)], capture_output=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn(b'no complete receipt/invoice train/dev support', run.stderr)
            self.assertFalse(self.output.parent.exists())


if __name__ == '__main__':
    unittest.main()
