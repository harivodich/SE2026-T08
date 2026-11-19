"""Rules B0 behavior on fictional OCR blocks, never OCR/model quality tests."""

from copy import deepcopy
from types import SimpleNamespace

import pytest


def page(texts):
    return {"page": 0, "width": 1000, "height": 1000, "ocr_version": "fictional-ocr.v1",
            "blocks": [{"block_id": f"b{i}", "text": text, "quad": None,
                        "score": None, "geometry_reason": "fixture text only"}
                       for i, text in enumerate(texts)]}


def baseline(value, kind="receipt", **kwargs):
    from vietdoc.pipeline.extraction.baseline import extract_baseline
    return extract_baseline(value, kind, **kwargs)


def metadata(result, path):
    return next(item for item in result.field_metadata if item["path"] == path)


def test_scalars_use_labels_not_largest_amount_or_runtime_ids():
    result = baseline(page(["Cửa hàng: Quán Hư Cấu", "Ngày bán: 03/10/2026", "Giờ: 10h05",
                            "Số tiền ghi lại: 999.000 đ", "Tổng tiền: 80.000 đ"]))
    assert result.payload == {
        "merchant_name": "Quán Hư Cấu", "merchant_address": None,
        "transaction_date": "2026-10-03", "transaction_time": "10:05",
        "total_amount": "80000", "items": [],
    }
    item = metadata(result, "/total_amount")
    assert item["raw_value"] == "80.000 đ"
    assert item["source_regions"] == [] and item["confidence"] is None
    assert set(item) == {"path", "raw_value", "value_origin", "source_regions", "ocr_score",
                         "confidence", "confidence_method", "review_flags"}
    assert "SOURCE_MATCHER_UNAVAILABLE" in item["review_flags"]


def test_invoice_and_receipt_fields_do_not_cross_types():
    result = baseline(page(["Số hóa đơn: HC-42", "Ngày lập: 04/10/2026", "Đơn vị bán: Xưởng Hư Cấu",
                            "Đơn vị mua: Người Hư Cấu", "Cộng tiền hàng: 90.000 đ",
                            "Thuế GTGT: 10.000 đ", "Chiết khấu: 0 đ", "Tổng thanh toán: 100.000 đ"]), "invoice")
    assert result.payload["seller_name"] == "Xưởng Hư Cấu"
    assert result.payload["buyer_name"] == "Người Hư Cấu"
    assert result.payload["subtotal"] == "90000"
    assert result.payload["tax_amount"] == "10000"
    assert result.payload["discount_amount"] == "0"
    assert result.payload["total_amount"] == "100000"
    assert "merchant_name" not in result.payload
    assert baseline(page(["Đơn vị bán: Xưởng Hư Cấu"])).payload["merchant_name"] is None


def test_absent_unreadable_and_unknown_are_distinct():
    absent = baseline(page(["Địa chỉ: Không có"]))
    unreadable = baseline(page(["Địa chỉ: [không đọc được]"]))
    unknown = baseline(page(["Cửa hàng: Hư Cấu"]))
    for result in (absent, unreadable, unknown):
        assert result.payload["merchant_address"] is None
    assert absent.field_states["/merchant_address"] == "absent"
    assert unreadable.field_states["/merchant_address"] == "unreadable"
    assert unknown.field_states["/merchant_address"] == "unknown"
    assert metadata(absent, "/merchant_address")["value_origin"] == "absent"
    assert metadata(unknown, "/merchant_address")["value_origin"] == "prediction"


def test_conflicting_labels_abstain_and_keep_raw_candidates():
    result = baseline(page(["Tổng tiền: 80.000", "Tổng tiền: 90.000"]))
    assert result.payload["total_amount"] is None
    assert [item["raw_value"] for item in result.raw_candidates["/total_amount"]] == ["80.000", "90.000"]
    assert "FIELD_AMBIGUOUS" in metadata(result, "/total_amount")["review_flags"]


@pytest.mark.parametrize(("text", "field"), [
    ("Tổng tiền: -40000", "total_amount"), ("Ngày bán: 31/02/2026", "transaction_date"),
    ("Giờ: 25:00", "transaction_time"),
])
def test_invalid_normalization_never_fills_zero(text, field):
    result = baseline(page([text]))
    assert result.payload[field] is None
    assert result.field_states[f"/{field}"] == "invalid"


