"""Run real Java JAR -> PostgreSQL -> native OCR/B0 -> review/approve/export.

Uses fictional checked-in samples and isolated caller-owned PostgreSQL. Does not
train, certify model accuracy, deploy, or substitute a fixture compute provider.
"""
import argparse
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from urllib.parse import urlsplit
import uuid

from scripts.ci.application import require, sha

ROOT = Path(__file__).resolve().parents[2]
SHA256 = re.compile(r'[0-9a-f]{64}\Z')


class HttpStatusMismatch(ValueError):
    def __init__(self, method, path, expected, actual):
        self.actual = actual
        super().__init__(f'{method} {path}: expected{expected}, got{actual}')


def provision(models):
    from vietdoc.pipeline.composition import PROFILE
    from vietdoc.pipeline.ocr.paddle_adapter import provision_models
    release = models / 'ci-native-b0-v1'
    release.mkdir(parents=True, exist_ok=False)
    provision_models(release / 'ocr')
    (release / 'pipeline.json').write_text(json.dumps(PROFILE, sort_keys=True), encoding='utf8')
    files = [dict(path=p.relative_to(release).as_posix(), sha256=sha(p), size_bytes=p.stat().st_size)
             for p in sorted(release.rglob('*')) if p.is_file()]
    (release / 'manifest.json').write_text(json.dumps(dict(manifest_version=1,
        pipeline_manifest_id=release.name, files=files), sort_keys=True), encoding='utf8')
    return release.name


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def compute_command(port, candidate_settings=None):
    if candidate_settings is None:
        return [sys.executable, '-m', 'uvicorn', 'vietdoc.entrypoints.api.app:create_runtime_app',
                '--factory', '--host', '127.0.0.1', '--port', str(port), '--no-access-log'], 'b0'
    settings = candidate_options(candidate_settings)
    arguments = [value for name, value in sorted(settings.items()) for value in ('--' + name, value)]
    return [sys.executable, '-m', 'scripts.serve_compute_candidate', '--extractor', 'qwen-local', *arguments], 'qwen-local'


def candidate_options(candidate_settings):
    require(candidate_settings.is_file() and candidate_settings.stat().st_size <= 16 * 1024,
            'Candidate settings missing or too large')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'Duplicate candidate setting')
            value[key] = item
        return value
    settings = json.loads(candidate_settings.read_text(encoding='utf8'), object_pairs_hook=unique)
    required = {'config', 'config-sha256', 'snapshot', 'snapshot-manifest-sha256'}
    allowed = required | {'run-dir', 'run-manifest-sha256', 'ocr-artifact-version'}
    require(isinstance(settings, dict) and required <= settings.keys() <= allowed,
            'Candidate needs explicit config/snapshot pins, without arbitrary command options')
    require(('run-dir' in settings) == ('run-manifest-sha256' in settings), 'Candidate adapter pins incomplete')
    require(all(isinstance(value, str) and value for value in settings.values()), 'Candidate settings must be strings')
    for name in ('config-sha256', 'snapshot-manifest-sha256', 'run-manifest-sha256'):
        if name in settings: require(SHA256.fullmatch(settings[name]) is not None, 'Invalid candidate SHA256 pin')
    if 'ocr-artifact-version' in settings:
        require(settings['ocr-artifact-version'] in ('1', '2'), 'Invalid OCR artifact version')
    return settings


def preflight_candidate(release, settings):
    paths = [('config', Path(settings['config'])),
             ('snapshot-manifest', Path(settings['snapshot']) / 'manifest.json')]
    if 'run-dir' in settings:
        paths.append(('run-manifest', Path(settings['run-dir']) / 'run_manifest.json'))
    for name, path in paths:
        require(path.is_absolute() and path.is_file() and not path.is_symlink(),
                f'Candidate {name} missing or unsafe')
        require(sha(path) == settings[name + '-sha256'], f'Candidate {name} pin mismatch')
    expected = dict(config_sha256=settings['config-sha256'],
                    snapshot_manifest_sha256=settings['snapshot-manifest-sha256'],
                    run_manifest_sha256=settings.get('run-manifest-sha256'))
    require('extractor.json' in {file.path for file in release.files},
            'Candidate release missing extractor selection')
    try:
        actual = json.loads(release.file('extractor.json').read_text(encoding='utf8'))
    except (UnicodeError, ValueError) as error:
        raise ValueError('Candidate extractor selection is invalid') from error
    require(actual == expected, 'Candidate extractor selection does not match pins')


