"""Exposure identity/hash/lineage isolation; all holdout candidates are fictional metadata."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from vietdoc.data import exposure
from vietdoc.data.manifest import encoded, read_json

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'tests/fixtures/d12/manifest.json'


class ExposureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = exposure.record(ROOT, FIXTURE, 'tests/fixtures/d12: exposed integration fixture')

    def candidate(self):
        # This is deliberately metadata only, with no claim of existing assets.
        return dict(sample_id='new-sample', base_id='new-base', family_id='new-family',
                    source_group='new-source', assignment_group='new-assignment',
                    content_sha256='a'*64, source_gold_sha256='b'*64,
                    assets={'png': {'sha256': 'c'*64}, 'gold.json': {'sha256': 'd'*64}})

    def test_real_fixture_capture_and_unknown_legacy_lineage_stays_null(self):
        self.assertEqual(len(self.ledger['entries']), 2)
        self.assertEqual(self.ledger['version'], exposure.VERSION)
        for entry in self.ledger['entries']:
            self.assertIsNone(entry['source_group'])
            self.assertIsNone(entry['assignment_group'])
        before = deepcopy(self.ledger)
        result = exposure.check([self.ledger], [self.candidate()])
        self.assertEqual(result['status'], 'no_known_exposure_overlap')
        self.assertEqual(self.ledger, before)

    def test_renaming_ids_cannot_hide_image_gold_or_known_lineage_overlap(self):
        known = deepcopy(self.ledger)
        known['entries'][0].update(source_group='exposed-source', assignment_group='exposed-assignment',
                                   content_sha256='e'*64, source_gold_sha256='f'*64)
        entry = known['entries'][0]
        for key in exposure.IDENTITIES + exposure.HASHES:
            with self.subTest(key=key):
                sample = self.candidate()
                if key in ('png_sha256', 'gold_sha256'):
                    sample['assets']['png' if key == 'png_sha256' else 'gold.json']['sha256'] = entry[key]
                else:
                    sample[key] = entry[key]
                with self.assertRaisesRegex(ValueError, 'exposed candidate metadata'):
                    exposure.check([known], [sample])

    def test_bad_versions_empty_inventory_duplicate_ids_and_hashes_rejected(self):
        bad = deepcopy(self.ledger)
        bad['version'] = 'other'
        with self.assertRaisesRegex(ValueError, 'unsupported exposure ledger'):
            exposure.check([bad], [self.candidate()])
        for samples, message in [([], 'nonempty candidate'), ([self.candidate()]*2, 'duplicate candidate')]:
            with self.assertRaisesRegex(ValueError, message):
                exposure.check([self.ledger], samples)
        bad = deepcopy(self.ledger)
        bad['entries'].append(deepcopy(bad['entries'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate sample ID'):
            exposure.check([bad], [self.candidate()])
        sample = self.candidate()
        sample['assets']['png']['sha256'] = 'not-a-hash'
        with self.assertRaisesRegex(ValueError, 'invalid exposure hash'):
            exposure.check([self.ledger], [sample])

    def test_normal_optimized_cli_rejects_exposed_without_output_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ledger = base / 'ledger.json'
            ledger.write_bytes(encoded(self.ledger))
            for optimized in (False, True):
                output = base / str(optimized) / 'preflight.json'
                run = subprocess.run([sys.executable, *(['-O'] if optimized else []), '-m',
                    'vietdoc.data.exposure', 'check', '--ledger', str(ledger), '--manifest', str(FIXTURE),
                    '--output', str(output)], capture_output=True)
                self.assertNotEqual(run.returncode, 0)
                self.assertIn(b'exposed candidate metadata', run.stderr)
                self.assertFalse(output.parent.exists())
            output = base / 'existing.json'
            output.write_bytes(b'keep')
            with self.assertRaisesRegex(ValueError, 'output already exists'):
                exposure.publish(output, {})
            self.assertEqual(output.read_bytes(), b'keep')


if __name__ == '__main__':
    unittest.main()
