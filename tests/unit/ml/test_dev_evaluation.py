"""Known-answer controls for offline evaluation (no torch/model downloads)."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_qwen_inference import Tokenizer
from vietdoc.ml.ocr_adapter import build_prompt
from vietdoc.ml.qwen_config import COMPACT_SERIALIZATION, MLFailure

from vietdoc.evaluation import extended
from vietdoc.ml import dev_evaluation as ev

pytest_plugins = ["test_qwen_inference", "test_model_provision"]


def payload():
    return {
        "merchant_name": "Fictional shop",
        "merchant_address": None,
        "transaction_date": "2026-11-25",
        "transaction_time": None,
        "total_amount": "40000",
        "items": [],
    }


def sample(sid="one"):
    gold = payload()
    return {
        "sample_id": sid,
        "document_type": "receipt",
        "split": "dev",
        "gold": gold,
        "labels": {
            "/" + k: {"status": "present" if v is not None else "absent"}
            for k, v in gold.items()
            if k != "items"
        },
    }


def artifact(records):
    return {
        "artifact_version": "vietdoc.predictions.v1",
        "model_version": "test",
        "normalizer_version": "test",
        "ocr_version": "test",
        "predictions": records,
        "dataset_manifest_sha256": "a" * 64,
    }


def test_missing_and_failed_predictions_remain_in_denominator():
    data = [sample("one"), sample("two")]
    output = ev.evaluate_artifacts(
        data,
        {"M1": artifact([{"sample_id": "one", "status": "failed", "error": "OOM"}])},
        expected_manifest_sha256="a" * 64,
        expected_ids={"one", "two"},
    )
    report = output["reports"]["M1"]
    assert report["accounting"]["gold_samples"] == 2
    assert report["accounting"]["outcomes"] == {"failed": 1, "missing": 1}
    assert report["scalar"]["all"]["normalized_exact_match"]["denominator"] == 6
    assert report["scalar"]["critical/total"]["counts"]["fn"] == 2
    assert output["promotion"]["eligible"] is False
    assert report["scalar"]["all"]["precision"]["value"] is None


def test_false_fill_and_wrong_total_are_counted():
    predicted = dict(payload(), merchant_address="invented", total_amount="1")
    report = extended.evaluate(
        [sample()],
        artifact([{"sample_id": "one", "status": "ok", "payload": predicted}]),
    )
    assert report["scalar"]["all"]["counts"]["false_fill"] == 1
    assert report["scalar"]["critical/total"]["counts"]["wrong_value"] == 1


def test_same_normalizer_accepts_fenced_and_numeric_model_output(config):
    raw = json.dumps(dict(payload(), total_amount=40000))
    for text in (raw, "```json\n" + raw + "\n```"):
        result = ev.normalize_output(text, "receipt", config)
        assert result["normalized_schema_valid"] is True
        assert result["payload"]["total_amount"] == "40000"
        assert result["raw_schema_valid"] is False
    assert not ev.normalize_output("```json\n" + raw + "\n```", "receipt", config)[
        "raw_json_valid"
    ]
    assert (
        ev.normalize_output(raw, "receipt", config, finish_reason="length")[
            "parse_status"
        ]
        == "truncated"
    )


def test_select_dev_keeps_obscured_without_opening_final_assets(tmp_path):
    manifest = {
        "samples": [
            {
                "sample_id": "one",
                "split": "dev",
                "document_type": "receipt",
                "labels": "obscured",
            },
            {"sample_id": "two", "split": "dev", "document_type": "invoice"},
            {
                "sample_id": "secret",
                "split": "final",
                "assets": {"gold": "MUST_NOT_OPEN"},
            },
        ]
    }
    target = tmp_path / "manifest.json"
    target.write_text(json.dumps(manifest))
    _, dev = ev.select_dev(target, ev.sha(target))
    assert [s["sample_id"] for s in dev] == ["one", "two"]
    with pytest.raises(MLFailure, match="DATASET_MANIFEST_MISMATCH"):
        ev.select_dev(target, "a" * 64)


def test_inference_never_receives_gold_and_accounts_missing_ocr(
    config, ocr, prepared, provenance, tmp_path
):
    calls = []

    def generate(page, pre, prov, kind, *, deadline):
        calls.append((page, pre, prov, kind))
        assert set(prov) == set(provenance)
        assert "gold" not in json.dumps(page)
        return SimpleNamespace(
            raw=json.dumps(payload()),
            finish_reason="stop",
            input_tokens=10,
            output_tokens=20,
            seconds=0.1,
            provenance={},
        )

    dev = [
        {"sample_id": "one", "document_type": "receipt", "gold": "NEVER_PASS"},
        {"sample_id": "two", "document_type": "receipt", "gold": "NEVER_PASS"},
    ]
    inputs = {
        "one": {
            "ocr": ocr,
            "prepared": prepared,
            "provenance": provenance,
            "document_type": "receipt",
        }
    }
    result = ev.infer_method(
        "M1",
        dev,
        inputs,
        config,
        {},
        tmp_path / "out",
        loader=SimpleNamespace(generate=generate),
    )
    assert len(calls) == 1
    assert len(result["predictions"]) == 2
    assert result["predictions"][1]["error"] == "OCR_INPUT_MISSING"
    assert result["predictions"][0]["status"] == "ok"


def test_gold_in_ocr_is_failed_before_model_call(
    config, ocr, prepared, provenance, tmp_path
):
    ocr["gold"] = payload()

    def forbidden(*args, **kwargs):
        pytest.fail("model called with gold")

    result = ev.infer_method(
        "M0",
        [{"sample_id": "one", "document_type": "receipt"}],
        {"one": {"ocr": ocr, "prepared": prepared, "provenance": provenance}},
        config,
        {},
        tmp_path / "out",
        loader=SimpleNamespace(generate=forbidden),
    )
    assert result["predictions"][0]["error"] == "GOLD_IN_OCR_INPUT"


def test_adapter_identity_mismatch_rejected_before_loading(tmp_path):
    run = tmp_path / "runs/full-epoch"
    run.mkdir(parents=True)
    (run / "run_manifest.json").write_text("{}")
    with pytest.raises(MLFailure, match="ADAPTER_IDENTITY_MISMATCH"):
        ev.verify_training_identity(
            tmp_path,
            tmp_path,
            run_sha256="0" * 64,
            checkpoint_sha256="1" * 64,
            config_sha256="2" * 64,
            preflight_sha256="3" * 64,
        )


def test_base_revision_mismatch_rejected_before_attachment(
    config, tmp_path, monkeypatch
):
    from vietdoc.ml import model_provision

    monkeypatch.setattr(
        model_provision,
        "verify_snapshot",
        lambda _: {"revision": "wrong", "model_id": config.model_id},
    )
    with pytest.raises(MLFailure, match="ADAPTER_BASE_MISMATCH"):
        ev.verify_model_identity(tmp_path, config, {})


def test_execution_toggle_preserves_training_inference_prompt(
    config, ocr, prepared, provenance
):
    cfg = replace(
        config, serialization_version=COMPACT_SERIALIZATION, execution_enabled=False
    )
    train_prompt = build_prompt(ocr, prepared, provenance, "receipt", cfg, Tokenizer())
    infer_prompt = build_prompt(
        ocr,
        prepared,
        provenance,
        "receipt",
        replace(cfg, execution_enabled=True),
        Tokenizer(),
    )
    assert train_prompt == infer_prompt


def test_generation_failure_is_recorded(config, ocr, prepared, provenance, tmp_path):
    def generate(*args, **kwargs):
        raise MLFailure("OOM", "generation")

    result = ev.infer_method(
        "M0",
        [{"sample_id": "one", "document_type": "receipt"}],
        {"one": {"ocr": ocr, "prepared": prepared, "provenance": provenance}},
        config,
        {},
        tmp_path / "out",
        loader=SimpleNamespace(generate=generate),
    )
    assert result["predictions"] == [
        {
            "sample_id": "one",
            "document_type": "receipt",
            "status": "failed",
            "error": "OOM",
        }
    ]


def test_model_load_failure_accounts_every_sample(config, tmp_path):
    dev = [{"sample_id": sid, "document_type": "receipt"} for sid in ("one", "two")]
    result = ev.infer_method(
        "M1", dev, {}, config, {}, tmp_path / "out", runtime_failure="MODEL_LOAD_FAILED"
    )
    assert len(result["predictions"]) == 2
    assert all(r["error"] == "MODEL_LOAD_FAILED" for r in result["predictions"])
    details = json.loads((tmp_path / "out/samples.json").read_text())
    assert details["predictions_sha256"] == ev.sha(tmp_path / "out/predictions.json")


def test_cleanup_closes_model_before_releasing_cache(monkeypatch):
    calls = []
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: True, empty_cache=lambda: calls.append("empty_cache")
        )
    )
    # Generation failures may already have cleared loader.runtime.
    monkeypatch.setitem(ev.sys.modules, "torch", fake_torch)
    loader = SimpleNamespace(runtime=None, close=lambda: calls.append("close"))
    ev.close_loader(loader)
    assert calls == ["close", "empty_cache"]


def test_unknown_or_final_prediction_is_rejected():
    with pytest.raises(MLFailure, match="NON_DEV_PREDICTION"):
        ev.evaluate_artifacts(
            [sample()],
            {"M1": artifact([{"sample_id": "final", "status": "failed"}])},
            expected_manifest_sha256="a" * 64,
            expected_ids={"one"},
        )


def test_non_dev_bundle_rejected_before_any_payload_read(tmp_path, monkeypatch):
    (tmp_path / "index.json").write_text(json.dumps({"samples": {
        "one": {"paths": {"ocr": "one/MUST_NOT_READ"}},
        "final-secret": {"paths": {"ocr": "final-secret/MUST_NOT_READ"}},
    }}))
    reads = []
    original = ev._read_strict_json
    def read(path, **kwargs):
        reads.append(path.name)
        return original(path, **kwargs)
    monkeypatch.setattr(ev, "_read_strict_json", read)
    def forbidden(*args, **kwargs):
        pytest.fail("payload loader must not be called for non-dev membership")
    monkeypatch.setattr(ev, "load_ocr_handoff_bundle", forbidden)
    with pytest.raises(MLFailure, match="NON_DEV_OCR_INPUT"):
        ev._load_dev_bundle(tmp_path, {"one"}, {})
    assert reads == ["index.json"]


def test_dev_bundle_loader_uses_frozen_checked_index(tmp_path, monkeypatch):
    paths = {key: f"one/{key}.json" for key in ("ocr", "prepared", "provenance")}
    metadata = {"samples": {"one": {"paths": paths}}}
    raw = json.dumps(metadata).encode()
    (tmp_path / "index.json").write_bytes(raw)
    (tmp_path / "one").mkdir()
    for path in paths.values():
        (tmp_path / path).write_text("{}")
    def frozen_loader(folder, **kwargs):
        # Changing the original index cannot redirect the loader to final data.
        (tmp_path / "index.json").write_text('{"samples":{"final-secret":{}}}')
        assert folder != tmp_path
        assert (folder / "index.json").read_bytes() == raw
        assert {p.parent.name for p in folder.glob("*/*.json")} == {"one"}
        return SimpleNamespace(index_sha256=ev.hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(ev, "load_ocr_handoff_bundle", frozen_loader)
    result = ev._load_dev_bundle(tmp_path, {"one"}, {"ocr_engine_sha256":"a"*64,"ocr_profile_sha256":"b"*64})
    assert result.index_sha256 == ev.hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("case", ["valid", "missing", "wrong_proof_hash", "wrong_revision", "wrong_upstream_hash", "wrong_file_list"])
def test_reprovision_keeps_strict_pins_and_verifies_upstream_bytes(tmp_path, config, fixture_model, case):
    from copy import deepcopy

    from vietdoc.ml import model_provision as provision
    _, metadata, _, download = fixture_model
    provision.provision(tmp_path / "models", approval_ref="lead-test", license_ack="apache-2.0",
                        metadata_source=lambda: deepcopy(metadata), downloader=download)
    snapshot = tmp_path / "models" / provision.REVISION
    pins = {"model_manifest_sha256": "a" * 64,
            "tokenizer_sha256": ev.sha(snapshot / "tokenizer.json")}
    proof = {
        "version": "vietdoc.base-reprovision.v1", "model_id": config.model_id,
        "revision": config.revision, "training_model_manifest_sha256": "a" * 64,
        "current_model_manifest_sha256": ev.sha(snapshot / "manifest.json"),
        "tokenizer_sha256": pins["tokenizer_sha256"],
        "upstream_metadata": metadata,
        "verified_files": [provision._verify_file(snapshot, entry) for entry in metadata["files"]],
    }
    if case == "wrong_revision":
        proof["revision"] = "b" * 40
    elif case == "wrong_upstream_hash":
        proof["upstream_metadata"]["files"][0]["source_hash"] = "b" * 40
    elif case == "wrong_file_list":
        proof["verified_files"] = []
    path = tmp_path / "proof.json"
    path.write_text(json.dumps(proof))
    kwargs = {} if case == "missing" else {
        "reprovision": path,
        "reprovision_sha256": "f" * 64 if case == "wrong_proof_hash" else ev.sha(path),
    }
    if case == "valid":
        result = ev.verify_model_identity(snapshot, config, pins, **kwargs)
        assert result["reprovisioned"] is True
        assert result["training_model_manifest_sha256"] == "a" * 64
        assert result["current_model_manifest_sha256"] != "a" * 64
    else:
        with pytest.raises((MLFailure, provision.ProvisionError)):
            ev.verify_model_identity(snapshot, config, pins, **kwargs)
