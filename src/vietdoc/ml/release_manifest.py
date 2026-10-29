"""Verified, read-only model/pipeline releases on the models volume.

Layout (đề xuất cho M2.3/M6.1, cần Lead/Backend duyệt trước khi coi là contract):

    <models_dir>/<pipeline_manifest_id>/manifest.json
    {"manifest_version": 1,
     "pipeline_manifest_id": "<id>",
     "files": [{"path": "adapter/adapter_model.safetensors", "sha256": "<hex>", "size_bytes": 123}]}

A release is usable only when every listed file exists inside the release folder,
is not a symlink, and matches its declared size and sha256. Weights stay on the
volume (ignored by Git); only this manifest format lives in the repository.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = 1
MAX_MANIFEST_BYTES = 1024 * 1024
# Same rule as compute-request.schema.json pipeline_manifest_id.
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ReleaseError(ValueError):
    pass


@dataclass(frozen=True)
class ReleaseFile:
    path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class Release:
    manifest_id: str
    root: Path
    files: tuple[ReleaseFile, ...]

    def file(self, relative: str) -> Path:
        for item in self.files:
            if item.path == relative:
                return self.root / PurePosixPath(item.path)
        raise ReleaseError(f"{relative} is not part of release {self.manifest_id}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_entry(root: Path, entry: object) -> ReleaseFile:
    if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size_bytes"}:
        raise ReleaseError("file entry needs exactly path, sha256, size_bytes")
    raw_path, sha256, size = entry["path"], entry["sha256"], entry["size_bytes"]
    if not isinstance(raw_path, str) or not isinstance(sha256, str) or not _SHA256.match(sha256):
        raise ReleaseError("file entry has invalid path or sha256")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ReleaseError(f"{raw_path}: invalid size_bytes")
    relative = PurePosixPath(raw_path)
    if relative.is_absolute() or "\\" in raw_path or any(part in ("", ".", "..") for part in raw_path.split("/")):
        raise ReleaseError(f"{raw_path}: path must be relative inside the release")
    target = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ReleaseError(f"{raw_path}: symlinks are not allowed")
    if not target.is_file():
        raise ReleaseError(f"{raw_path}: missing")
    if target.stat().st_size != size:
        raise ReleaseError(f"{raw_path}: size mismatch")
    if _sha256(target) != sha256:
        raise ReleaseError(f"{raw_path}: sha256 mismatch")
    return ReleaseFile(raw_path, sha256, size)


def load_release(models_dir: Path, manifest_id: str) -> Release:
    if not ID_PATTERN.match(manifest_id):
        raise ReleaseError("invalid pipeline_manifest_id")
    root = models_dir / manifest_id
    if root.is_symlink() or not root.is_dir():
        raise ReleaseError("release folder missing")
    manifest_path = root / MANIFEST_NAME
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ReleaseError("manifest.json missing")
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ReleaseError("manifest.json too large")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseError("manifest.json is not valid JSON") from error
    if not isinstance(data, dict) or set(data) != {"manifest_version", "pipeline_manifest_id", "files"}:
        raise ReleaseError("manifest needs exactly manifest_version, pipeline_manifest_id, files")
    if data["manifest_version"] != MANIFEST_VERSION:
        raise ReleaseError("unsupported manifest_version")
    if data["pipeline_manifest_id"] != manifest_id:
        raise ReleaseError("pipeline_manifest_id does not match folder name")
    if not isinstance(data["files"], list) or not data["files"]:
        raise ReleaseError("files must be a non-empty list")
    files = tuple(_file_entry(root, entry) for entry in data["files"])
    if len({item.path for item in files}) != len(files):
        raise ReleaseError("duplicate file paths")
    return Release(manifest_id, root, files)


def discover_releases(models_dir: Path) -> tuple[dict[str, Release], dict[str, str]]:
    """Verify every `<id>/manifest.json` under models_dir; returns (releases, errors)."""
    releases: dict[str, Release] = {}
    errors: dict[str, str] = {}
    if not models_dir.is_dir():
        return releases, {"<models_dir>": "models directory is not mounted"}
    for child in sorted(models_dir.iterdir()):
        if not (child / MANIFEST_NAME).exists():
            continue
        try:
            releases[child.name] = load_release(models_dir, child.name)
        except (OSError, ReleaseError) as error:
            errors[child.name] = str(error) if isinstance(error, ReleaseError) else type(error).__name__
    return releases, errors