@pytest.mark.parametrize("change", ["duplicate", "nan", "surrogate", "negative_quad", "bad_page", "too_many"])
def test_invalid_ocr_input_is_a_typed_failure(change):
    from vietdoc.pipeline.extraction.ocr_input import BaselineError
    value = page(["Tổng tiền: 80.000"])
    if change == "duplicate":
        value["blocks"] *= 2
    elif change == "nan":
        value["blocks"][0]["score"] = float("nan")
    elif change == "surrogate":
        value["blocks"][0]["text"] = "\ud800"
    elif change == "negative_quad":
        value["blocks"][0].update(quad=[[-1, 0], [1, 0], [1, 1], [0, 1]], geometry_reason=None)
    elif change == "bad_page":
        value["page"] = 1
    else:
        value["blocks"] = [{**value["blocks"][0], "block_id": f"b{i}"} for i in range(4097)]
    with pytest.raises(BaselineError):
        baseline(value)


def table_page(rows=1, order=("description", "quantity", "unit", "unit_price", "line_total")):
    labels = {"description": "Tên hàng", "quantity": "SL", "unit": "ĐVT",
              "unit_price": "Đơn giá", "line_total": "Thành tiền"}
    value = page([])
    def add(text, col, y, name):
        x = .03 + .18 * col
        value["blocks"].append({"block_id": name, "text": text,
            "quad": [[x, y], [x + .12, y], [x + .12, y + .009], [x, y + .009]],
            "score": .9, "geometry_reason": None})
    for col, key in enumerate(order):
        add(labels[key], col, .05, f"header-{key}")
    for row in range(rows):
        y = .08 + row * .025
        values = {"description": "Cà phê", "quantity": "2", "unit": "ly",
                  "unit_price": "20.000", "line_total": "40.000"}
        for col, key in enumerate(order):
            add(values[key], col, y, f"r{row}-{key}")
    value["blocks"].append({"block_id": "total", "text": "Tổng tiền: 80.000",
                             "quad": None, "score": None, "geometry_reason": "fixture"})
    return value


@pytest.mark.parametrize("order", [
    ("description", "quantity", "unit", "unit_price", "line_total"),
    ("description", "unit", "quantity", "line_total", "unit_price"),
])
def test_table_roles_follow_headers_and_total_label(order):
    result = baseline(table_page(order=order))
    assert result.payload["items"] == [{"description": "Cà phê", "quantity": "2", "unit": "ly",
                                        "unit_price": "20000", "line_total": "40000"}]
    assert result.payload["total_amount"] == "80000"
    assert metadata(result, "/items/0/line_total")["raw_value"] == "40.000"


def test_geometry_keeps_wrapped_repeated_descriptions_and_missing_cell_in_row():
    value = table_page(rows=2)
    first = next(block for block in value["blocks"] if block["block_id"] == "r0-description")
    wrapped = deepcopy(first)
    wrapped.update(block_id="wrap", text="hư cấu")
    wrapped["quad"] = [[x, y + .01] for x, y in wrapped["quad"]]
    value["blocks"].insert(6, wrapped)
    value["blocks"] = [block for block in value["blocks"] if block["block_id"] != "r0-unit"]
    result = baseline(value)
    assert len(result.payload["items"]) == 2
    assert result.payload["items"][0]["description"] == "Cà phê hư cấu"
    assert result.payload["items"][0]["unit"] is None
    assert result.payload["items"][0]["unit_price"] == "20000"
    assert result.payload["items"][1]["description"] == "Cà phê"
    assert result.payload["items"][1]["unit"] == "ly"


@pytest.mark.parametrize("rows", [0, 1, 30])
def test_table_row_profile_preserves_all_rows(rows):
    assert len(baseline(table_page(rows=rows)).payload["items"]) == rows


def test_31_rows_is_failure_not_silent_truncation():
    from vietdoc.pipeline.extraction.ocr_input import BaselineError
    with pytest.raises(BaselineError, match="PROFILE_EXCEEDED"):
        baseline(table_page(rows=31))


def test_unavailable_geometry_uses_ordered_grammar_without_inventing_boxes():
    value = page(["Tên hàng", "SL", "ĐVT", "Đơn giá", "Thành tiền", "Cà phê", "hư cấu",
                  "2", "ly", "20.000", "40.000", "Tổng tiền: 80.000"])
    result = baseline(value)
    assert result.payload["items"][0]["description"] == "Cà phê hư cấu"
    assert result.payload["items"][0]["quantity"] == "2"
    assert all(item["source_regions"] == [] for item in result.field_metadata)


def test_ordered_grammar_rejects_missing_cell_instead_of_shifting():
    from vietdoc.pipeline.extraction.ocr_input import BaselineError
    with pytest.raises(BaselineError, match="TABLE_LAYOUT_UNSUPPORTED"):
        baseline(page(["Tên hàng", "SL", "ĐVT", "Đơn giá", "Thành tiền", "Cà phê",
                       "2", "20.000", "40.000", "Tổng tiền: 80.000"]))