def wait_ready(client, path, processes, timeout=120, poll_seconds=1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        require(all(process.poll() is None for process in processes),
                'Test service exited before readiness')
        try:
            return client.json('GET', path)
        except HttpStatusMismatch as error:
            if error.actual != 503: raise
        except (URLError, TimeoutError):
            pass
        time.sleep(poll_seconds)
    raise TimeoutError('Test service readiness timeout')


class Client:
    def __init__(self, base):
        self.base = base
        self.opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf = None

    def request(self, method, path, expected=200, payload=None, data=None, headers=None):
        headers = dict(headers or {})
        if payload is not None:
            data = json.dumps(payload).encode()
            headers['Content-Type'] = 'application/json'
        if self.csrf:
            headers['X-CSRF-TOKEN'] = self.csrf
        try:
            response = self.opener.open(Request(self.base + path, data=data, method=method, headers=headers), timeout=15)
        except HTTPError as error:
            response = error
        with response:
            content = response.read(4 * 1024 * 1024 + 1)
            require(len(content) <= 4 * 1024 * 1024, 'Oversize test response')
            if response.status != expected:
                raise HttpStatusMismatch(method, path, expected, response.status)
        return content

    def json(self, method, path, expected=200, **kwargs):
        return json.loads(self.request(method, path, expected, **kwargs))


def run(jar, run_root, database_url, java, source_sha, models=None, manifest_id='ci-native-b0-v1',
        candidate_settings=None, pg_bin=None, release_manifest_sha256=None):
    require(database_url.startswith('jdbc:postgresql://127.0.0.1:') or
            database_url.startswith('jdbc:postgresql://localhost:'), 'Use isolated loopback PostgreSQL only')
    require(candidate_settings is None or models is not None, 'Candidate model release must be provisioned explicitly')
    require((models is None) == (release_manifest_sha256 is None),
            'Explicit models need a pinned release manifest SHA256')
    if models is not None:
        require(SHA256.fullmatch(release_manifest_sha256) is not None, 'Invalid release manifest SHA256 pin')
        manifest = models / manifest_id / 'manifest.json'
        require(manifest.is_file() and not manifest.is_symlink() and sha(manifest) == release_manifest_sha256,
                'Release manifest missing or changed')
    settings = candidate_options(candidate_settings) if candidate_settings is not None else None
    run_root.mkdir(parents=True, exist_ok=False)
    manifest_id = provision(run_root / 'models') if models is None else manifest_id
    models = models or run_root / 'models'
    # Validate explicitly provisioned bytes before starting processes.
    from vietdoc.ml.release_manifest import load_release
    release = load_release(models, manifest_id)
    require(release is not None, 'Native release missing')
    if settings is not None: preflight_candidate(release, settings)
    token, password = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    attempts, storage = run_root / 'attempts', run_root / 'java-storage'
    attempts.mkdir()
    ai_port, web_port = free_port(), free_port()
    require(ai_port != web_port, 'Port allocation collision; retry with a new run directory')
    processes, logs = [], []
    def start(argv, env, name):
        log = (run_root / (name + '.log')).open('wb')
        logs.append(log)
        process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=os.name != 'nt')
        processes.append(process)
        return process
    try:
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                   PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='true', VIETDOC_SERVICE_TOKEN=token,
                   VIETDOC_MODELS_DIR=str(models), VIETDOC_ATTEMPTS_DIR=str(attempts),
                   VIETDOC_CONTRACTS_DIR=str(ROOT / 'specs/contracts'), VIETDOC_PIPELINE_MANIFEST_ID=manifest_id,
                   VIETDOC_HOST='127.0.0.1', VIETDOC_PORT=str(ai_port))
        command, extractor = compute_command(ai_port, candidate_settings)
        start(command, env, 'compute')
        ready = wait_ready(Client(f'http://127.0.0.1:{ai_port}'), '/health/ready', processes)
        require(ready['status'] == 'READY' and manifest_id in ready['releases'], 'Native provider not ready')
        env = dict(os.environ, SERVER_PORT=str(web_port), DATABASE_URL=database_url,
                   DATABASE_USER=os.environ['VIETDOC_PG_TEST_USER'], DATABASE_PASSWORD=os.environ['VIETDOC_PG_TEST_PASSWORD'],
                   STORAGE_ROOT=str(storage), AI_ATTEMPTS_ROOT=str(attempts), AI_MODE='http',
                   AI_WORKER_URL=f'http://127.0.0.1:{ai_port}/internal/v1/compute', AI_WORKER_TOKEN=token,
                   PIPELINE_MANIFEST=manifest_id, SEED_USERNAME='ci-native-owner', SEED_PASSWORD=password)
        java_command = [java, '-Duser.timezone=UTC', '-Dserver.address=127.0.0.1', '-jar', str(jar.resolve())]
        java_process = start(java_command, env, 'java')
        wait_ready(Client(f'http://127.0.0.1:{web_port}'), '/actuator/health', processes)
        client = Client(f'http://127.0.0.1:{web_port}/api/v1')
        client.csrf = client.json('GET', '/auth/csrf')['token']
        client.json('POST', '/auth/session', payload=dict(username='ci-native-owner', password=password))
        client.csrf = client.json('GET', '/auth/csrf')['token']
        result = dict(version=1, source_sha=source_sha, jar_sha256=sha(jar), actual_native_provider=True,
                      database='PostgreSQL', model_release=manifest_id, candidate_id=manifest_id,
                      release_manifest_sha256=sha(release.root / 'manifest.json'), extractor=extractor,
                      candidate_pins=None if settings is None else {
                          name: settings.get(name) for name in
                          ('config-sha256', 'snapshot-manifest-sha256', 'run-manifest-sha256',
                           'ocr-artifact-version')}, cases=[],
                      scope='Actual native application integration; quality/final acceptance remains separate')
        for kind, extension, total in [('receipt', 'png', '45000'), ('invoice', 'pdf', '110000')]:
            sample = ROOT / 'samples' / f'{kind}-demo.{extension}'
            boundary = 'vietdoc-' + uuid.uuid4().hex
            media = 'image/png' if extension == 'png' else 'application/pdf'
            body = (f'--{boundary}\r\nContent-Disposition: form-data; name="document_type"\r\n\r\n{kind}\r\n'
                    f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{sample.name}"\r\n'
                    f'Content-Type: {media}\r\n\r\n').encode() + sample.read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
            document = client.json('POST', '/documents', 201, data=body,
                                   headers={'Content-Type': 'multipart/form-data; boundary=' + boundary,
                                            'Idempotency-Key': str(uuid.uuid4())})
            did = document['id']
            job = client.json('POST', f'/documents/{did}/jobs', 202, headers={'Idempotency-Key': str(uuid.uuid4())})
            deadline = time.monotonic() + 210
            while job['state'] in ('QUEUED', 'RUNNING', 'RETRYING') and time.monotonic() < deadline:
                time.sleep(1)
                job = client.json('GET', f'/jobs/{job["id"]}')
            require(job['state'] == 'SUCCEEDED', f'Native{kind} job failed: ' + job['state'])
            document = client.json('GET', f'/documents/{did}')
            run = client.json('GET', f'/runs/{job["result_run_id"]}')
            provenance = run['result']['provenance']
            require(provenance['pipeline_manifest_id'] == manifest_id and
                    'tesseract' in provenance['ocr_version'] and 'fixture' not in provenance['ocr_version'],
                    'Fixture or wrong provider cannot satisfy native E2E')
            canonical = client.request('GET', f'/documents/{did}/pages/0')
            paths = list((attempts / job['id']).glob('*/canonical.png'))
            require(len(paths) == 1 and paths[0].read_bytes() == canonical, 'Native canonical not promoted')
            paths[0].write_bytes(b'isolated acceptance mutation after completion')
            require(client.request('GET', f'/documents/{did}/pages/0') == canonical, 'Viewer serves mutable attempt')
            client.json('POST', f'/documents/{did}/exports', 409,
                        payload=dict(revision_id=document['head_revision_id'], format='json'))
            payload = document['head']['payload']
            payload['total_amount'] = total  # Explicit human edit to a fictional sample, not a predicted score.
            edit = dict(base_revision_id=document['head_revision_id'], expected_document_version=document['version'],
                        payload=payload, row_ids=document['head']['row_ids'], reviewed_paths=['/total_amount'],
                        reason='CI fictional sample explicit total review')
            document = client.json('PATCH', f'/documents/{did}/review', 201, payload=edit)
            client.json('PATCH', f'/documents/{did}/review', 409, payload=edit)
            warnings = [i['id'] for i in document['head']['issues'] if i['severity'] == 'warning']
            approved = client.json('POST', f'/documents/{did}/approve', 201,
                payload=dict(revision_id=document['head_revision_id'], expected_document_version=document['version'],
                             confirmed_review=True, acknowledged_issue_ids=warnings, reason='CI synthetic review'))
            export_request = dict(revision_id=approved['head_revision_id'], format='json')
            exported = client.json('POST', f'/documents/{did}/exports', 201, payload=export_request)
            repeated = client.json('POST', f'/documents/{did}/exports', 201, payload=export_request)
            content = client.request('GET', f'/exports/{exported["id"]}/download')
            require(exported['id'] == repeated['id'] and exported['sha256'] == hashlib.sha256(content).hexdigest(),
                    'Approved export is not deterministic')
            Client(client.base).request('GET', f'/documents/{did}/pages/0', 401)
            result['cases'].append(dict(type=kind, input_sha256=sha(sample), export_sha256=exported['sha256'],
                                        ocr_version=provenance['ocr_version'], state=job['state'],
                                        document_id=did, export_id=exported['id'], revision_id=approved['head_revision_id'],
                                        canonical_sha256=hashlib.sha256(canonical).hexdigest()))
        result['backup_restore'] = dict(status='NOT_RUN', reason='--pg-bin was not supplied')
        if pg_bin is not None:
            parsed = urlsplit(database_url.removeprefix('jdbc:'))
            database = parsed.path.removeprefix('/')
            require(database.replace('_', '').isalnum() and len(database) <= 48 and not parsed.query,
                    'Use a simple isolated database name for restore rehearsal')
            java_process.terminate()
            try:
                java_process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                java_process.kill()
                java_process.wait(timeout=5)
            processes.remove(java_process)
            restored_database = database + '_restore'
            pg_env = dict(os.environ, PGHOST=parsed.hostname, PGPORT=str(parsed.port or 5432),
                          PGUSER=os.environ['VIETDOC_PG_TEST_USER'], PGPASSWORD=os.environ['VIETDOC_PG_TEST_PASSWORD'])
            dump = run_root / 'database.backup'
            for tool, arguments in [('pg_dump', ['--format=custom', '--file', str(dump), database]),
                                    ('createdb', [restored_database]),
                                    ('pg_restore', ['--exit-on-error', '--no-owner', '--dbname', restored_database, str(dump)])]:
                outcome = subprocess.run([str(pg_bin / tool), *arguments], env=pg_env,
                                         capture_output=True, timeout=90)
                require(outcome.returncode == 0, 'Isolated PostgreSQL ' + tool + ' failed')
            restored_storage = run_root / 'restored-java-storage'
            shutil.copytree(storage, restored_storage)
            original_files = {p.relative_to(storage).as_posix(): sha(p) for p in storage.rglob('*') if p.is_file()}
            copied_files = {p.relative_to(restored_storage).as_posix(): sha(p)
                            for p in restored_storage.rglob('*') if p.is_file()}
            require(original_files and original_files == copied_files, 'Committed-storage backup changed bytes')
            restored_env = dict(env, DATABASE_URL=database_url.rsplit('/', 1)[0] + '/' + restored_database,
                                STORAGE_ROOT=str(restored_storage), WORKER_ENABLED='false')
            start(java_command, restored_env, 'java-restored')
            wait_ready(Client(f'http://127.0.0.1:{web_port}'), '/actuator/health', processes)
            replay = Client(client.base)
            replay.csrf = replay.json('GET', '/auth/csrf')['token']
            replay.json('POST', '/auth/session', payload=dict(username='ci-native-owner', password=password))
            replay.csrf = replay.json('GET', '/auth/csrf')['token']
            for case in result['cases']:
                document = replay.json('GET', f'/documents/{case["document_id"]}')
                require(document['head_revision_id'] == case['revision_id'], 'Restored approved head changed')
                canonical = replay.request('GET', f'/documents/{case["document_id"]}/pages/0')
                exported = replay.request('GET', f'/exports/{case["export_id"]}/download')
                require(hashlib.sha256(canonical).hexdigest() == case['canonical_sha256'] and
                        hashlib.sha256(exported).hexdigest() == case['export_sha256'],
                        'Restored business assets/exports changed bytes')
            result['backup_restore'] = dict(status='PASS', documents=len(result['cases']),
                                            storage_files=len(original_files), same_jar_sha256=sha(jar),
                                            scope='Actual isolated DB+storage restore; same application version, not downgrade compatibility')
        result['status'] = 'PASS'
        (run_root / 'summary.json').write_text(json.dumps(result, indent=2), encoding='utf8')
        return result
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                if os.name == 'nt':process.terminate()
                else:os.killpg(process.pid, signal.SIGTERM)
                try:process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    if os.name == 'nt':process.kill()
                    else:os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
        for log in logs:log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--database-url', required=True)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--models', type=Path)
    parser.add_argument('--manifest-id', default='ci-native-b0-v1')
    parser.add_argument('--release-manifest-sha256', help='Required SHA256 pin when --models is supplied')
    parser.add_argument('--candidate-settings', type=Path, help='Explicit pinned qwen-local config; no silent B0 fallback')
    parser.add_argument('--pg-bin', type=Path, help='PostgreSQL client directory; enables actual isolated backup/restore')
    parser.add_argument('--java', default='java')
    args = parser.parse_args()
    result = run(args.jar, args.run_root.resolve(), args.database_url, args.java, args.sha,
                 args.models, args.manifest_id, args.candidate_settings, args.pg_bin,
                 args.release_manifest_sha256)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
