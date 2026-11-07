"""O1.1 metadata contract checks; no engine, image decoder or model involved."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
import struct
from pathlib import Path
import unittest

from vietdoc.contracts.ocr import ImageInfo, OcrBlock, OcrPage, PreparedPage, UnreadableRegion


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ocr-page-proposal.json"


class OcrContractsTest(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.prepared = PreparedPage.from_dict(self.fixture["prepared_page"])
        self.page = OcrPage.from_dict(self.fixture["ocr_page"])

    def test_observed_native_snapshot_parses_against_its_canonical_source(self):
        observed = json.loads((FIXTURE.parent / "ocr-vietnamese-observed.json").read_text(encoding="utf-8"))
        page = OcrPage.from_dict(observed)
        png = (FIXTURE.parent / "ocr-vietnamese-source.png").read_bytes()
        self.assertEqual((page.width, page.height), struct.unpack(">II", png[16:24]))
        self.assertEqual(page.to_dict(), observed)
        self.assertEqual([block.text for block in page.blocks], ["Tổng tiền", "80.000"])

    def test_fixture_round_trip_and_reading_order(self):
        self.page.validate_against(self.prepared)
        self.assertEqual(self.prepared.to_dict(), self.fixture["prepared_page"])
        self.assertEqual(self.page.to_dict(), self.fixture["ocr_page"])
        self.assertEqual([b.text for b in self.page.blocks], ["Tổng tiền", "45.000"])
        self.assertEqual(json.loads(json.dumps(self.page.to_dict())), self.fixture["ocr_page"])

    def test_d1_native_handoff_parses_two_types_and_retains_missing_denominator(self):
        bundle = json.loads((FIXTURE.parent / "ocr-d1-native-handoff.json").read_text(encoding="utf-8"))
        self.assertEqual(bundle["run_summary"]["counts"], {"requested": 20, "native_attempted": 2, "ok": 2, "failed": 0, "not_run": 18})
        self.assertEqual({s["document_type"] for s in bundle["samples"]}, {"receipt", "invoice"})
        ids = [s["sample_id"] for s in bundle["samples"] + bundle["unavailable_inputs"]]
        self.assertEqual(len(set(ids)), 20)
        for sample in bundle["samples"]:
            page = OcrPage.from_dict(sample["ocr"])
            page.validate_against(PreparedPage.from_dict(sample["prepared"]))
            self.assertEqual((page.width, page.height), (1500, 2600))
            self.assertEqual(page.to_dict(), sample["ocr"])
            self.assertEqual(len(page.blocks), sample["block_count"])

    def test_fixture_explains_processed_to_canonical_direction(self):
        matrix = self.prepared.inverse_transform
        point = (250, 420, 1)
        mapped = [sum(row[i] * point[i] for i in range(3)) for row in matrix]
        self.assertEqual(mapped, [500, 840, 1])
        self.assertEqual((mapped[0] / self.page.width, mapped[1] / self.page.height), self.page.blocks[1].quad[0])

    def test_dimensions_and_single_page_are_strict(self):
        for bad in (0, -1, 1.5, "1000", True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                replace(self.page, width=bad)
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ImageInfo(1000, bad, "RGB", "uint8")
        for bad in (1, -1, False, 0.0, "0"):
            with self.subTest(page=bad), self.assertRaises(ValueError):
                replace(self.prepared, page=bad)
            with self.subTest(page=bad), self.assertRaises(ValueError):
                replace(self.page, page=bad)

    def test_color_and_dtype_are_explicit(self):
        for color in ("RGB", "BGR", "GRAY"):
            image = ImageInfo(500, 600, color, "uint8")
            replace(self.prepared, processed=image)
        for color, dtype in (("RGBA", "uint8"), ("rgb", "uint8"), ("RGB", "float32"), (None, "uint8")):
            with self.subTest(color=color, dtype=dtype), self.assertRaises(ValueError):
                ImageInfo(500, 600, color, dtype)
        with self.assertRaises(ValueError):
            replace(self.prepared, canonical=ImageInfo(1000, 1200, "BGR", "uint8"))

    def test_nonfinite_and_out_of_range_coordinates_rejected(self):
        for value in (-0.1, 1.1, float("nan"), float("inf"), True, "0.1"):
            quad = deepcopy(self.fixture["ocr_page"]["blocks"][0]["quad"])
            quad[0][0] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                replace(self.page.blocks[0], quad=quad)

    def test_quad_shape_winding_and_anchor_rejected(self):
        quad = self.fixture["ocr_page"]["blocks"][0]["quad"]
        cases = [
            quad[:3], quad + [quad[0]], [[0.1]] + quad[1:],
            [quad[0], quad[3], quad[2], quad[1]],
            [quad[0], quad[2], quad[1], quad[3]],
            [quad[0], quad[1], quad[1], quad[3]],
            [[0, 0], [1, 0], [0.2, 0.2], [0, 1]],
            quad[1:] + quad[:1],
        ]
        for bad in cases:
            with self.subTest(quad=bad), self.assertRaises(ValueError):
                replace(self.page.blocks[0], quad=bad)

    def test_full_page_edges_and_rotated_convex_quad_allowed(self):
        for quad in (
            [[0, 0], [1, 0], [1, 1], [0, 1]],
            [[0.5, 0.1], [0.8, 0.5], [0.5, 0.9], [0.2, 0.5]],
        ):
            with self.subTest(quad=quad):
                self.assertEqual(replace(self.page.blocks[0], quad=quad).quad[0], tuple(quad[0]))

    def test_transform_shape_singularity_and_finite_values(self):
        for matrix in (
            None, [], [[1, 0], [0, 1]],
            [[1, 0, 0], [0, 1, 0], [0, 0]],
            [[1, 0, 0], [0, 0, 0], [0, 0, 1]],
            [[float("nan"), 0, 0], [0, 1, 0], [0, 0, 1]],
            [[True, 0, 0], [0, 1, 0], [0, 0, 1]],
        ):
            with self.subTest(matrix=matrix), self.assertRaises(ValueError):
                replace(self.prepared, inverse_transform=matrix)

    def test_homogeneous_transform_scales_round_trip_without_rewriting_metadata(self):
        for scale in (1e-200, -1e-200, 1e200, -1e200):
            matrix = tuple(tuple(scale if row == column else 0.0 for column in range(3)) for row in range(3))
            with self.subTest(scale=scale):
                prepared = replace(self.prepared, inverse_transform=matrix)
                self.assertEqual(prepared.inverse_transform, matrix)
                self.assertEqual(PreparedPage.from_dict(prepared.to_dict()), prepared)

    def test_unavailable_geometry_requires_reason_and_no_transform(self):
        missing = replace(self.prepared, geometry_status="unavailable", inverse_transform=None, geometry_reason="NONINVERTIBLE_PREPROCESS")
        self.assertIsNone(missing.inverse_transform)
        self.assertEqual(PreparedPage.from_dict(missing.to_dict()), missing)
        for changes in (
            {"geometry_status": "unavailable"},
            {"geometry_status": "unavailable", "inverse_transform": None},
            {"geometry_reason": "unexpected"},
            {"geometry_status": "unknown"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.prepared, **changes)

    def test_unavailable_blocks_keep_text_without_fabricating_boxes(self):
        block = replace(self.page.blocks[0], quad=None, geometry_reason="MAPPING_UNAVAILABLE")
        page = replace(self.page, blocks=(block,))
        missing = replace(self.prepared, geometry_status="unavailable", inverse_transform=None, geometry_reason="MAPPING_UNAVAILABLE")
        page.validate_against(missing)
        self.assertEqual(page.blocks[0].text, "Tổng tiền")
        self.assertEqual(OcrPage.from_dict(page.to_dict()), page)
        with self.assertRaises(ValueError):
            replace(block, geometry_reason=None)
        with self.assertRaises(ValueError):
            replace(self.page.blocks[0], geometry_reason="unexpected")
        with self.assertRaises(ValueError):
            self.page.validate_against(missing)

    def test_canonical_dimensions_must_match_prepared_page(self):
        with self.assertRaises(ValueError):
            replace(self.page, width=500, height=600).validate_against(self.prepared)

    def test_score_is_nullable_bounded_engine_score(self):
        for score in (None, 0, 0.5, 1):
            self.assertEqual(replace(self.page.blocks[0], score=score).score, score)
        for score in (-0.1, 1.1, float("inf"), float("nan"), "0.9", True):
            with self.subTest(score=score), self.assertRaises(ValueError):
                replace(self.page.blocks[0], score=score)
        self.assertNotIn("confidence", self.page.to_dict()["blocks"][0])

    def test_blocks_have_unique_ids_and_explicit_order(self):
        with self.assertRaises(ValueError):
            replace(self.page, blocks=(self.page.blocks[0], self.page.blocks[0]))
        empty = replace(self.page, blocks=())
        self.assertEqual(empty.to_dict()["blocks"], [])
        reversed_page = replace(self.page, blocks=tuple(reversed(self.page.blocks)))
        self.assertEqual(reversed_page.blocks[0].text, "45.000")

    def test_required_and_unknown_keys_for_all_records(self):
        cases = (
            (PreparedPage, self.fixture["prepared_page"]),
            (ImageInfo, self.fixture["prepared_page"]["canonical"]),
            (OcrPage, self.fixture["ocr_page"]),
            (OcrBlock, self.fixture["ocr_page"]["blocks"][0]),
        )
        for cls, valid in cases:
            with self.subTest(cls=cls.__name__), self.assertRaises(ValueError):
                cls.from_dict({**valid, "unexpected": 1})
            for key in valid:
                data = dict(valid)
                del data[key]
                with self.subTest(cls=cls.__name__, missing=key), self.assertRaises(ValueError):
                    cls.from_dict(data)

    def test_bad_nested_records_and_arrays_rejected(self):
        for value in (None, [], "invalid"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                OcrPage.from_dict(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                PreparedPage.from_dict({**self.fixture["prepared_page"], "canonical": value})
        for value in (None, "text", {}, [None]):
            with self.subTest(blocks=value), self.assertRaises(ValueError):
                OcrPage.from_dict({**self.fixture["ocr_page"], "blocks": value})

    def test_nonblank_ids_versions_and_text_required(self):
        for value in (None, "", " ", 123):
            for field in ("block_id", "text"):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    replace(self.page.blocks[0], **{field: value})
            with self.subTest(value=value), self.assertRaises(ValueError):
                replace(self.page, ocr_version=value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                replace(self.prepared, preprocess_version=value)

    def test_objects_are_deeply_immutable_and_input_is_not_modified(self):
        original = deepcopy(self.fixture)
        source = deepcopy(self.fixture["ocr_page"])
        parsed = OcrPage.from_dict(source)
        source["blocks"][0]["quad"][0][0] = 0.9
        self.assertEqual(parsed.blocks[0].quad[0][0], 0.1)
        self.assertEqual(self.fixture, original)
        with self.assertRaises(FrozenInstanceError):
            parsed.width = 500
        output = parsed.to_dict()
        output["blocks"][0]["quad"][0][0] = 0.9
        self.assertEqual(parsed.blocks[0].quad[0][0], 0.1)

    def test_v2_consumer_golden_outcomes_and_round_trip(self):
        fixture = json.loads((FIXTURE.parent / "ocr-artifact-v2.json").read_text(encoding="utf-8"))
        prepared = PreparedPage.from_dict(fixture["prepared_page"])
        for case in fixture["cases"]:
            with self.subTest(case=case["case_id"]):
                page = OcrPage.from_dict(case["expected"])
                page.validate_against(prepared)
                self.assertEqual(page.to_dict(), case["expected"])
                self.assertEqual(page.recognition_status, case["expected"]["recognition_status"])
                self.assertTrue(all(block.text.strip() for block in page.blocks))

    def test_legacy_migration_is_explicit_and_never_drops_unreadable_regions(self):
        migrated = replace(self.page, artifact_version=2)
        self.assertEqual(migrated.blocks, self.page.blocks)
        self.assertEqual(migrated.recognition_status, "complete")
        self.assertEqual(OcrPage.from_dict(migrated.to_dict()), migrated)
        self.assertNotIn("artifact_version", self.page.to_dict())
        region = UnreadableRegion("unread", self.page.blocks[0].quad, 0, None)
        partial = replace(migrated, unreadable_regions=(region,))
        with self.assertRaises(ValueError):
            replace(partial, artifact_version=1)

    def test_v2_status_flags_versions_and_keys_are_validated(self):
        valid = replace(self.page, artifact_version=2).to_dict()
        changes = ({"artifact_version": True}, {"artifact_version": 3}, {"artifact_version": 1},
                   {"recognition_status": "partial"}, {"review_flags": ["OCR_UNREADABLE_REGIONS"]},
                   {"unreadable_regions": None}, {"unexpected": 1})
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                OcrPage.from_dict({**valid, **change})
        for key in ("artifact_version", "unreadable_regions", "recognition_status", "review_flags"):
            invalid = dict(valid)
            del invalid[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                OcrPage.from_dict(invalid)

    def test_unreadable_ids_geometry_score_reason_and_immutability(self):
        region = UnreadableRegion("unread", self.page.blocks[0].quad, None, None)
        for change in ({"region_id": " "}, {"score": float("nan")}, {"score": True},
                       {"score": 1.1}, {"reason": "PROVIDER_CRASH"}, {"quad": None},
                       {"geometry_reason": "unexpected"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(region, **change)
        with self.assertRaises(ValueError):
            replace(self.page, artifact_version=2, unreadable_regions=(replace(region, region_id=self.page.blocks[0].block_id),))
        unavailable = replace(region, quad=None, geometry_reason="NO_MAPPING")
        partial = replace(self.page, artifact_version=2, unreadable_regions=(unavailable,))
        self.assertEqual(partial.recognition_status, "partial")
        with self.assertRaises(FrozenInstanceError):
            unavailable.reason = "changed"
        missing = replace(self.prepared, geometry_status="unavailable", inverse_transform=None, geometry_reason="NO_MAPPING")
        with self.assertRaises(ValueError):
            replace(self.page, blocks=(), artifact_version=2, unreadable_regions=(region,)).validate_against(missing)


if __name__ == "__main__":
    unittest.main()
