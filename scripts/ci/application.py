"""Bind tested Java application bytes, reports and runtime smoke to one source SHA."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_TESTS = {'WorkflowIntegrationTest', 'HttpWorkflowIntegrationTest', 'AiClientTest',
                  'ArtifactPromoterTest', 'JobWorkerTest', 'BusinessContractTest', 'ComputeContractTest'}
MINIMUM_COUNTS = dict(WorkflowIntegrationTest=20, HttpWorkflowIntegrationTest=3, AiClientTest=10,
                      ArtifactPromoterTest=7, JobWorkerTest=2, BusinessContractTest=2, ComputeContractTest=9)
ASSETS = ('templates/index.html', 'static/app.js', 'static/api.js', 'static/domain.js', 'static/styles.css')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reports(directory):
    paths = sorted(Path(directory).glob('TEST-*.xml'))
    require(bool(paths), 'Missing Surefire XML reports')
    classes, class_counts, identities, count = set(), Counter(), set(), 0
    for path in paths:
        # No external entities; ElementTree rejects unresolved entities.
        require(path.stat().st_size < 16 * 1024 * 1024, 'Oversize test report')
        suite = ET.fromstring(path.read_bytes())
        cases = suite.findall('testcase')
        require(suite.tag == 'testsuite' and cases, 'Empty or unsupported test suite')
        require(int(suite.get('tests', '-1')) == len(cases), 'Test count mismatch')
        for kind in ('failures', 'errors', 'skipped'):
            require(int(suite.get(kind, '-1')) == 0, f'Test suite has {kind}')
        for case in cases:
            require(not any(case.find(name) is not None for name in ('failure', 'error', 'skipped')),
                    'Failed/skipped test case cannot become release proof')
            identity = case.attrib['classname'], case.attrib['name']
            require(identity not in identities, 'Duplicate JUnit testcase cannot inflate release proof')
            identities.add(identity)
            name = case.attrib['classname'].rsplit('.', 1)[-1]
            classes.add(name)
            class_counts[name] += 1
        count += len(cases)
    require(REQUIRED_TESTS <= classes, f'Missing mandatory backend tests: {sorted(REQUIRED_TESTS - classes)}')
    require(all(class_counts[name] >= minimum for name, minimum in MINIMUM_COUNTS.items()),
            'Backend test inventory shrank')
    return dict(tests=count, classes=sorted(classes), files={p.name: sha(p) for p in paths})


def jar_assets(jar, root=ROOT):
    with zipfile.ZipFile(jar) as bundle:
        names = bundle.namelist()
        require(len(names) == len(set(names)), 'Duplicate JAR entries')
        for name in ASSETS:
            entry = 'BOOT-INF/classes/' + name
            require(entry in names, f'Missing packaged asset: {name}')
            require(bundle.read(entry) == (root / 'backend/src/main/resources' / name).read_bytes(),
                    f'Packaged asset differs from tested source: {name}')
        for source in sorted((root / 'backend/src/main/resources/contracts').glob('*.schema.json')):
            require(bundle.read('BOOT-INF/classes/contracts/' + source.name) == source.read_bytes(),
                    'Packaged contract mismatch')
        migrations = sorted((root / 'backend/src/main/resources/db/migration').glob('*.sql'))
        require(bool(migrations), 'No Flyway migration inventory')
        for source in migrations:
            require(bundle.read('BOOT-INF/classes/db/migration/' + source.name) == source.read_bytes(),
                    'Packaged migration mismatch')
    return {p.name: sha(p) for p in migrations}


def capture(jar, report_dir, source_sha, output):
    require(re.fullmatch('[0-9a-f]{40}', source_sha) is not None, 'Invalid source SHA')
    require(jar.is_file() and not jar.is_symlink(), 'Missing/linked JAR')
    report = dict(version=1, source_sha=source_sha, jar_name=jar.name, jar_sha256=sha(jar),
                  tests=reports(report_dir), migrations=jar_assets(jar))
    with output.open('x', encoding='utf8') as stream:
        json.dump(report, stream, indent=2)
    return report


def verify(jar, report_dir, receipt, source_sha):
    data = json.loads(receipt.read_text(encoding='utf8'))
    require(data.get('version') == 1 and data.get('source_sha') == source_sha,
            'Build source SHA mismatch')
    require(jar.name == data['jar_name'] and not jar.is_symlink() and sha(jar) == data['jar_sha256'],
            'JAR bytes differ from tested artifact')
    require(reports(report_dir) == data['tests'], 'JUnit evidence changed since build')
    require(jar_assets(jar) == data['migrations'], 'Migration inventory changed')
    return data


def smoke(jar, java='java'):
    with tempfile.TemporaryDirectory(prefix='vietdoc-jar-smoke-') as raw:
        root = Path(raw)
        with socket.socket() as port_socket:
            port_socket.bind(('127.0.0.1', 0))
            port = port_socket.getsockname()[1]
        env = dict(os.environ, SPRING_PROFILES_ACTIVE='demo', WORKER_ENABLED='false',
                   SERVER_PORT=str(port), STORAGE_ROOT=str(root / 'storage'),
                   DATABASE_URL='jdbc:h2:file:' + (root / 'db').as_posix(),
                   DATABASE_USER='sa', DATABASE_PASSWORD='')
        with (root / 'java.log').open('wb') as log:
            process = subprocess.Popen([java, '-Dserver.address=127.0.0.1', '-jar', str(jar.resolve())],
                                       cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                base = f'http://127.0.0.1:{port}'
                deadline = time.monotonic() + 90
                while True:
                    require(process.poll() is None, 'Application JAR exited before readiness')
                    try:
                        with urlopen(base + '/', timeout=2) as response:
                            page = response.read(2 * 1024 * 1024).decode('utf8')
                            require('name="_csrf"' in page, 'Rendered page missing CSRF token')
                        break
                    except (URLError, TimeoutError):
                        if time.monotonic() >= deadline:
                            raise TimeoutError('Application JAR readiness timed out')
                        time.sleep(0.5)
                for name in ('app.js', 'api.js', 'domain.js', 'styles.css'):
                    with urlopen(base + '/' + name, timeout=5) as response:
                        require(response.status == 200 and bool(response.read(2 * 1024 * 1024)),
                                'Packaged static asset unavailable')
                try:
                    urlopen(base + '/api/v1/auth/me', timeout=5).close()
                except HTTPError as error:
                    require(error.code == 401, 'Anonymous API did not return401')
                else:
                    raise ValueError('Anonymous API unexpectedly allowed')
            finally:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    return dict(scope='same tested JAR demo smoke; not actual-provider or model quality',
                jar_sha256=sha(jar), status='PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('capture', 'verify', 'smoke'))
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--reports', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--java', default='java')
    args = parser.parse_args()
    if args.command == 'capture':
        result = capture(args.jar, args.reports, args.sha, args.receipt)
    else:
        result = verify(args.jar, args.reports, args.receipt, args.sha)
        if args.command == 'smoke':
            result = smoke(args.jar, args.java)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
