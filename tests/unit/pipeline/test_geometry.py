"""Independent fixture geometry oracles; native OCR is in tests/native/ocr."""

from dataclasses import replace
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import unittest

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from vietdoc.contracts.ocr import ImageInfo, OcrPage, PreparedPage
from vietdoc.pipeline.geometry import canonical_quad, inverse_projective_transform, ordered_quad, pixel_quad, processed_quad, project_points, reading_order
from vietdoc.pipeline.preprocess import LoadedPage, PreprocessLimits, load_document
from vietdoc.pipeline.evidence import EVIDENCE_VERSION, EvidenceRequest, match_evidence
from vietdoc.pipeline.ocr.paddle_adapter import VietnameseOcrEngine, _sort_polygons, draw_overlay


def rectangle(x, y, width, height):
    return ((x, y), (x + width, y), (x + width, y + height), (x, y + height))


class GeometryTest(unittest.TestCase):
    def test_actual_loader_resize_edge_quads_survive_mapping_and_roundtrip(self):
        from io import BytesIO

        for size, long_edge in (((2007, 1000), 2000), ((503, 1000), 400)):
            with self.subTest(size=size, long_edge=long_edge):
                with Image.new("RGB", size, "white") as image:
                    stream = BytesIO()
                    image.save(stream, format="PNG")
                with load_document(stream.getvalue(), limits=PreprocessLimits(processed_long_edge=long_edge)) as loaded:
                    width, height = loaded.processed.size
                    source = rectangle(0, 0, width, height)
                    mapped = canonical_quad(source, loaded.metadata)
                    np.testing.assert_allclose(mapped, rectangle(0, 0, 1, 1), rtol=0, atol=1e-15)
                    restored = processed_quad(mapped, loaded.metadata)
                    np.testing.assert_allclose(restored, source, rtol=0, atol=1e-7)

    def test_transformed_full_frame_edges_keep_valid_bounds(self):
        source = rectangle(0, 0, 201, 400)
        scale_x = 503 / 201
        cases = (
            ((503, 1000), ((scale_x, 0, 0), (0, 2.5, 0), (0, 0, 1))),
            ((1000, 503), ((0, -2.5, 1000), (scale_x, 0, 0), (0, 0, 1))),
            ((503, 1000), ((-scale_x, 0, 503), (0, -2.5, 1000), (0, 0, 1))),
            ((503, 1000), ((-scale_x, 0, 503), (0, 2.5, 0), (0, 0, 1))),
        )
        for dimensions, matrix in cases:
            metadata = PreparedPage(0, ImageInfo(*dimensions, "RGB", "uint8"), ImageInfo(201, 400, "RGB", "uint8"),
                                    "fixture.edge.v1", "available", matrix, None)
            with self.subTest(matrix=matrix):
                mapped = canonical_quad(source, metadata)
                np.testing.assert_allclose(mapped, rectangle(0, 0, 1, 1), rtol=0, atol=1e-15)
                restored = processed_quad(mapped, metadata)
                # Mapping changes corner anchor/winding, not the actual corner set.
                np.testing.assert_allclose(sorted(restored), sorted(source), rtol=0, atol=1e-7)

    def test_roundoff_tolerance_never_repairs_invalid_source_or_real_overflow(self):
        metadata = PreparedPage(0, ImageInfo(100, 100, "RGB", "uint8"), ImageInfo(100, 100, "RGB", "uint8"),
                                "fixture.edge.v1", "available", ((1,0,0),(0,1,0),(0,0,1)), None)
        for source in (rectangle(-math.ulp(100), 0, 10, 10), rectangle(0, 0, 100 + math.ulp(100), 10)):
            with self.subTest(source=source), self.assertRaises(ValueError):
                canonical_quad(source, metadata)
        with self.assertRaises(ValueError):
            processed_quad(rectangle(0, 0, 1 + math.ulp(1), 1), metadata)
        for offset in (-1e-7, 1e-7):
            outside = replace(metadata, inverse_transform=((1,0,offset),(0,1,0),(0,0,1)))
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                canonical_quad(rectangle(0, 0, 100, 100), outside)

    def test_round_trip_against_independent_numpy_inverse_with_pixel_tolerance(self):
        points = ((0, 0), (17.25, 31.5), (120, 80), (400, 300))
        angle = np.deg2rad(17)
        transforms = {
            "identity": np.eye(3),
            "resize": np.diag((2.3, 1.7, 1)),
            "crop-resize": np.array(((2, 0, 40), (0, 2, 20), (0, 0, 1))),
            "rotate90": np.array(((0, -1, 300), (1, 0, 0), (0, 0, 1))),
            "rotate17": np.array(((np.cos(angle), -np.sin(angle), 100), (np.sin(angle), np.cos(angle), 30), (0, 0, 1))),
            "reflection": np.array(((-1, 0, 400), (0, 1, 0), (0, 0, 1))),
            "perspective": np.array(((1.2, .03, 10), (.02, .9, 15), (.0002, .0001, 1))),
        }
        for name, matrix in transforms.items():
            with self.subTest(transform=name):
                expected = np.column_stack((points, np.ones(len(points)))) @ matrix.T
                expected = expected[:, :2] / expected[:, 2:]
                mapped = project_points(points, matrix.tolist())
                np.testing.assert_allclose(mapped, expected, rtol=0, atol=1e-7)
                restored = project_points(mapped, np.linalg.inv(matrix).tolist())
                np.testing.assert_allclose(restored, points, rtol=0, atol=1e-7)
                restored = project_points(expected.tolist(), inverse_projective_transform(matrix.tolist()))
                np.testing.assert_allclose(restored, points, rtol=0, atol=1e-7)

    def test_projection_is_invariant_to_global_matrix_scale(self):
        matrix = np.array(((2, 0, 40), (0, 2, 20), (.001, 0, 1)))
        points = rectangle(10, 10, 30, 20)
        expected = project_points(points, matrix.tolist())
        for scale in (1e-200, -1e-200, 1e-15, -1e-15, 1e15, -1e15, 1e200, -1e200):
            with self.subTest(scale=scale):
                np.testing.assert_allclose(project_points(points, (matrix * scale).tolist()), expected, rtol=0, atol=1e-7)
                np.testing.assert_allclose(project_points(expected, inverse_projective_transform((matrix * scale).tolist())), points, rtol=0, atol=1e-7)

    def test_normalized_projection_avoids_intermediate_global_scale_overflow(self):
        matrix = ((1e200, 0, 0), (0, 1e200, 0), (0, 0, 1e200))
        points = ((1e200, 2e200),)
        self.assertEqual(project_points(points, matrix), points)

    def test_contract_and_geometry_accept_the_same_scaled_identity(self):
        points = rectangle(10, 10, 30, 20)
        for scale in (1e-200, -1e-200, 1e200, -1e200):
            matrix = tuple(tuple(scale if row == column else 0.0 for column in range(3)) for row in range(3))
            with self.subTest(scale=scale):
                prepared = PreparedPage(0, ImageInfo(100, 100, "RGB", "uint8"), ImageInfo(100, 100, "RGB", "uint8"),
                                        "fixture.scale.v1", "available", matrix, None)
                mapped = canonical_quad(points, prepared)
                np.testing.assert_allclose(mapped, rectangle(.1, .1, .3, .2), rtol=0, atol=1e-15)
                np.testing.assert_allclose(processed_quad(mapped, prepared), points, rtol=0, atol=1e-12)

    def test_invalid_horizon_and_numerically_undefined_projections_are_rejected(self):
        for matrix in (
            ((1, 0, 0), (0, 0, 0), (0, 0, 1)),
            ((1, 0, 0), (0, 1, 0), (1, 0, -10)),
            ((1, 0, 0), (0, 1, 0), (1, 0, -20)),
            ((1, 0, 0), (0, 1, 0), (1, 0, -10 + 1e-13)),
            ((float("nan"), 0, 0), (0, 1, 0), (0, 0, 1)),
            ((1, 0), (0, 1)),
        ):
            with self.subTest(matrix=matrix), self.assertRaises(ValueError):
                project_points(rectangle(10, 10, 20, 20), matrix)

    def test_canonical_crop_has_known_coordinates_and_unavailable_is_explicit(self):
        metadata = PreparedPage(0, ImageInfo(1200, 700, "RGB", "uint8"), ImageInfo(560, 310, "RGB", "uint8"),
                                "fixture.crop.v1", "available", ((2, 0, 40), (0, 2, 20), (0, 0, 1)), None)
        quad = canonical_quad(rectangle(10, 20, 100, 30), metadata)
        self.assertEqual(quad, ((60 / 1200, 60 / 700), (260 / 1200, 60 / 700), (260 / 1200, 120 / 700), (60 / 1200, 120 / 700)))
        unavailable = replace(metadata, geometry_status="unavailable", inverse_transform=None, geometry_reason="NO_MAPPING")
        self.assertIsNone(canonical_quad(rectangle(10, 20, 100, 30), unavailable))
        self.assertIsNone(processed_quad(quad, unavailable))
        self.assertIsNone(processed_quad(None, metadata))
        np.testing.assert_allclose(processed_quad(quad, metadata), rectangle(10, 20, 100, 30), rtol=0, atol=1e-7)
        with self.assertRaises(ValueError):
            canonical_quad(rectangle(0, 0, 560, 310), replace(metadata, inverse_transform=((3, 0, 40), (0, 3, 20), (0, 0, 1))))

    def test_quad_rejects_invalid_boundaries_without_clamping_or_repair(self):
        for points in (
            rectangle(-.001, 0, 10, 10), rectangle(0, 0, 101, 10),
            ((0, 0), (10, 10), (10, 0), (0, 10)),
            ((0, 0), (10, 0), (5, 5), (10, 10)),
            rectangle(0, 0, 0, 10), ((True, 0), (10, 0), (10, 10), (0, 10)),
            ((float("inf"), 0), (10, 0), (10, 10), (0, 10)),
        ):
            with self.subTest(points=points), self.assertRaises(ValueError):
                pixel_quad(points, 100, 100)
        points = rectangle(0, 0, 100, 100)
        self.assertEqual(pixel_quad(points, 100, 100), points)
        self.assertEqual(ordered_quad(tuple(reversed(points))), points)


