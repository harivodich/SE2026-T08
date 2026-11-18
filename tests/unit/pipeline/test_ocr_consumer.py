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
