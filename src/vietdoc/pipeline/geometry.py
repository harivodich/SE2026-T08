"""Pixel-edge geometry and geometric reading order, independent of OCR libraries.

Matrices multiply homogeneous column vectors. Reading order belongs to the
upright processed frame; mapping to a rotated viewer must not reorder blocks.
"""

import math

from vietdoc.contracts.ocr import PreparedPage


GEOMETRY_VERSION = "pixel-edge-projective-relative-rows.v2"


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Geometry requires finite numeric coordinates")
    return float(value)


def _points(points):
    result = []
    for point in points:
        if len(point) != 2:
            raise ValueError("Expected two coordinates per point")
        result.append(tuple(_number(n) for n in point))
    return tuple(result)


def ordered_quad(points):
    """Validate a convex boundary; return clockwise corners starting at min(y,x).

    Does not sort arbitrary point clouds: a bow tie is invalid, not repaired.
    """
    points = _points(points)
    if len(points) != 4:
        raise ValueError("Expected four quad corners")
    crosses = []
    for i in range(4):
        a, b, c = points[i], points[(i + 1) % 4], points[(i + 2) % 4]
        crosses.append((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
    if not all(math.isfinite(c) for c in crosses) or not (all(c > 0 for c in crosses) or all(c < 0 for c in crosses)):
        raise ValueError("Quad must be convex and nondegenerate")
    if crosses[0] < 0:
        points = tuple(reversed(points))
    first = min(range(4), key=lambda i: (points[i][1], points[i][0]))
    return points[first:] + points[:first]


def pixel_quad(points, width, height):
    """Validate source bounds, preserving detector corner order for cropping."""
    if type(width) is not int or type(height) is not int or min(width, height) <= 0:
        raise ValueError("Expected positive pixel dimensions")
    points = _points(points)
    ordered_quad(points)
    if any(not (0 <= x <= width and 0 <= y <= height) for x, y in points):
        raise ValueError("Quad is outside the image")
    return points


def _projected_pixel_quad(points, width, height):
    """Correct boundary roundoff from arithmetic on already-validated points.

    Only excursions <= 16 ULPs of the image extent may snap to an edge. Source
    detector/normalized quads always pass strict pixel_quad validation first;
    real out-of-bounds projections still fail. Interior coordinates stay intact.
    """
    tolerance = 16 * math.ulp(float(max(width, height)))

    def edge(value, extent):
        if -tolerance <= value < 0:
            return 0.0
        if extent < value <= extent + tolerance:
            return float(extent)
        return value

    corrected = tuple((edge(x, width), edge(y, height)) for x, y in _points(points))
    return pixel_quad(corrected, width, height)


def _validated_transform(matrix):
    rows = tuple(tuple(_number(n) for n in row) for row in matrix)
    if len(rows) != 3 or any(len(row) != 3 for row in rows):
        raise ValueError("Expected a 3x3 transform")
    scale = max(abs(n) for row in rows for n in row)
    if scale == 0:
        raise ValueError("Singular transform")
    normalized = tuple(tuple(n / scale for n in row) for row in rows)
    (a, b, c), (d, e, f), (g, h, i) = normalized
    determinant = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if determinant == 0 or not math.isfinite(determinant):
        raise ValueError("Singular transform")
    return rows, normalized


def inverse_projective_transform(matrix):
    """Return the inverse up to a nonzero homogeneous scale (the adjugate).

    Normalizing first avoids overflow from a harmless global matrix scale.
    Division by the determinant is unnecessary for homogeneous projection.
    """
    _, normalized = _validated_transform(matrix)
    (a, b, c), (d, e, f), (g, h, i) = normalized
    return ((e * i - f * h, c * h - b * i, b * f - c * e),
            (f * g - d * i, a * i - c * g, c * d - a * f),
            (d * h - e * g, b * g - a * h, a * e - b * d))


def project_points(points, matrix):
    """Project points without clamping; reject singular or undefined mappings.

    A global nonzero matrix scale must not change the projection. Denominator
    tolerance is relative to its own terms, rather than a fixed pixel epsilon.
    Points straddling the projective horizon cannot describe a finite region.
    """
    rows, _ = _validated_transform(matrix)
    result, signs = [], set()
    for x, y in _points(points):
        terms = tuple(tuple(coefficient * coordinate for coefficient, coordinate in zip(row, (x, y, 1))) for row in rows)
        if any(not math.isfinite(n) for row in terms for n in row):
            raise ValueError("Nonfinite projection")
        u, v, w = (math.fsum(row) for row in terms)
        if abs(w) <= 1e-12 * math.fsum(abs(n) for n in terms[2]):
            raise ValueError("Undefined canonical projection")
        signs.add(w > 0)
        projected = (u / w, v / w)
        if not all(math.isfinite(n) for n in projected):
            raise ValueError("Nonfinite projection")
        result.append(projected)
    if len(signs) > 1:
        raise ValueError("Canonical projection crosses a horizon")
    return tuple(result)


def canonical_quad(points, metadata: PreparedPage):
    """Return viewer-normalized corners, or None for explicitly unavailable geometry."""
    points = pixel_quad(points, metadata.processed.width, metadata.processed.height)
    if metadata.geometry_status == "unavailable":
        return None
    mapped = project_points(points, metadata.inverse_transform)
    mapped = _projected_pixel_quad(mapped, metadata.canonical.width, metadata.canonical.height)
    return ordered_quad(tuple((x / metadata.canonical.width, y / metadata.canonical.height) for x, y in mapped))


def processed_quad(canonical_normalized, metadata: PreparedPage):
    """Recover processed pixel-edge corners for spatial context, never for display."""
    if metadata.geometry_status == "unavailable" or canonical_normalized is None:
        return None
    points = pixel_quad(canonical_normalized, 1, 1)
    canonical = pixel_quad(tuple((x * metadata.canonical.width, y * metadata.canonical.height) for x, y in points),
                           metadata.canonical.width, metadata.canonical.height)
    mapped = project_points(canonical, inverse_projective_transform(metadata.inverse_transform))
    return _projected_pixel_quad(mapped, metadata.processed.width, metadata.processed.height)


def reading_order(polygons):
    """Return source indices in geometric row order, independent of image scale.

    Same-row candidates overlap >= half the smaller height and their centers
    or top edges differ <= half that height. The shortest top-aligned candidate
    anchors each row, so tall cells cannot bridge successive lines. This keeps
    separate wrapped lines/regions; it neither
    groups table cells nor infers semantic columns or product associations.
    """
    boxes = []
    for index, polygon in enumerate(polygons):
        points = ordered_quad(polygon)
        xs, ys = zip(*points)
        boxes.append((min(xs), min(ys), max(xs), max(ys), index))
    pending = sorted(boxes, key=lambda b: (b[1], b[0], b[3], b[2], b[4]))
    ordered = []
    while pending:
        seed = pending[0]
        top_aligned = [box for box in pending if box[1] - seed[1] <= min(box[3] - box[1], seed[3] - seed[1]) / 2]
        anchor = min(top_aligned, key=lambda b: (b[3] - b[1], b[1], b[0], b[4]))
        row, remaining = [], []
        for box in pending:
            height = min(anchor[3] - anchor[1], box[3] - box[1])
            overlap = min(anchor[3], box[3]) - max(anchor[1], box[1])
            center_delta = abs((anchor[1] + anchor[3]) - (box[1] + box[3])) / 2
            top_delta = abs(anchor[1] - box[1])
            (row if overlap >= height / 2 and min(center_delta, top_delta) <= height / 2 else remaining).append(box)
        ordered.extend(box[4] for box in sorted(row, key=lambda b: (b[0], b[1], b[2], b[3], b[4])))
        pending = remaining
    return tuple(ordered)
