"""Tiny fictional model bytes only. Never download weights, use GPU or train."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import sys

import pytest

from vietdoc.ml import model_provision as p
from vietdoc.ml.release_manifest import ReleaseError, load_release

APPROVED = dict(approval_ref="lead-issue-55", license_ack="apache-2.0")


def test_selected_model_is_pinned_qwen3_text_model():
    assert p.MODEL_ID == "Qwen/Qwen3-1.7B"
    assert p.REVISION == "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
    assert len(p.REQUIRED_FILES) == 11
    assert "preprocessor_config.json" not in p.REQUIRED_FILES
    assert "chat_template.json" not in p.REQUIRED_FILES


def test_non_weight_lfs_assets_use_content_sha256(tmp_path,fixture_model):
    blobs,metadata,_,_=fixture_model
    entry=next(e for e in metadata['files'] if e['path']=='tokenizer.json')
    entry.update(source_hash_kind='sha256',source_hash=hashlib.sha256(blobs['tokenizer.json']).hexdigest())
    assert run(tmp_path,fixture_model)['integrity']=='verified'
    assert p.verify_snapshot(tmp_path/p.REVISION)['integrity']=='verified'


def encoded(value):
    return json.dumps(value, separators=(",", ":")).encode()


@pytest.fixture
def fixture_model(monkeypatch):
    monkeypatch.setattr(p.time, "sleep", lambda _: None)
    blobs = {name: b"fictional fixture\n" for name in p.REQUIRED_FILES}
    blobs["config.json"] = encoded(dict(model_type="qwen3", architectures=["Qwen3ForCausalLM"]))
    mapping = {}
    for i, name in enumerate(sorted(p.SHARDS)):
        tensor = f"layer.{i}"
        header = encoded({tensor: dict(dtype="BF16", shape=[2], data_offsets=[0, 4])})
        blobs[name] = struct.pack("<Q", len(header)) + header + b"\0" * 4
        mapping[tensor] = name
    blobs["model.safetensors.index.json"] = encoded(dict(metadata=dict(total_size=8), weight_map=mapping))
    metadata = dict(model_id=p.MODEL_ID, revision=p.REVISION, files=[])
    for name, data in blobs.items():
        digest = hashlib.sha256(data).hexdigest() if name in p.SHARDS else hashlib.sha1(
            f"blob {len(data)}\0".encode() + data).hexdigest()
        metadata["files"].append(dict(path=name, size_bytes=len(data), source_hash=digest,
                                     source_hash_kind="sha256" if name in p.SHARDS else "git_blob_sha1"))
    calls = []

    def download(name, directory, force):
        calls.append((name, force))
        (directory / name).write_bytes(blobs[name])

    return blobs, metadata, calls, download


def run(root, fixture_model, **overrides):
    _, metadata, _, download = fixture_model
    return p.provision(root, metadata_source=lambda: deepcopy(metadata), downloader=download,
                       **(APPROVED | overrides))


def test_gate_precedes_any_network_or_storage(tmp_path):
    root = tmp_path / "new"
    def network():
        pytest.fail("network before approval")
    with pytest.raises(p.ProvisionError, match="BLOCKED_"):
        p.provision(root, metadata_source=network)
    assert not root.exists()


@pytest.mark.parametrize("changes", [{"approval_ref": ""}, {"license_ack": "yes"}, {"license_ack": "research-evaluation"}])
def test_both_lead_reference_and_license_ack_required(tmp_path, fixture_model, changes):
    with pytest.raises(p.ProvisionError, match="BLOCKED_"):
        run(tmp_path, fixture_model, **changes)
    assert not fixture_model[2]


def test_complete_verify_existing_manifest_and_offline_idempotency(tmp_path, fixture_model):
    result = run(tmp_path, fixture_model)
    assert result == dict(model_id=p.MODEL_ID, revision=p.REVISION, status="ready", integrity="verified",
                          ready_scope="offline_pretrained_snapshot_only", production_active=False)
    folder = tmp_path / p.REVISION
    assert len(load_release(tmp_path, p.REVISION).files) == len(p.REQUIRED_FILES) + 1
    assert set(folder.iterdir()) == {folder / n for n in (*p.REQUIRED_FILES, "inventory.json", "manifest.json")}
    before = {f.name: f.read_bytes() for f in folder.iterdir()}
    count = len(fixture_model[2])
    # Existing snapshot can be verified with no network or approval variables.
    assert p.provision(tmp_path, metadata_source=lambda: pytest.fail("network")) == result
    assert len(fixture_model[2]) == count
    assert before == {f.name: f.read_bytes() for f in folder.iterdir()}


def test_real_state_transitions_are_not_runtime_activation(tmp_path, fixture_model, capsys):
    run(tmp_path, fixture_model)
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [event['status'] for event in events] == ['downloading', 'downloaded', 'verified', 'ready']
    assert events[-1]['production_active'] is False


@pytest.mark.parametrize("field,value", [("revision", "main"), ("revision", "0" * 40), ("model_id", "other/model")])
def test_wrong_pin_rejected_before_file_download(tmp_path, fixture_model, field, value):
    fixture_model[1][field] = value
    with pytest.raises(p.ProvisionError, match="PIN_MISMATCH"):
        run(tmp_path, fixture_model)
    assert not fixture_model[2] and not (tmp_path / p.REVISION).exists()


@pytest.mark.parametrize("change", ["missing", "traversal", "duplicate", "badsize", "badhash"])
def test_upstream_manifest_rejects_invalid_file_inventory(tmp_path, fixture_model, change):
    files = fixture_model[1]["files"]
    if change == "missing": files.pop()
    elif change == "traversal": files[0]["path"] = "../secret"
    elif change == "duplicate": files[1] = dict(files[0])
    elif change == "badsize": files[0]["size_bytes"] = True
    else: files[0]["source_hash"] = "invalid"
    with pytest.raises(p.ProvisionError):
        run(tmp_path, fixture_model)
    assert not fixture_model[2]


@pytest.mark.parametrize("change", ["missing", "corrupt", "extra", "inventory", "manifest"])
def test_existing_corruption_never_overwritten(tmp_path, fixture_model, change):
    run(tmp_path, fixture_model)
    root = tmp_path / p.REVISION
    if change == "missing": (root / "LICENSE").unlink()
    elif change == "corrupt": (root / "LICENSE").write_bytes(b"X" * len(fixture_model[0]["LICENSE"]))
    elif change == "extra": (root / "extra").write_bytes(b"unexpected")
    elif change == "inventory": (root / "inventory.json").write_bytes(b"{}")
    else: (root / "manifest.json").write_bytes(b"{}")
    before = {f.name: f.read_bytes() for f in root.iterdir()}
    with pytest.raises((p.ProvisionError, ReleaseError)):
        run(tmp_path, fixture_model)
    assert before == {f.name: f.read_bytes() for f in root.iterdir()}


def test_incomplete_download_preserves_staging_and_resume(tmp_path, fixture_model):
    _, _, calls, download = fixture_model
    def interrupted(name, directory, force):
        if name == "tokenizer.json":
            (directory / ".partial-cache").write_bytes(b"partial")
            raise OSError("private secret must not reach report")
        return download(name, directory, force)
    with pytest.raises(p.ProvisionError, match="DOWNLOAD_OR_CHECKSUM_FAILED"):
        p.provision(tmp_path, **APPROVED, metadata_source=lambda: fixture_model[1], downloader=interrupted)
    assert not (tmp_path / p.REVISION).exists()
    assert json.loads((tmp_path / "provision-status.json").read_bytes())["status"] == "failed"
    count = len(calls)
    assert run(tmp_path, fixture_model)["integrity"] == "verified"
    # Previously verified candidate files were not downloaded a second time.
    assert not set(name for name, _ in calls[:count]) & set(name for name, _ in calls[count:])


def test_bad_download_checksum_never_publishes(tmp_path, fixture_model):
    def corrupt(name, directory, force):
        (directory / name).write_bytes(b"wrong")
    with pytest.raises(p.ProvisionError, match="DOWNLOAD_OR_CHECKSUM_FAILED"):
        p.provision(tmp_path, **APPROVED, metadata_source=lambda: fixture_model[1], downloader=corrupt)
    assert not (tmp_path / p.REVISION).exists()


def test_inconsistent_index_rejected_even_with_correct_file_hashes(tmp_path, fixture_model):
    blobs, metadata, _, _ = fixture_model
    data = json.loads(blobs["model.safetensors.index.json"])
    data["weight_map"]["invented"] = next(iter(p.SHARDS))
    raw = encoded(data)
    blobs["model.safetensors.index.json"] = raw
    for entry in metadata["files"]:
        if entry["path"] == "model.safetensors.index.json":
            entry.update(size_bytes=len(raw), source_hash=hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest())
    with pytest.raises(p.ProvisionError, match="TENSOR_INDEX_MISMATCH"):
        run(tmp_path, fixture_model)
    assert not (tmp_path / p.REVISION).exists()


@pytest.mark.parametrize("config", [
    {"model_type": "qwen2_5_vl", "architectures": ["Qwen2_5_VLForConditionalGeneration"]},
    {"model_type": "qwen3", "architectures": ["OtherModel"]},
])
def test_wrong_model_config_cannot_publish_even_with_valid_hashes(tmp_path, fixture_model, config):
    blobs, metadata, _, _ = fixture_model
    raw = encoded(config)
    blobs["config.json"] = raw
    for entry in metadata["files"]:
        if entry["path"] == "config.json":
            entry.update(size_bytes=len(raw), source_hash=hashlib.sha1(
                f"blob {len(raw)}\0".encode() + raw).hexdigest())
    with pytest.raises(p.ProvisionError, match="MODEL_CONFIG_MISMATCH"):
        run(tmp_path, fixture_model)
    assert not (tmp_path / p.REVISION).exists()


@pytest.mark.parametrize('change', ['oversized-header', 'truncated-data', 'wrong-offsets'])
def test_safetensors_structure_checked_after_source_checksum(tmp_path, fixture_model, change):
    blobs, metadata, _, _ = fixture_model
    name = sorted(p.SHARDS)[0]
    if change == 'oversized-header': raw = struct.pack('<Q', p.MAX_JSON_BYTES + 1) + b'abc'
    elif change == 'truncated-data': raw = blobs[name][:-1]
    else:
        header = encoded({'layer.0': dict(dtype='BF16', shape=[2], data_offsets=[1, 5])})
        raw = struct.pack('<Q', len(header)) + header + b'\0' * 5
    blobs[name] = raw
    for entry in metadata['files']:
        if entry['path'] == name:
            entry.update(size_bytes=len(raw), source_hash=hashlib.sha256(raw).hexdigest())
    with pytest.raises(p.ProvisionError):
        run(tmp_path, fixture_model)
    assert not (tmp_path / p.REVISION).exists()


def test_publication_does_not_replace_even_empty_destination(tmp_path):
    source, dest = tmp_path / "stage", tmp_path / "published"
    source.mkdir()
    dest.mkdir()
    (source / "file").write_bytes(b"value")
    with pytest.raises(OSError):
        p._publish(source, dest)
    assert source.exists() and list(dest.iterdir()) == []


def test_exclusive_copy_fallback_is_readable_and_never_replaces(tmp_path, fixture_model, monkeypatch):
    monkeypatch.setattr(p, '_publish', p._copy_publish)
    assert run(tmp_path, fixture_model)['integrity'] == 'verified'
    final = tmp_path / p.REVISION
    with pytest.raises(FileExistsError):
        p._copy_publish(tmp_path / f'.staging-{p.REVISION}' / p.REVISION, final)


def test_copy_failure_never_has_completion_manifest(tmp_path, fixture_model, monkeypatch):
    run(tmp_path, fixture_model)
    source = tmp_path / p.REVISION
    target = tmp_path / 'partial'
    def fail(*args, **kwargs):
        raise OSError('disk unavailable')
    monkeypatch.setattr(p.shutil, 'copyfileobj', fail)
    with pytest.raises(OSError):
        p._copy_publish(source, target)
    assert target.is_dir() and not (target / 'manifest.json').exists()


def test_lock_fails_closed_and_does_not_remove_other_lock(tmp_path, fixture_model):
    (tmp_path / ".provision.lock").write_bytes(b"other owner")
    with pytest.raises(p.ProvisionError, match="PROVISION_LOCKED"):
        run(tmp_path, fixture_model)
    assert (tmp_path / ".provision.lock").read_bytes() == b"other owner"


def test_hub_calls_cannot_change_pin_or_use_ambient_credentials(tmp_path, monkeypatch, fixture_model):
    # Hub also stores non-weight tokenizer assets as LFS pointers.
    entry=next(e for e in fixture_model[1]['files'] if e['path']=='tokenizer.json')
    entry.update(source_hash_kind='sha256',source_hash=hashlib.sha256(fixture_model[0]['tokenizer.json']).hexdigest())
    calls = []
    def download(**kwargs):
        calls.append(kwargs)
    class Api:
        def __init__(self, **kwargs):
            assert kwargs == dict(endpoint=p.ENDPOINT, token=False)
        def model_info(self, model, **kwargs):
            assert model == p.MODEL_ID and kwargs == dict(revision=p.REVISION, files_metadata=True, token=False)
            siblings = [SimpleNamespace(rfilename=e['path'], size=e['size_bytes'], blob_id=e['source_hash'],
                        lfs=SimpleNamespace(sha256=e['source_hash']) if e['source_hash_kind']=='sha256' else None)
                        for e in fixture_model[1]['files']]
            return SimpleNamespace(id=p.MODEL_ID, sha=p.REVISION, siblings=siblings)
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(HfApi=Api, hf_hub_download=download))
    assert p.hub_metadata()==fixture_model[1]
    p.hub_download("LICENSE", tmp_path)
    assert calls == [dict(repo_id=p.MODEL_ID, revision=p.REVISION, filename="LICENSE", endpoint=p.ENDPOINT,
                          token=False, local_dir=tmp_path, force_download=False)]


def test_cli_blocked_safe_and_verify_only_never_network(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("VIETDOC_QWEN_PROVISION_APPROVAL", raising=False)
    monkeypatch.delenv("VIETDOC_QWEN_LICENSE_ACK", raising=False)
    assert p.main(["--root", str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
    assert p.main(["--root", str(tmp_path), "--verify-only"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "failed"


def test_snapshot_symlink_rejected(tmp_path, fixture_model, monkeypatch):
    target = tmp_path / "real"
    target.mkdir()
    try:
        (tmp_path / p.REVISION).symlink_to(target, target_is_directory=True)
    except OSError:
        # Exercise the same guard without adding another allowed skip to the AI gate.
        # Linux Docker executes the actual filesystem symlink branch.
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda path: path.name == p.REVISION or original(path))
    with pytest.raises(p.ProvisionError, match="UNSAFE_PATH"):
        run(tmp_path, fixture_model)
