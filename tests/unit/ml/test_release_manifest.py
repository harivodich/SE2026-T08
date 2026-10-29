import hashlib
import json
import os

import pytest

from vietdoc.ml.release_manifest import ReleaseError, discover_releases, load_release

CONTENT = b"fictional adapter bytes for tests"


def write_release(models, manifest_id="rules.v1", files=None, **overrides):
    root = models / manifest_id
    (root / "adapter").mkdir(parents=True)
    (root / "adapter" / "weights.data").write_bytes(CONTENT)
    entry = {"path": "adapter/weights.data", "sha256": hashlib.sha256(CONTENT).hexdigest(), "size_bytes": len(CONTENT)}
    manifest = {"manifest_version": 1, "pipeline_manifest_id": manifest_id, "files": files or [entry]}
    manifest.update(overrides)
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root, entry


def test_verified_release_loads(tmp_path):
    root, entry = write_release(tmp_path)
    release = load_release(tmp_path, "rules.v1")
    assert release.files[0].sha256 == entry["sha256"]
    assert release.file("adapter/weights.data") == root / "adapter" / "weights.data"


@pytest.mark.parametrize(
    "change",
    [
        {"sha256": "0" * 64},
        {"size_bytes": 1},
        {"path": "adapter/missing.data"},
        {"path": "../outside.data"},
        {"path": "/etc/passwd"},
        {"path": "adapter\\weights.data"},
        {"extra": True},
    ],
)
def test_bad_file_entries_are_rejected(tmp_path, change):
    _, entry = write_release(tmp_path)
    write_manifest = {**entry, **change}
    (tmp_path / "rules.v1" / "manifest.json").write_text(
        json.dumps({"manifest_version": 1, "pipeline_manifest_id": "rules.v1", "files": [write_manifest]}),
        encoding="utf-8",
    )
    with pytest.raises(ReleaseError):
        load_release(tmp_path, "rules.v1")


@pytest.mark.parametrize(
    "overrides",
    [{"manifest_version": 2}, {"pipeline_manifest_id": "other.v1"}, {"unexpected": 1}],
)
def test_bad_manifest_header_is_rejected(tmp_path, overrides):
    write_release(tmp_path, **overrides)
    with pytest.raises(ReleaseError):
        load_release(tmp_path, "rules.v1")


def test_invalid_manifest_id_is_rejected(tmp_path):
    with pytest.raises(ReleaseError):
        load_release(tmp_path, "../rules.v1")


def test_symlinked_file_is_rejected(tmp_path):
    _, entry = write_release(tmp_path)
    target = tmp_path / "rules.v1" / "adapter" / "weights.data"
    link = tmp_path / "rules.v1" / "adapter" / "link.data"
    try:
        os.symlink(target, link)
    except OSError:
        pytest.skip("symlink creation not permitted on this host")
    (tmp_path / "rules.v1" / "manifest.json").write_text(
        json.dumps({"manifest_version": 1, "pipeline_manifest_id": "rules.v1", "files": [{**entry, "path": "adapter/link.data"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ReleaseError):
        load_release(tmp_path, "rules.v1")


def test_discover_reports_good_and_bad_releases(tmp_path):
    write_release(tmp_path, "good.v1")
    write_release(tmp_path, "bad.v1")
    (tmp_path / "bad.v1" / "adapter" / "weights.data").write_bytes(b"tampered")
    (tmp_path / "notes").mkdir()
    releases, errors = discover_releases(tmp_path)
    assert sorted(releases) == ["good.v1"]
    assert set(errors) == {"bad.v1"}


def test_discover_reports_unmounted_directory(tmp_path):
    releases, errors = discover_releases(tmp_path / "absent")
    assert releases == {} and errors
