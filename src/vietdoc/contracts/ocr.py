"""OCR/page proposal for O1.1; see docs/ocr-input-proposal.md.

These dependency-free types validate metadata, not image bytes, storage assets,
or OCR accuracy. Shared wire-schema approval remains with Backend and consumers.
"""

from dataclasses import asdict, dataclass
import math
from typing import Literal, TypeAlias


Point: TypeAlias = tuple[float, float]
Quad: TypeAlias = tuple[Point, Point, Point, Point]
MatrixRow: TypeAlias = tuple[float, float, float]
Matrix3x3: TypeAlias = tuple[MatrixRow, MatrixRow, MatrixRow]


def _record(value: object, keys: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"Expected exactly these keys: {', '.join(sorted(keys))}")
    return value


def _sequence(value: object, name: str) -> tuple:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be an array")
    return tuple(value)


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonblank string")


def _number(value: object, name: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _dimensions(width: int, height: int) -> None:
    if any(type(n) is not int or n <= 0 for n in (width, height)):
        raise ValueError("width and height must be positive integers")


def _page(page: int) -> None:
    if type(page) is not int or page != 0:
        raise ValueError("Only page index 0 is supported")


def _quad(value: object) -> Quad:
    points = []
    for point in _sequence(value, "quad"):
        pair = _sequence(point, "point")
        if len(pair) != 2:
            raise ValueError("Each point must contain x and y")
        pair = tuple(_number(n, "coordinate") for n in pair)
        if any(n < 0 or n > 1 for n in pair):
            raise ValueError("Canonical coordinates must be in [0, 1]")
        points.append(pair)
    if len(points) != 4:
        raise ValueError("quad must contain four points")
    if points[0] != min(points, key=lambda p: (p[1], p[0])):
        raise ValueError("quad must start at the smallest (y, x) point")
    for i in range(4):
        a, b, c = (points[(i + j) % 4] for j in range(3))
        cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if cross <= 0:
            raise ValueError("quad must be convex, nondegenerate and clockwise in image coordinates")
    return tuple(points)


def _matrix(value: object) -> Matrix3x3:
    rows = _sequence(value, "inverse_transform")
    if len(rows) != 3:
        raise ValueError("inverse_transform must be a 3x3 matrix")
    matrix = tuple(tuple(_number(n, "matrix entry") for n in _sequence(row, "matrix row")) for row in rows)
    if any(len(row) != 3 for row in matrix):
        raise ValueError("inverse_transform must be a 3x3 matrix")
    (a, b, c), (d, e, f), (g, h, i) = matrix
    determinant = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if not math.isfinite(determinant) or determinant == 0:
        raise ValueError("inverse_transform must be finite and nonsingular")
    return matrix


@dataclass(frozen=True, slots=True)
class ImageInfo:
    """Decoded image descriptor; uint8 values are in [0, 255]. No pixels or paths."""

    width: int
    height: int
    color_order: Literal["RGB", "BGR", "GRAY"]
    dtype: Literal["uint8"]

    def __post_init__(self) -> None:
        _dimensions(self.width, self.height)
        if self.color_order not in ("RGB", "BGR", "GRAY") or self.dtype != "uint8":
            raise ValueError("Expected RGB/BGR/GRAY with uint8 values in [0, 255]")

    @classmethod
    def from_dict(cls, value: object) -> "ImageInfo":
        return cls(**_record(value, {"width", "height", "color_order", "dtype"}))


@dataclass(frozen=True, slots=True)
class PreparedPage:
    """Descriptors after orientation/render and preprocessing.

    inverse_transform maps processed pixel-edge coordinates to canonical pixel-
    edge coordinates, using homogeneous column vectors. No mapping is inferred.
    """

    page: int
    canonical: ImageInfo
    processed: ImageInfo
    preprocess_version: str
    geometry_status: Literal["available", "unavailable"]
    inverse_transform: Matrix3x3 | None
    geometry_reason: str | None

    def __post_init__(self) -> None:
        _page(self.page)
        if not isinstance(self.canonical, ImageInfo) or not isinstance(self.processed, ImageInfo):
            raise ValueError("canonical and processed must be ImageInfo")
        if self.canonical.color_order != "RGB":
            raise ValueError("Canonical viewer image must be RGB uint8")
        _text(self.preprocess_version, "preprocess_version")
        if self.geometry_status == "available":
            if self.geometry_reason is not None:
                raise ValueError("Available geometry must not have an unavailable reason")
            object.__setattr__(self, "inverse_transform", _matrix(self.inverse_transform))
        elif self.geometry_status == "unavailable":
            if self.inverse_transform is not None:
                raise ValueError("Unavailable geometry must not contain an invented transform")
            _text(self.geometry_reason, "geometry_reason")
        else:
            raise ValueError("Unknown geometry_status")

    @classmethod
    def from_dict(cls, value: object) -> "PreparedPage":
        data = dict(_record(value, {
            "page", "canonical", "processed", "preprocess_version",
            "geometry_status", "inverse_transform", "geometry_reason",
        }))
        data["canonical"] = ImageInfo.from_dict(data["canonical"])
        data["processed"] = ImageInfo.from_dict(data["processed"])
        return cls(**data)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["inverse_transform"] = None if self.inverse_transform is None else [list(row) for row in self.inverse_transform]
        return data


@dataclass(frozen=True, slots=True)
class OcrBlock:
    """A source block. quad is canonical; score is the raw engine score only."""

    block_id: str
    text: str
    quad: Quad | None
    score: float | None
    geometry_reason: str | None

    def __post_init__(self) -> None:
        _text(self.block_id, "block_id")
        _text(self.text, "text")
        if self.quad is None:
            _text(self.geometry_reason, "geometry_reason")
        else:
            if self.geometry_reason is not None:
                raise ValueError("Located block must not have an unavailable reason")
            object.__setattr__(self, "quad", _quad(self.quad))
        if self.score is not None:
            score = _number(self.score, "score")
            if not 0 <= score <= 1:
                raise ValueError("OCR score must be in [0, 1] or null")
            object.__setattr__(self, "score", score)

    @classmethod
    def from_dict(cls, value: object) -> "OcrBlock":
        return cls(**_record(value, {"block_id", "text", "quad", "score", "geometry_reason"}))


@dataclass(frozen=True, slots=True)
class OcrPage:
    """Ordered blocks on one canonical page; block IDs are unique within it."""

    page: int
    width: int
    height: int
    ocr_version: str
    blocks: tuple[OcrBlock, ...]

    def __post_init__(self) -> None:
        _page(self.page)
        _dimensions(self.width, self.height)
        _text(self.ocr_version, "ocr_version")
        blocks = _sequence(self.blocks, "blocks")
        if any(not isinstance(block, OcrBlock) for block in blocks):
            raise ValueError("blocks must contain OcrBlock values")
        ids = [block.block_id for block in blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate block_id on page")
        object.__setattr__(self, "blocks", blocks)

    @classmethod
    def from_dict(cls, value: object) -> "OcrPage":
        data = dict(_record(value, {"page", "width", "height", "ocr_version", "blocks"}))
        data["blocks"] = tuple(OcrBlock.from_dict(block) for block in _sequence(data["blocks"], "blocks"))
        return cls(**data)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["blocks"] = [
            {**asdict(block), "quad": None if block.quad is None else [list(point) for point in block.quad]}
            for block in self.blocks
        ]
        return data

    def validate_against(self, prepared: PreparedPage) -> None:
        """Reject processed dimensions or fabricated canonical regions."""
        if not isinstance(prepared, PreparedPage):
            raise ValueError("Expected PreparedPage")
        if (self.page, self.width, self.height) != (prepared.page, prepared.canonical.width, prepared.canonical.height):
            raise ValueError("OCR page must describe the matching canonical image")
        if prepared.geometry_status == "unavailable" and any(block.quad is not None for block in self.blocks):
            raise ValueError("Unavailable mapping cannot produce canonical quads")
