"""Executable CI checks for the current Data increment, without a model or DB."""

import argparse
from collections import Counter
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SUITES = {
    'data': ('tests/unit', 'test_data*.py', {'test_data_values.py', 'test_data_integration.py',
                                          'test_data_d21.py', 'test_data_d22.py'}),
    'pdf': ('tests/unit', 'test_data_d21.py', {'test_data_d21.py'}),
    'contracts': ('tests/contract', 'test_schemas.py', {'test_schemas.py'}),
    'ci': ('tests/unit', 'test_ci_gate.py', {'test_ci_gate.py'}),
}
CANONICAL_TEST = 'test_data_integration.IntegrationDataTest.test_canonical_reference_bytes'
PDF_TEST = 'test_data_d21.D21Test.test_pdf_independent_parser_render_and_lossless_image'
PDF_TOOLS = ('pdfinfo', 'pdfimages', 'pdftoppm')
MINIMUM_TESTS = {'data': 30, 'pdf': 1, 'contracts': 9, 'ci': 9}


def test_cases(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from test_cases(test)
        else:
            yield test


def run_tests(name: str, *, separate_pdf: bool = False) -> int:
    if separate_pdf and name != 'data':
        raise ValueError('--separate-pdf is only valid for the Data suite')
    if name == 'pdf':
        missing_tools = [tool for tool in PDF_TOOLS if shutil.which(tool) is None]
        if missing_tools:
            raise ValueError('Missing required PDF tools: ' + ', '.join(missing_tools))
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
    cases = list(test_cases(suite))
    discovered = len(cases)
    if discovered < MINIMUM_TESTS[name]:
        raise ValueError(f'Test inventory shrank for {name}: {discovered} < {MINIMUM_TESTS[name]}')
    delegated = []
    if name == 'pdf' or separate_pdf:
        if sum(test.id() == PDF_TEST for test in cases) != 1:
            raise ValueError('Expected exactly one mandatory PDF verification test')
        if separate_pdf:
            cases = [test for test in cases if test.id() != PDF_TEST]
            delegated = [PDF_TEST]
        else:
            cases = [test for test in cases if test.id() == PDF_TEST]
    suite = unittest.TestSuite(cases)
    count = len(cases)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    unexpected_skips = [test.id() for test, _ in result.skipped
                        if name != 'data' or test.id() != CANONICAL_TEST]
    versions = {}
    for dependency in ('Pillow', 'jsonschema'):
        try:
            versions[dependency] = version(dependency)
        except PackageNotFoundError:
            versions[dependency] = None
    report = dict(suite=name, discovered=discovered, selected=count, delegated_to_pdf_job=delegated,
                  run_count=result.testsRun,
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
    tests_parser = subparsers.add_parser('tests')
    tests_parser.add_argument('suite', choices=SUITES)
    tests_parser.add_argument('--separate-pdf', action='store_true',
                              help='Data matrix only; mandatory PDF job runs the PDF test separately')
    subparsers.add_parser('integration')
    subparsers.add_parser('package')
    args = parser.parse_args()
    if args.command == 'tests':
        return run_tests(args.suite, separate_pdf=args.separate_pdf)
    if args.command == 'integration':
        integration()
    else:
        package()
    return 0


if __name__ == '__main__':
    sys.exit(main())
