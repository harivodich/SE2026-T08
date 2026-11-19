"""Conservative source matching for raw values supplied by the extractor.

No business extraction, numeric normalization or fuzzy correction. Context IDs
are explicit consumer hints, never inferred grid cells. Ambiguous candidates
remain reviewable without being published as selected source regions.
"""

from dataclasses import dataclass
import re
import unicodedata

from vietdoc.contracts.ocr import OcrBlock, OcrPage, PreparedPage
from vietdoc.pipeline.geometry import processed_quad


EVIDENCE_VERSION = "exact-raw-cross-block-occurrence-guard.v5"
MAX_SPAN_BLOCKS = 4
_TOKENS = re.compile(r"\d+(?:[.,]\d+)*|[^\W\d]+|[^\w\s]")


def _text(value: str) -> str:
    # Retain Vietnamese accents, punctuation and digits. Never turn 80.000 into
    # 80000 or repair OCR using the extractor value/transcript.
    return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


def _unresolved_occurrences(blocks, target_tokens, exact_ids):
    """Return minimal block spans covering unresolved token occurrences.

    Numeric tokens retain all separators/digits, but attached currency/letters
    are separate tokens for abstention only. Positive matching still compares
    exact raw text. Track the actual token range rather than every enclosing
    span, so an exact scoped wrap is not counted again with a neighboring label.
    No substring coordinates or item/row association are inferred here.
    """
    flattened = tuple((token, index) for index, block in enumerate(blocks)
                      for token in _TOKENS.findall(_text(block.text)))
    tokens = tuple(token for token, _ in flattened)
    count = len(target_tokens)
    unresolved, seen = [], set(exact_ids)
    for start in range(len(tokens) - count + 1):
        if tokens[start:start + count] != target_tokens:
            continue
        first, last = flattened[start][1], flattened[start + count - 1][1]
        # Unsupported long spans alone still have no publishable candidate.
        # They must nevertheless invalidate an otherwise false exact unique.
        if last - first + 1 > MAX_SPAN_BLOCKS and not exact_ids:
            continue
        span = blocks[first:last + 1]
        ids = tuple(block.block_id for block in span)
        if ids not in seen:
            seen.add(ids)
            unresolved.append(span)
    return tuple(unresolved)


@dataclass(frozen=True, slots=True)
class EvidenceRequest:
    path: str
    raw_value: str | None
    context_block_ids: tuple[str, ...] = ()
    label_text: str | None = None

    def __post_init__(self):
        if not isinstance(self.path, str) or not self.path.startswith("/"):
            raise ValueError("Expected an extraction field JSON Pointer")
        for name, value in (("raw_value", self.raw_value), ("label_text", self.label_text)):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be nonblank text or null")
        if not isinstance(self.context_block_ids, (tuple, list)):
            raise ValueError("context_block_ids must be an array of source IDs")
        ids = tuple(self.context_block_ids)
        if any(not isinstance(value, str) or not value.strip() for value in ids) or len(ids) != len(set(ids)):
            raise ValueError("Context IDs must be unique nonblank strings")
        object.__setattr__(self, "context_block_ids", ids)


@dataclass(frozen=True, slots=True)
class EvidenceMatch:
    path: str
    raw_value: str | None
    status: str
    blocks: tuple[OcrBlock, ...]
    candidate_block_ids: tuple[tuple[str, ...], ...]
    review_flags: tuple[str, ...]

    def to_field_metadata(self) -> dict:
        """Adapt to the existing FieldMetadata schema, without changing payload.

        Regions retain each source quad instead of inventing a union box. Only
        one block has an unaggregated OCR score; multi-block score stays null.
        A missing prediction is not evidence that a field is absent on paper.
        """
        return {
            "path": self.path,
            "raw_value": self.raw_value,
            "value_origin": "prediction",
            "source_regions": [
                {"page": 0, "quad": [list(point) for point in block.quad], "ocr_block_ids": [block.block_id]}
                for block in self.blocks if self.status == "matched"
            ],
            "ocr_score": self.blocks[0].score if self.status == "matched" and len(self.blocks) == 1 else None,
            "confidence": None,
            "confidence_method": None,
            "review_flags": list(self.review_flags),
        }


def _right_of_label_on_row(label_quad, value_quad):
    def bounds(quad):
        xs, ys = zip(*quad)
        return min(xs), min(ys), max(xs), max(ys)
    label, value = bounds(label_quad), bounds(value_quad)
    height = min(label[3] - label[1], value[3] - value[1])
    overlap = min(label[3], value[3]) - max(label[1], value[1])
    centers = abs((label[1] + label[3]) - (value[1] + value[3])) / 2
    return value[0] >= label[2] and overlap >= height / 2 and centers <= height / 2


