"""AI2 boundary validation for isolated provider evidence and consumer reports."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from vietdoc.pipeline.extraction.ocr_input import BaselineError

FIXTURES = Path(__file__).parents[2] / "fixtures"
PIN = "7d96e93bf8315beb6fa33807231316e957671249"


def evidence_input():
    golden = json.loads((FIXTURES / "ocr-artifact-v2.json").read_text(encoding="utf-8"))
    page = golden["cases"][0]["expected"]
    request = dict(path="/total_amount", raw_value="80.000", context_block_ids=["p0-b0004"], label_text=None)
    metadata = dict(path="/total_amount", raw_value="80.000", value_origin="prediction",
                    source_regions=[dict(page=0, quad=page["blocks"][1]["quad"], ocr_block_ids=["p0-b0004"])],
                    ocr_score=.8, confidence=None, confidence_method=None,
                    review_flags=["OCR_UNREADABLE_REGIONS", "SOURCE_OCR_INCOMPLETE"])
    match = dict(status="matched", candidate_block_ids=[["p0-b0004"]], field_metadata=metadata)
    return page, request, match


def test_valid_scoped_partial_evidence_retains_raw_score_and_null_confidence():
    from vietdoc.pipeline.extraction.ocr_consumer import validate_match
    page, request, match = evidence_input()
    assert validate_match(page, request, match) == match


@pytest.mark.parametrize("change", ["confidence", "foreign-id", "score", "flags", "raw", "abstain-regions"])
def test_consumer_rejects_invalid_provider_metadata(change):
    from vietdoc.pipeline.extraction.ocr_consumer import validate_match
    page, request, match = evidence_input()
    field = match["field_metadata"]
    if change == "confidence": field["confidence"] = .8
    elif change == "foreign-id": field["source_regions"][0]["ocr_block_ids"] = ["p0-b0001"]
    elif change == "score": field["ocr_score"] = .99
    elif change == "flags": field["review_flags"] = []
    elif change == "raw": field["raw_value"] = "80000"
    else: match["status"] = "ambiguous"
    with pytest.raises(BaselineError, match="EVIDENCE_INVALID"):
        validate_match(page, request, match)


@pytest.mark.parametrize("sha", [PIN, "0" * 40, "feature/AI1_preprocess_ocr"])
def test_unavailable_or_unpinned_provider_snapshot_is_rejected(tmp_path, sha):
    from vietdoc.pipeline.extraction.ocr_consumer import ProviderEvidence
    with pytest.raises(BaselineError, match="OCR_PROVIDER_INVALID"):
        ProviderEvidence(tmp_path, sha)


def test_native_report_uses_observed_ocr_without_opening_gold_or_transcript(monkeypatch):
    from vietdoc.pipeline.extraction.ocr_consumer import consume_native
    bundle = json.loads((FIXTURES / "ocr-d1-native-handoff.json").read_text(encoding="utf-8"))
    original = Path.open
    def no_gold(path, *args, **kwargs):
        assert not path.name.endswith((".gold.json", ".labels.json", ".txt"))
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", no_gold)
    records = consume_native(bundle)
    assert [r["sample_id"] for r in records] == ["d12-receipt-03", "d12-invoice-04"]
    assert [r["payload"]["total_amount"] for r in records] == ["178000", "233000"]
    assert all(r["status"] == "ok" and r["ocr_diagnostics"]["artifact_version"] == 2 for r in records)
    assert all(r["ocr_diagnostics"]["recognition_status"] == "complete" for r in records)
    assert all(r["evidence_execution"] == "NOT_RUN" for r in records)
    # This is raw observed OCR; do not repair the known unit error using gold.
    assert any(b["text"] == "nộp" for b in records[0]["ocr_diagnostics"]["blocks"])
    assert all(f["confidence"] is None for r in records for f in r["field_metadata"])


@pytest.mark.parametrize("change", ["canonical-size", "version", "count", "input-hash"])
def test_native_sample_correlation_failure_is_reported_per_sample(change):
    from vietdoc.pipeline.extraction.ocr_consumer import consume_native
    bundle = json.loads((FIXTURES / "ocr-d1-native-handoff.json").read_text(encoding="utf-8"))
    sample = bundle["samples"][0]
    if change == "canonical-size": sample["canonical"]["width"] += 1
    elif change == "version": sample["artifact_version"] = 1
    elif change == "count": sample["block_count"] += 1
    else: sample["input_sha256"] = "0" * 64
    records = consume_native(bundle)
    assert records[0]["status"] == "failed"
    assert records[0]["error"] == "PROVENANCE_MISMATCH"
    assert records[1]["status"] == "ok"


def test_cli_refuses_to_overwrite_an_existing_report(tmp_path, capsys):
    from vietdoc.entrypoints.cli.ocr_consumer import main
    output = tmp_path / "out"
    output.mkdir()
    report = output / "consumer-report.json"
    report.write_bytes(b"existing-user-report")
    with pytest.raises(SystemExit) as raised:
        main(["--provider-root", str(tmp_path), "--output", str(output)])
    assert raised.value.code == 2
    assert "output directory already exists" in capsys.readouterr().err
    assert report.read_bytes() == b"existing-user-report"


@pytest.mark.parametrize("bad", [{}, {"sample_id": None}, {"sample_id": "../private"}, None, 5])
def test_invalid_id_does_not_lose_following_sample(bad):
    from vietdoc.pipeline.extraction.ocr_consumer import consume_native, batch_summary
    bundle = json.loads((FIXTURES / "ocr-d1-native-handoff.json").read_text(encoding="utf-8"))
    bundle["samples"].insert(1, bad)
    records = consume_native(bundle)
    assert [r["status"] for r in records] == ["ok", "failed", "ok"]
    assert records[1] == dict(sample_index=1, status="failed", error="OCR_INPUT_INVALID")
    assert batch_summary(records) == dict(requested=3, ok=2, failed=1, not_run=0, incomplete=False)


@pytest.mark.parametrize("bundle", [None, {}, {"samples": None}, {"samples": "invalid"}])
def test_invalid_batch_is_rejected_before_processing(bundle):
    from vietdoc.pipeline.extraction.ocr_consumer import consume_native
    with pytest.raises(BaselineError, match="OCR_BATCH_INVALID"):
        consume_native(bundle)


def test_unexpected_failure_preserves_incomplete_denominator(monkeypatch):
    from vietdoc.pipeline.extraction import ocr_consumer as consumer
    bundle = json.loads((FIXTURES / "ocr-d1-native-handoff.json").read_text(encoding="utf-8"))
    def fail(*args, **kwargs):
        raise RuntimeError("secret/private/path")
    monkeypatch.setattr(consumer, "extract_baseline", fail)
    records = consumer.consume_native(bundle)
    assert [r["status"] for r in records] == ["failed", "not_run"]
    assert records[0]["error"] == "INTERNAL_ERROR"
    assert records[1]["error"] == "BATCH_ABORTED"
    assert consumer.batch_summary(records) == dict(requested=2, ok=0, failed=1, not_run=1, incomplete=True)
    assert "secret" not in json.dumps(records)


def test_semantic_mismatch_is_not_execution_pass_and_report_exit_is_nonzero(tmp_path):
    from vietdoc.entrypoints.cli.ocr_consumer import evaluate_expectations, publish_report
    checks = evaluate_expectations({"payload": {"total_amount": "100000"}},
                                   [{"path": "/payload/total_amount", "expected": "80000"}])
    assert checks == [dict(path="/payload/total_amount", expected="80000", actual="100000", result="FAIL")]
    report = dict(golden_results=[dict(execution_status="PASS", status="FAIL", checks=checks)],
                  evidence_checks=[], native_results=[])
    assert publish_report(tmp_path / "out", report) == 1
    saved = json.loads((tmp_path / "out/consumer-report.json").read_bytes())
    assert saved["summary"]["status"] == "FAIL"
    assert saved["golden_results"][0]["execution_status"] == "PASS"


def test_parse_only_has_no_accuracy_pass():
    from vietdoc.entrypoints.cli.ocr_consumer import evaluate_expectations
    assert evaluate_expectations({"payload": {}}, []) == []


def test_golden_expectations_are_independent_of_baseline_output():
    from vietdoc.entrypoints.cli.ocr_consumer import golden_reports
    golden = json.loads((FIXTURES / "ocr-artifact-v2.json").read_bytes())
    records = golden_reports(golden)
    assert all(r["execution_status"] == "PASS" and r["status"] == "PASS" for r in records)
    assert all(r["quality_status"] == "NOT_EVALUATED" for r in records)
    assert all(r["checks"] for r in records)
    assert records[0]["ocr_diagnostics"]["recognition_status"] == "partial"


def test_unexpected_cli_failure_still_writes_safe_failure_report(tmp_path, monkeypatch, capsys):
    from vietdoc.entrypoints.cli import ocr_consumer as cli
    def crash(*args, **kwargs):
        raise RuntimeError("credential/private/path")
    monkeypatch.setattr(cli, "ProviderEvidence", crash)
    output = tmp_path / "failure"
    with pytest.raises(SystemExit) as error:
        cli.main(["--provider-root", str(tmp_path), "--output", str(output)])
    assert error.value.code == 2
    report = json.loads((output / "consumer-report.json").read_bytes())
    assert report["summary"]["status"] == "FAIL" and report["summary"]["incomplete"]
    assert "credential" not in json.dumps(report) + capsys.readouterr().err
