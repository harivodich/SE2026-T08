"""Offline producer tests; renderer input is explicitly simulated OCR."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def dataset(tmp_path):
    root = tmp_path / "root"
    shutil.copytree(ROOT / "tests/fixtures/d12", root / "tests/fixtures/d12")
    return root, root / "tests/fixtures/d12/manifest.json"


def export(root, manifest, output, **kwargs):
    from vietdoc.pipeline.extraction.predictions import export_predictions
    return export_predictions(root, manifest, output, **kwargs)


def test_d1_fixture_export_is_canonical_versioned_and_never_reads_gold(dataset, tmp_path, monkeypatch):
    root, manifest = dataset
    expected_hash = hashlib.sha256(manifest.read_bytes()).hexdigest()
    original = Path.open
    def no_gold(path, *args, **kwargs):
        assert not path.name.endswith((".gold.json", ".labels.json")), "Extractor read gold/labels"
        return original(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", no_gold)
        artifact = export(root, manifest, tmp_path / "out", renderer_fixtures=True)
    assert artifact["artifact_version"] == "vietdoc.predictions.v1"
    assert artifact["dataset_manifest_sha256"] == expected_hash
    assert artifact["normalizer_version"] == "vi-VND.v2"
    assert artifact["input_mode"] == "renderer-fixture" and artifact["actual_ocr"] is False
    assert artifact["ocr_version"] == "renderer-simulated-ocr.v1"
    assert "evaluator_version" not in artifact  # Producer has not executed an evaluator.
    assert artifact["target_evaluator_versions"] == ["d3.1.v1", "d3.2.v1"]
    records = {record["sample_id"]: record for record in artifact["predictions"]}
    receipt, invoice = records["d12-receipt-03"], records["d12-invoice-04"]
    assert receipt["status"] == invoice["status"] == "ok"
    assert receipt["payload"]["total_amount"] == "178000"
    assert receipt["payload"]["items"][0]["quantity"] == "0.5"
    assert receipt["payload"]["items"][0]["line_total"] == "40000"
    assert len(receipt["payload"]["items"]) == 3
    assert invoice["payload"]["total_amount"] == "233000"
    assert invoice["payload"]["buyer_name"] is None
    assert invoice["field_states"]["/buyer_name"] == "unknown"  # no annotation leakage
    assert invoice["payload"]["items"][0]["quantity"] == "2"
    assert "pointer" not in receipt["raw_candidates"]["/total_amount"][0]
    assert all(field["confidence"] is None for record in records.values() for field in record["field_metadata"])
    assert json.loads((tmp_path / "out/predictions.json").read_text(encoding="utf-8")) == artifact


def test_producer_requires_explicit_input_mode_and_refuses_overwrite(dataset, tmp_path):
    from vietdoc.pipeline.extraction.ocr_input import BaselineError
    root, manifest = dataset
    with pytest.raises(BaselineError):
        export(root, manifest, tmp_path / "no-mode")
    output = tmp_path / "out"
    export(root, manifest, output, renderer_fixtures=True)
    before = (output / "predictions.json").read_bytes()
    with pytest.raises(FileExistsError):
        export(root, manifest, output, renderer_fixtures=True)
    assert (output / "predictions.json").read_bytes() == before


@pytest.mark.parametrize("change", ["duplicate", "type", "traversal", "hash"])
def test_manifest_and_asset_errors_are_not_silently_skipped(dataset, tmp_path, change):
    from vietdoc.pipeline.extraction.ocr_input import BaselineError
    root, manifest = dataset
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if change == "duplicate":
        data["samples"].append(data["samples"][0])
    elif change == "type":
        data["samples"][0]["document_type"] = "third-type"
    elif change == "traversal":
        data["samples"][0]["assets"]["regions.json"]["path"] = "../outside.json"
    else:
        data["samples"][0]["assets"]["regions.json"]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(data), encoding="utf-8")
    if change in ("duplicate", "type"):
        with pytest.raises(BaselineError):
            export(root, manifest, tmp_path / "out", renderer_fixtures=True)
    else:
        artifact = export(root, manifest, tmp_path / "out", renderer_fixtures=True)
        assert len(artifact["predictions"]) == 2
        assert artifact["predictions"][0]["status"] == "failed"
        assert artifact["predictions"][0]["error"] in ("ASSET_PATH_INVALID", "ASSET_HASH_MISMATCH")
        assert artifact["predictions"][1]["status"] == "ok"


def test_cli_materializes_predictions_without_model_or_data_renderer(dataset, tmp_path):
    root, manifest = dataset
    output = tmp_path / "cli-out"
    result = subprocess.run([sys.executable, "-m", "vietdoc.entrypoints.cli.baseline",
                             "--root", str(root), "--manifest", str(manifest),
                             "--renderer-fixtures", "--output", str(output)],
                            cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] == 2
    assert (output / "predictions.json").is_file()


def write_ocr_inputs(root, manifest):
    from vietdoc.pipeline.extraction.predictions import renderer_input
    entries = json.loads(manifest.read_text(encoding="utf-8"))["samples"]
    directory = root / "ocr-inputs"
    directory.mkdir()
    records = []
    for entry in entries:
        ocr, prepared, _ = renderer_input(root, entry)
        record = {"sample_id": entry["sample_id"]}
        for key, value in (("ocr", ocr), ("prepared", prepared)):
            path = directory / f'{entry["sample_id"]}-{key}.json'
            data = json.dumps(value, ensure_ascii=False).encode("utf-8")
            path.write_bytes(data)
            record[key] = {"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(data).hexdigest()}
        records.append(record)
    data = {"artifact_version": "vietdoc.baseline-inputs.v1", "ocr_version": "renderer-simulated-ocr.v1",
            "preprocess_version": "renderer-identity.fixture.v1", "samples": records}
    path = root / "ocr-inputs.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path, data


def test_hash_pinned_ocr_input_mode_keeps_provenance_and_missing_failures(dataset, tmp_path):
    root, manifest = dataset
    inputs, data = write_ocr_inputs(root, manifest)
    data["samples"].pop()
    inputs.write_text(json.dumps(data), encoding="utf-8")
    artifact = export(root, manifest, tmp_path / "out", ocr_inputs=inputs)
    assert artifact["input_mode"] == "ocr-artifact"
    assert artifact["actual_ocr"] is None  # Consumer does not certify how supplied OCR was produced.
    assert artifact["ocr_inputs_sha256"] == hashlib.sha256(inputs.read_bytes()).hexdigest()
    assert artifact["predictions"][0]["status"] == "ok"
    assert artifact["predictions"][1] == {"sample_id": "d12-invoice-04", "status": "failed", "error": "OCR_INPUT_MISSING"}


@pytest.mark.parametrize("change", ["root_type", "duplicate", "unknown", "version"])
def test_ocr_input_manifest_rejects_invalid_identity_and_versions(dataset, tmp_path, change):
    from vietdoc.pipeline.extraction.ocr_input import BaselineError
    root, manifest = dataset
    inputs, data = write_ocr_inputs(root, manifest)
    if change == "root_type":
        data = []
    elif change == "duplicate":
        data["samples"].append(data["samples"][0])
    elif change == "unknown":
        data["samples"][0]["sample_id"] = "unknown-sample"
    else:
        data["ocr_version"] = "different.v1"
    inputs.write_text(json.dumps(data), encoding="utf-8")
    if change == "version":
        artifact = export(root, manifest, tmp_path / "out", ocr_inputs=inputs)
        assert all(record["error"] == "PROVENANCE_MISMATCH" for record in artifact["predictions"])
    else:
        with pytest.raises(BaselineError):
            export(root, manifest, tmp_path / "out", ocr_inputs=inputs)


def test_malformed_fixture_record_is_typed_failure_not_exporter_crash(dataset, tmp_path):
    root, manifest = dataset
    data = json.loads(manifest.read_text(encoding="utf-8"))
    asset = data["samples"][0]["assets"]["regions.json"]
    (root / asset["path"]).write_bytes(b"[]")
    asset["sha256"] = hashlib.sha256(b"[]").hexdigest()
    manifest.write_text(json.dumps(data), encoding="utf-8")
    artifact = export(root, manifest, tmp_path / "out", renderer_fixtures=True)
    assert artifact["predictions"][0]["status"] == "failed"
    assert artifact["predictions"][0]["error"] == "FIXTURE_INPUT_INVALID"
    assert artifact["predictions"][1]["status"] == "ok"


@pytest.mark.parametrize("sample_id", ["has.dot", "a" * 121])
def test_sample_ids_follow_data_consumer_grammar(dataset, tmp_path, sample_id):
    from vietdoc.pipeline.extraction.ocr_input import BaselineError
    root, manifest = dataset
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["samples"][0]["sample_id"] = sample_id
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BaselineError):
        export(root, manifest, tmp_path / "out", renderer_fixtures=True)