def test_structural_ai1_objects_are_accepted_without_importing_owning_types():
    data = page(["Tổng tiền: 80.000"])
    obj = SimpleNamespace(**{**data, "blocks": tuple(SimpleNamespace(**b) for b in data["blocks"])})
    assert baseline(obj).payload["total_amount"] == "80000"


def test_item_description_with_total_label_is_not_a_scalar_or_table_end():
    value = table_page()
    next(b for b in value["blocks"] if b["block_id"] == "r0-description")["text"] = "Tổng tiền: bộ quà hư cấu"
    result = baseline(value)
    assert len(result.payload["items"]) == 1
    assert result.payload["items"][0]["description"] == "Tổng tiền: bộ quà hư cấu"
    assert result.payload["total_amount"] == "80000"


def test_same_total_value_multiple_labels_retains_value_without_selecting_highlight():
    result = baseline(page(["Tổng tiền: 80.000", "Tổng thanh toán: 80.000"]))
    assert result.payload["total_amount"] == "80000"
    field = metadata(result, "/total_amount")
    assert field["source_regions"] == []
    assert "SOURCE_AMBIGUOUS" in field["review_flags"]


def test_matcher_receives_only_field_cell_context_and_confidence_stays_null():
    value = table_page()
    blocks = {block["block_id"]: block for block in value["blocks"]}
    def matcher(path, raw, ids):
        field = dict(path=path, raw_value=raw, value_origin="prediction", source_regions=[],
                     ocr_score=None, confidence=None, confidence_method=None, review_flags=[])
        if path == "/items/0/line_total":
            assert ids == ("r0-line_total",)
            field["source_regions"] = [{"page": 0, "quad": blocks[ids[0]]["quad"], "ocr_block_ids": list(ids)}]
        return field
    result = baseline(value, evidence_matcher=matcher)
    field = metadata(result, "/items/0/line_total")
    assert field["source_regions"][0]["ocr_block_ids"] == ["r0-line_total"]
    assert field["confidence"] is None


def test_prepared_unavailable_mapping_never_accepts_quads():
    from vietdoc.pipeline.extraction.ocr_input import BaselineError
    prepared = {"page": 0, "canonical": {"width": 1000, "height": 1000},
                "geometry_status": "unavailable", "preprocess_version": "fixture.v1"}
    with pytest.raises(BaselineError):
        baseline(table_page(), prepared=prepared)


@pytest.mark.parametrize("bad", ["score", "flags", "regions"])
def test_malformed_matcher_output_is_typed_failure(bad):
    from vietdoc.pipeline.extraction.ocr_input import BaselineError
    def matcher(path, raw, ids):
        field = dict(path=path, raw_value=raw, value_origin="prediction", source_regions=[],
                     ocr_score=None, confidence=None, confidence_method=None, review_flags=[])
        if bad == "score":
            field["ocr_score"] = float("nan")
        elif bad == "flags":
            field["review_flags"] = "invalid"
        else:
            field["source_regions"] = [None]
        return field
    with pytest.raises(BaselineError):
        baseline(page(["Tổng tiền: 80.000"]), evidence_matcher=matcher)


@pytest.mark.parametrize("matrix", [None, [[0, -1, 1000], [1, 0, 0], [0, 0, 1]],
                                   [[1, 0, 0], [0, 0, 0], [0, 0, 1]]], ids=["missing", "rotated", "singular"])
def test_baseline_never_treats_unsupported_prepared_transform_as_identity(matrix):
    from vietdoc.pipeline.extraction.ocr_input import BaselineError
    image = dict(width=1000, height=1000, color_order="RGB", dtype="uint8")
    prepared = dict(page=0, canonical=image, processed=dict(image), preprocess_version="fixture.v1",
                    geometry_status="available", inverse_transform=matrix, geometry_reason=None)
    with pytest.raises(BaselineError):
        baseline(table_page(), prepared=prepared)


def test_table_preserves_declared_row_reading_order_after_grouping_geometry():
    value = table_page(rows=2)
    next(b for b in value["blocks"] if b["block_id"] == "r1-quantity")["text"] = "3"
    headers = value["blocks"][:5]
    row0 = [b for b in value["blocks"] if b["block_id"].startswith("r0-")]
    row1 = [b for b in value["blocks"] if b["block_id"].startswith("r1-")]
    value["blocks"] = headers + row1 + row0 + value["blocks"][-1:]
    result = baseline(value)
    assert [item["quantity"] for item in result.payload["items"]] == ["3", "2"]


