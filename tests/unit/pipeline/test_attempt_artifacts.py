"""Actual bytes, no-replace and partial-publication checks."""
import hashlib
import os
import sys
import time
import uuid

import pytest


def test_written_bytes_and_manifest_are_verified(tmp_path):
    from vietdoc.pipeline.attempt_artifacts import AttemptWriter, reserve_attempt
    job, attempt = str(uuid.uuid4()), str(uuid.uuid4())
    directory = reserve_attempt(tmp_path, job, attempt)
    writer = AttemptWriter(directory, job, attempt, time.monotonic() + 10)
    entry = writer.write("ocr.json", b'{"blocks":[]}', "ocr", "application/json")
    assert entry == dict(kind="ocr", asset_key=f"attempts/{job}/{attempt}/ocr.json",
                         sha256=hashlib.sha256(b'{"blocks":[]}').hexdigest(), size_bytes=13,
                         media_type="application/json")
    assert (directory / "ocr.json").read_bytes() == b'{"blocks":[]}'
    writer.verify()
    (directory / "ocr.json").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="OUTPUT_INVALID"):
        writer.verify()


def test_duplicate_attempt_and_file_never_overwrite(tmp_path):
    from vietdoc.pipeline.attempt_artifacts import AttemptWriter, reserve_attempt
    job, attempt = str(uuid.uuid4()), str(uuid.uuid4())
    directory = reserve_attempt(tmp_path, job, attempt)
    writer = AttemptWriter(directory, job, attempt, time.monotonic() + 10)
    writer.write("ocr.json", b"original", "ocr", "application/json")
    with pytest.raises(FileExistsError):
        reserve_attempt(tmp_path, job, attempt)
    with pytest.raises(FileExistsError):
        writer.write("ocr.json", b"replacement", "ocr", "application/json")
    assert (directory / "ocr.json").read_bytes() == b"original"


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/b", "a\\b", "a:b", "x\x00"])
def test_artifact_names_cannot_escape_attempt(tmp_path, name):
    from vietdoc.pipeline.attempt_artifacts import AttemptWriter
    writer = AttemptWriter(tmp_path, str(uuid.uuid4()), str(uuid.uuid4()), time.monotonic() + 10)
    with pytest.raises(ValueError):
        writer.write(name, b"data", "ocr", "application/json")
    assert list(tmp_path.iterdir()) == []


def test_publication_failure_has_no_final_file(tmp_path, monkeypatch):
    from vietdoc.pipeline.attempt_artifacts import AttemptWriter
    def fail(*args, **kwargs):
        raise OSError("disk failed/private/path")
    monkeypatch.setattr(os, "link", fail)
    writer = AttemptWriter(tmp_path, str(uuid.uuid4()), str(uuid.uuid4()), time.monotonic() + 10)
    with pytest.raises(OSError):
        writer.write("ocr.json", b"data", "ocr", "application/json")
    assert list(tmp_path.iterdir()) == []


def test_expired_deadline_does_not_publish(tmp_path):
    from vietdoc.pipeline.attempt_artifacts import AttemptWriter
    writer = AttemptWriter(tmp_path, str(uuid.uuid4()), str(uuid.uuid4()), time.monotonic() - 1)
    with pytest.raises(ValueError, match="COMPUTE_TIMEOUT"):
        writer.write("ocr.json", b"data", "ocr", "application/json")
    assert list(tmp_path.iterdir()) == []


def test_attempt_parent_cannot_redirect_to_another_directory(tmp_path):
    from vietdoc.pipeline.attempt_artifacts import reserve_attempt
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "attempts"
    root.mkdir()
    job, attempt = str(uuid.uuid4()), str(uuid.uuid4())
    link = root / job
    if sys.platform == "win32":
        import _winapi
        _winapi.CreateJunction(str(outside), str(link))
    else:
        link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="OUTPUT_INVALID"):
        reserve_attempt(root, job, attempt)
    assert list(outside.iterdir()) == []