class ReadingOrderTest(unittest.TestCase):
    def test_nearby_rows_do_not_interleave_after_downsize(self):
        # Native SortQuadBoxes' fixed 10px threshold interleaved these at scale 1.
        polygons = [rectangle(10, 10, 20, 4), rectangle(70, 10, 20, 4), rectangle(10, 17, 20, 4), rectangle(70, 17, 20, 4)]
        for scale in (.1, 1, 3, 20):
            with self.subTest(scale=scale):
                self.assertEqual(reading_order((np.asarray(polygons) * scale).tolist()), (0, 1, 2, 3))

    def test_wrap_columns_jitter_duplicate_values_keep_every_source_region(self):
        # Input is deliberately shuffled: same-row jitter, separate wrapped
        # description and repeated amounts must not merge or cross to next item.
        polygons = [rectangle(100, 50, 20, 10), rectangle(10, 10, 30, 12),
                    rectangle(10, 30, 30, 10), rectangle(100, 12, 20, 10),
                    rectangle(10, 50, 30, 10)]
        self.assertEqual(reading_order(polygons), (1, 3, 2, 4, 0))
        source = np.asarray(polygons)
        sorted_polygons = _sort_polygons(source)
        for actual, index in zip(sorted_polygons, (1, 3, 2, 4, 0)):
            np.testing.assert_array_equal(actual, source[index])
        self.assertEqual(len(sorted_polygons), len(source))
        self.assertEqual(reading_order([]), ())

    def test_tall_box_does_not_bridge_successive_rows(self):
        polygons = [rectangle(10, 10, 20, 10), rectangle(60, 10, 20, 30), rectangle(10, 25, 20, 10)]
        self.assertEqual(reading_order(polygons), (0, 1, 2))
        # Tall region may be the first detection, slightly above the short row.
        polygons = [rectangle(10, 9, 20, 30), rectangle(60, 10, 20, 10), rectangle(60, 25, 20, 10)]
        self.assertEqual(reading_order(polygons), (0, 1, 2))




if __name__ == "__main__":
    unittest.main()
