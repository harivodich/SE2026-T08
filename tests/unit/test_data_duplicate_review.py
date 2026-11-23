"""Disposition accounting, binding and evidence regressions (no renderer needed)."""
import copy
from pathlib import Path
import tempfile
import unittest

from vietdoc.data.duplicate_review import VERSION, candidate_id, candidates, validate_review
from vietdoc.data.manifest import encoded, read_json, sha

ROOT = Path(__file__).resolve().parents[2]
MANIFESTS = ROOT / 'datasets/manifests'


class DuplicateReviewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manifest = Path(self.temp.name) / 'd22-smoke-v01.json'
        self.report = Path(self.temp.name) / 'd22-report-v01.json'
        for path in (self.manifest, self.report):
            path.write_bytes((MANIFESTS / path.name).read_bytes())
        self.review = dict(version=VERSION,
                           manifest=dict(name=self.manifest.name, sha256=sha(self.manifest)),
                           report=dict(name=self.report.name, sha256=sha(self.report)),
                           dispositions=[dict(candidate_id=key, base_ids=pair['base_ids'][:],
                                              disposition='pending', reason='Awaiting image/content inspection',
                                              reviewer='test-reviewer',
                                              evidence=dict(image=False, content=False, lineage=True))
                                         for key, pair in candidates(self.manifest, self.report).items()])

    def validate(self, review=None):
        return validate_review(self.review if review is None else review, self.manifest, self.report)

    def test_historical_accounting_pending_does_not_clear_gate(self):
        result = self.validate()
        self.assertEqual(result['candidates'], 81)
        self.assertEqual(result['cross_split'], {'pending': 43})
        self.assertEqual(result['unresolved'], 81)
        self.assertFalse(result['review_complete'])

    def test_order_independent_identity_and_dispositions(self):
        pair = self.review['dispositions'][0]['base_ids']
        self.assertEqual(candidate_id(pair), candidate_id(pair[::-1]))
        self.review['dispositions'].reverse()
        self.review['dispositions'][0]['base_ids'].reverse()
        self.validate()

    def test_bad_accounting_and_attribution(self):
        for case, message in [('missing', 'missing dispositions'), ('duplicate', 'duplicate disposition'),
                              ('unknown', 'unknown candidate'), ('pair', 'base IDs mismatch'),
                              ('reason', 'missing reason'), ('reviewer', 'missing reviewer'),
                              ('disposition', 'unknown disposition'), ('evidence', 'invalid review evidence'),
                              ('version', 'unsupported review version'), ('extra', 'review keys')]:
            with self.subTest(case=case):
                review = copy.deepcopy(self.review)
                first = review['dispositions'][0]
                if case == 'missing': review['dispositions'].pop()
                elif case == 'duplicate': review['dispositions'].append(copy.deepcopy(first))
                elif case == 'unknown': first['candidate_id'] = 'pair-unknown'
                elif case == 'pair': first['base_ids'][0] = 'other-base'
                elif case in ('reason', 'reviewer'): first[case] = ' '
                elif case == 'disposition': first[case] = 'dhash-close'
                elif case == 'evidence': first[case]['image'] = 1
                elif case == 'version': review[case] = True
                elif case == 'extra': review['reviewed'] = True
                with self.assertRaisesRegex(ValueError, message): self.validate(review)

    def test_nonpending_requires_all_review_modes(self):
        for disposition in ('distinct', 'duplicate', 'ambiguous'):
            self.review['dispositions'][0]['disposition'] = disposition
            with self.assertRaisesRegex(ValueError, 'requires image/content/lineage'):
                self.validate()
        self.review['dispositions'][0]['evidence'] = dict(image=True, content=True, lineage=True)
        self.assertEqual(self.validate()['dispositions']['ambiguous'], 1)

    def test_completed_review_is_not_split_approval(self):
        for entry in self.review['dispositions']:
            entry.update(disposition='distinct', evidence=dict(image=True, content=True, lineage=True))
        result = self.validate()
        self.assertTrue(result['review_complete'])
        self.assertIn('Lead', result['approval'])

    def test_manifest_and_report_bytes_drift_even_for_whitespace(self):
        for path, message in [(self.manifest, 'manifest reference/hash drift'),
                              (self.report, 'report reference/hash drift')]:
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(original + b'\n')
                with self.assertRaisesRegex(ValueError, message): self.validate()
                path.write_bytes(original)

    def test_rebinding_cannot_hide_report_or_screening_drift(self):
        report = read_json(self.report)
        report['leakage']['ambiguous'].pop()
        self.report.write_bytes(encoded(report))
        with self.assertRaisesRegex(ValueError, 'report hash drift'):
            candidates(self.manifest, self.report)
        manifest = read_json(self.manifest)
        manifest['report']['sha256'] = sha(self.report)
        self.manifest.write_bytes(encoded(manifest))
        with self.assertRaisesRegex(ValueError, 'candidate report drift'):
            candidates(self.manifest, self.report)

    def test_validation_never_mutates_files_or_review(self):
        before = copy.deepcopy(self.review)
        hashes = (sha(self.manifest), sha(self.report))
        self.validate()
        self.assertEqual(self.review, before)
        self.assertEqual(hashes, (sha(self.manifest), sha(self.report)))


if __name__ == '__main__':
    unittest.main()
