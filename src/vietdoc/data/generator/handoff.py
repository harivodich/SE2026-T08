"""Pack existing D1 bytes and verify a relocated bundle; never render or infer."""
import argparse
from collections import Counter
import hashlib
from importlib.metadata import version
import io
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import tempfile
import zipfile

from ..manifest import asset_path, encoded, read_json, require, sha
from . import integration

VERSION = 'vietdoc.d12-handoff.v1'
ARCHIVE = 'd12-handoff.zip'
TINY_IDS = {'d12-receipt-03', 'd12-invoice-04'}
SCHEMA = 'specs/contracts/business.schema.json'
MAX_BYTES = 256 * 1024 * 1024


def member_name(name):
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name and
            not any(ord(c) < 32 for c in name), 'invalid bundle path')
    require(not PurePosixPath(name).is_absolute() and
            all(p not in ('', '.', '..') for p in name.split('/')), 'invalid bundle path')
    return name


def inventory(root, manifest, *, tiny=False):
    """Validate existing artifacts, retaining their exact root-relative paths."""
    root, manifest = Path(root).resolve(), Path(manifest).resolve()
    require(manifest.is_relative_to(root), 'manifest escapes root')
    rows = list(integration.load_artifacts(root, manifest, full_set=not tiny))
    require(not tiny or {m['sample_id'] for m, _ in rows} == TINY_IDS, 'tiny requires receipt-03 and invoice-04')
    name = manifest.relative_to(root).as_posix()
    names = [name, SCHEMA] + [a['path'] for m, _ in rows for a in m['assets'].values()]
    require(len(names) == len(set(names)), 'duplicate bundle member path')
    files = {}
    for name in sorted(names):
        member_name(name)
        path = asset_path(root, name)
        files[name] = dict(sha256=sha(path), size=path.stat().st_size)
    require(sum(f['size'] for f in files.values()) <= MAX_BYTES, 'bundle exceeds size limit')
    return dict(artifact_version=VERSION, manifest_path=manifest.relative_to(root).as_posix(),
                manifest_sha256=sha(manifest), tiny=tiny, files=files,
                samples=len(rows), document_types=dict(Counter(m['document_type'] for m, _ in rows)),
                rows=sum(len(g['items']) for _, g in rows),
                sample_ids=[m['sample_id'] for m, _ in rows])


def pack(root, manifest, output, *, tiny=False):
    root, manifest, output = Path(root).resolve(), Path(manifest).resolve(), Path(output)
    require(manifest.is_relative_to(root), 'manifest escapes root')
    require(not output.exists(), 'output already exists')
    data = inventory(root, manifest, tiny=tiny)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, record in data['files'].items():
            content = asset_path(root, name).read_bytes()
            require(hashlib.sha256(content).hexdigest() == record['sha256'], 'source changed during packing')
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content, compresslevel=9)
    data.update(archive_sha256=hashlib.sha256(buffer.getvalue()).hexdigest(),
                scope='integrity/schema/sidecar verification; no pixel QA, OCR or consumer approval',
                verification_runtime=dict(python=platform.python_version(),
                    pillow=version('Pillow'), jsonschema=version('jsonschema')),
                validator_sources={p.name: sha(p) for p in (Path(integration.__file__), Path(__file__))})
    output.mkdir(parents=True, exist_ok=False)
    (output / ARCHIVE).write_bytes(buffer.getvalue())
    (output / 'inventory.json').write_bytes(encoded(data))
    (output / 'SHA256SUMS').write_bytes(''.join(
        f'{sha(output / name)}  {name}\n' for name in (ARCHIVE, 'inventory.json')).encode('ascii'))
    return data


def verify(bundle, output):
    """Check checksums/members before extracting into a new, isolated asset root."""
    bundle, output = Path(bundle).resolve(), Path(output)
    require(not output.exists(), 'output already exists')
    sums = asset_path(bundle, 'SHA256SUMS').read_text(encoding='ascii').splitlines()
    require(len(sums) == 2, 'invalid checksum inventory')
    expected = {}
    for line in sums:
        match = re.fullmatch(r'([0-9a-f]{64})  (d12-handoff\.zip|inventory\.json)', line)
        require(match is not None and match[2] not in expected, 'invalid checksum entry')
        expected[match[2]] = match[1]
    for name, digest in expected.items():
        require(sha(asset_path(bundle, name)) == digest, f'checksum mismatch: {name}')
    data = read_json(bundle / 'inventory.json')
    require(isinstance(data, dict) and data.get('artifact_version') == VERSION and
            type(data.get('tiny')) is bool, 'unsupported handoff format')
    require(data.get('archive_sha256') == expected[ARCHIVE], 'archive inventory mismatch')
    files = data.get('files')
    require(isinstance(files, dict) and len(files) == (12 if data['tiny'] else 102), 'invalid bundle member count')
    for name, record in files.items():
        member_name(name)
        require(isinstance(record, dict) and type(record.get('size')) is int and record['size'] >= 0 and
                isinstance(record.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', record['sha256']),
                'invalid member inventory')
    require(sum(r['size'] for r in files.values()) <= MAX_BYTES, 'bundle exceeds size limit')
    contents = {}
    with zipfile.ZipFile(bundle / ARCHIVE) as archive:
        members = archive.infolist()
        require(len(members) == len(files) and {m.filename for m in members} == set(files),
                'missing/duplicate/unknown archive member')
        for info in members:
            member_name(info.filename)
            require(stat.S_ISREG(info.external_attr >> 16) and not info.flag_bits & 1,
                    'non-regular/encrypted archive member')
            record = files[info.filename]
            require(info.file_size == record['size'], 'archive member size mismatch')
            content = archive.read(info)
            require(hashlib.sha256(content).hexdigest() == record['sha256'], 'archive member hash mismatch')
            contents[info.filename] = content
    # The loader must read only the relocated copies, never checkout assets.
    with tempfile.TemporaryDirectory(prefix='d12-handoff-') as temporary:
        stage = Path(temporary)
        for name, content in contents.items():
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        manifest = asset_path(stage, data['manifest_path'])
        actual = inventory(stage, manifest, tiny=data['tiny'])
        for key, value in actual.items():
            require(data.get(key) == value, f'relocated inventory mismatch: {key}')
        output.mkdir(parents=True, exist_ok=False)
        for name, content in contents.items():
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(content)
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('pack')
    create.add_argument('--root', type=Path, required=True)
    create.add_argument('--manifest', type=Path, required=True)
    create.add_argument('--tiny', action='store_true')
    check = commands.add_parser('verify')
    check.add_argument('--bundle', type=Path, required=True)
    for command in (create, check):
        command.add_argument('--output', type=Path, required=True, help='new directory; never overwritten')
    args = parser.parse_args()
    if args.command == 'pack':
        result = pack(args.root, args.manifest, args.output, tiny=args.tiny)
    else:
        result = verify(args.bundle, args.output)
    print(encoded({k: result[k] for k in ('samples', 'document_types', 'rows', 'manifest_sha256')}).decode(), end='')


if __name__ == '__main__':
    main()
