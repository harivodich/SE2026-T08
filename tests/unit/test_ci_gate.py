"""Regression checks for false-green gates and trusted release target selection."""

import copy
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
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

    def test_ai_and_pdf_success_are_required_on_develop_and_main(self):
        for branch in ('develop', 'main'):
            baseline = dict(self.develop, **{'release-readiness': {
                'result': 'skipped' if branch == 'develop' else 'success'}})
            for name in ('ai', 'data-pdf'):
                for status in (None, 'failure', 'cancelled', 'skipped'):
                    broken = copy.deepcopy(baseline)
                    if status is None:
                        broken.pop(name, None)
                    else:
                        broken[name] = {'result': status}
                    self.assertTrue(evaluate('ci', branch, broken), (branch, name, status))

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


class DataPdfRunnerTest(unittest.TestCase):
    def probe(self, name, outcomes, *, separate_pdf=False, tools=True):
        executed = []
        cases = []
        for test_id, outcome in outcomes:
            def body(test_id=test_id, outcome=outcome):
                executed.append(test_id)
                if outcome == 'skip':
                    raise unittest.SkipTest('probe dependency unavailable')
                if outcome == 'fail':
                    raise AssertionError('probe PDF mismatch')
            case = unittest.FunctionTestCase(body)
            case.id = lambda test_id=test_id: test_id
            cases.append(case)
        output = StringIO()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_cases.py').touch()
            config = {name: ('.', 'test_cases.py', {'test_cases.py'})}
            with patch.object(checks, 'ROOT', root), patch.object(checks, 'SUITES', config), \
                 patch.object(checks, 'MINIMUM_TESTS', {name: 1}), \
                 patch.object(checks.shutil, 'which', return_value='/tool' if tools else None), \
                 patch.object(unittest.defaultTestLoader, 'discover', return_value=unittest.TestSuite(cases)), \
                 patch.dict(checks.os.environ, {'GITHUB_STEP_SUMMARY': ''}), \
                 redirect_stdout(output), redirect_stderr(StringIO()):
                status = checks.run_tests(name, separate_pdf=separate_pdf)
        return status, json.loads(output.getvalue()), executed

    def test_portable_suite_delegates_pdf_explicitly_and_keeps_canonical_skip(self):
        cases = [(checks.PDF_TEST, 'fail'), (checks.CANONICAL_TEST, 'skip'), ('portable', 'pass')]
        status, report, executed = self.probe('data', cases, separate_pdf=True, tools=False)
        self.assertEqual(status, 0)
        self.assertEqual(report['delegated_to_pdf_job'], [checks.PDF_TEST])
        self.assertEqual((report['discovered'], report['selected'], report['run_count']), (3, 2, 2))
        self.assertNotIn(checks.PDF_TEST, executed)
        self.assertEqual(len(report['skipped']), 1)

    def test_default_data_suite_rejects_pdf_skip(self):
        status, report, _ = self.probe('data', [(checks.PDF_TEST, 'skip')])
        self.assertEqual(status, 1)
        self.assertEqual(report['delegated_to_pdf_job'], [])

    def test_portable_suite_still_rejects_other_skips_and_failures(self):
        for outcome in ('skip', 'fail'):
            with self.subTest(outcome=outcome):
                status, _, _ = self.probe('data', [(checks.PDF_TEST, 'pass'), ('portable', outcome)],
                                          separate_pdf=True)
                self.assertEqual(status, 1)

    def test_pdf_job_requires_tools_before_discovery(self):
        with self.assertRaisesRegex(ValueError, 'Missing required PDF tools: pdfinfo, pdfimages, pdftoppm'):
            self.probe('pdf', [(checks.PDF_TEST, 'pass')], tools=False)

    def test_pdf_job_executes_only_pdf_and_rejects_skip_or_mismatch(self):
        for outcome in ('pass', 'skip', 'fail'):
            with self.subTest(outcome=outcome):
                status, report, executed = self.probe('pdf', [(checks.PDF_TEST, outcome), ('other', 'fail')])
                self.assertEqual(status, 0 if outcome == 'pass' else 1)
                self.assertEqual(executed, [checks.PDF_TEST])
                self.assertEqual((report['selected'], report['run_count']), (1, 1))

    def test_missing_or_duplicate_pdf_test_cannot_be_delegated(self):
        for cases in ([('other', 'pass')], [(checks.PDF_TEST, 'pass')] * 2):
            for name in ('data', 'pdf'):
                with self.subTest(name=name, cases=cases), \
                     self.assertRaisesRegex(ValueError, 'exactly one mandatory PDF'):
                    self.probe(name, cases, separate_pdf=name == 'data')

    def test_pdf_delegation_cannot_be_used_for_other_suites(self):
        with self.assertRaisesRegex(ValueError, 'only valid for the Data suite'):
            checks.run_tests('contracts', separate_pdf=True)


if __name__ == '__main__':
    unittest.main()
