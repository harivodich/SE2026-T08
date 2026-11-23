"""Pinned queue coverage, priority and validation publication boundary."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vietdoc.data import review_batches
from vietdoc.data.manifest import read_json, encoded

ROOT = Path(__file__).resolve().parents[2]
MANIFESTS = ROOT / 'datasets/manifests'
MANIFEST = MANIFESTS / 'd22-smoke-v01.json'
REPORT = MANIFESTS / 'd22-report-v01.json'
REVIEW = MANIFESTS / 'd22-duplicate-review-20261122-batch01.json'


class ReviewBatchesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.asset_manifest = self.base / 'manifest.json'
        self.asset_manifest.write_bytes(MANIFEST.read_bytes())
        # Queue tests isolate sorting/coverage, not renderer certification. The
        # real exporter has its own tests and is exercised in the actual replay.
        self.packet = dict(manifest=dict(sha256=review_batches.sha(MANIFEST)), counts=dict(samples=80),
                           records=[dict(sample=s, gold=dict(items=[{}] * s['row_count']),
                                         labels=dict(fields=[])) for s in read_json(MANIFEST)['samples']])

    def prepare(self, **kwargs):
        return review_batches.prepare(ROOT, MANIFEST, REPORT, REVIEW, self.asset_manifest, **kwargs)

    def test_queue_covers_every_unresolved_pair_once_cross_split_first(self):
        before = deepcopy(self.packet)
        with patch.object(review_batches, 'training_packet', return_value=self.packet):
            result = self.prepare()
        self.assertEqual(result['queued_pairs'], 71)
        self.assertEqual(result['queued_by_split'], dict(cross=33, same=38))
        self.assertEqual([b['cross_split'] for b in result['batches']], [True]*4 + [False]*4)
        self.assertEqual([len(b['pairs']) for b in result['batches']], [10, 10, 10, 3, 10, 10, 10, 8])
        pairs = [p for b in result['batches'] for p in b['pairs']]
        expected = {e['candidate_id'] for e in read_json(REVIEW)['dispositions'] if e['disposition'] == 'pending'}
        self.assertEqual({p['candidate_id'] for p in pairs}, expected)
        self.assertEqual(len(pairs), len(expected))
        self.assertTrue(all(p['inspection']['verdict'] is None and not p['inspection']['image'] for p in pairs))
        self.assertEqual(len(result['sample_catalog']), 20)
        self.assertEqual(self.packet, before)

    def test_bad_size_or_asset_manifest_drift_rejected_before_loader(self):
        with patch.object(review_batches, 'training_packet') as loader:
            for size in (0, 21, True):
                with self.assertRaisesRegex(ValueError, 'batch size'):
                    self.prepare(batch_size=size)
            self.asset_manifest.write_bytes(MANIFEST.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'asset manifest differs'):
                self.prepare()
            loader.assert_not_called()

    def test_invalid_assets_or_input_drift_publish_nothing(self):
        output = self.base / 'new/batches.json'
        with patch.object(review_batches, 'training_packet', side_effect=ValueError('hash mismatch')):
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                review_batches.export(ROOT, MANIFEST, REPORT, REVIEW, self.asset_manifest, output)
        self.assertFalse(output.parent.exists())
        def changing(*args):
            self.asset_manifest.write_bytes(MANIFEST.read_bytes() + b'\n')
            return self.packet
        with patch.object(review_batches, 'training_packet', side_effect=changing):
            with self.assertRaisesRegex(ValueError, 'batch inputs changed'):
                self.prepare()

    def test_existing_output_preserved_without_validation(self):
        output = self.base / 'batches.json'
        output.write_bytes(b'keep')
        with patch.object(review_batches, 'prepare') as prepare:
            with self.assertRaisesRegex(ValueError, 'output already exists'):
                review_batches.export(ROOT, MANIFEST, REPORT, REVIEW, self.asset_manifest, output)
        prepare.assert_not_called()
        self.assertEqual(output.read_bytes(), b'keep')


if __name__ == '__main__':
    unittest.main()
