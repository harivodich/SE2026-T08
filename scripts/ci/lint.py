"""Download audited upstream validator binaries by fixed SHA-256, then lint CI."""

import hashlib
import io
import os
from pathlib import Path
import platform
import subprocess
import tarfile
import tempfile
from urllib.request import urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[2]
TOOLS = {
    'actionlint': {
        'linux': ('https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_linux_amd64.tar.gz',
                  '8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8'),
        'windows': ('https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_windows_amd64.zip',
                    '6e7241b51e6817ea6a047693d8e6fed13b31819c9a0dd6c5a726e1592d22f6e9'),
    },
    'zizmor': {
        'linux': ('https://github.com/zizmorcore/zizmor/releases/download/v1.31.1/zizmor-x86_64-unknown-linux-gnu.tar.gz',
                  'd185f726bdaf92df78273217dfdd24ebcd6b0ef48cf3ce776ff5762b6e138c99'),
        'windows': ('https://github.com/zizmorcore/zizmor/releases/download/v1.31.1/zizmor-x86_64-pc-windows-msvc.zip',
                    '4de30371c8a3b483aecbcf0dec1fd6a2b6aae65051ca226b4f6527baac6a8c7a'),
    },
}


def download(name: str, directory: Path) -> Path:
    system = platform.system().lower()
    if system not in ('linux', 'windows') or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise ValueError('CI validators currently support x86_64 Linux/Windows only')
    url, expected = TOOLS[name][system]
    with urlopen(url, timeout=60) as response:
        data = response.read(64 * 1024 * 1024 + 1)
    if len(data) > 64 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f'{name}: download size/hash mismatch')
    filename = name + ('.exe' if system == 'windows' else '')
    if system == 'windows':
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            binary = archive.read(filename)
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
            member = archive.getmember(filename)
            if not member.isfile() or member.size > 128 * 1024 * 1024:
                raise ValueError('Invalid validator archive member')
            with archive.extractfile(member) as stream:
                binary = stream.read()
    path = directory / filename
    path.write_bytes(binary)
    path.chmod(0o700)
    return path


def main() -> None:
    files = sorted((ROOT / '.github/workflows').glob('*.yml'))
    if not files:
        raise ValueError('No CI workflows found')
    with tempfile.TemporaryDirectory(prefix='vietdoc-ci-lint-') as temporary:
        directory = Path(temporary)
        actionlint = download('actionlint', directory)
        zizmor = download('zizmor', directory)
        subprocess.run([str(actionlint), '-color', *map(str, files)], check=True, cwd=ROOT)
        subprocess.run([str(zizmor), '--offline', '--no-progress', '--strict-collection',
                        *map(str, files)], check=True, cwd=ROOT,
                       env={key: value for key, value in os.environ.items() if key != 'GH_TOKEN'})


if __name__ == '__main__':
    main()
