"""Conservative source matching for raw values supplied by the extractor.

No business extraction, numeric normalization or fuzzy correction. Context IDs
are explicit consumer hints, never inferred grid cells. Ambiguous candidates
remain reviewable without being published as selected source regions.
"""

from dataclasses import dataclass
import unicodedata

from vietdoc.contracts.ocr import OcrBlock, OcrPage, PreparedPage
from vietdoc.pipeline.geometry import processed_quad


EVIDENCE_VERSION = "exact-raw-label-row-spans.v3"
MAX_SPAN_BLOCKS = 4


def _text(value: str) -> str:
    # Retain Vietnamese accents, punctuation and digits. Never turn 80.000 into
    # 80000 or repair OCR using the extractor value/transcript.
    return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


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
    Label text must identify one complete block in that scope. When PreparedPage
    geometry and a label are supplied, every candidate must satisfy that spatial
    context, including a unique text match. Exactly one candidate to the right
    on the label's processed row may be selected; otherwise remain uncertain.
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
        return EvidenceMatch(request.path, request.raw_value, status, tuple(selected), tuple(candidates), (flag,) if flag else ())

    if request.raw_value is None:
        return outcome("value_unavailable", "SOURCE_VALUE_UNAVAILABLE")
    if request.label_text is not None:
        labels = [block for block in blocks if _text(block.text) == _text(request.label_text)]
        if not labels:
            return outcome("context_not_found", "SOURCE_CONTEXT_NOT_FOUND")
        if len(labels) > 1:
            return outcome("ambiguous", "SOURCE_CONTEXT_AMBIGUOUS")
    target = _text(request.raw_value)
    candidates = []
    for start in range(len(blocks)):
        for count in range(1, min(MAX_SPAN_BLOCKS, len(blocks) - start) + 1):
            span = blocks[start:start + count]
            candidate = _text(" ".join(block.text for block in span))
            if candidate == target:
                candidates.append(span)
            if len(candidate) >= len(target):
                break
    candidate_ids = tuple(tuple(block.block_id for block in span) for span in candidates)
    if not candidates:
        return outcome("not_found", "SOURCE_NOT_FOUND")
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
    if any(block.quad is None for block in selected):
        return outcome("geometry_unavailable", "SOURCE_GEOMETRY_UNAVAILABLE", candidates=candidate_ids)
    return outcome("matched", selected=selected, candidates=candidate_ids)