def test_footer_amount_split_into_tokens_does_not_become_an_extra_item():
    value = table_page()
    value["blocks"].pop()
    def block(name, text, x):
        return dict(block_id=name, text=text, quad=[[x, .9], [x+.02, .9], [x+.02, .91], [x, .91]],
                    score=None, geometry_reason=None)
    value["blocks"] += [block("footer", "Tổng tiền", .03), block("amount", "80.000", .75), block("currency", "đ", .8)]
    result = baseline(value)
    assert len(result.payload["items"]) == 1
    assert result.payload["total_amount"] == "80000"


def test_multiple_tables_fail_instead_of_silently_returning_first_table():
    from vietdoc.pipeline.extraction.ocr_input import BaselineError
    value = table_page()
    second = table_page()
    for block in second["blocks"]:
        block["block_id"] = "second-" + block["block_id"]
        if block["quad"] is not None:
            block["quad"] = [[x, y + .3] for x, y in block["quad"]]
    value["blocks"] += second["blocks"]
    with pytest.raises(BaselineError, match="TABLE_LAYOUT_UNSUPPORTED"):
        baseline(value)


def located(name, text, x, y, height=.01, width=.12):
    return dict(block_id=name, text=text,
                quad=[[x, y], [x+width, y], [x+width, y+height], [x, y+height]],
                score=.9, geometry_reason=None)


@pytest.mark.parametrize("value_first", [True, False])
@pytest.mark.parametrize("label_height", [.01, .03])
def test_footer_pairing_uses_visual_line_not_next_cash_amount(value_first, label_height):
    value = table_page()
    value["blocks"].pop()
    amount = located("total-value", "80.000", .75, .9)
    label = located("total-label", "Tổng tiền", .03, .9, height=label_height)
    value["blocks"] += ([amount, label] if value_first else [label, amount]) + [
        located("cash-value", "100.000", .75, .943),
        located("cash-label", "Tiền khách đưa", .03, .945),
        located("change-label", "Tiền thừa", .03, .97),
        located("change-value", "20.000", .75, .97),
    ]
    result = baseline(value)
    assert result.payload["total_amount"] == "80000"
    assert len(result.payload["items"]) == 1
    assert result.payload["items"][0]["line_total"] == "40000"
    assert metadata(result, "/total_amount")["raw_value"] == "80.000"
    assert metadata(result, "/total_amount")["confidence"] is None


def test_scalar_only_value_before_label_is_paired_with_source_context():
    value = page([])
    value["blocks"] = [located("amount", "80.000", .7, .1),
                       located("label", "Tổng tiền", .1, .1)]
    result = baseline(value)
    assert result.payload["total_amount"] == "80000"
    assert result.raw_candidates["/total_amount"] == [
        {"raw_value": "80.000", "context_block_ids": ["label", "amount"]}]


def test_separate_label_without_geometry_does_not_take_next_cash_value():
    result = baseline(page(["Tổng tiền", "100.000", "Tiền khách đưa"]))
    assert result.payload["total_amount"] is None
    assert result.issues


def test_two_amounts_on_total_row_abstain_instead_of_picking_reading_order():
    value = page([])
    value["blocks"] = [located("label", "Tổng tiền", .1, .1),
                       located("one", "80.000", .5, .1),
                       located("two", "100.000", .75, .1)]
    result = baseline(value)
    assert result.payload["total_amount"] is None
    assert "FIELD_AMBIGUOUS" in metadata(result, "/total_amount")["review_flags"]


def test_numeric_continuation_before_footer_stays_a_table_row():
    value = table_page()
    value["blocks"].pop()
    value["blocks"] += [located("continuation", "5.000", .75, .2),
                        located("total-value", "80.000", .75, .9),
                        located("total-label", "Tổng tiền", .03, .9)]
    result = baseline(value)
    assert len(result.payload["items"]) == 2
    assert result.payload["items"][1]["line_total"] == "5000"
    assert result.payload["total_amount"] == "80000"


@pytest.mark.parametrize("case_index", [0, 1, 2])
def test_missing_fields_on_v2_pages_stay_unknown_with_page_diagnostics(case_index):
    import json
    from pathlib import Path
    golden = json.loads((Path(__file__).parents[2] / "fixtures/ocr-artifact-v2.json").read_text(encoding="utf-8"))
    result = baseline(golden["cases"][case_index]["expected"])
    assert result.payload["total_amount"] is None
    assert result.field_states["/total_amount"] == "unknown"
    field = metadata(result, "/total_amount")
    assert field["value_origin"] == "prediction"
    assert field["source_regions"] == [] and field["confidence"] is None
    if case_index < 2:
        assert "OCR_UNREADABLE_REGIONS" in field["review_flags"]
        assert "SOURCE_OCR_INCOMPLETE" in field["review_flags"]
        assert any(issue["code"] == "OCR_UNREADABLE_REGIONS" for issue in result.issues)
    else:
        assert "OCR_UNREADABLE_REGIONS" not in field["review_flags"]


