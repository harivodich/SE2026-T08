"""Regression checks for false-green gates and trusted release target selection."""

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.ci import checks
from scripts.ci.gate import APPLICATION_CHECKS, CORE_CHECKS, evaluate, target_branch


def results(*names):
    return {name: {'result': 'success'} for name in names}


class CiGateTest(unittest.TestCase):
    def setUp(self):
        self.develop = results(*CORE_CHECKS)
        self.develop['release-readiness'] = {'result': 'skipped'}

    def test_increment_success_requires_all_core_jobs(self):
        self.assertEqual(evaluate('ci', 'develop', self.develop), [])
        for name in CORE_CHECKS:
            broken = copy.deepcopy(self.develop)
            del broken[name]
            self.assertTrue(evaluate('ci', 'develop', broken), name)

    def test_failure_cancel_skip_unknown_and_empty_never_pass(self):
        for name in CORE_CHECKS:
            for status in ('failure', 'cancelled', 'skipped', 'neutral', '', None):
                with self.subTest(name=name, status=status):
                    broken = copy.deepcopy(self.develop)
                    broken[name] = {'result': status}
                    self.assertTrue(evaluate('ci', 'develop', broken))
        self.assertTrue(evaluate('ci', 'develop', {}))

    def test_main_requires_successful_release_gate(self):
        self.assertTrue(evaluate('ci', 'main', self.develop))
        ready = dict(self.develop, **{'release-readiness': {'result': 'success'}})
        self.assertEqual(evaluate('ci', 'main', ready), [])
        for status in ('failure', 'cancelled', 'skipped'):
            ready['release-readiness']['result'] = status
            self.assertTrue(evaluate('ci', 'main', ready))

    def test_current_data_only_increment_is_not_release_ready(self):
        failures = evaluate('release', 'main', self.develop)
        for name in APPLICATION_CHECKS:
            self.assertIn(f'{name}: missing', failures)

    def test_all_application_checks_required_not_only_file_presence(self):
        ready = results(*(CORE_CHECKS + APPLICATION_CHECKS))
        self.assertEqual(evaluate('release', 'main', ready), [])
        for name in APPLICATION_CHECKS:
            for status in ('failure', 'cancelled', 'skipped'):
                broken = copy.deepcopy(ready)
                broken[name]['result'] = status
                self.assertTrue(evaluate('release', 'main', broken))
        self.assertTrue(evaluate('release', 'develop', ready))

    def test_develop_skip_must_be_explicit(self):
        del self.develop['release-readiness']
        self.assertTrue(evaluate('ci', 'develop', self.develop))

    def test_pr_base_is_authority_even_if_head_is_named_main(self):
        event = {'pull_request': {'base': {'ref': 'develop'}, 'head': {'ref': 'main'}}}
        self.assertEqual(target_branch('pull_request', 'refs/pull/17/merge', event), 'develop')
        event['pull_request']['base']['ref'] = 'main'
        self.assertEqual(target_branch('pull_request', 'refs/pull/17/merge', event), 'main')

    def test_push_and_dispatch_ignore_untrusted_input_branch(self):
        for event in ('push', 'workflow_dispatch'):
            payload = {'inputs': {'branch': 'develop'}}
            self.assertEqual(target_branch(event, 'refs/heads/main', payload), 'main')
            self.assertEqual(target_branch(event, 'refs/heads/develop', payload), 'develop')

    def test_unknown_events_tags_and_branches_fail_closed(self):
        for event, ref, payload in (
            ('pull_request_target', 'refs/heads/main', {}),
            ('workflow_run', 'refs/heads/main', {}),
            ('push', 'refs/tags/RELEASE_VietDoc_1.0.0', {}),
            ('workflow_dispatch', 'refs/heads/feature/main', {}),
            ('pull_request', 'refs/pull/1/merge', {}),
        ):
            with self.subTest(event=event, ref=ref):
                with self.assertRaises(ValueError):
                    target_branch(event, ref, payload)

    def test_empty_test_discovery_cannot_report_success(self):
        with patch.object(unittest.defaultTestLoader, 'discover', return_value=unittest.TestSuite()):
            with self.assertRaisesRegex(ValueError, 'No tests discovered'):
                checks.run_tests('data')

    def test_missing_mandatory_suite_file_fails_before_running(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'tests/unit').mkdir(parents=True)
            with patch.object(checks, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'Missing mandatory test files'):
                    checks.run_tests('data')


if __name__ == '__main__':
    unittest.main()