def match_evidence(page: OcrPage, request: EvidenceRequest, *, prepared: PreparedPage | None = None) -> EvidenceMatch:
    """Match complete OCR blocks or up to four consecutive blocks in context.

    Explicit context is traversed in page reading order, independent of the hint
    array's order. This lets the consumer scope a row or wrapped description.
    Multi-block spans require explicit consumer scope for the same item/field;
    consecutive reading order alone does not prove a wrapped description.
    Label context requires PreparedPage and a unique complete label block. Every
    candidate must then satisfy the label's processed row, including unique text
    matches. Embedded whole-token occurrences block false uniqueness without
    inventing substring quads; explicit scope can exclude unrelated occurrences.
    """
    if not isinstance(page, OcrPage) or not isinstance(request, EvidenceRequest):
        raise ValueError("Expected OcrPage and EvidenceRequest")
    if prepared is not None:
        page.validate_against(prepared)
    by_id = {block.block_id: block for block in page.blocks}
    if any(block_id not in by_id for block_id in request.context_block_ids):
        raise ValueError("Context refers to an unknown OCR block")
    scope = set(request.context_block_ids)
    blocks = tuple(block for block in page.blocks if not scope or block.block_id in scope)

    def outcome(status, flag=None, selected=(), candidates=()):
        flags = tuple(dict.fromkeys(((flag,) if flag else ()) + page.review_flags +
                      (("SOURCE_OCR_INCOMPLETE",) if page.unreadable_regions else ())))
        return EvidenceMatch(request.path, request.raw_value, status, tuple(selected), tuple(candidates), flags)

    if request.raw_value is None:
        return outcome("value_unavailable", "SOURCE_VALUE_UNAVAILABLE")
    if request.label_text is not None:
        labels = [block for block in blocks if _text(block.text) == _text(request.label_text)]
        if not labels:
            return outcome("context_not_found", "SOURCE_CONTEXT_NOT_FOUND")
        if len(labels) > 1:
            return outcome("ambiguous", "SOURCE_CONTEXT_AMBIGUOUS")
    target = _text(request.raw_value)
    target_tokens = tuple(_TOKENS.findall(target))
    candidates = []
    for start in range(len(blocks)):
        for count in range(1, min(MAX_SPAN_BLOCKS, len(blocks) - start) + 1):
            span = blocks[start:start + count]
            candidate = _text(" ".join(block.text for block in span))
            if candidate == target:
                candidates.append(span)
            if len(candidate) >= len(target):
                break
    exact_ids = tuple(tuple(block.block_id for block in span) for span in candidates)
    unresolved = _unresolved_occurrences(blocks, target_tokens, exact_ids)
    candidate_ids = exact_ids + tuple(tuple(block.block_id for block in span) for span in unresolved)
    if request.label_text is not None and prepared is None:
        return outcome("ambiguous", "SOURCE_CONTEXT_GEOMETRY_UNAVAILABLE", candidates=candidate_ids)
    if unresolved:
        return outcome("ambiguous", "SOURCE_OCCURRENCE_UNRESOLVED", candidates=candidate_ids)
    if not candidates:
        return outcome("not_found", "SOURCE_NOT_FOUND")
    if page.unreadable_regions and not scope:
        return outcome("ambiguous", "SOURCE_OCR_INCOMPLETE", candidates=candidate_ids)
    selected = candidates[0]
    if prepared is not None and request.label_text is not None:
        label_quad = processed_quad(labels[0].quad, prepared)
        candidate_quads = [tuple(processed_quad(block.quad, prepared) for block in span) for span in candidates]
        # Unknown candidate geometry cannot be excluded as if it were elsewhere.
        if label_quad is None or any(quad is None for span in candidate_quads for quad in span):
            return outcome("ambiguous", "SOURCE_CONTEXT_GEOMETRY_UNAVAILABLE", candidates=candidate_ids)
        row_candidates = [span for span, quads in zip(candidates, candidate_quads)
                          if all(_right_of_label_on_row(label_quad, quad) for quad in quads)]
        if len(row_candidates) != 1:
            return outcome("ambiguous", "SOURCE_AMBIGUOUS", candidates=candidate_ids)
        selected = row_candidates[0]
    elif len(candidates) > 1:
        return outcome("ambiguous", "SOURCE_AMBIGUOUS", candidates=candidate_ids)
    if len(selected) > 1 and not scope:
        return outcome("ambiguous", "SOURCE_SPAN_CONTEXT_REQUIRED", candidates=candidate_ids)
    if any(block.quad is None for block in selected):
        return outcome("geometry_unavailable", "SOURCE_GEOMETRY_UNAVAILABLE", candidates=candidate_ids)
    return outcome("matched", selected=selected, candidates=candidate_ids)
