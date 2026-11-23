"""Transitive quarantine, group invariants and real hash-bound snapshot planning."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from vietdoc.data import pilot
from vietdoc.data.duplicate_review import candidate_id
from vietdoc.data.manifest import encoded, read_json, sha
from vietdoc.data.splits import digest
from vietdoc.data import splits

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'datasets/manifests/d22-smoke-v01.json'
REPORT = ROOT / 'datasets/manifests/d22-report-v01.json'
REVIEW = ROOT / 'datasets/manifests/d22-duplicate-review-20261122-batch01.json'


def sample(base, split='train', kind='receipt', *, family=None, source=None, variant='clean',
           png=None, content=None):
    return dict(sample_id=base + '-' + variant, base_id=base, family_id=family or 'family-' + base,
                source_group=source or 'source-' + base, assignment_group=digest(base),
                document_type=kind, split=split, quality=variant,
                assets=dict(png=dict(sha256=png or digest(['png', base, variant]))),
                content_sha256=content or digest(['content', base]))


def pair(left, right, disposition='pending'):
    return dict(candidate_id=candidate_id([left, right]), base_ids=[left, right], disposition=disposition)


class PilotComponentsTest(unittest.TestCase):
    def test_unresolved_chain_excludes_entire_family_and_all_variants(self):
        samples = [sample('a', family='f'), sample('sibling', family='f'),
                   sample('a', variant='mild', family='f'), sample('b', 'dev'), sample('c', 'dev')]
        result = pilot._plan(samples, [pair('a', 'b'), pair('b', 'c', 'ambiguous')])
        self.assertEqual(len(result['risk_components']), 1)
        self.assertEqual(result['risk_components'][0]['base_ids'], ['a', 'b', 'c', 'sibling'])
        self.assertEqual(len(result['excluded']), 5)
        self.assertEqual(result['counts']['after']['samples_including_variants'], 0)
        self.assertTrue(all('unresolved_component' in e['reasons'] for e in result['excluded']))

    def test_confirmed_duplicate_and_source_alias_transitivity_preserve_conflicts(self):
        samples = [sample('a'), sample('b', source='alias'), sample('c', 'dev', source='alias')]
        result = pilot._plan(samples, [pair('a', 'b', 'duplicate')])
        self.assertEqual(len(result['confirmed_groups']), 1)
        self.assertEqual(result['confirmed_groups'][0]['base_ids'], ['a', 'b', 'c'])
        self.assertEqual(result['members'], dict(train=[], dev=[]))
        self.assertTrue(all('confirmed_group_cross_split' in x['reasons'] for x in result['excluded']))
        self.assertEqual({e['relation'] for e in result['union_reasons']}, {'source_group', 'review_duplicate'})

    def test_exact_image_and_content_are_separate_relations_not_equal_total(self):
        samples = [sample('a', png='x'), sample('b', png='x'),
                   sample('c', content='y'), sample('d', content='y'), sample('other')]
        for s in samples:
            s['total_amount'] = '1000'  # equal scalar is deliberately not a grouping relation
        result = pilot._plan(samples, [])
        groups = [g['base_ids'] for g in result['confirmed_groups']]
        self.assertEqual(groups, [['a', 'b'], ['c', 'd'], ['other']])
        self.assertEqual({r['relation'] for r in result['union_reasons']}, {'exact_png', 'exact_clean_content'})

    def test_nonempty_both_type_split_support_still_is_not_approval(self):
        samples = [sample('rt'), sample('rd', 'dev'), sample('it', kind='invoice'),
                   sample('id', 'dev', kind='invoice'), sample('old', 'final')]
        before = deepcopy(samples)
        result = pilot._plan(samples, [pair('rt', 'rd', 'distinct')])
        self.assertEqual(result['status'], 'prepared_not_approved')
        self.assertEqual(result['missing_type_split_support'], [])
        self.assertEqual(result['counts']['before']['base_documents'], 5)
        self.assertEqual(result['counts']['after']['base_documents'], 4)
        self.assertEqual(result['excluded'][0]['sample_id'], 'old-clean')
        self.assertEqual(result['excluded'][0]['reasons'], ['historical_final_not_train_dev'])
        self.assertEqual(samples, before)

    def test_variant_split_conflict_excludes_every_variant_without_resplit(self):
        samples = [sample('a'), sample('a', 'dev', variant='mild')]
        result = pilot._plan(samples, [])
        self.assertEqual(len(result['excluded']), 2)
        self.assertEqual(result['confirmed_groups'][0]['source_splits'], ['dev', 'train'])
        self.assertEqual(result['counts']['before']['base_documents'], 1)
        self.assertEqual(result['counts']['before']['bases_by_type_split']['receipt'],
                         dict(train=1, dev=1, final=0))
        self.assertEqual(result, pilot._plan(samples[::-1], []))
        self.assertEqual([s['split'] for s in samples], ['train', 'dev'])

    def test_ids_and_results_are_deterministic_under_permutation(self):
        samples = [sample('a'), sample('b', 'dev'), sample('c', source='s'), sample('d', source='s')]
        entries = [pair('a', 'b'), pair('b', 'c')]
        expected = pilot._plan(samples, entries)
        entries = [dict(e, base_ids=e['base_ids'][::-1]) for e in entries[::-1]]
        self.assertEqual(expected, pilot._plan(samples[::-1], entries))

    def test_bad_identity_or_type_is_rejected(self):
        for samples, message in [([], 'nonempty'), ([sample('a'), sample('a')], 'duplicate sample'),
                                 ([sample('a'), sample('a', 'dev', kind='invoice', variant='mild')], 'mixed document'),
                                 ([sample('a', 'test')], 'invalid type/split')]:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                pilot._plan(samples, [])


class PilotFileBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = []
        for path in (MANIFEST, REPORT, REVIEW):
            target = self.root / path.name
            target.write_bytes(path.read_bytes())
            self.paths.append(target)

    def rebind_invalid_clean_inventory(self, case):
        manifest = read_json(MANIFEST)
        base = manifest['samples'][0]['base_id']
        if case == 'missing_all':
            manifest['samples'] = [s for s in manifest['samples'] if s['quality'] != 'clean']
        elif case == 'missing_one':
            manifest['samples'] = [s for s in manifest['samples']
                                   if not (s['base_id'] == base and s['quality'] == 'clean')]
        else:
            clean = deepcopy(next(s for s in manifest['samples'] if s['base_id'] == base and s['quality'] == 'clean'))
            clean['sample_id'] += '-alias'
            manifest['samples'].append(clean)
        report = read_json(REPORT)
        # Bind the exact legacy screening output, not stale hashes. This setup
        # reproduces the fail-open input independently of the new guard.
        with patch.object(splits, 'require_clean_representatives'):
            report['leakage'] = splits.duplicate_report(manifest['samples'])
        self.paths[1].write_bytes(encoded(report))
        manifest['report']['sha256'] = sha(self.paths[1])
        self.paths[0].write_bytes(encoded(manifest))
        review = read_json(REVIEW)
        old = {e['candidate_id']: e for e in review['dispositions']}
        review['dispositions'] = [old[candidate_id(p['base_ids'])]
                                  for p in report['leakage']['ambiguous']]
        for key, path in zip(('manifest', 'report'), self.paths):
            review[key] = dict(name=path.name, sha256=sha(path))
        self.paths[2].write_bytes(encoded(review))

    def test_rebound_missing_and_duplicate_clean_rejected_before_planning_or_output(self):
        for case in ('missing_one', 'missing_all', 'duplicate'):
            with self.subTest(case=case):
                self.rebind_invalid_clean_inventory(case)
                expected = 'requires exactly one clean representative; found ' + ('2' if case == 'duplicate' else '0')
                with self.assertRaisesRegex(ValueError, expected):
                    pilot.plan_files(*self.paths)
                for optimized in (False, True):
                    output = self.root / case / f'{optimized}.json'
                    command = [sys.executable, *(['-O'] if optimized else []), '-m', 'vietdoc.data.pilot']
                    for key, path in zip(('manifest', 'report', 'review'), self.paths):
                        command += ['--' + key, str(path)]
                    run = subprocess.run([*command, '--output', str(output)], capture_output=True)
                    self.assertNotEqual(run.returncode, 0)
                    self.assertIn(expected.encode(), run.stderr)
                    self.assertFalse(output.parent.exists())

    def test_valid_metadata_subset_keeps_clean_and_variants(self):
        samples = read_json(MANIFEST)['samples']
        base = samples[0]['base_id']
        subset = [s for s in samples if s['base_id'] == base]
        result = splits.duplicate_report(subset)
        self.assertEqual(result['ambiguous'], [])
        self.assertEqual(len(subset), 4)

    def test_actual_snapshot_quarantines_all_twenty_bases_in_two_components(self):
        original = [sha(p) for p in self.paths]
        result = pilot.plan_files(*self.paths)
        self.assertEqual(result['status'], 'blocked_membership')
        self.assertEqual(result['unresolved_candidates'], 71)
        self.assertEqual(sorted(len(c['base_ids']) for c in result['risk_components']), [4, 16])
        self.assertEqual(result['counts']['before']['base_documents'], 20)
        self.assertEqual(result['counts']['before']['samples_including_variants'], 80)
        self.assertEqual(result['counts']['after']['base_documents'], 0)
        self.assertEqual(len(result['excluded']), 80)
        self.assertEqual(result['members'], dict(train=[], dev=[]))
        self.assertEqual(result['review']['dispositions'], dict(pending=71, distinct=10))
        self.assertEqual(original, [sha(p) for p in self.paths])

    def test_missing_disposition_cannot_remove_an_unresolved_edge(self):
        review = read_json(self.paths[2])
        review['dispositions'].pop()
        self.paths[2].write_bytes(encoded(review))
        with self.assertRaisesRegex(ValueError, 'missing dispositions'):
            pilot.plan_files(*self.paths)

    def test_drift_and_frozen_snapshot_rejected(self):
        manifest = read_json(self.paths[0])
        manifest['final_frozen'] = True
        self.paths[0].write_bytes(encoded(manifest))
        with self.assertRaisesRegex(ValueError, 'non-frozen'):
            pilot.plan_files(*self.paths)
        self.paths[0].write_bytes(MANIFEST.read_bytes())
        original = pilot.validate_review

        def changing(*args):
            result = original(*args)
            self.paths[2].write_bytes(self.paths[2].read_bytes() + b'\n')
            return result

        with patch.object(pilot, 'validate_review', side_effect=changing):
            with self.assertRaisesRegex(ValueError, 'inputs changed'):
                pilot.plan_files(*self.paths)

    def test_normal_optimized_cli_and_no_overwrite(self):
        for optimized in (False, True):
            output = self.root / f'{optimized}.json'
            command = [sys.executable, *(['-O'] if optimized else []), '-m', 'vietdoc.data.pilot']
            for key, path in zip(('manifest', 'report', 'review'), self.paths):
                command += ['--' + key, str(path)]
            command += ['--output', str(output)]
            run = subprocess.run(command, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr.decode())
            self.assertEqual(read_json(output)['status'], 'blocked_membership')
            before = output.read_bytes()
            run = subprocess.run(command, capture_output=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn(b'output already exists', run.stderr)
            self.assertEqual(before, output.read_bytes())


if __name__ == '__main__':
    unittest.main()
