"""Existing-byte D1 handoff, relocation and hostile archive regressions."""
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile

from vietdoc.data.generator import handoff, integration
from vietdoc.data.manifest import encoded, sha

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'tests/fixtures/d12/manifest.json'


class HandoffTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.bundle = self.base / 'bundle'
        self.inventory = handoff.pack(ROOT, MANIFEST, self.bundle, tiny=True)

    def checksum(self):
        (self.bundle / 'SHA256SUMS').write_bytes(''.join(
            f'{sha(self.bundle/name)}  {name}\n' for name in (handoff.ARCHIVE, 'inventory.json')).encode('ascii'))

    def rewrite_archive(self, change):
        target = self.bundle / handoff.ARCHIVE
        with zipfile.ZipFile(target) as archive:
            members = [(i, archive.read(i)) for i in archive.infolist()]
        members = change(members)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            for info, content in members:
                archive.writestr(info, content)
        target.write_bytes(buffer.getvalue())
        self.inventory['archive_sha256'] = sha(target)
        (self.bundle / 'inventory.json').write_bytes(encoded(self.inventory))
        self.checksum()

    def test_exact_bytes_relocate_and_no_overwrite(self):
        output = self.base / 'consumer'
        actual = handoff.verify(self.bundle, output)
        self.assertEqual((actual['samples'], actual['rows']), (2, 6))
        self.assertEqual(len(actual['files']), 12)
        for name, record in actual['files'].items():
            self.assertEqual((output/name).read_bytes(), (ROOT/name).read_bytes())
            self.assertEqual(sha(output/name), record['sha256'])
        with self.assertRaisesRegex(ValueError, 'output already exists'):
            handoff.verify(self.bundle, output)
        with self.assertRaisesRegex(ValueError, 'output already exists'):
            handoff.pack(ROOT, MANIFEST, self.bundle, tiny=True)

    def test_repack_is_byte_identical(self):
        other = self.base / 'second'
        handoff.pack(ROOT, MANIFEST, other, tiny=True)
        for name in (handoff.ARCHIVE, 'inventory.json', 'SHA256SUMS'):
            self.assertEqual((self.bundle/name).read_bytes(), (other/name).read_bytes())

    def test_archive_checksum_corruption_does_not_create_output(self):
        with (self.bundle/handoff.ARCHIVE).open('ab') as stream:
            stream.write(b'drift')
        output = self.base / 'consumer'
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            handoff.verify(self.bundle, output)
        self.assertFalse(output.exists())

    def test_modified_member_with_updated_archive_hash_still_fails(self):
        self.rewrite_archive(lambda members: [(i, b'wrong' if j == 0 else b)
                                             for j, (i, b) in enumerate(members)])
        with self.assertRaisesRegex(ValueError, 'member size mismatch|member hash mismatch'):
            handoff.verify(self.bundle, self.base/'consumer')

    def test_symlink_member_rejected(self):
        def change(members):
            members[0][0].external_attr = (stat.S_IFLNK | 0o777) << 16
            return members
        self.rewrite_archive(change)
        with self.assertRaisesRegex(ValueError, 'non-regular'):
            handoff.verify(self.bundle, self.base/'consumer')

    def test_unsafe_paths_and_duplicate_members(self):
        for name in ('../escape', '/absolute', 'C:/drive', 'a\\b', 'a//b', 'a/./b', 'a\x00b'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'invalid bundle path'):
                handoff.member_name(name)
        def change(members):
            members[0][0].filename = members[1][0].filename
            return members
        self.rewrite_archive(change)
        with self.assertRaisesRegex(ValueError, 'missing/duplicate/unknown'):
            handoff.verify(self.bundle, self.base/'consumer')

    def test_normal_and_optimized_cli(self):
        for optimized in (False, True):
            command = [sys.executable, *(['-O'] if optimized else []), '-m',
                'vietdoc.data.generator.handoff', 'verify', '--bundle', str(self.bundle),
                '--output', str(self.base/str(optimized))]
            run = subprocess.run(command, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr.decode())
            self.assertEqual(json.loads(run.stdout)['samples'], 2)
        (self.bundle/'SHA256SUMS').write_bytes(b'invalid\n')
        for optimized in (False, True):
            command = [sys.executable, *(['-O'] if optimized else []), '-m',
                'vietdoc.data.generator.handoff', 'verify', '--bundle', str(self.bundle),
                '--output', str(self.base/('corrupt'+str(optimized)))]
            run = subprocess.run(command, capture_output=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn(b'invalid checksum inventory', run.stderr)

    def test_full_set_pack_and_relocated_consumer(self):
        # Real fresh output; this test does not depend on ignored historical assets.
        with tempfile.TemporaryDirectory(dir=ROOT/'datasets/processed') as temporary:
            source = Path(temporary)
            manifest = source/'manifest.json'
            integration.build(ROOT, source/'samples', manifest, font_path=integration.resolve_font())
            bundle = self.base/'full'
            handoff.pack(ROOT, manifest, bundle)
            result = handoff.verify(bundle, self.base/'full-consumer')
            self.assertEqual(result['samples'], 20)
            self.assertEqual(result['document_types'], {'receipt': 10, 'invoice': 10})
            self.assertEqual(result['rows'], 204)
            self.assertEqual(len(result['files']), 102)


if __name__ == '__main__':
    unittest.main()
