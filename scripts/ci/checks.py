"""Executable CI checks for the current Data increment, without a model or DB."""

import argparse
from collections import Counter
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SUITES = {
    'data': ('tests/unit', 'test_data*.py', {'test_data_values.py', 'test_data_integration.py'}),
    'contracts': ('tests/contract', 'test_schemas.py', {'test_schemas.py'}),
    'ci': ('tests/unit', 'test_ci_gate.py', {'test_ci_gate.py'}),
}
CANONICAL_TEST = 'test_data_integration.IntegrationDataTest.test_canonical_reference_bytes'
MINIMUM_TESTS = {'data': 14, 'contracts': 9, 'ci': 9}


def run_tests(name: str) -> int:
    folder, pattern, required = SUITES[name]
    directory = ROOT / folder
    missing = required - {path.name for path in directory.glob(pattern)}
    if missing:
        raise ValueError(f'Missing mandatory test files: {sorted(missing)}')
    suite = unittest.TestSuite()
    for path in sorted(directory.glob(pattern)):
        module_suite = unittest.defaultTestLoader.discover(str(directory), pattern=path.name)
        if not module_suite.countTestCases():
            raise ValueError(f'No tests discovered in {path.name}')
        suite.addTests(module_suite)
    count = suite.countTestCases()
    if count < MINIMUM_TESTS[name]:
        raise ValueError(f'Test inventory shrank for {name}: {count} < {MINIMUM_TESTS[name]}')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    unexpected_skips = [test.id() for test, _ in result.skipped if test.id() != CANONICAL_TEST]
    versions = {}
    for dependency in ('Pillow', 'jsonschema'):
        try:
            versions[dependency] = version(dependency)
        except PackageNotFoundError:
            versions[dependency] = None
    report = dict(suite=name, discovered=count, run_count=result.testsRun,
                  executed=result.testsRun - len(result.skipped),
                  failures=len(result.failures), errors=len(result.errors),
                  skipped=[dict(test=test.id(), reason=reason) for test, reason in result.skipped],
                  python=platform.python_version(), dependencies=versions)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if summary := os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(summary).open('a', encoding='utf-8') as stream:
            stream.write(f'\n### {name} tests\n\n```json\n{output}\n```\n')
    return int(not result.wasSuccessful() or bool(unexpected_skips) or result.testsRun != count)


def integration() -> None:
    from vietdoc.data.generator.integration import build, load_artifacts, resolve_font

    with tempfile.TemporaryDirectory(prefix='ci-d12-', dir=ROOT / 'datasets/processed') as temporary:
        directory = Path(temporary)
        manifest = directory / 'manifest.json'
        build(ROOT, directory / 'samples', manifest, seed=1202, font_path=resolve_font())
        actual = list(load_artifacts(ROOT, manifest, full_set=True))
        counts = Counter(metadata['document_type'] for metadata, _ in actual)
        if len(actual) != 20 or counts != {'receipt': 10, 'invoice': 10}:
            raise ValueError(f'Incomplete D1.2 set: {counts}')
        print(json.dumps(dict(samples=len(actual), per_type=counts, scope='synthetic integration')))


def package() -> None:
    destination = ROOT / 'dist'
    destination.mkdir(exist_ok=True)
    subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation',
                    '--wheel-dir', str(destination), str(ROOT)], check=True)
    wheels = list(destination.glob('vietdoc-*.whl'))
    if len(wheels) != 1:
        raise ValueError('Expected exactly one VietDoc wheel in dist; use a clean checkout')
    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as archive:
        member = 'vietdoc/data/generator/fake-values.json'
        if member not in archive.namelist():
            raise ValueError('Wheel is missing the fictional generator dictionary')
        json.loads(archive.read(member))
    with tempfile.TemporaryDirectory(prefix='vietdoc-wheel-') as temporary:
        isolated = Path(temporary)
        venv.EnvBuilder(with_pip=True).create(isolated / 'venv')
        python = isolated / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        subprocess.run([str(python), '-m', 'pip', 'install', '-c', str(ROOT / '.github/ci-constraints.txt'),
                        f'{wheel}[data]'], check=True, cwd=isolated)
        subprocess.run([str(python), '-I', '-c',
                        'from vietdoc.data.generator.values import generate; '
                        'samples=generate(); '
                        'assert len(samples)==4 and "Hư Cấu" in samples[0][1]["merchant_name"]; '
                        'print("Installed-wheel Data generation: 4 fictional samples")'],
                       check=True, cwd=isolated)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    provenance = dict(scope='Data Python package only; not an application release',
                      source_sha=commit, wheel=wheel.name,
                      sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),
                      python=platform.python_version())
    (destination / 'data-package.json').write_text(
        json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(provenance, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    subparsers.add_parser('tests').add_argument('suite', choices=SUITES)
    subparsers.add_parser('integration')
    subparsers.add_parser('package')
    args = parser.parse_args()
    if args.command == 'tests':
        return run_tests(args.suite)
    if args.command == 'integration':
        integration()
    else:
        package()
    return 0


if __name__ == '__main__':
    sys.exit(main())
