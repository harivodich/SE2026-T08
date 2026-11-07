"""Run fixture-based AI suites in their own serve/test environment, fail closed."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SUITES = (
    "tests/unit/pipeline", "tests/unit/ml", "tests/contract", "tests/architecture",
    "tests/integration/api", "tests/unit/test_ci_gate.py", "tests/unit/test_ci_ai.py",
)
REQUIRED_FILES = (
    "tests/unit/pipeline/test_ocr_consumer.py",
    "tests/unit/pipeline/test_ocr_input.py",
    "tests/unit/pipeline/test_baseline.py", "tests/unit/pipeline/test_baseline_export.py",
    "tests/unit/pipeline/test_normalization.py", "tests/unit/pipeline/test_output_parser.py",
    "tests/unit/ml/test_release_manifest.py", "tests/contract/test_schemas.py",
    "tests/contract/test_compute_contract.py", "tests/architecture/test_python_boundaries.py",
    "tests/integration/api/test_compute_api.py", "tests/unit/test_ci_gate.py", "tests/unit/test_ci_ai.py",
)
SYMLINK_TEST = "tests/unit/ml/test_release_manifest.py::test_symlinked_file_is_rejected"


class _Inventory:
    def __init__(self, files: set[Path], minimum: int, allow_windows_skip: bool):
        self.files = files
        self.minimum = minimum
        self.allow_windows_skip = allow_windows_skip
        self.failures: list[str] = []
        self.collected = 0
        self.passed = 0
        self.passed_subtests = 0
        self.skipped: list[str] = []

    def pytest_collection_finish(self, session):
        self.collected = len(session.items)
        collected_files = {item.path.resolve() for item in session.items}
        for path in sorted(self.files - collected_files):
            self.failures.append(f"No tests collected from {path.name}")
        if self.collected < self.minimum:
            self.failures.append(f"Test inventory shrank: {self.collected} < {self.minimum}")

    def pytest_deselected(self, items):
        self.failures.append(f"Unexpected deselection: {len(items)} tests")

    def pytest_collectreport(self, report):
        if report.skipped:
            self.failures.append(f"Unexpected collection skip: {report.nodeid}")

    def pytest_runtest_logreport(self, report):
        if report.when == "call" and report.passed:
            if hasattr(report, "context"):
                self.passed_subtests += 1
            else:
                self.passed += 1
        if report.skipped:
            self.skipped.append(report.nodeid)
            allowed = (
                self.allow_windows_skip and sys.platform == "win32"
                and report.nodeid.replace("\\", "/") == SYMLINK_TEST
                and report.when == "call" and not hasattr(report, "wasxfail")
                and report.longrepr[2] == "Skipped: symlink creation not permitted on this host"
            )
            if not allowed:
                self.failures.append(f"Unexpected test skip: {report.nodeid}")

    def pytest_sessionfinish(self, session, exitstatus):
        if exitstatus == pytest.ExitCode.OK and self.passed + len(self.skipped) != self.collected:
            self.failures.append("Collected tests were not fully executed")
        if self.failures:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
            reporter = session.config.pluginmanager.getplugin("terminalreporter")
            if reporter:
                for failure in self.failures:
                    reporter.write_line(f"AI gate: {failure}", red=True)


def run_tests(paths: list[Path], *, junitxml: Path | None = None,
              minimum_tests: int = 1, allow_windows_symlink_skip: bool = False) -> int:
    files: set[Path] = set()
    for path in paths:
        if not path.exists():
            print(f"Missing mandatory test path: {path}", file=sys.stderr)
            return 1
        discovered = set(path.rglob("test_*.py")) if path.is_dir() else {path}
        if not discovered:
            print(f"No test modules in {path}", file=sys.stderr)
            return 1
        files.update(item.resolve() for item in discovered)
    inventory = _Inventory(files, minimum_tests, allow_windows_symlink_skip)
    args = ["-q", "-p", "no:cacheprovider", "--tb=short", *map(str, paths)]
    if junitxml is not None:
        args.append(f"--junitxml={junitxml}")
    status = int(pytest.main(args, plugins=[inventory]))
    report = dict(suite="ai", collected=inventory.collected, passed=inventory.passed,
                  passed_subtests=inventory.passed_subtests,
                  skipped=inventory.skipped, policy_failures=inventory.failures, exit_code=status)
    output = json.dumps(report, indent=2)
    print(output)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write(f"\n### AI fixture suites\n\n```json\n{output}\n```\n")
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junitxml", type=Path)
    parser.add_argument("--allow-windows-symlink-skip", action="store_true",
                        help="Local Windows only; Linux CI permits no skipped AI tests")
    args = parser.parse_args()
    for name in REQUIRED_FILES:
        if not (ROOT / name).is_file():
            print(f"Missing mandatory test file: {name}", file=sys.stderr)
            return 1
    return run_tests([ROOT / name for name in SUITES], junitxml=args.junitxml,
                     minimum_tests=473, allow_windows_symlink_skip=args.allow_windows_symlink_skip)


if __name__ == "__main__":
    sys.exit(main())
