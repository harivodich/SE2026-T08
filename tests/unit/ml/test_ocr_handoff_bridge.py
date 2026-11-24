"""Offline AI-1 handoff -> AI-2 consumer bundle bridge tests.

Uses tiny fictional fixtures and lightweight doubles only; makes no native OCR
or model quality claims.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import io
from io import BytesIO
import json
from pathlib import Path
import sys
from unittest.mock import Mock

from PIL import Image
import pytest

from vietdoc.contracts.ocr import OcrBlock, OcrPage
from vietdoc.ml import model_provision as provision
from vietdoc.ml.ocr_adapter import build_prompt
from vietdoc.ml.ocr_handoff import (
    BUNDLE_VERSION,
    HandoffBridgeError,
    compute_profile_sha256,
    export_handoff,
    main,
)
from vietdoc.ml.qwen_config import MLFailure, QwenConfig
from vietdoc.ml.qwen_smoke import _read as smoke_read
from vietdoc.pipeline.ocr import OcrError
from vietdoc.pipeline.ocr.handoff import review_manifest
from vietdoc.pipeline.ocr.paddle_adapter import _to_page

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def qwen_config():
    data = {
        "model": {
            "id": provision.MODEL_ID,
            "revision": provision.REVISION,
            "tokenizer_revision": provision.REVISION,
            "local_files_only": True,
            "trust_remote_code": False,
            "use_safetensors": True,
        },
        "execution": {"enabled": True, "runtime_activation": False},
        "input": {
            "input_profile": "ocr_text_layout_v1",
            "accept_image_input": False,
            "max_input_tokens": 3072,
            "ocr_context": {"max_tokens_when_enabled": 1024},
        },
        "output": {
            "schema_path": "specs/contracts/business.schema.json",
            "schema_sha256": "0948307b0c274d565fbe89b25d69f1692d0d6a4241352939f424ce0eba6b3ded",
        },
        "inference": {
            "enable_thinking": False,
            "do_sample": False,
            "num_beams": 1,
            "batch_size": 1,
            "max_new_tokens": 2048,
            "max_sequence_tokens": 5120,
            "selected_profile": "reference_lora",
            "input_profile": "ocr_text_layout_v1",
        },
        "profiles": {
            "reference_lora": {"device": "cpu", "dtype": "float32", "quantization": "none"},
        },
    }
    return QwenConfig.from_mapping(data, ROOT)


class StubTokenizer:
    chat_template = "official-fixture-template"
    eos_token_id, pad_token_id = 9, 0
    all_special_tokens = ["<|im_start|>", "<|im_end|>", "<think>", "</think>"]
    model_max_length = 40960

    def __len__(self):
        return 100

    def get_vocab(self):
        return {f"t{i}": i for i in range(len(self))}

    def encode(self, text, **kwargs):
        return list(range(max(1, len(text) // 8)))

    def apply_chat_template(self, messages, **kwargs):
        assert kwargs == dict(
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=False,
            return_dict=False,
        )
        self.messages = messages
        return [1, 2, 3]


def make_png(size=(100, 100), mode="RGB", color="white") -> bytes:
    with Image.new(mode, size, color) as image, BytesIO() as stream:
        image.save(stream, format="PNG")
        return stream.getvalue()


def write_engine_manifest(
    root: Path,
    *,
    manifest_id: str = "ocr-release.v1",
    create_files: bool = False,
    overrides: dict | None = None,
) -> tuple[Path, bytes]:
    root.mkdir(parents=True, exist_ok=True)
    content = b"fictional local engine release payload"
    rel_path = "ocr/model.bin"
    if create_files:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    manifest = {
        "manifest_version": 1,
        "pipeline_manifest_id": manifest_id,
        "files": [
            {
                "path": rel_path,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
        ],
    }
    if overrides:
        manifest.update(overrides)
    path = root / "engine-manifest.json"
    raw = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return path, raw


def build_ai1_handoff(
    root: Path,
    *,
    artifact_version: int = 1,
    include_failures: bool = True,
) -> tuple[Path, dict]:
    data_root = root / "data"
    data_root.mkdir(parents=True, exist_ok=True)

    samples = []
    for index, (sid, doc_type, write_file) in enumerate(
        [
            ("rec_ok", "receipt", True),
            ("inv_ok", "invoice", True),
            *([("ocr_fail", "receipt", True), ("missing_input", "invoice", False)] if include_failures else []),
        ]
    ):
        png_bytes = make_png((100, 100), color=(255 - index, 255, 255))
        png_sha = hashlib.sha256(png_bytes).hexdigest()
        if write_file:
            (data_root / f"{sid}.png").write_bytes(png_bytes)
            (data_root / f"{sid}.gold.json").write_text('{"total_amount":"45000"}', encoding="utf-8")
            (data_root / f"{sid}.txt").write_text("PRIVATE_GOLD_TRANSCRIPT", encoding="utf-8")
        samples.append(
            {
                "sample_id": sid,
                "document_type": doc_type,
                "assets": {"png": {"path": f"{sid}.png", "sha256": png_sha}},
            }
        )

    manifest_path = data_root / "manifest.json"
    manifest_path.write_text(json.dumps({"version": "d1.fixture.v1", "samples": samples}), encoding="utf-8")

    golden_v2 = json.loads((ROOT / "tests/fixtures/ocr-artifact-v2.json").read_text(encoding="utf-8"))
    mixed_provider = golden_v2["cases"][0]["provider"]

    calls = {"count": 0}
    engine = Mock()
    engine.load_seconds = 0.12
    engine.last_inference_seconds = 0.05

    def recognize(loaded, *, remaining_budget_ms):
        assert remaining_budget_ms > 0
        calls["count"] += 1
        if include_failures and calls["count"] == 3:
            raise OcrError("MODEL_OOM", "PRIVATE_ENGINE_SECRET")
        if artifact_version == 2:
            return _to_page(mixed_provider, loaded.metadata, artifact_version=2)
        w, h = loaded.metadata.canonical.width, loaded.metadata.canonical.height
        return OcrPage(
            0,
            w,
            h,
            "fictional.ocr.v1",
            (
                OcrBlock("p0-b0001", "Cửa hàng: Mẫu Hư Cấu", ((0.1, 0.1), (0.8, 0.1), (0.8, 0.2), (0.1, 0.2)), 0.95, None),
                OcrBlock("p0-b0002", "Tổng tiền: 45.000", ((0.1, 0.4), (0.8, 0.4), (0.8, 0.5), (0.1, 0.5)), 0.91, None),
            ),
        )

    engine.recognize.side_effect = recognize
    handoff_dir = root / f"handoff-v{artifact_version}"
    report = review_manifest(data_root, manifest_path, handoff_dir, engine)
    return handoff_dir, report


def test_v1_handoff_to_bridge_to_build_prompt_and_exclusion_accounting(tmp_path, qwen_config, monkeypatch, capsys):
    handoff_dir, report = build_ai1_handoff(tmp_path, artifact_version=1, include_failures=True)
    engine_manifest, manifest_bytes = write_engine_manifest(tmp_path / "release", create_files=False)
    output_dir = tmp_path / "ai2-bundle"

    original_open = Path.open

    def forbid_input_and_gold(path: Path, *args, **kwargs):
        resolved = path.resolve()
        assert not resolved.is_relative_to((tmp_path / "data").resolve()), f"Bridge must not read raw input/gold: {path}"
        assert not path.name.endswith((".gold.json", ".labels.json", ".txt", ".regions.json"))
        return original_open(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", forbid_input_and_gold)
        rc = main(
            [
                "--handoff-root",
                str(handoff_dir),
                "--engine-manifest",
                str(engine_manifest),
                "--output-dir",
                str(output_dir),
            ]
        )

    assert rc == 0
    stdout_text = capsys.readouterr().out
    assert " Mẫu Hư Cấu" not in stdout_text
    assert "45.000" not in stdout_text
    assert "PRIVATE_GOLD_TRANSCRIPT" not in stdout_text
    cli_payload = json.loads(stdout_text)
    assert cli_payload == {
        "status": "ok",
        "counts": {"requested": 4, "exported": 2, "excluded": 2, "ok": 2, "failed": 1, "not_run": 1},
        "weights_verified": False,
        "production_active": False,
    }

    index = smoke_read(output_dir / "index.json")
    assert index["bundle_version"] == BUNDLE_VERSION
    assert index["shared_wire_schema"] is False
    assert index["pilot_approval"] is False
    assert index["production_active"] is False
    assert index["engine_manifest"]["engine_sha256"] == hashlib.sha256(manifest_bytes).hexdigest()
    assert index["engine_manifest"]["weights_verified"] is False
    assert set(index["samples"]) == {"rec_ok", "inv_ok"}
    assert not (output_dir / "ocr_fail").exists()
    assert not (output_dir / "missing_input").exists()
    assert index["excluded"] == [
        {
            "sample_id": "ocr_fail",
            "document_type": "receipt",
            "status": "failed",
            "stage": "ocr",
            "reason": "MODEL_OOM",
            "error_code": "MODEL_OOM",
        },
        {
            "sample_id": "missing_input",
            "document_type": "invoice",
            "status": "not_run",
            "stage": "input",
            "reason": "INPUT_ARTIFACT_UNAVAILABLE",
            "error_code": "INPUT_ARTIFACT_UNAVAILABLE",
        },
    ]

    expected_profile_sha = compute_profile_sha256(
        report["profile"],
        artifact_version=1,
        ocr_version="fictional.ocr.v1",
    )
    assert index["profile"]["profile_sha256"] == expected_profile_sha

    samples_by_id = {s["sample_id"]: s for s in report["samples"]}
    for sid, doc_type in (("rec_ok", "receipt"), ("inv_ok", "invoice")):
        sample_dir = output_dir / sid
        assert {p.name for p in sample_dir.iterdir()} == {"ocr.json", "prepared.json", "provenance.json"}
        ocr = smoke_read(sample_dir / "ocr.json")
        prepared = smoke_read(sample_dir / "prepared.json")
        provenance = smoke_read(sample_dir / "provenance.json")

        canonical_bytes = (handoff_dir / sid / "canonical.png").read_bytes()
        assert provenance == {
            "input_sha256": samples_by_id[sid]["input_sha256"],
            "canonical_sha256": hashlib.sha256(canonical_bytes).hexdigest(),
            "engine_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "profile_sha256": expected_profile_sha,
        }
        entry = index["samples"][sid]
        assert entry["document_type"] == doc_type
        assert entry["status"] == "ok"
        assert entry["paths"] == {
            "ocr": f"{sid}/ocr.json",
            "prepared": f"{sid}/prepared.json",
            "provenance": f"{sid}/provenance.json",
        }
        assert entry["hashes"]["ocr_sha256"] == hashlib.sha256((sample_dir / "ocr.json").read_bytes()).hexdigest()
        assert entry["hashes"]["prepared_sha256"] == hashlib.sha256((sample_dir / "prepared.json").read_bytes()).hexdigest()
        assert entry["hashes"]["provenance_sha256"] == hashlib.sha256((sample_dir / "provenance.json").read_bytes()).hexdigest()

        tokenizer = StubTokenizer()
        prompt = build_prompt(ocr, prepared, provenance, doc_type, qwen_config, tokenizer)
        assert prompt.input_ids == (1, 2, 3)
        assert prompt.provenance["input_sha256"] == provenance["input_sha256"]
        assert prompt.provenance["canonical_sha256"] == provenance["canonical_sha256"]
        assert prompt.provenance["engine_sha256"] == provenance["engine_sha256"]
        assert prompt.provenance["profile_sha256"] == provenance["profile_sha256"]
        user_msg = json.loads(prompt.messages[1]["content"])
        assert user_msg["document_type"] == doc_type
        assert [b["text"] for b in user_msg["ocr"]["blocks"]] == ["Cửa hàng: Mẫu Hư Cấu", "Tổng tiền: 45.000"]


def test_partial_v2_handoff_preserves_readable_blocks_and_unreadable_diagnostics(tmp_path, qwen_config):
    handoff_dir, report = build_ai1_handoff(tmp_path, artifact_version=2, include_failures=False)
    engine_manifest, _ = write_engine_manifest(tmp_path / "release", create_files=True)
    output_dir = tmp_path / "bundle-v2"

    index = export_handoff(handoff_dir, engine_manifest, output_dir, sample_ids=["inv_ok"])
    assert index["engine_manifest"]["weights_verified"] is True
    assert " with local release files verified" in index["provenance_assurance"]["engine_sha256"]
    assert set(index["samples"]) == {"inv_ok"}
    assert index["excluded"] == [
        {
            "sample_id": "rec_ok",
            "document_type": "receipt",
            "status": "ok",
            "stage": "export",
            "reason": "NOT_SELECTED",
            "error_code": None,
        }
    ]

    sample_dir = output_dir / "inv_ok"
    ocr = smoke_read(sample_dir / "ocr.json")
    prepared = smoke_read(sample_dir / "prepared.json")
    provenance = smoke_read(sample_dir / "provenance.json")
    assert ocr["artifact_version"] == 2
    assert ocr["recognition_status"] == "partial"
    assert ocr["review_flags"] == ["OCR_UNREADABLE_REGIONS"]

    prompt = build_prompt(ocr, prepared, provenance, "invoice", qwen_config, StubTokenizer())
    assert "OCR_UNREADABLE_REGIONS" in prompt.diagnostics
    user_payload = json.loads(prompt.messages[1]["content"])
    assert [b["block_id"] for b in user_payload["ocr"]["blocks"]] == ["p0-b0001", "p0-b0004"]
    assert [b["text"] for b in user_payload["ocr"]["blocks"]] == ["Có chữ", "80.000"]
    assert [(r["region_id"], r["reason"]) for r in user_payload["ocr"]["unreadable_regions"]] == [
        ("p0-b0002", "EMPTY_RECOGNITION"),
        ("p0-b0003", "EMPTY_RECOGNITION"),
    ]
    assert index["profile"]["profile_sha256"] == compute_profile_sha256(
        report["profile"],
        artifact_version=2,
        ocr_version=ocr["ocr_version"],
    )


def test_profile_sha256_excludes_timing_hardware_and_sample_ids_and_handles_missing_source_canonical_hash(tmp_path):
    handoff_dir, _ = build_ai1_handoff(tmp_path, artifact_version=1, include_failures=False)
    engine_manifest, _ = write_engine_manifest(tmp_path / "release")

    report_path = handoff_dir / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    baseline_profile_sha = compute_profile_sha256(
        report["profile"],
        artifact_version=1,
        ocr_version=report["samples"][0]["ocr_version"],
    )

    # Remove optional recorded canonical sha256/size_bytes/rgb_pixel_sha256 and mutate timing/hardware.
    report["hardware"] = "Different-Hardware-Host"
    report["python"] = "3.99.0"
    report["engine_load_seconds"] = 99.5
    for sample in report["samples"]:
        sample["ocr_seconds"] = 42.25
        sample["duration_seconds"] = 50.0
        sample["canonical"] = {"width": sample["canonical"]["width"], "height": sample["canonical"]["height"]}
        (handoff_dir / sample["sample_id"] / "run.json").write_text(json.dumps(sample, indent=2), encoding="utf-8")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    output_dir = tmp_path / "bundle-no-source-hash"
    index = export_handoff(handoff_dir, engine_manifest, output_dir)
    entry = index["samples"]["rec_ok"]
    actual_png_sha = hashlib.sha256((handoff_dir / "rec_ok/canonical.png").read_bytes()).hexdigest()
    assert entry["provenance"]["profile_sha256"] == baseline_profile_sha
    assert entry["provenance"]["canonical_sha256"] == actual_png_sha
    assert entry["canonical"]["source_hash_recorded"] is False
    assert entry["hash_origins"]["canonical_sha256"] == "computed_from_verified_canonical_png_bytes_no_source_hash_recorded"
    assert "not_upstream_origin_proof" in entry["hash_origins"]["ocr_sha256"]


@pytest.mark.parametrize(
    "mutation",
    [
        "corrupt_png_bytes",
        "tampered_png_hash",
        "wrong_png_dimensions",
        "non_rgb_png",
        "wrong_size_bytes",
        "wrong_rgb_pixel_hash",
        "pixel_cap_exceeded",
    ],
)
def test_corrupt_or_mismatched_canonical_png_rejected_before_output(tmp_path, mutation):
    handoff_dir, _ = build_ai1_handoff(tmp_path, artifact_version=1, include_failures=False)
    engine_manifest, _ = write_engine_manifest(tmp_path / "release")
    report_path = handoff_dir / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    sample = report["samples"][0]
    png_path = handoff_dir / sample["sample_id"] / "canonical.png"

    if mutation == "corrupt_png_bytes":
        bad = b"\x89PNG\r\n\x1a\ncorrupt-stream"
        png_path.write_bytes(bad)
        sample["canonical"]["sha256"] = hashlib.sha256(bad).hexdigest()
        sample["canonical"]["size_bytes"] = len(bad)
    elif mutation == "tampered_png_hash":
        png_path.write_bytes(make_png((100, 100), color="black"))
    elif mutation == "wrong_png_dimensions":
        other_png = make_png((80, 100))
        png_path.write_bytes(other_png)
        sample["canonical"]["sha256"] = hashlib.sha256(other_png).hexdigest()
        sample["canonical"]["size_bytes"] = len(other_png)
    elif mutation == "non_rgb_png":
        gray_png = make_png((100, 100), mode="L", color=128)
        png_path.write_bytes(gray_png)
        sample["canonical"]["sha256"] = hashlib.sha256(gray_png).hexdigest()
        sample["canonical"]["size_bytes"] = len(gray_png)
    elif mutation == "wrong_size_bytes":
        sample["canonical"]["size_bytes"] += 1
    elif mutation == "wrong_rgb_pixel_hash":
        sample["canonical"]["rgb_pixel_sha256"] = "0" * 64
    elif mutation == "pixel_cap_exceeded":
        report["profile"]["max_pixels"] = 5000

    (handoff_dir / sample["sample_id"] / "run.json").write_text(json.dumps(sample, indent=2), encoding="utf-8")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    output_dir = tmp_path / f"out-{mutation}"
    with pytest.raises(HandoffBridgeError):
        export_handoff(handoff_dir, engine_manifest, output_dir)
    assert not output_dir.exists()


@pytest.mark.parametrize(
    "mismatch",
    [
        "run_json_input_sha",
        "run_json_missing",
        "failed_run_json_missing",
        "input_ vs_expected_sha",
        "prepared_snapshot_mismatch",
        "ocr_version_mismatch",
        "block_count_mismatch",
        "counts_mismatch",
        "run_status_aborted",
        "wrong_report_version",
        "select_failed_sample",
    ],
)
def test_report_run_or_accounting_mismatch_rejected_before_output(tmp_path, mismatch):
    handoff_dir, _ = build_ai1_handoff(tmp_path, artifact_version=1, include_failures=True)
    engine_manifest, _ = write_engine_manifest(tmp_path / "release")
    report_path = handoff_dir / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    sample = report["samples"][0]
    run_path = handoff_dir / sample["sample_id"] / "run.json"

    sample_ids = None
    if mismatch == "run_json_input_sha":
        run_data = json.loads(run_path.read_text(encoding="utf-8"))
        run_data["ocr_seconds"] = 9.99
        run_path.write_text(json.dumps(run_data, indent=2), encoding="utf-8")
    elif mismatch == "run_json_missing":
        run_path.unlink()
    elif mismatch == "failed_run_json_missing":
        (handoff_dir / "ocr_fail/run.json").unlink()
    elif mismatch == "input_ vs_expected_sha":
        sample["input_sha256"] = "f" * 64
        run_path.write_text(json.dumps(sample, indent=2), encoding="utf-8")
    elif mismatch == "prepared_snapshot_mismatch":
        sample["prepared"]["preprocess_version"] = "mutated.v2"
        run_path.write_text(json.dumps(sample, indent=2), encoding="utf-8")
    elif mismatch == "ocr_version_mismatch":
        sample["ocr_version"] = "mutated.ocr.v9"
        run_path.write_text(json.dumps(sample, indent=2), encoding="utf-8")
    elif mismatch == "block_count_mismatch":
        sample["block_count"] = 99
        run_path.write_text(json.dumps(sample, indent=2), encoding="utf-8")
    elif mismatch == "counts_mismatch":
        report["counts"]["ok"] = 3
    elif mismatch == "run_status_aborted":
        report["run_status"] = "aborted"
    elif mismatch == "wrong_report_version":
        report["report_version"] = "vietdoc.ocr-handoff.v1"
    elif mismatch == "select_failed_sample":
        sample_ids = ["ocr_fail"]

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    output_dir = tmp_path / f"out-{mismatch}"
    with pytest.raises(HandoffBridgeError):
        export_handoff(handoff_dir, engine_manifest, output_dir, sample_ids=sample_ids)
    assert not output_dir.exists()


@pytest.mark.parametrize(
    "ocr_issue",
    [
        "duplicate_block_id",
        "invalid_quad",
        "wrong_dimensions",
        "unavailable_geometry_with_quad",
        "v2_flag_contradiction",
        "extra_gold_key",
    ],
)
def test_invalid_ocr_or_prepared_contract_rejected_before_output(tmp_path, ocr_issue):
    handoff_dir, _ = build_ai1_handoff(tmp_path, artifact_version=1, include_failures=False)
    engine_manifest, _ = write_engine_manifest(tmp_path / "release")
    report_path = handoff_dir / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    sample = report["samples"][0]
    sid = sample["sample_id"]
    sample["artifact_paths"] = {
        "canonical.png": f"{sid}/canonical.png",
        "ocr.json": f"{sid}/ocr.json",
        "prepared.json": f"{sid}/prepared.json",
    }
    ocr_path = handoff_dir / sid / "ocr.json"
    prepared_path = handoff_dir / sid / "prepared.json"
    ocr_data = json.loads(ocr_path.read_text(encoding="utf-8"))
    prepared_data = json.loads(prepared_path.read_text(encoding="utf-8"))

    if ocr_issue == "duplicate_block_id":
        ocr_data["blocks"][1]["block_id"] = ocr_data["blocks"][0]["block_id"]
    elif ocr_issue == "invalid_quad":
        ocr_data["blocks"][0]["quad"] = [[0.0, 0.0], [1.2, 0.0], [1.2, 0.2], [0.0, 0.2]]
    elif ocr_issue == "wrong_dimensions":
        ocr_data["width"] = 200
    elif ocr_issue == "unavailable_geometry_with_quad":
        prepared_data.update(geometry_status="unavailable", inverse_transform=None, geometry_reason="no_mapping")
        prepared_path.write_text(json.dumps(prepared_data, indent=2), encoding="utf-8")
        sample["prepared"] = prepared_data
    elif ocr_issue == "v2_flag_contradiction":
        ocr_data.update(
            artifact_version=2,
            unreadable_regions=[
                {
                    "region_id": "p0-b0099",
                    "quad": None,
                    "score": None,
                    "geometry_reason": "unavailable",
                    "reason": "EMPTY_RECOGNITION",
                }
            ],
            recognition_status="complete",
            review_flags=[],
        )
    elif ocr_issue == "extra_gold_key":
        ocr_data["gold_transcript"] = "forbidden"

    ocr_path.write_text(json.dumps(ocr_data, indent=2), encoding="utf-8")
    (handoff_dir / sid / "run.json").write_text(json.dumps(sample, indent=2), encoding="utf-8")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    output_dir = tmp_path / f"out-{ocr_issue}"
    with pytest.raises(HandoffBridgeError):
        export_handoff(handoff_dir, engine_manifest, output_dir)
    assert not output_dir.exists()


@pytest.mark.parametrize(
    "manifest_case",
    [
        "missing_file",
        "version_2",
        "bool_version",
        "bad_manifest_id",
        "empty_files",
        "extra_top_key",
        "bad_file_sha",
        "zero_size_bytes",
        "bool_size_bytes",
        "duplicate_file_path",
        "unsafe_file_path",
        "tampered_present_weight_file",
    ],
)
def test_invalid_engine_manifest_rejected_before_output(tmp_path, manifest_case):
    handoff_dir, _ = build_ai1_handoff(tmp_path, artifact_version=1, include_failures=False)
    release_dir = tmp_path / f"release-{manifest_case}"
    release_dir.mkdir()
    manifest_path, _ = write_engine_manifest(
        release_dir,
        create_files=(manifest_case == "tampered_present_weight_file"),
    )
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    if manifest_case == "missing_file":
        manifest_path.unlink()
    elif manifest_case == "version_2":
        data["manifest_version"] = 2
    elif manifest_case == "bool_version":
        data["manifest_version"] = True
    elif manifest_case == "bad_manifest_id":
        data["pipeline_manifest_id"] = "../escape"
    elif manifest_case == "empty_files":
        data["files"] = []
    elif manifest_case == "extra_top_key":
        data["extra"] = True
    elif manifest_case == "bad_file_sha":
        data["files"][0]["sha256"] = "xyz"
    elif manifest_case == "zero_size_bytes":
        data["files"][0]["size_bytes"] = 0
    elif manifest_case == "bool_size_bytes":
        data["files"][0]["size_bytes"] = True
    elif manifest_case == "duplicate_file_path":
        data["files"].append(dict(data["files"][0]))
    elif manifest_case == "unsafe_file_path":
        data["files"][0]["path"] = "../outside.bin"
    elif manifest_case == "tampered_present_weight_file":
        (release_dir / "ocr/model.bin").write_bytes(b"tampered bytes of different length")

    if manifest_case != "missing_file":
        manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    output_dir = tmp_path / f"out-{manifest_case}"
    with pytest.raises(HandoffBridgeError, match="ENGINE_MANIFEST_INVALID"):
        export_handoff(handoff_dir, manifest_path, output_dir)
    assert not output_dir.exists()


@pytest.mark.parametrize(
    "path_case",
    [
        "unsafe_sample_id",
        "casefold_sample_alias",
        "unsafe_input_declared_path",
        "unsafe_artifact_path_traversal",
        "mismatched_artifact_path_sample",
        "symlink_ocr_file",
        "symlink_sample_dir",
    ],
)
def test_unsafe_paths_and_links_rejected_before_output(tmp_path, monkeypatch, path_case):
    handoff_dir, _ = build_ai1_handoff(tmp_path, artifact_version=1, include_failures=False)
    engine_manifest, _ = write_engine_manifest(tmp_path / "release")
    report_path = handoff_dir / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    sample = report["samples"][0]
    sid = sample["sample_id"]
    sample["artifact_paths"] = {
        "canonical.png": f"{sid}/canonical.png",
        "ocr.json": f"{sid}/ocr.json",
        "prepared.json": f"{sid}/prepared.json",
    }

    if path_case == "unsafe_sample_id":
        sample["sample_id"] = "../escape"
    elif path_case == "casefold_sample_alias":
        report["samples"][1]["sample_id"] = sid.upper()
    elif path_case == "unsafe_input_declared_path":
        sample["input_declared_path"] = "../outside.png"
    elif path_case == "unsafe_artifact_path_traversal":
        sample["artifact_paths"]["ocr.json"] = "../escape/ocr.json"
    elif path_case == "mismatched_artifact_path_sample":
        sample["artifact_paths"]["ocr.json"] = "inv_ok/ocr.json"
    elif path_case == "symlink_ocr_file":
        target_ocr = handoff_dir / sid / "ocr.json"
        outside_ocr = tmp_path / "outside-ocr.json"
        outside_ocr.write_bytes(target_ocr.read_bytes())
        target_ocr.unlink()
        try:
            target_ocr.symlink_to(outside_ocr)
        except OSError:
            target_ocr.write_bytes(outside_ocr.read_bytes())
            original = Path.is_symlink
            monkeypatch.setattr(Path, "is_symlink", lambda p: p == target_ocr or original(p))
    elif path_case == "symlink_sample_dir":
        sample_dir = handoff_dir / sid
        outside_dir = tmp_path / "outside-sample"
        sample_dir.rename(outside_dir)
        if sys.platform == "win32":
            import _winapi

            _winapi.CreateJunction(str(outside_dir), str(sample_dir))
        else:
            sample_dir.symlink_to(outside_dir, target_is_directory=True)

    if path_case not in ("symlink_ocr_file", "symlink_sample_dir", "unsafe_sample_id", "casefold_sample_alias"):
        (handoff_dir / sid / "run.json").write_text(json.dumps(sample, indent=2), encoding="utf-8")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    output_dir = tmp_path / f"out-{path_case}"
    with pytest.raises(HandoffBridgeError):
        export_handoff(handoff_dir, engine_manifest, output_dir)
    assert not output_dir.exists()


@pytest.mark.parametrize("target_file", ["report.json", "run.json", "ocr.json", "prepared.json", "engine-manifest.json"])
@pytest.mark.parametrize("bad_kind", ["duplicate_key", "nan", "infinity", "overflow", "surrogate", "invalid_utf8", "oversized"])
def test_duplicate_keys_nonfinite_and_invalid_utf8_rejected_before_output(tmp_path, target_file, bad_kind):
    handoff_dir, _ = build_ai1_handoff(tmp_path, artifact_version=1, include_failures=False)
    engine_manifest, _ = write_engine_manifest(tmp_path / "release")
    paths = {
        "report.json": handoff_dir / "report.json",
        "run.json": handoff_dir / "rec_ok/run.json",
        "ocr.json": handoff_dir / "rec_ok/ocr.json",
        "prepared.json": handoff_dir / "rec_ok/prepared.json",
        "engine-manifest.json": engine_manifest,
    }
    path = paths[target_file]

    if bad_kind == "duplicate_key":
        raw = b'{"a": 1, "a": 2}'
    elif bad_kind == "nan":
        raw = b'{"a": NaN}'
    elif bad_kind == "infinity":
        raw = b'{"a": Infinity}'
    elif bad_kind == "overflow":
        raw = b'{"a": 1e999}'
    elif bad_kind == "surrogate":
        raw = b'{"a": "\\ud800"}'
    elif bad_kind == "oversized":
        raw = b'{"a": "' + b"x" * (1024 * 1024) + b'"}'
    else:
        raw = b"\xff\xfeinvalid"

    path.write_bytes(raw)
    output_dir = tmp_path / f"out-{target_file}-{bad_kind}"
    with pytest.raises(HandoffBridgeError):
        export_handoff(handoff_dir, engine_manifest, output_dir)
    assert not output_dir.exists()


def test_all_excluded_samples_rejected_and_partial_output_cleaned_on_write_error(tmp_path, monkeypatch):
    handoff_dir, _ = build_ai1_handoff(tmp_path, artifact_version=1, include_failures=True)
    engine_manifest, _ = write_engine_manifest(tmp_path / "release")
    report_path = handoff_dir / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))

    # Keep only the failed and not_run samples so ok == 0.
    only_excluded = [s for s in report["samples"] if s["status"] != "ok"]
    only_report = deepcopy(report)
    only_report["samples"] = only_excluded
    only_report["counts"] = {
        "requested": len(only_excluded),
        "native_attempted": sum(s["native_attempted"] for s in only_excluded),
        "ok": 0,
        "failed": sum(s["status"] == "failed" for s in only_excluded),
        "not_run": sum(s["status"] == "not_run" for s in only_excluded),
    }
    only_report["observed_engine_calls"] = sum(s.get("engine_calls", 0) for s in only_excluded)
    report_path.write_text(json.dumps(only_report, indent=2), encoding="utf-8")

    with pytest.raises(HandoffBridgeError, match="NO_OK_SAMPLES"):
        export_handoff(handoff_dir, engine_manifest, tmp_path / "no-ok-out")
    assert not (tmp_path / "no-ok-out").exists()

    # Restore valid report and simulate an OSError when writing index.json inside the new output_dir.
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    output_dir = tmp_path / "partial-cleanup-out"
    original_open = Path.open

    def fail_on_index(path: Path, mode="r", *args, **kwargs):
        if path == output_dir / "index.json" and "x" in mode:
            raise OSError("disk full during index write")
        return original_open(path, mode, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", fail_on_index)
        with pytest.raises(HandoffBridgeError, match="EXPORT_IO_ERROR"):
            export_handoff(handoff_dir, engine_manifest, output_dir)
    assert not output_dir.exists()


def test_existing_output_directory_never_overwritten_and_cli_help_cp1252_safe(tmp_path, monkeypatch, capsys):
    handoff_dir, _ = build_ai1_handoff(tmp_path, artifact_version=1, include_failures=False)
    engine_manifest, _ = write_engine_manifest(tmp_path / "release")
    output_dir = tmp_path / "existing-output"
    output_dir.mkdir()
    sentinel = output_dir / "keep.txt"
    sentinel.write_bytes(b"preserve-user-bytes")

    rc = main(
        [
            "--handoff-root",
            str(handoff_dir),
            "--engine-manifest",
            str(engine_manifest),
            "--output-dir",
            str(output_dir),
        ]
    )
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "status": "failed",
        "code": "OUTPUT_EXISTS",
        "stage": "export",
        "production_active": False,
    }
    assert sentinel.read_bytes() == b"preserve-user-bytes"
    assert list(output_dir.iterdir()) == [sentinel]

    with io.BytesIO() as buffer:
        with io.TextIOWrapper(buffer, encoding="cp1252", write_through=True) as stream:
            with monkeypatch.context() as patch:
                patch.setattr(sys, "stdout", stream)
                with pytest.raises(SystemExit) as exited:
                    main(["--help"])
                assert exited.value.code == 0
            assert b"--handoff-root" in buffer.getvalue()
            assert b"profile_sha256" in buffer.getvalue()
