"""Source attribution must preserve canonical geometry and expose ambiguity."""

from dataclasses import replace
import json
from pathlib import Path
import unittest
import unicodedata

from vietdoc.contracts.ocr import ImageInfo, OcrBlock, OcrPage, PreparedPage
from vietdoc.pipeline.evidence import EvidenceRequest, match_evidence


def block(block_id, text, y, score=.8, x=.1):
    return OcrBlock(block_id, text, ((x, y), (x + .3, y), (x + .3, y + .04), (x, y + .04)), score, None)


class EvidenceTest(unittest.TestCase):
    def setUp(self):
        self.page = OcrPage(0, 800, 600, "fictional-ocr.v1", (
            block("description", "Bánh mì", .1), block("line-amount", "45.000", .1, x=.65),
            block("wrap", "loại nhỏ", .16), block("total-label", "Tổng tiền", .7),
            block("total-amount", "45.000", .7, .93, x=.65),
        ))
        self.prepared = PreparedPage(0, ImageInfo(800, 600, "RGB", "uint8"), ImageInfo(800, 600, "RGB", "uint8"),
                                     "fixture.v1", "available", ((1, 0, 0), (0, 1, 0), (0, 0, 1)), None)

    def test_repeated_amount_without_context_does_not_select_a_box(self):
        result = match_evidence(self.page, EvidenceRequest("/total_amount", "45.000"))
        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(result.candidate_block_ids, (("line-amount",), ("total-amount",)))
        self.assertEqual(result.to_field_metadata()["source_regions"], [])
        self.assertIn("SOURCE_AMBIGUOUS", result.review_flags)

    def test_label_alone_does_not_guess_which_repeated_amount_is_total(self):
        request = EvidenceRequest("/total_amount", "45.000", label_text="Tổng tiền")
        self.assertEqual(match_evidence(self.page, request).status, "ambiguous")

    def test_label_and_processed_row_resolve_repeated_amount_without_manual_ids(self):
        request = EvidenceRequest("/total_amount", "45.000", label_text="Tổng tiền")
        result = match_evidence(self.page, request, prepared=self.prepared)
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.blocks, (self.page.blocks[-1],))
        self.assertEqual(result.candidate_block_ids, (("line-amount",), ("total-amount",)))
        self.assertEqual(result.to_field_metadata()["ocr_score"], .93)

    def test_row_selection_survives_resize_rotated_and_reflected_viewer(self):
        request = EvidenceRequest("/total_amount", "45.000", label_text="Tổng tiền")
        # Independent closed-form normalized coordinates, no production mapper.
        rotated = tuple(replace(b, quad=tuple((1 - b.quad[i][1], b.quad[i][0]) for i in (3, 0, 1, 2))) for b in self.page.blocks)
        reflected = tuple(replace(b, quad=tuple((1 - b.quad[i][0], b.quad[i][1]) for i in (1, 0, 3, 2))) for b in self.page.blocks)
        cases = (
            (self.page, replace(self.prepared, processed=ImageInfo(400, 300, "RGB", "uint8"), inverse_transform=((2, 0, 0), (0, 2, 0), (0, 0, 1)))),
            (replace(self.page, width=600, height=800, blocks=rotated), replace(self.prepared, canonical=ImageInfo(600, 800, "RGB", "uint8"), inverse_transform=((0, -1, 600), (1, 0, 0), (0, 0, 1)))),
            (replace(self.page, blocks=reflected), replace(self.prepared, inverse_transform=((-1, 0, 800), (0, 1, 0), (0, 0, 1)))),
        )
        for page, prepared in cases:
            with self.subTest(matrix=prepared.inverse_transform):
                result = match_evidence(page, request, prepared=prepared)
                self.assertEqual(result.status, "matched")
                self.assertEqual(result.blocks, (page.blocks[-1],))
                self.assertEqual(result.to_field_metadata()["source_regions"][0]["quad"], [list(p) for p in page.blocks[-1].quad])

    def test_two_values_on_label_row_remain_ambiguous_instead_of_choosing_nearest(self):
        narrow = replace(self.page.blocks[-1], quad=((.5, .7), (.6, .7), (.6, .74), (.5, .74)))
        page = replace(self.page, blocks=self.page.blocks[:-1] + (narrow, block("other-right", "45.000", .7, x=.65)))
        result = match_evidence(page, EvidenceRequest("/total_amount", "45.000", label_text="Tổng tiền"), prepared=self.prepared)
        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(result.to_field_metadata()["source_regions"], [])

    def test_candidates_to_left_or_on_other_rows_do_not_resolve_label_context(self):
        misplaced = replace(self.page.blocks[-1], quad=((.01, .7), (.08, .7), (.08, .74), (.01, .74)))
        page = replace(self.page, blocks=self.page.blocks[:-1] + (misplaced,))
        result = match_evidence(page, EvidenceRequest("/total_amount", "45.000", label_text="Tổng tiền"), prepared=self.prepared)
        self.assertEqual(result.status, "ambiguous")

    def test_unknown_geometry_cannot_be_silently_excluded_from_candidates(self):
        request = EvidenceRequest("/total_amount", "45.000", label_text="Tổng tiền")
        for index in (1, 3):
            blocks = list(self.page.blocks)
            blocks[index] = replace(blocks[index], quad=None, geometry_reason="NO_MAPPING")
            with self.subTest(index=index):
                result = match_evidence(replace(self.page, blocks=tuple(blocks)), request, prepared=self.prepared)
                self.assertEqual(result.status, "ambiguous")
                self.assertIn("SOURCE_CONTEXT_GEOMETRY_UNAVAILABLE", result.review_flags)

    def test_wrong_page_dimensions_or_invalid_back_projection_are_rejected(self):
        request = EvidenceRequest("/total_amount", "45.000", label_text="Tổng tiền")
        for prepared in (
            replace(self.prepared, canonical=ImageInfo(801, 600, "RGB", "uint8")),
            replace(self.prepared, inverse_transform=((1, 0, 5000), (0, 1, 0), (0, 0, 1))),
        ):
            with self.subTest(prepared=prepared), self.assertRaises(ValueError):
                match_evidence(self.page, request, prepared=prepared)

    def test_explicit_total_context_preserves_actual_block_quad_and_score(self):
        request = EvidenceRequest("/total_amount", "45.000", ("total-label", "total-amount"), "Tổng tiền")
        result = match_evidence(self.page, request)
        metadata = result.to_field_metadata()
        self.assertEqual(result.status, "matched")
        self.assertEqual(metadata["source_regions"], [{"page": 0, "quad": [list(p) for p in self.page.blocks[-1].quad], "ocr_block_ids": ["total-amount"]}])
        self.assertEqual(metadata["ocr_score"], .93)
        self.assertIsNone(metadata["confidence"])
        self.assertIsNone(metadata["confidence_method"])
        self.assertEqual(metadata["raw_value"], "45.000")

    def test_item_context_selects_line_amount_instead_of_total(self):
        request = EvidenceRequest("/items/0/line_total", "45.000", ("description", "line-amount"), "Bánh mì")
        self.assertEqual(match_evidence(self.page, request).blocks, (self.page.blocks[1],))

    def test_wrapped_description_keeps_two_regions_and_page_order(self):
        request = EvidenceRequest("/items/0/description", "Bánh mì loại nhỏ", ("wrap", "description"))
        result = match_evidence(self.page, request)
        self.assertEqual(result.status, "matched")
        self.assertEqual([b.block_id for b in result.blocks], ["description", "wrap"])
        self.assertEqual(len(result.to_field_metadata()["source_regions"]), 2)
        self.assertIsNone(result.to_field_metadata()["ocr_score"])
        self.assertEqual(self.page.blocks[0].text, "Bánh mì")

    def test_nfc_case_and_whitespace_match_without_mutating_raw_text(self):
        raw = unicodedata.normalize("NFD", "  BÁNH\tmì  ")
        result = match_evidence(self.page, EvidenceRequest("/items/0/description", raw))
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.raw_value, raw)
        self.assertEqual(result.blocks[0].text, "Bánh mì")

    def test_no_digit_punctuation_accent_substring_or_transcript_repair(self):
        for raw in ("45000", "45,000", "5.000", "Banh mi", "Tổng tiển", "80.000"):
            with self.subTest(raw=raw):
                result = match_evidence(self.page, EvidenceRequest("/total_amount", raw))
                self.assertEqual(result.status, "not_found")
                self.assertEqual(result.to_field_metadata()["source_regions"], [])

    def test_missing_prediction_does_not_claim_absent_field(self):
        result = match_evidence(self.page, EvidenceRequest("/buyer_name", None))
        metadata = result.to_field_metadata()
        self.assertEqual(result.status, "value_unavailable")
        self.assertEqual(metadata["value_origin"], "prediction")
        self.assertEqual(metadata["source_regions"], [])
        self.assertIsNone(metadata["ocr_score"])

    def test_missing_geometry_keeps_candidate_id_but_never_publishes_null_quad(self):
        unavailable = replace(self.page.blocks[0], quad=None, geometry_reason="NO_MAPPING")
        page = replace(self.page, blocks=(unavailable,))
        result = match_evidence(page, EvidenceRequest("/items/0/description", "Bánh mì"))
        self.assertEqual(result.status, "geometry_unavailable")
        self.assertEqual(result.candidate_block_ids, (("description",),))
        self.assertEqual(result.to_field_metadata()["source_regions"], [])

    def test_partial_geometry_does_not_publish_incomplete_wrapped_evidence(self):
        page = replace(self.page, blocks=(self.page.blocks[0], replace(self.page.blocks[2], quad=None, geometry_reason="NO_MAPPING")))
        result = match_evidence(page, EvidenceRequest("/items/0/description", "Bánh mì loại nhỏ"))
        self.assertEqual(result.status, "geometry_unavailable")
        self.assertEqual(result.to_field_metadata()["source_regions"], [])

    def test_missing_or_duplicate_label_does_not_produce_selected_regions(self):
        result = match_evidence(self.page, EvidenceRequest("/total_amount", "45.000", label_text="Thành tiền"))
        self.assertEqual(result.status, "context_not_found")
        duplicate = replace(self.page, blocks=self.page.blocks + (block("other-label", "Tổng tiền", .8),))
        result = match_evidence(duplicate, EvidenceRequest("/total_amount", "45.000", label_text="Tổng tiền"))
        self.assertEqual(result.status, "ambiguous")
        self.assertIn("SOURCE_CONTEXT_AMBIGUOUS", result.review_flags)

    def test_unknown_ids_and_malformed_requests_are_rejected(self):
        with self.assertRaises(ValueError):
            match_evidence(self.page, EvidenceRequest("/total_amount", "45.000", ("unknown",)))
        for args in (("total_amount", "45.000"), ("/total_amount", ""), ("/total_amount", 45000),
                     ("/total_amount", "45.000", ("total-amount", "total-amount")),
                     ("/total_amount", "45.000", "total-amount"), ("/total_amount", "45.000", (), "")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                EvidenceRequest(*args)

    def test_blank_page_and_null_engine_score_are_valid(self):
        empty = replace(self.page, blocks=())
        self.assertEqual(match_evidence(empty, EvidenceRequest("/total_amount", "45.000")).status, "not_found")
        page = replace(self.page, blocks=(replace(self.page.blocks[0], score=None),))
        metadata = match_evidence(page, EvidenceRequest("/items/0/description", "Bánh mì")).to_field_metadata()
        self.assertEqual(len(metadata["source_regions"]), 1)
        self.assertIsNone(metadata["ocr_score"])

    def test_actual_engine_snapshot_maps_total_to_observed_region(self):
        fixture = Path(__file__).resolve().parents[2] / "fixtures" / "ocr-vietnamese-observed.json"
        page = OcrPage.from_dict(json.loads(fixture.read_text(encoding="utf-8")))
        request = EvidenceRequest("/total_amount", "80.000", ("p0-b0001", "p0-b0002"), "Tổng tiền")
        metadata = match_evidence(page, request).to_field_metadata()
        self.assertEqual(metadata["source_regions"][0]["ocr_block_ids"], ["p0-b0002"])
        self.assertEqual(metadata["source_regions"][0]["quad"], [list(p) for p in page.blocks[1].quad])
        self.assertEqual(metadata["ocr_score"], .96)

    def test_span_limit_and_ambiguous_wrapped_matches_are_explicit(self):
        page = replace(self.page, blocks=tuple(block(str(i), text, .05 * i) for i, text in enumerate(("một", "hai", "ba", "bốn", "năm"))))
        self.assertEqual(match_evidence(page, EvidenceRequest("/items/0/description", "một hai ba bốn")).status, "matched")
        self.assertEqual(match_evidence(page, EvidenceRequest("/items/0/description", "một hai ba bốn năm")).status, "not_found")
        page = replace(self.page, blocks=(block("a", "loại", .1), block("b", "nhỏ", .2), block("c", "loại nhỏ", .3)))
        result = match_evidence(page, EvidenceRequest("/items/0/description", "loại nhỏ"))
        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(result.candidate_block_ids, (("a", "b"), ("c",)))


if __name__ == "__main__":
    unittest.main()
