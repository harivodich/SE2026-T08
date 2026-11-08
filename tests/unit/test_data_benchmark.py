"""Resource guards, output safety and failure accounting for local benchmarks."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from vietdoc.data.benchmark import run, worker, workload
from vietdoc.data.manifest import encoded, read_json

ROOT = Path(__file__).resolve().parents[2]


class BenchmarkTest(unittest.TestCase):
    def test_internal_worker_cannot_bypass_workload_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / 'config.json').write_bytes(encoded(dict(rows=[1], base_limit=41,
                repeats=1, stage_timeout_seconds=300)))
            with self.assertRaisesRegex(ValueError, 'base-limit'):
                worker('render', ROOT, output)
            self.assertFalse((output / 'dataset').exists())

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
            with self.assertRaises(FileExistsError):
                run(ROOT, output)
            self.assertEqual(sentinel.read_bytes(), b'user bytes')

    def test_timeout_is_recorded_and_stops_later_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'new'
            with patch('vietdoc.data.benchmark.subprocess.run',
                       side_effect=subprocess.TimeoutExpired('render', 1)) as child:
                with self.assertRaises(subprocess.TimeoutExpired):
                    run(ROOT, output, timeout=1)
            self.assertEqual(child.call_count, 1)
            report = read_json(output / 'benchmark.json')
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['runs'][0]['stages'], [])
            self.assertIn('timed out', report['error'])


if __name__ == '__main__':
    unittest.main()
