"""AI2 acceptance of pinned AI1 OCR artifacts, not provider roundtrip tests."""

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from vietdoc.pipeline.extraction.ocr_input import BaselineError, snapshot_page

FIXTURES = Path(__file__).parents[2] / "fixtures"
GOLDEN = json.loads((FIXTURES / "ocr-artifact-v2.json").read_text(encoding="utf-8"))


def test_fixture_matches_pinned_provider_bytes():
    source = json.loads((FIXTURES / "ocr-ai2-source.json").read_text(encoding="utf-8"))
    expected = source["files"]["tests/fixtures/ocr-artifact-v2.json"]["sha256"]
    assert hashlib.sha256((FIXTURES / "ocr-artifact-v2.json").read_bytes()).hexdigest() == expected


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda c: c["case_id"])
def test_golden_v2_preserves_recognized_and_unreadable_detection_provenance(case):
    source = case["expected"]
    page = snapshot_page(source, GOLDEN["prepared_page"])
    assert page.artifact_version == 2
    assert page.recognition_status == source["recognition_status"]
    assert page.review_flags == tuple(source["review_flags"])
    assert [block.block_id for block in page.blocks] == [block["block_id"] for block in source["blocks"]]
    for actual, expected in zip(page.unreadable_regions, source["unreadable_regions"], strict=True):
        assert json.loads(json.dumps(asdict(actual))) == expected
    assert [block.text for block in page.blocks] == [block["text"] for block in source["blocks"]]


def test_legacy_shape_and_structural_objects_keep_v1_semantics():
    value = {key: deepcopy(GOLDEN["cases"][0]["expected"][key])
             for key in ("page", "width", "height", "ocr_version", "blocks")}
    for source in (value, SimpleNamespace(**value)):
        page = snapshot_page(source)
        assert page.artifact_version == 1
        assert page.unreadable_regions == ()
        assert page.recognition_status == "complete"
    value.update(artifact_version=2, unreadable_regions=[], recognition_status="complete", review_flags=[])
    assert snapshot_page(value).blocks == page.blocks


@pytest.mark.parametrize("mutation", [
    "unknown-version", "bool-version", "explicit-v1", "missing-version", "missing-regions",
    "status", "flags", "duplicate-id", "unreadable-score", "unreadable-quad",
    "unreadable-reason", "blank-recognized", "too-many-detections",
])
def test_invalid_versioned_metadata_is_rejected_not_silently_discarded(mutation):
    value = deepcopy(GOLDEN["cases"][0]["expected"])
    if mutation == "unknown-version": value["artifact_version"] = 3
    elif mutation == "bool-version": value["artifact_version"] = True
    elif mutation == "explicit-v1": value["artifact_version"] = 1
    elif mutation == "missing-version": del value["artifact_version"]
    elif mutation == "missing-regions": del value["unreadable_regions"]
    elif mutation == "status": value["recognition_status"] = "complete"
    elif mutation == "flags": value["review_flags"] = []
    elif mutation == "duplicate-id": value["unreadable_regions"][0]["region_id"] = value["blocks"][0]["block_id"]
    elif mutation == "unreadable-score": value["unreadable_regions"][0]["score"] = float("nan")
    elif mutation == "unreadable-quad": value["unreadable_regions"][0]["quad"][0][0] = -1
    elif mutation == "unreadable-reason": value["unreadable_regions"][0]["reason"] = "NATIVE_TIMEOUT"
    elif mutation == "blank-recognized": value["blocks"][0]["text"] = " \t "
    else:
        value["unreadable_regions"] = [dict(value["unreadable_regions"][0], region_id=f"u{i}") for i in range(4095)]
    with pytest.raises(BaselineError):
        snapshot_page(value)


def test_unavailable_geometry_applies_to_unreadable_regions_too():
    prepared = deepcopy(GOLDEN["prepared_page"])
    prepared.update(geometry_status="unavailable", inverse_transform=None, geometry_reason="mapping unavailable")
    with pytest.raises(BaselineError):
        snapshot_page(GOLDEN["cases"][1]["expected"], prepared)


def test_unreadable_unavailable_mapping_preserves_reason_without_boxes():
    value = deepcopy(GOLDEN["cases"][1]["expected"])
    value["unreadable_regions"][0].update(quad=None, geometry_reason="mapping unavailable")
    page = snapshot_page(value)
    assert page.unreadable_regions[0].quad is None
    assert page.unreadable_regions[0].geometry_reason == "mapping unavailable"
