"""Conservative Vietnamese label/header rules baseline, not a trained extractor."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Any

from vietdoc.contracts.compute import BUSINESS_SCHEMA, ComputeContracts
from vietdoc.pipeline.normalization import normalize_date, normalize_money, normalize_quantity, normalize_text, normalize_time

from .ocr_input import BaselineError, Block, horizontally_separate, norm, same_visual_row, snapshot_page
from .table import HEADERS, NUMBER, table_rows

BASELINE_VERSION = "vi-label-header-b0.v2"
LABELS = {
    "merchant_name": ("cửa hàng", "tên cửa hàng"),
    "merchant_address": ("địa chỉ", "địa chỉ cửa hàng"),
    "transaction_date": ("ngày bán", "ngày", "ngày giao dịch"),
    "transaction_time": ("giờ", "giờ bán"),
    "invoice_number": ("số hóa đơn", "số hđ", "hóa đơn số"),
    "issue_date": ("ngày lập", "ngày hóa đơn"),
    "seller_name": ("đơn vị bán", "bên bán", "người bán", "tên đơn vị bán"),
    "buyer_name": ("đơn vị mua", "bên mua", "người mua", "tên người mua"),
    "subtotal": ("cộng tiền hàng", "tổng tiền hàng", "tạm tính"),
    "tax_amount": ("tiền thuế gtgt", "thuế gtgt", "tiền thuế", "thuế"),
    "discount_amount": ("chiết khấu", "giảm giá"),
    "total_amount": ("tổng thanh toán", "tổng tiền", "tổng cộng", "tổng tiền thanh toán", "tổng"),
}
BY_LABEL = {label: key for key, labels in LABELS.items() for label in labels}
ABSENT = {"không có", "không áp dụng", "n/a"}
UNREADABLE = {"[không đọc được]", "[unreadable]", "???"}
METADATA_KEYS = {"path", "raw_value", "value_origin", "source_regions", "ocr_score",
                 "confidence", "confidence_method", "review_flags"}


@dataclass(frozen=True)
class BaselineResult:
    payload: dict
    raw_candidates: dict
    field_metadata: list[dict]
    issues: list[dict]
    field_states: dict[str, str]


def _label(text: str) -> tuple[str, str | None] | None:
    label, separator, raw = text.partition(":")
    key = BY_LABEL.get(norm(label))
    if key is None:
        return None
    return key, raw.strip() if separator else None


def _normalize(key, raw):
    if not raw or norm(raw) in UNREADABLE:
        return None, "unreadable", "FIELD_UNREADABLE"
    if norm(raw) in ABSENT:
        return None, "absent", "FIELD_EXPLICITLY_ABSENT"
    if key == "quantity":
        function = normalize_quantity
    elif key.endswith("date"):
        function = normalize_date
    elif key.endswith("time"):
        function = normalize_time
    elif key.endswith("amount") or key in ("subtotal", "unit_price", "line_total"):
        function = normalize_money
    else:
        function = normalize_text
    result = function(raw)
    if result.status == "ok":
        return result.value, "present", None
    return None, result.status, "VALUE_AMBIGUOUS" if result.status == "ambiguous" else "VALUE_INVALID"


def extract_baseline(page: Any, document_type: str, *, prepared: Any = None,
                     evidence_matcher: Callable[[str, str, tuple[str, ...]], dict] | None = None) -> BaselineResult:
    """Extract business values only; IDs and runtime envelope belong to service.

    evidence_matcher binds AI1's OcrPage/PreparedPage and EvidenceRequest adapter.
    With no accepted matcher, publish no regions rather than invent source boxes.
    """
    if document_type not in ("receipt", "invoice"):
        raise BaselineError("DOCUMENT_TYPE_UNSUPPORTED")
    source = snapshot_page(page, prepared)
    contracts = ComputeContracts()
    scalar_fields, item_fields = contracts.business_fields(document_type)
    rows, located = table_rows(source, lambda text: _label(text) is not None)
    table_ids = {b.block_id for row in rows for blocks in row.values() for b in blocks}
    candidates = defaultdict(list)
    for block in source.blocks:
        if block.block_id in table_ids:
            continue
        found = _label(block.text)
        if found is None or found[0] not in scalar_fields:
            continue
        key, raw = found
        context = [block]
        if raw is None:
            numeric = key.endswith("amount") or key == "subtotal"
            paired = [other for other in source.blocks
                      if other is not block and other.block_id not in table_ids
                      and _label(other.text) is None and norm(other.text) not in HEADERS
                      and same_visual_row(block, other) and horizontally_separate(block, other)
                      and (not numeric or NUMBER.fullmatch(other.text.strip()))]
            if paired:
                candidates[f"/{key}"].extend((other.text, (block, other)) for other in paired)
                continue
        candidates[f"/{key}"].append((raw or "", tuple(context)))

    payload = {key: None for key in scalar_fields}
    payload["items"] = []
    for index, row in enumerate(rows):
        payload["items"].append({key: None for key in item_fields})
        for key in item_fields:
            blocks = tuple(row.get(key, ()))
            if not blocks:
                continue
            if key == "description":
                candidates[f"/items/{index}/{key}"].append((" ".join(b.text for b in blocks), blocks))
            else:
                candidates[f"/items/{index}/{key}"].extend((b.text, (b,)) for b in blocks)

    metadata, issues, states, raw_candidates = [], [], {"/items": "present" if located else "unknown"}, {}
    paths = [(f"/{key}", key, payload) for key in scalar_fields]
    paths += [(f"/items/{index}/{key}", key, item) for index, item in enumerate(payload["items"]) for key in item_fields]
    by_id = {block.block_id: block for block in source.blocks}

    def issue(code, path):
        issues.append({"id": f"{code}:{path}", "code": code, "severity": "warning", "paths": [path],
                       "message": "Baseline diagnostic; review source and unresolved values."})

    for path, key, target in paths:
        choices = candidates[path]
        raw_candidates[path] = [{"raw_value": raw, "context_block_ids": [b.block_id for b in blocks]}
                                for raw, blocks in choices]
        flags = ["CONFIDENCE_UNCALIBRATED"]
        raw, value, state, context = None, None, "unknown", ()
        if not choices:
            flags.append("FIELD_NOT_LOCATED")
        else:
            outcomes = [_normalize(key, candidate[0]) for candidate in choices]
            if len(set((value, state) for value, state, _ in outcomes)) != 1:
                state = "ambiguous"
                flags.append("FIELD_AMBIGUOUS")
            else:
                value, state, diagnostic = outcomes[0]
                raw, context = choices[0]
                if diagnostic:
                    flags.append(diagnostic)
                if len(choices) > 1:
                    raw, context = None, ()
                    flags.append("SOURCE_AMBIGUOUS")
        target[key], states[path] = value, state
        field = dict(path=path, raw_value=raw, value_origin="absent" if state == "absent" else "prediction",
                     source_regions=[], ocr_score=None, confidence=None, confidence_method=None, review_flags=[])
        if value is not None and len(choices) == 1 and evidence_matcher is not None:
            context_ids = tuple(block.block_id for block in context)
            matched = evidence_matcher(path, raw, context_ids)
            if (not isinstance(matched, dict) or set(matched) != METADATA_KEYS
                    or matched["path"] != path or matched["raw_value"] != raw
                    or matched["confidence"] is not None or matched["confidence_method"] is not None
                    or matched["value_origin"] != "prediction"
                    or not isinstance(matched["source_regions"], list)
                    or not isinstance(matched["review_flags"], list)
                    or any(not isinstance(flag, str) for flag in matched["review_flags"])):
                raise BaselineError("EVIDENCE_INVALID")
            for region in matched["source_regions"]:
                if not isinstance(region, dict) or set(region) != {"page", "quad", "ocr_block_ids"}:
                    raise BaselineError("EVIDENCE_INVALID")
                ids = region.get("ocr_block_ids")
                if not isinstance(ids, list) or len(ids) != 1 or ids[0] not in context_ids:
                    raise BaselineError("EVIDENCE_INVALID")
                block = by_id[ids[0]]
                if block.quad is None or region.get("page") != 0 or region.get("quad") != [list(p) for p in block.quad]:
                    raise BaselineError("EVIDENCE_INVALID")
            score = matched["ocr_score"]
            if score is not None:
                regions = matched["source_regions"]
                if (type(score) not in (int, float) or len(regions) != 1
                        or score != by_id[regions[0]["ocr_block_ids"][0]].score):
                    raise BaselineError("EVIDENCE_INVALID")
            field.update(matched)
        elif value is not None and evidence_matcher is None:
            flags.append("SOURCE_MATCHER_UNAVAILABLE")
        field["review_flags"] = list(dict.fromkeys(field["review_flags"] + flags))
        metadata.append(field)
        for flag in flags:
            if flag.startswith(("FIELD_", "VALUE_")):
                issue(flag, path)
    if not located:
        issue("TABLE_NOT_LOCATED", "/items")
    # Arithmetic is diagnostic only and never fills or changes recognized values.
    with localcontext() as context:
        context.prec = 80
        for index, item in enumerate(payload["items"]):
            if all(item[k] is not None for k in ("quantity", "unit_price", "line_total")):
                if Decimal(item["quantity"]) * Decimal(item["unit_price"]) != Decimal(item["line_total"]):
                    issue("ITEM_ARITHMETIC_MISMATCH", f"/items/{index}/line_total")
    contracts.validate(BUSINESS_SCHEMA, payload)
    return BaselineResult(payload, raw_candidates, metadata, issues, states)
