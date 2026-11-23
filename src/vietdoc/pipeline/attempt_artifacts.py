"""Service-owned attempt files; exclusive publication, never replace existing bytes.

Storage must be private to the service. Individual hard-link publications are
atomic/no-replace on supported local Windows/Linux filesystems, NOT a multi-file
transaction. Failed attempts are retained for owner-managed orphan handling.
"""
import hashlib
import os
from pathlib import Path
import re
import stat
import time
import uuid


class ArtifactError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def check_deadline(deadline: float):
    if time.monotonic() >= deadline:
        raise ArtifactError("COMPUTE_TIMEOUT")


def _no_links(path: Path):
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ArtifactError("OUTPUT_INVALID")


def _uuid(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ArtifactError("OUTPUT_INVALID")


def reserve_attempt(root: Path, job_id: str, attempt_id: str) -> Path:
    _uuid(job_id)
    _uuid(attempt_id)
    root = Path(root).absolute()
    _no_links(root)
    root.mkdir(parents=True, exist_ok=True)
    parent = root / job_id
    _no_links(parent)
    parent.mkdir(exist_ok=True)
    target = parent / attempt_id
    _no_links(target)
    target.mkdir(exist_ok=False)
    return target


class AttemptWriter:
    def __init__(self, directory: Path, job_id: str, attempt_id: str, deadline: float):
        _uuid(job_id)
        _uuid(attempt_id)
        self.directory, self.deadline = Path(directory), deadline
        _no_links(self.directory)
        self.prefix = f"attempts/{job_id}/{attempt_id}/"
        self.artifacts: list[dict] = []

    def write(self, name: str, data: bytes, kind: str, media_type: str) -> dict:
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", name):
            raise ArtifactError("OUTPUT_INVALID")
        if not isinstance(data, bytes) or not 0 < len(data) <= 50 * 1024 * 1024:
            raise ArtifactError("OUTPUT_INVALID")
        check_deadline(self.deadline)
        _no_links(self.directory)
        target = self.directory / name
        _no_links(target)
        temporary = self.directory / f".{uuid.uuid4()}.tmp"
        try:
            with temporary.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            check_deadline(self.deadline)
            # os.rename/os.replace may overwrite on POSIX. link fails if target
            # exists and fails closed on filesystems without hard-link support.
            os.link(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        entry = dict(kind=kind, asset_key=self.prefix + name, sha256=hashlib.sha256(data).hexdigest(),
                     size_bytes=len(data), media_type=media_type)
        self.artifacts.append(entry)
        check_deadline(self.deadline)
        return entry

    def verify(self):
        for entry in self.artifacts:
            check_deadline(self.deadline)
            path = self.directory / entry["asset_key"].removeprefix(self.prefix)
            _no_links(path)
            data = path.read_bytes()
            if len(data) != entry["size_bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise ArtifactError("OUTPUT_INVALID")
        check_deadline(self.deadline)