def test_bare_label_is_value_not_located_not_an_unreadable_gold_claim():
    result = baseline(page(["Địa chỉ:"]))
    assert result.field_states["/merchant_address"] == "unknown"
    assert "FIELD_VALUE_NOT_LOCATED" in metadata(result, "/merchant_address")["review_flags"]


def test_partial_page_keeps_explicit_absence_distinct_from_missing_prediction():
    value = page(["Địa chỉ: Không có"])
    value.update(artifact_version=2, recognition_status="partial", review_flags=["OCR_UNREADABLE_REGIONS"],
                 unreadable_regions=[dict(region_id="u1", quad=None, score=None,
                                          geometry_reason="unavailable", reason="EMPTY_RECOGNITION")])
    result = baseline(value)
    assert result.field_states["/merchant_address"] == "absent"
    assert result.field_states["/total_amount"] == "unknown"
    assert "OCR_UNREADABLE_REGIONS" in metadata(result, "/merchant_address")["review_flags"]


@pytest.mark.parametrize("document_type", ["receipt", "invoice"])
@pytest.mark.parametrize("label", ["Tổng cộng", "Tổng cộng:"])
@pytest.mark.parametrize("numbers_first", [False, True])
@pytest.mark.parametrize("with_cash", [False, True])
def test_summary_quantity_never_creates_product_rows(document_type, label, numbers_first, with_cash):
    value = table_page()
    value["blocks"].pop()
    footer = located("summary-label", label, .03, .9)
    numbers = [located("summary-quantity", "2", .21, .9),
               located("summary-amount", "80.000", .75, .9)]
    value["blocks"] += numbers + [footer] if numbers_first else [footer] + numbers
    if with_cash:
        value["blocks"] += [located("cash-label", "Tiền khách đưa", .03, .94),
                            located("cash-amount", "100.000", .75, .94)]
    result = baseline(value, document_type)
    assert result.payload["items"] == [{"description": "Cà phê", "quantity": "2", "unit": "ly",
                                        "unit_price": "20000", "line_total": "40000"}]
    # Quantity and amount are both possible numeric candidates on this row.
    # Decline the scalar instead of inferring its role from number size/order.
    assert result.payload["total_amount"] is None
    assert "FIELD_AMBIGUOUS" in metadata(result, "/total_amount")["review_flags"]


@pytest.mark.parametrize("value_first", [False, True])
@pytest.mark.parametrize("suffix", [":", ":   "])
def test_empty_colon_suffix_pairs_same_row_scalar(value_first, suffix):
    label = located("label", "Tổng tiền" + suffix, .1, .1)
    amount = located("amount", "80.000", .7, .1)
    value = page([])
    value["blocks"] = [amount, label] if value_first else [label, amount]
    result = baseline(value)
    assert result.payload["total_amount"] == "80000"
    assert metadata(result, "/total_amount")["raw_value"] == "80.000"


def test_colon_pairing_still_declines_multiple_amounts_or_missing_geometry():
    value = page([])
    value["blocks"] = [located("label", "Tổng tiền:", .1, .1),
                       located("one", "80.000", .5, .1),
                       located("two", "100.000", .75, .1)]
    result = baseline(value)
    assert result.payload["total_amount"] is None
    assert "FIELD_AMBIGUOUS" in metadata(result, "/total_amount")["review_flags"]
    result = baseline(page(["Tổng tiền:", "80.000"]))
    assert result.payload["total_amount"] is None
    assert result.field_states["/total_amount"] == "unknown"


@pytest.mark.parametrize("description", ["Tổng tiền: bộ quà hư cấu", "Tổng cộng: bộ giấy hư cấu"])
def test_label_like_product_description_survives_sparse_table(description):
    value = table_page()
    next(block for block in value["blocks"] if block["block_id"] == "r0-description")["text"] = description
    value["blocks"] = [block for block in value["blocks"] if block["block_id"] not in
                       {"r0-quantity", "r0-unit", "r0-unit_price"}]
    result = baseline(value)
    assert len(result.payload["items"]) == 1
    assert result.payload["items"][0]["description"] == description
    assert result.payload["items"][0]["line_total"] == "40000"
    assert result.payload["total_amount"] == "80000"
