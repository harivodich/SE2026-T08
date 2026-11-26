"""Real disposable Git repos: squash recovery, unchanged tree and no overwrites."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.preserve_pr_history import ancestor, git, inventory, prepare


class PreserveHistoryTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='history-test-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.env = patch.dict(os.environ, {'GIT_CONFIG_COUNT': '0', 'GIT_AUTHOR_NAME': 'Fictional Test',
            'GIT_AUTHOR_EMAIL': 'test@example.invalid', 'GIT_COMMITTER_NAME': 'Fictional Test',
            'GIT_COMMITTER_EMAIL': 'test@example.invalid'})
        self.env.start()
        self.addCleanup(self.env.stop)
        git(self.root, 'init', '--initial-branch=main')
        (self.root / 'app.txt').write_text('base')
        git(self.root, 'add', 'app.txt')
        git(self.root, 'commit', '-m', 'base')
        self.main = git(self.root, 'rev-parse', 'HEAD')
        git(self.root, 'switch', '-c', 'feature/accepted')
        (self.root / 'app.txt').write_text('accepted feature')
        git(self.root, 'commit', '-am', 'feature increment')
        self.head = git(self.root, 'rev-parse', 'HEAD')
        git(self.root, 'switch', '-c', 'develop', self.main)
        git(self.root, 'merge', '--squash', 'feature/accepted')
        git(self.root, 'commit', '-m', 'accepted squash')
        self.base = git(self.root, 'rev-parse', 'HEAD')
        self.prs = [dict(number=1, state='MERGED', headRefOid=self.head,
                         mergeCommit={'oid': self.base}, baseRefName='develop')]

    def test_real_squashed_commit_recovered_with_original_sha_and_tree_unchanged(self):
        before = git(self.root, 'status', '--porcelain=v1')
        self.assertFalse(ancestor(self.root, self.head, self.base))
        report = inventory(self.root, self.prs, self.base, self.main)
        result = prepare(self.root, report, 'release/preserved')
        self.assertTrue(ancestor(self.root, self.head, result['tip']))
        self.assertEqual(git(self.root, 'rev-parse', result['tip'] + '^{tree}'), report['tree'])
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), self.base)
        self.assertEqual(git(self.root, 'status', '--porcelain=v1'), before)
        self.assertEqual(result['commit_count'], report['base_commit_count'] + 2)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            prepare(self.root, report, 'release/preserved')

    def test_open_or_unmerged_pr_never_becomes_ancestry_and_invalid_metadata_fails(self):
        closed = dict(self.prs[0], number=2, state='CLOSED', headRefOid='a' * 40)
        report = inventory(self.root, [*self.prs, closed], self.base, self.main)
        self.assertEqual([p['number'] for p in report['merged_prs']], [1])
        with self.assertRaisesRegex(ValueError, 'missing or unmerged'):
            inventory(self.root, [*self.prs, closed], self.base, self.main, [2])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            inventory(self.root, self.prs * 2, self.base, self.main)
        with self.assertRaisesRegex(ValueError, 'new release/'):
            prepare(self.root, report, 'main')

    def test_unrelated_feature_merge_rejected_instead_of_silently_accepted(self):
        pr = dict(self.prs[0], baseRefName='feature/unreceived', mergeCommit={'oid': self.head})
        report = inventory(self.root, [pr], self.base, self.main)
        self.assertEqual(report['unresolved'], [1])
        with self.assertRaisesRegex(ValueError, 'Unproven integration'):
            prepare(self.root, report, 'release/bad')


if __name__ == '__main__':
    unittest.main()
