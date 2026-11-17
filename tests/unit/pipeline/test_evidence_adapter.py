"""Accepted AI1 objects through the production B0 source-bound adapter."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from vietdoc.contracts.ocr import OcrPage, PreparedPage
from vietdoc.pipeline.extraction.baseline import extract_baseline
from vietdoc.pipeline.extraction.ocr_input import BaselineError


def inputs(index=0):
    fixture = json.loads((Path(__file__).parents[2] / "fixtures/ocr-artifact-v2.json").read_bytes())
    return OcrPage.from_dict(fixture["cases"][index]["expected"]), PreparedPage.from_dict(fixture["prepared_page"])


def test_scoped_match_keeps_original_geometry_and_partial_flags():
    from vietdoc.pipeline.extraction.evidence_adapter import BoundEvidence
    page, prepared = inputs()
    field = BoundEvidence(page, prepared)("/total_amount", "80.000", ("p0-b0004",))
    assert field["source_regions"] == [dict(page=0, quad=[[.1,.4],[.4,.4],[.4,.5],[.1,.5]], ocr_block_ids=["p0-b0004"])]
    assert field["confidence"] is None
    assert "SOURCE_OCR_INCOMPLETE" in field["review_flags"]


@pytest.mark.parametrize("raw,ids", [("90.000", ("p0-b0004",)), ("80.000", ("p0-b0001",)), ("80.000", ())])
def test_wrong_or_unscoped_partial_value_abstains(raw, ids):
    from vietdoc.pipeline.extraction.evidence_adapter import BoundEvidence
    page, prepared = inputs()
    assert BoundEvidence(page, prepared)("/total_amount", raw, ids)["source_regions"] == []


@pytest.mark.parametrize("index", [0, 1, 2])
def test_partial_and_blank_are_not_absent(index):
    from vietdoc.pipeline.extraction.evidence_adapter import BoundEvidence
    page, prepared = inputs(index)
    result = extract_baseline(page, "receipt", prepared=prepared, evidence_matcher=BoundEvidence(page, prepared))
    assert result.payload["total_amount"] is None
    assert result.field_states["/total_amount"] == "unknown"
    assert all(f["value_origin"] != "absent" for f in result.field_metadata)


def test_baseline_rejects_same_box_and_score_with_wrong_text():
    from vietdoc.pipeline.extraction.ocr_consumer import validate_match
    from test_ocr_consumer import evidence_input
    page, request, match = evidence_input()
    # This is an OCR source mutation, not an output metadata shape mutation.
    page["blocks"][1]["text"] = "90.000"
    with pytest.raises(BaselineError, match="EVIDENCE_INVALID"):
        validate_match(page, request, match)


def test_candidate_ids_cannot_escape_context():
    from vietdoc.pipeline.extraction.ocr_consumer import validate_match
    from test_ocr_consumer import evidence_input
    page, request, match = evidence_input()
    match["candidate_block_ids"] = [["p0-b0001"]]
    with pytest.raises(BaselineError, match="EVIDENCE_INVALID"):
        validate_match(page, request, match)
