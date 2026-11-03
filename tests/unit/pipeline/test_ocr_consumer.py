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
