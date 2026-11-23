"""Resource guards, output safety and failure accounting for local benchmarks."""
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from vietdoc.data import benchmark
from vietdoc.data.benchmark import main, run, worker, workload
from vietdoc.data.manifest import encoded, read_json

ROOT = Path(__file__).resolve().parents[2]


class BenchmarkTest(unittest.TestCase):
    def environment_fixture(self):
        # Environment probes are not the output-safety/failure-accounting behavior.
        # Never use this fixture to claim performance measurements.
        return patch.object(benchmark, 'measurement_environment', return_value=(
            read_json(benchmark.d21.DEFAULT_CONFIG), {'scope': 'unit-test fixture'}, {}))

    def test_import_and_workload_without_resource_module(self):
        code = ('import sys; sys.modules["resource"] = None; '
                'from vietdoc.data.benchmark import workload; '
                'print(workload([1], 8, 1, 30))')
        child = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT,
                               capture_output=True, text=True, timeout=30)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertEqual(child.stdout.strip(), '8')

    def test_internal_worker_cannot_bypass_workload_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / 'config.json').write_bytes(encoded(dict(rows=[1], base_limit=41,
                repeats=1, stage_timeout_seconds=300)))
            with self.assertRaisesRegex(ValueError, 'base-limit'):
                worker('render', ROOT, output)
            self.assertFalse((output / 'dataset').exists())

    def test_internal_worker_rejects_forged_or_malformed_counter_before_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            config = dict(rows=[1], base_limit=8, repeats=1, stage_timeout_seconds=30, seed=2101)
            for counter in (10000, 7, '8', True, None):
                with self.subTest(counter=counter):
                    (output / 'config.json').write_bytes(encoded(dict(config, attempted_bases_per_repeat=counter)))
                    with patch.object(benchmark, 'require_measurement_platform') as platform, \
                            self.assertRaisesRegex(ValueError, 'counter drift'):
                        worker('validate', ROOT, output)
                    platform.assert_not_called()
                    self.assertFalse((output / 'validate.json').exists())

    def test_internal_worker_bounds_samples_without_optional_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            config = dict(rows=[1], base_limit=8, repeats=1, stage_timeout_seconds=30, seed=2101)
            renderer = dict(read_json(benchmark.d21.DEFAULT_CONFIG), rows=[1])
            (output / 'config.json').write_bytes(encoded(config))
            (output / 'renderer-config.json').write_bytes(encoded(renderer))
            dataset = output / 'dataset'
            dataset.mkdir()
            (dataset / 'manifest.json').write_bytes(encoded(dict(version=benchmark.d21.VERSION,
                config=renderer, seed=2101, samples=[{} for _ in range(9)])))
            with patch.object(benchmark, 'require_measurement_platform'), \
                    patch.object(benchmark.d21, 'validate') as validate, \
                    self.assertRaisesRegex(ValueError, 'exceeds computed workload'):
                worker('validate', ROOT, output)
            validate.assert_not_called()
            self.assertFalse((output / 'validate.json').exists())

    def test_bounds_include_rejection_probes(self):
        self.assertEqual(workload([1], 8, 1, 30), 8)
        self.assertEqual(workload(list(range(9)), 40, 3, 600), 40)
        for rows, limit, repeats, timeout in [([1], 7, 1, 30), ([1], 41, 1, 30),
                                             ([31], 40, 1, 30), ([1, 1], 40, 1, 30),
                                             ([], 40, 1, 30), ([1], 40, 4, 30),
                                             ([1], 40, 1, 601)]:
            with self.subTest(rows=rows, limit=limit, repeats=repeats, timeout=timeout):
                with self.assertRaises(ValueError):
                    workload(rows, limit, repeats, timeout)

    def test_bad_workload_creates_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'new'
            with self.assertRaisesRegex(ValueError, 'base-limit'):
                run(ROOT, output, base_limit=1)
            self.assertFalse(output.exists())

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            sentinel = output / 'benchmark.json'
            sentinel.write_bytes(b'user bytes')
            with self.environment_fixture(), self.assertRaises(FileExistsError):
                run(ROOT, output)
            self.assertEqual(sentinel.read_bytes(), b'user bytes')

    def test_timeout_is_recorded_and_stops_later_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'new'
            with self.environment_fixture(), patch('vietdoc.data.benchmark.subprocess.run',
                       side_effect=subprocess.TimeoutExpired('render', 1)) as child:
                with self.assertRaises(subprocess.TimeoutExpired):
                    run(ROOT, output, timeout=1)
            self.assertEqual(child.call_count, 1)
            report = read_json(output / 'benchmark.json')
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['runs'][0]['stages'], [])
            self.assertIn('timed out', report['error'])

    def test_unsupported_platform_fails_before_probes_or_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'new'
            with patch.object(benchmark.sys, 'platform', 'win32'), \
                    patch.object(benchmark, 'sha') as hasher, \
                    patch.object(benchmark.subprocess, 'run') as child:
                with self.assertRaisesRegex(ValueError, 'require the pinned Linux Data environment'):
                    run(ROOT, output)
            hasher.assert_not_called()
            child.assert_not_called()
            self.assertFalse(output.exists())

    def test_internal_worker_rejects_unsupported_platform(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / 'config.json').write_bytes(encoded(dict(rows=[1], base_limit=8,
                repeats=1, stage_timeout_seconds=30, seed=2101)))
            with patch.object(benchmark.sys, 'platform', 'win32'), \
                    patch.object(benchmark.d21, 'build') as render:
                with self.assertRaisesRegex(ValueError, 'require the pinned Linux Data environment'):
                    worker('render', ROOT, output)
            render.assert_not_called()
            self.assertFalse((output / 'dataset').exists())

    def test_cli_unsupported_platform_has_clear_error_and_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'new'
            error = io.StringIO()
            with patch.object(benchmark.sys, 'platform', 'win32'), \
                    patch.object(benchmark.sys, 'argv', ['benchmark', '--output', str(output)]), \
                    contextlib.redirect_stderr(error), self.assertRaises(SystemExit) as raised:
                main()
            self.assertEqual(raised.exception.code, 1)
            self.assertIn('Benchmark failed: benchmark measurements require the pinned Linux Data environment',
                          error.getvalue())
            self.assertFalse(output.exists())

    def test_worker_failure_preserves_completed_stage_and_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'new'
            stages = []

            def child(command, **kwargs):
                stage = command[command.index('--worker') + 1]
                stages.append(stage)
                if stage == 'render':
                    trial = output / 'run-01'
                    (trial / 'partial.txt').write_bytes(b'retained worker output')
                    (trial / 'render.json').write_bytes(encoded(dict(stage='render', status='ok',
                        wall_seconds=0.01, cpu_seconds=0.01, process_peak_rss_bytes=1024,
                        disk={}, result={})))
                    return subprocess.CompletedProcess(command, 0)
                raise subprocess.CalledProcessError(7, command, stderr='worker failed')

            with self.environment_fixture(), patch.object(benchmark.subprocess, 'run', side_effect=child):
                with self.assertRaises(subprocess.CalledProcessError):
                    run(ROOT, output)
            self.assertEqual(stages, ['render', 'validate'])
            report = read_json(output / 'benchmark.json')
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['worker_stderr'], 'worker failed')
            self.assertIn('finished_utc', report)
            self.assertEqual([s['stage'] for s in report['runs'][0]['stages']], ['render'])
            self.assertEqual((output / 'run-01/partial.txt').read_bytes(), b'retained worker output')


if __name__ == '__main__':
    unittest.main()
