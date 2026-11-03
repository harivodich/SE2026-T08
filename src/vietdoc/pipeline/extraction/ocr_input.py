"""AI2's bounded internal snapshot consumer of the AI1 OcrPage proposal.

Accepts AI1 objects or their JSON representation without importing/forking the
owning types. This is not an approved shared wire schema or image validator.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import Any
import unicodedata

MAX_BLOCKS = 4096
MAX_TEXT_CHARS = 128 * 1024


class BaselineError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def norm(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


def get(value: Any, key: str) -> Any:
    try:
        return value[key] if isinstance(value, Mapping) else getattr(value, key)
    except (KeyError, AttributeError, TypeError) as error:
        raise BaselineError("OCR_INPUT_INVALID") from error


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BaselineError("OCR_INPUT_INVALID")
    if len(value) > MAX_TEXT_CHARS:
        raise BaselineError("PROFILE_EXCEEDED")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise BaselineError("OCR_INPUT_INVALID") from error
    return value


def _number(value: Any) -> float:
    if type(value) not in (int, float):
        raise BaselineError("OCR_INPUT_INVALID")
    try:
        number = float(value)
    except (ValueError, OverflowError) as error:
        raise BaselineError("OCR_INPUT_INVALID") from error
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise BaselineError("OCR_INPUT_INVALID")
    return number


@dataclass(frozen=True)
class Block:
    block_id: str
    text: str
    quad: tuple | None
    score: float | None
    geometry_reason: str | None

    @property
    def x(self) -> float:
        return min(point[0] for point in self.quad)

    @property
    def y(self) -> float:
        return sum(point[1] for point in self.quad) / 4

    @property
    def height(self) -> float:
        return max(point[1] for point in self.quad) - min(point[1] for point in self.quad)


@dataclass(frozen=True)
class Page:
    width: int
    height: int
    ocr_version: str
    blocks: tuple[Block, ...]
    preprocess_version: str | None


def same_visual_row(left: Block, right: Block) -> bool:
    """Geometry filter only; callers must establish the semantic field scope."""
    if left.quad is None or right.quad is None:
        return False
    top = max(min(p[1] for p in left.quad), min(p[1] for p in right.quad))
    bottom = min(max(p[1] for p in left.quad), max(p[1] for p in right.quad))
    return bottom - top >= .5 * min(left.height, right.height)


def horizontally_separate(left: Block, right: Block) -> bool:
    if left.quad is None or right.quad is None:
        return False
    return (max(p[0] for p in left.quad) <= min(p[0] for p in right.quad)
            or max(p[0] for p in right.quad) <= min(p[0] for p in left.quad))


def snapshot_page(page: Any, prepared: Any = None) -> Page:
    if type(get(page, "page")) is not int or get(page, "page") != 0:
        raise BaselineError("OCR_INPUT_INVALID")
    width, height = get(page, "width"), get(page, "height")
    if any(type(n) is not int or n <= 0 for n in (width, height)):
        raise BaselineError("OCR_INPUT_INVALID")
    if width * height > 20_000_000:
        raise BaselineError("PROFILE_EXCEEDED")
    version = _text(get(page, "ocr_version"))
    blocks = get(page, "blocks")
    if not isinstance(blocks, (list, tuple)):
        raise BaselineError("OCR_INPUT_INVALID")
    if len(blocks) > MAX_BLOCKS:
        raise BaselineError("PROFILE_EXCEEDED")
    result, ids, characters = [], set(), 0
    for item in blocks:
        block_id, text = _text(get(item, "block_id")), _text(get(item, "text"))
        characters += len(text)
        if characters > MAX_TEXT_CHARS:
            raise BaselineError("PROFILE_EXCEEDED")
        if block_id in ids:
            raise BaselineError("OCR_INPUT_INVALID")
        ids.add(block_id)
        score, quad, reason = get(item, "score"), get(item, "quad"), get(item, "geometry_reason")
        if quad is None:
            _text(reason)
        else:
            if reason is not None or not isinstance(quad, (tuple, list)) or len(quad) != 4:
                raise BaselineError("OCR_INPUT_INVALID")
            points = []
            for point in quad:
                if not isinstance(point, (tuple, list)) or len(point) != 2:
                    raise BaselineError("OCR_INPUT_INVALID")
                points.append(tuple(_number(n) for n in point))
            if points[0] != min(points, key=lambda p: (p[1], p[0])):
                raise BaselineError("OCR_INPUT_INVALID")
            for i in range(4):
                a, b, c = (points[(i + j) % 4] for j in range(3))
                if (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]) <= 0:
                    raise BaselineError("OCR_INPUT_INVALID")
            quad = tuple(points)
        result.append(Block(block_id, text, quad, None if score is None else _number(score), reason))
    preprocess_version = None
    if prepared is not None:
        canonical = get(prepared, "canonical")
        if (get(prepared, "page"), get(canonical, "width"), get(canonical, "height")) != (0, width, height):
            raise BaselineError("OCR_INPUT_INVALID")
        status = get(prepared, "geometry_status")
        if status not in ("available", "unavailable"):
            raise BaselineError("OCR_INPUT_INVALID")
        if type(get(prepared, "page")) is not int:
            raise BaselineError("OCR_INPUT_INVALID")
        for image in (canonical, get(prepared, "processed")):
            if (any(type(get(image, key)) is not int or get(image, key) <= 0 for key in ("width", "height"))
                    or get(image, "color_order") not in ("RGB", "BGR", "GRAY") or get(image, "dtype") != "uint8"):
                raise BaselineError("OCR_INPUT_INVALID")
        if get(canonical, "color_order") != "RGB":
            raise BaselineError("OCR_INPUT_INVALID")
        matrix = get(prepared, "inverse_transform")
        if status == "available":
            if (get(prepared, "geometry_reason") is not None or not isinstance(matrix, (list, tuple))
                    or len(matrix) != 3 or any(not isinstance(row, (list, tuple)) or len(row) != 3 for row in matrix)):
                raise BaselineError("OCR_INPUT_INVALID")
            try:
                if any(type(n) not in (int, float) or not math.isfinite(n) for row in matrix for n in row):
                    raise BaselineError("OCR_INPUT_INVALID")
                scale = matrix[2][2]
                valid_axes = scale != 0 and matrix[0][0] / scale > 0 and matrix[1][1] / scale > 0
            except OverflowError as error:
                raise BaselineError("OCR_INPUT_INVALID") from error
            if not valid_axes or any(matrix[r][c] != 0 for r, c in ((0, 1), (1, 0), (2, 0), (2, 1))):
                # B0 groups canonical axes only when they preserve processed rows/columns.
                # Rotated/sheared/projective layout needs AI1's processed-frame adapter.
                raise BaselineError("LAYOUT_TRANSFORM_UNSUPPORTED")
        elif matrix is not None or not isinstance(get(prepared, "geometry_reason"), str) or not get(prepared, "geometry_reason").strip():
            raise BaselineError("OCR_INPUT_INVALID")
        if status == "unavailable" and any(block.quad is not None for block in result):
            raise BaselineError("OCR_INPUT_INVALID")
        preprocess_version = _text(get(prepared, "preprocess_version"))
    return Page(width, height, version, tuple(result), preprocess_version)
