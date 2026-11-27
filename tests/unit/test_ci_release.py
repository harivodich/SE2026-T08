"""Release false-green controls; fictional packets never represent measured quality."""
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET
import zipfile

from scripts.ci import acceptance, application, native_e2e


class NativeCommandTest(unittest.TestCase):
    def test_remote_database_is_rejected_before_creating_runtime_files(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / 'should-not-exist'
            with self.assertRaisesRegex(ValueError, 'loopback PostgreSQL'):
                native_e2e.run(Path('missing.jar'), root, 'jdbc:postgresql://production.example:5432/business',
                               'java', 'a' * 40)
            self.assertFalse(root.exists())

    def test_default_is_actual_runtime_and_candidate_never_silently_falls_back(self):
        command, extractor = native_e2e.compute_command(18090)
        self.assertEqual(extractor, 'b0')
        self.assertIn('vietdoc.entrypoints.api.app:create_runtime_app', command)
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / 'candidate.json'
            path.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'explicit config'):
                native_e2e.compute_command(18090, path)
            settings = {'config': '/fixed/config.yaml', 'config-sha256': 'a' * 64,
                        'snapshot': '/fixed/snapshot', 'snapshot-manifest-sha256': 'b' * 64}
            path.write_text(json.dumps(settings))
            command, extractor = native_e2e.compute_command(18090, path)
            self.assertEqual(extractor, 'qwen-local')
            self.assertIn('scripts.serve_compute_candidate', command)
            self.assertIn('a' * 64, command)
            settings['arbitrary-python-command'] = 'bad'
            path.write_text(json.dumps(settings))
            with self.assertRaises(ValueError):native_e2e.compute_command(18090, path)

    def test_explicit_release_requires_manifest_pin_before_runtime_directory(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with self.assertRaisesRegex(ValueError, 'pinned release manifest'):
                native_e2e.run(Path('missing.jar'), root / 'run',
                    'jdbc:postgresql://127.0.0.1:5432/isolated', 'java', 'a' * 40,
                    models=root / 'models')
            self.assertFalse((root / 'run').exists())
            release = root / 'models' / 'candidate'
            release.mkdir(parents=True)
            (release / 'manifest.json').write_text('fictional manifest')
            with self.assertRaisesRegex(ValueError, 'manifest missing or changed'):
                native_e2e.run(Path('missing.jar'), root / 'run',
                    'jdbc:postgresql://127.0.0.1:5432/isolated', 'java', 'a' * 40,
                    models=root / 'models', manifest_id='candidate',
                    release_manifest_sha256='0' * 64)
            self.assertFalse((root / 'run').exists())

    def test_candidate_preflight_rejects_changed_pins_and_selection(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            config = root / 'config.yaml'
            config.write_text('fictional config')
            snapshot = root / 'snapshot'
            snapshot.mkdir()
            (snapshot / 'manifest.json').write_text('fictional snapshot')
            selection = root / 'extractor.json'
            settings = {'config': str(config), 'config-sha256': native_e2e.sha(config),
                        'snapshot': str(snapshot),
                        'snapshot-manifest-sha256': native_e2e.sha(snapshot / 'manifest.json')}
            selected = dict(config_sha256=settings['config-sha256'],
                            snapshot_manifest_sha256=settings['snapshot-manifest-sha256'],
                            run_manifest_sha256=None)
            selection.write_text(json.dumps(selected))
            release = SimpleNamespace(files=[SimpleNamespace(path='extractor.json')],
                                      file=lambda name: selection)
            native_e2e.preflight_candidate(release, settings)
            config.write_text('changed config')
            with self.assertRaisesRegex(ValueError, 'config pin mismatch'):
                native_e2e.preflight_candidate(release, settings)
            config.write_text('fictional config')
            selected['config_sha256'] = 'b' * 64
            selection.write_text(json.dumps(selected))
            with self.assertRaisesRegex(ValueError, 'selection does not match pins'):
                native_e2e.preflight_candidate(release, settings)

    def test_readiness_retries_only_transient_status(self):
        class Process:
            def poll(self):return None
        class Client:
            calls = 0
            def json(self, method, path):
                self.calls += 1
                if self.calls == 1:raise native_e2e.HttpStatusMismatch(method, path, 200, 503)
                return {'status': 'READY'}
        client = Client()
        self.assertEqual('READY', native_e2e.wait_ready(client, '/health/ready', [Process()],
                                                       timeout=2, poll_seconds=0)['status'])
        self.assertEqual(2, client.calls)
        class Unauthorized(Client):
            def json(self, method, path):
                raise native_e2e.HttpStatusMismatch(method, path, 200, 401)
        with self.assertRaises(native_e2e.HttpStatusMismatch):
            native_e2e.wait_ready(Unauthorized(), '/health/ready', [Process()],
                                 timeout=2, poll_seconds=0)


class ArtifactEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reports = self.root / 'surefire-reports'
        self.reports.mkdir()
        self.xml = self.reports / 'TEST-required.xml'
        suite = ET.Element('testsuite', tests=str(sum(application.MINIMUM_COUNTS.values())), failures='0', errors='0', skipped='0')
        for name in sorted(application.REQUIRED_TESTS):
            for index in range(application.MINIMUM_COUNTS[name]):
                ET.SubElement(suite, 'testcase', classname='fixture.' + name, name=f'fictionalCase{index}')
        ET.ElementTree(suite).write(self.xml)
        self.jar = self.root / 'app.jar'
        resources = application.ROOT / 'backend/src/main/resources'
        with zipfile.ZipFile(self.jar, 'w') as bundle:
            paths = [resources / name for name in application.ASSETS]
            paths += list((resources / 'contracts').glob('*.schema.json'))
            paths += list((resources / 'db/migration').glob('*.sql'))
            for path in paths:bundle.write(path, 'BOOT-INF/classes/' + path.relative_to(resources).as_posix())
        self.receipt = self.root / 'receipt.json'
        self.sha = 'a' * 40

    def test_capture_verify_then_reject_rebuilt_or_modified_bytes(self):
        application.capture(self.jar, self.reports, self.sha, self.receipt)
        application.verify(self.jar, self.reports, self.receipt, self.sha)
        self.jar.write_bytes(self.jar.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'JAR bytes'):
            application.verify(self.jar, self.reports, self.receipt, self.sha)

    def test_changed_source_or_junit_cannot_reuse_receipt(self):
        application.capture(self.jar, self.reports, self.sha, self.receipt)
        with self.assertRaisesRegex(ValueError, 'source SHA'):
            application.verify(self.jar, self.reports, self.receipt, 'b' * 40)
        self.xml.write_text('<testsuite tests="0" failures="0" errors="0" skipped="0"/>')
        with self.assertRaisesRegex(ValueError, 'Empty'):
            application.verify(self.jar, self.reports, self.receipt, self.sha)

    def test_failure_skip_or_missing_required_class_cannot_pass(self):
        original = self.xml.read_bytes()
        for state in ('failures', 'errors', 'skipped'):
            tree = ET.fromstring(original)
            tree.set(state, '1')
            ET.ElementTree(tree).write(self.xml)
            with self.assertRaises(ValueError):application.reports(self.reports)
        tree = ET.fromstring(original)
        tree[0].set('classname', 'fixture.UnrelatedTest')
        ET.ElementTree(tree).write(self.xml)
        with self.assertRaisesRegex(ValueError, 'inventory shrank'):
            application.reports(self.reports)


class QualityPacketTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'src/vietdoc').mkdir(parents=True)
        (self.root / 'src/vietdoc/fictional.py').write_text('fictional source inventory')
        self.ids = [f'{kind}/{metric}' for kind in ('receipt', 'invoice') for metric in acceptance.METRICS]
        self.documents = {
            'policy': dict(status='frozen', final_open_permitted=True, minimums={key: 0.85 for key in self.ids}),
            'quality': {key: dict(value=0.9, support=10) for key in self.ids},
            'candidate_e2e': dict(status='PASS', actual_native_provider=True, database='PostgreSQL',
                                  candidate_id='fictional-unit-test', extractor='qwen-local',
                                  cases=[dict(type='receipt'), dict(type='invoice')])}
        self.packet = dict(version=1, status='accepted', final_status='completed', candidate_id='fictional-unit-test',
            source_files=acceptance.fingerprint(self.root), reports={}, checks=[dict(id=key, report='quality',
                value_pointer='/' + key.replace('/', '~1') + '/value',
                support_pointer='/' + key.replace('/', '~1') + '/support') for key in self.ids])
        self.index = self.root / 'index.json'

    def publish(self):
        for name, data in self.documents.items():
            raw = json.dumps(data).encode()
            (self.root / (name + '.json')).write_bytes(raw)
            self.packet['reports'][name] = dict(path=name + '.json', sha256=hashlib.sha256(raw).hexdigest())
        self.index.write_text(json.dumps(self.packet))

    def test_positive_packet_and_missing_packet(self):
        with self.assertRaisesRegex(ValueError, 'V1_NOT_READY'):
            acceptance.check(self.index, self.root)
        self.publish()
        self.assertEqual(acceptance.check(self.index, self.root)['per_type_checks'], 10)

    def test_proposed_policy_or_b0_fixture_is_not_model_acceptance(self):
        self.documents['policy']['status'] = 'proposed'
        self.publish()
        with self.assertRaisesRegex(ValueError, 'policy/final-open'):
            acceptance.check(self.index, self.root)
        self.documents['policy']['status'] = 'frozen'
        self.documents['candidate_e2e']['extractor'] = 'b0'
        self.publish()
        with self.assertRaisesRegex(ValueError, 'actual accepted model'):
            acceptance.check(self.index, self.root)

    def test_raw_schema_failure_or_zero_support_or_bool_support_cannot_pass(self):
        key = 'receipt/raw_schema_validity'
        for value, support in ((0, 10), (None, 10), (1, 0), (1, True)):
            self.documents['quality'][key] = dict(value=value, support=support)
            self.publish()
            with self.assertRaises(ValueError):acceptance.check(self.index, self.root)

    def test_changed_report_source_missing_metric_and_path_escape_rejected(self):
        self.publish()
        (self.root / 'quality.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            acceptance.check(self.index, self.root)
        self.publish()
        (self.root / 'src/vietdoc/new.py').write_text('new model implementation')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            acceptance.check(self.index, self.root)
        self.packet['source_files'] = acceptance.fingerprint(self.root)
        self.packet['checks'].pop()
        self.publish()
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            acceptance.check(self.index, self.root)
        self.packet['reports']['quality']['path'] = '../quality.json'
        self.index.write_text(json.dumps(self.packet))
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            acceptance.check(self.index, self.root)


if __name__ == '__main__':
    unittest.main()
