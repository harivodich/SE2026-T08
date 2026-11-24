"""Explicit Qwen provisioning only. No inference, GPU imports or release activation.

Hub Git blob IDs authenticate Git files; LFS SHA-256 authenticates every LFS asset.
Every verified local file also gets SHA-256 in the existing release manifest.
Storage must be owner-controlled: hashes detect corruption, not a hostile owner
rewriting both inventory and manifest. No network before the approval gate.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import time
import uuid

from vietdoc.ml.release_manifest import ReleaseError, load_release

MODEL_ID = "Qwen/Qwen3-1.7B"
REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
ENDPOINT = "https://huggingface.co"
REQUIRED_FILES = (
    "LICENSE", "README.md", "config.json", "generation_config.json",
    "tokenizer_config.json",
    "tokenizer.json", "vocab.json", "merges.txt", "model.safetensors.index.json",
    "model-00001-of-00002.safetensors", "model-00002-of-00002.safetensors",
)
SHARDS = frozenset(name for name in REQUIRED_FILES if name.endswith(".safetensors"))
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_FILE_BYTES = 10 * 1024**3


class ProvisionError(ValueError):
    """Safe code only, never an upstream exception or credential."""


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProvisionError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _decode(data):
    if len(data) > MAX_JSON_BYTES:
        raise ProvisionError("METADATA_TOO_LARGE")
    return json.loads(data, object_pairs_hook=_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ProvisionError("INVALID_JSON")))


def _no_links(path):
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            if item.is_symlink() or getattr(item.lstat(), "st_file_attributes", 0) & 0x400:
                raise ProvisionError("UNSAFE_PATH")


def _read(path):
    _no_links(path)
    with path.open("rb") as stream:
        return _decode(stream.read(MAX_JSON_BYTES + 1))


def _json(path, data, scratch=None):
    _no_links(path)
    temporary = (scratch or path.parent) / f".{path.name}.{uuid.uuid4()}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write((json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)  # Only mutable staging/status metadata, never final snapshots.
    finally:
        temporary.unlink(missing_ok=True)


def _identity(data):
    if not isinstance(data, dict) or data.get("model_id") != MODEL_ID or data.get("revision") != REVISION:
        raise ProvisionError("PIN_MISMATCH")


def _metadata(data):
    _identity(data)
    entries = data.get("files")
    if not isinstance(entries, list) or len(entries) != len(REQUIRED_FILES):
        raise ProvisionError("FILE_SET_MISMATCH")
    found = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "size_bytes", "source_hash", "source_hash_kind"}:
            raise ProvisionError("INVALID_METADATA")
        name, size, digest, kind = (entry[key] for key in ("path", "size_bytes", "source_hash", "source_hash_kind"))
        if name not in REQUIRED_FILES or name in found:
            raise ProvisionError("FILE_SET_MISMATCH")
        limit = MAX_FILE_BYTES if name in SHARDS else MAX_JSON_BYTES
        if type(size) is not int or not 0 < size <= limit:
            raise ProvisionError("INVALID_SIZE")
        allowed_kinds = {"sha256"} if name in SHARDS else {"sha256", "git_blob_sha1"}
        if kind not in allowed_kinds or not isinstance(digest, str) or not re.fullmatch(
                r"[0-9a-f]{64}" if kind == "sha256" else r"[0-9a-f]{40}", digest):
            raise ProvisionError("INVALID_SOURCE_HASH")
        found[name] = entry
    return found


def _verify_file(root, entry):
    path = root / entry["path"]
    _no_links(path)
    if not path.is_file() or path.stat().st_size != entry["size_bytes"]:
        raise ProvisionError("FILE_SIZE_OR_MISSING")
    sha = hashlib.sha256()
    upstream = hashlib.sha256() if entry["source_hash_kind"] == "sha256" else hashlib.sha1()
    if entry["source_hash_kind"] == "git_blob_sha1":
        upstream.update(f"blob {entry['size_bytes']}\0".encode())
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
            upstream.update(chunk)
    if upstream.hexdigest() != entry["source_hash"]:
        raise ProvisionError("CHECKSUM_MISMATCH")
    return dict(path=entry["path"], size_bytes=entry["size_bytes"], sha256=sha.hexdigest())


def _safetensors(root):
    index = _read(root / "model.safetensors.index.json")
    if not isinstance(index, dict) or not isinstance(index.get("metadata"), dict):
        raise ProvisionError("INVALID_SAFETENSORS_INDEX")
    mapping = index.get("weight_map")
    if not isinstance(mapping, dict) or not mapping or set(mapping.values()) != SHARDS:
        raise ProvisionError("INVALID_SAFETENSORS_INDEX")
    seen, total = {}, 0
    widths = {"BOOL": 1, "U8": 1, "I8": 1, "I16": 2, "U16": 2, "F16": 2,
              "BF16": 2, "I32": 4, "U32": 4, "F32": 4, "I64": 8, "U64": 8, "F64": 8}
    for name in sorted(SHARDS):
        path = root / name
        _no_links(path)
        with path.open("rb") as stream:
            prefix = stream.read(8)
            if len(prefix) != 8:
                raise ProvisionError("INVALID_SAFETENSORS_HEADER")
            length = struct.unpack("<Q", prefix)[0]
            if not 0 < length <= MAX_JSON_BYTES or length + 8 > path.stat().st_size:
                raise ProvisionError("INVALID_SAFETENSORS_HEADER")
            header = _decode(stream.read(length))
        if not isinstance(header, dict):
            raise ProvisionError("INVALID_SAFETENSORS_HEADER")
        cursor = 0
        tensors = []
        for key, value in header.items():
            if key == "__metadata__":
                continue
            if not isinstance(value, dict):
                raise ProvisionError("INVALID_TENSOR")
            shape, offsets, dtype = value.get("shape"), value.get("data_offsets"), value.get("dtype")
            if (not isinstance(shape, list) or any(type(d) is not int or d < 0 for d in shape)
                    or not isinstance(offsets, list) or len(offsets) != 2
                    or any(type(d) is not int or d < 0 for d in offsets) or dtype not in widths):
                raise ProvisionError("INVALID_TENSOR")
            start, end = offsets
            if end - start != math.prod(shape) * widths[dtype] or key in seen or mapping.get(key) != name:
                raise ProvisionError("TENSOR_INDEX_MISMATCH")
            seen[key] = name
            tensors.append((start, end))
        for start, end in sorted(tensors):
            if start != cursor:
                raise ProvisionError("TENSOR_OFFSETS_INVALID")
            cursor = end
        if cursor != path.stat().st_size - 8 - length:
            raise ProvisionError("TENSOR_DATA_INCOMPLETE")
        total += cursor
    if seen != mapping or type(index.get("metadata", {}).get("total_size")) is not int or index["metadata"]["total_size"] != total:
        raise ProvisionError("TENSOR_INDEX_MISMATCH")


def verify_snapshot(root):
    """Offline verify using the existing release schema/loader, no Hub dependency."""
    _no_links(root)
    release = load_release(root.parent, root.name)
    if release.manifest_id != REVISION:
        raise ProvisionError("PIN_MISMATCH")
    inventory = _read(root / "inventory.json")
    if inventory.get("inventory_version") != 1:
        raise ProvisionError("INVALID_INVENTORY")
    expected = _metadata(inventory)
    entries = [_verify_file(root, expected[name]) for name in REQUIRED_FILES]
    if inventory.get("local_files") != entries:
        raise ProvisionError("INVENTORY_HASH_MISMATCH")
    inventory_hash = hashlib.sha256((root / "inventory.json").read_bytes()).hexdigest()
    wanted = entries + [dict(path="inventory.json", size_bytes=(root / "inventory.json").stat().st_size, sha256=inventory_hash)]
    if {item.path: (item.size_bytes, item.sha256) for item in release.files} != {
            item["path"]: (item["size_bytes"], item["sha256"]) for item in wanted}:
        raise ProvisionError("MANIFEST_FILE_SET_MISMATCH")
    if set(item.name for item in root.iterdir()) != set(REQUIRED_FILES) | {"inventory.json", "manifest.json"}:
        raise ProvisionError("UNEXPECTED_SNAPSHOT_FILES")
    _safetensors(root)
    config = _read(root / "config.json")
    if config.get("model_type") != "qwen3" or config.get("architectures") != ["Qwen3ForCausalLM"]:
        raise ProvisionError("MODEL_CONFIG_MISMATCH")
    return dict(model_id=MODEL_ID, revision=REVISION, status="ready", integrity="verified",
                ready_scope="offline_pretrained_snapshot_only", production_active=False)


def hub_metadata():
    from huggingface_hub import HfApi
    info = HfApi(endpoint=ENDPOINT, token=False).model_info(
        MODEL_ID, revision=REVISION, files_metadata=True, token=False)
    if info.sha != REVISION or info.id != MODEL_ID:
        raise ProvisionError("PIN_MISMATCH")
    selected = {item.rfilename: item for item in info.siblings if item.rfilename in REQUIRED_FILES}
    if set(selected) != set(REQUIRED_FILES):
        raise ProvisionError("FILE_SET_MISMATCH")
    files = []
    for name in REQUIRED_FILES:
        item = selected[name]
        digest = item.lfs.sha256 if item.lfs else item.blob_id
        files.append(dict(path=name, size_bytes=item.size, source_hash=digest,
                          source_hash_kind="sha256" if item.lfs else "git_blob_sha1"))
    data = dict(model_id=MODEL_ID, revision=REVISION, files=files)
    _metadata(data)
    return data


def hub_download(name, directory, force=False):
    if name not in REQUIRED_FILES:
        raise ProvisionError("FILE_SET_MISMATCH")
    from huggingface_hub import hf_hub_download
    # No ambient token, custom endpoint, repo/revision argument or model code execution.
    return hf_hub_download(repo_id=MODEL_ID, revision=REVISION, filename=name,
                           endpoint=ENDPOINT, token=False, local_dir=directory,
                           force_download=force)


def _publish(source, target):
    """Prefer atomic no-replace rename; Desktop binds may need exclusive copies.

    Fallback reserves a NEW directory, opens each destination with xb, and copies
    manifest last. It is not a multi-file transaction. A killed publish leaves an
    unusable partial directory, never READY; operator quarantine is then required.
    """
    if sys.platform == "win32":
        os.rename(source, target)  # Windows rename rejects any existing destination.
        return "atomic_directory_rename"
    libc = ctypes.CDLL(None, use_errno=True)
    function = getattr(libc, "renameat2", None)
    if function is not None:
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        if function(-100, os.fsencode(source), -100, os.fsencode(target), 1) == 0:
            return "atomic_directory_rename"
        code = ctypes.get_errno()
        if code not in {errno.EINVAL, errno.ENOSYS, errno.ENOTSUP}:
            raise OSError(code, os.strerror(code))
    return _copy_publish(source, target)


def _copy_publish(source, target):
    target.mkdir()  # Exclusive reservation, NEVER replace an existing final directory.
    names = sorted(item.name for item in source.iterdir() if item.name != "manifest.json")
    for name in [*names, "manifest.json"]:
        _no_links(source / name)
        with (source / name).open("rb") as src, (target / name).open("xb") as dest:
            shutil.copyfileobj(src, dest, 1024 * 1024)
            dest.flush()
            os.fsync(dest.fileno())
    return "exclusive_copy_manifest_last"


@contextmanager
def _lock(root):
    path = root / ".provision.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ProvisionError("PROVISION_LOCKED") from None
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        path.unlink()


def _event(root, status, **extra):
    data = dict(model_id=MODEL_ID, revision=REVISION, status=status, **extra)
    _json(root / "provision-status.json", data)
    print(json.dumps(data), flush=True)


def provision(root, *, approval_ref="", license_ack="", metadata_source=hub_metadata,
              downloader=hub_download, attempts=3):
    root = Path(root).absolute()
    _no_links(root)
    final = root / REVISION
    if final.exists() or final.is_symlink():
        return verify_snapshot(final)  # Idempotent, offline, no mutation even if corrupt.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/#-]{2,199}", approval_ref) or license_ack != "apache-2.0":
        raise ProvisionError("BLOCKED_APPROVAL_AND_LICENSE_REQUIRED")
    if type(attempts) is not int or not 1 <= attempts <= 3:
        raise ProvisionError("INVALID_RETRY_LIMIT")
    root.mkdir(parents=True, exist_ok=True)
    _no_links(root)
    with _lock(root):
        if final.exists():
            return verify_snapshot(final)
        stage = root / f".staging-{REVISION}"
        candidate, download = stage / REVISION, stage / "download"
        _no_links(candidate)
        _no_links(download)
        candidate.mkdir(parents=True, exist_ok=True)
        download.mkdir(exist_ok=True)
        try:
            _event(root, "downloading")
            metadata_path = stage / "upstream.json"
            if metadata_path.exists():
                metadata = _read(metadata_path)
            else:
                metadata = metadata_source()
                _metadata(metadata)
                _json(metadata_path, metadata)
            expected = _metadata(metadata)
            entries = []
            for name in REQUIRED_FILES:
                entry = expected[name]
                try:
                    verified = _verify_file(candidate, entry)
                except (OSError, ProvisionError):
                    verified = None
                if verified is None:
                    # Resume Hub partials. A known corrupt completed staged file forces refresh.
                    _no_links(download / name)
                    force = False
                    if (download / name).exists():
                        try:
                            _verify_file(download, entry)
                        except ProvisionError:
                            force = True
                    for attempt in range(attempts):
                        try:
                            downloader(name, download, force)
                            _verify_file(download, entry)
                            break
                        except Exception as error:
                            if attempt + 1 == attempts:
                                raise ProvisionError("DOWNLOAD_OR_CHECKSUM_FAILED") from None
                            if isinstance(error, ProvisionError):
                                force = True
                            time.sleep(min(attempt + 1, 2))
                    _no_links(candidate / name)
                    temporary = stage / f".{name}.{uuid.uuid4()}.tmp"
                    try:
                        with (download / name).open("rb") as source, temporary.open("xb") as dest:
                            shutil.copyfileobj(source, dest, 1024 * 1024)
                            dest.flush()
                            os.fsync(dest.fileno())
                        os.replace(temporary, candidate / name)  # Staging only.
                    finally:
                        temporary.unlink(missing_ok=True)
                    verified = _verify_file(candidate, entry)
                entries.append(verified)
            _event(root, "downloaded", files=len(entries))
            _safetensors(candidate)
            inventory = dict(metadata, inventory_version=1, license_ack=license_ack,
                             approval_ref=approval_ref, local_files=entries)
            _json(candidate / "inventory.json", inventory, stage)
            inv = candidate / "inventory.json"
            manifest_files = entries + [dict(path=inv.name, size_bytes=inv.stat().st_size,
                                             sha256=hashlib.sha256(inv.read_bytes()).hexdigest())]
            _json(candidate / "manifest.json", dict(manifest_version=1, pipeline_manifest_id=REVISION, files=manifest_files), stage)
            verify_snapshot(candidate)
            _event(root, "verified", files=len(entries))
            publication_mode = _publish(candidate, final)
            result = verify_snapshot(final)
            _event(root, "ready", integrity="verified", production_active=False, publication_mode=publication_mode)
            return result
        except Exception:
            _event(root, "failed", code="PROVISION_FAILED", final_published=final.exists())
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/provision"))
    parser.add_argument("--verify-only", action="store_true", help="Offline, read-only; never downloads")
    args = parser.parse_args(argv)
    try:
        if args.verify_only:
            result = verify_snapshot(args.root.absolute() / REVISION)
        else:
            result = provision(args.root, approval_ref=os.getenv("VIETDOC_QWEN_PROVISION_APPROVAL", ""),
                               license_ack=os.getenv("VIETDOC_QWEN_LICENSE_ACK", ""))
        print(json.dumps(result))
        return 0
    except Exception:
        code = "VERIFY_OR_PROVISION_FAILED"
        error = sys.exc_info()[1]
        if isinstance(error, ProvisionError):
            code = str(error)
        print(json.dumps(dict(status="blocked" if code.startswith("BLOCKED_") else "failed", code=code,
                              model_id=MODEL_ID, revision=REVISION, production_active=False)))
        return 2 if code.startswith("BLOCKED_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
