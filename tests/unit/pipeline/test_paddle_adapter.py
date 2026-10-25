"""Boundary checks and opt-in native synthetic smoke; no D1 quality claims."""

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import os
import time
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image

from vietdoc.contracts.ocr import ImageInfo, OcrPage, PreparedPage
from vietdoc.pipeline.ocr import OCR_STAGE_VERSION, recognize_document
from vietdoc.pipeline.preprocess import LoadedPage
from vietdoc.pipeline.ocr.paddle_adapter import (
    OcrError, VietnameseOcrEngine, RUNTIME_VERSIONS, _PaddleTessPredictor,
    _to_page, _verify_model, draw_overlay, provision_models, MODELS,
)


class PaddleAdapterTest(unittest.TestCase):
    def setUp(self):
        self.metadata = PreparedPage(
            page=0, canonical=ImageInfo(200, 100, "RGB", "uint8"),
            processed=ImageInfo(100, 50, "RGB", "uint8"),
            preprocess_version="fixture.v1", geometry_status="available",
            inverse_transform=((2, 0, 0), (0, 2, 0), (0, 0, 1)), geometry_reason=None,
        )
        self.loaded = LoadedPage(
            Image.new("RGB", (200, 100)), Image.new("RGB", (100, 50), (11, 22, 33)),
            self.metadata, "0" * 64,
        )
        self.result = {
            "rec_texts": ["Tổng tiền", "80.000"],
            "rec_polys": np.array([
                [[10, 10], [30, 10], [30, 20], [10, 20]],
                [[60, 10], [90, 10], [90, 20], [60, 20]],
            ], dtype=np.int16),
            "rec_scores": np.array([0.93, 0.87], dtype=np.float32),
        }
        self.engine = VietnameseOcrEngine("unused-local-models")
        self.predictor = Mock()
        self.predictor.predict.side_effect = lambda _, **kwargs: iter([deepcopy(self.result)])
        self.engine._predictor = self.predictor

    def tearDown(self):
        self.loaded.close()

    def assert_error(self, code, operation):
        with self.assertRaises(OcrError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_each_detected_region_keeps_text_id_coordinates_and_engine_score(self):
        page = self.engine.recognize(self.loaded)
        self.assertEqual([block.text for block in page.blocks], ["Tổng tiền", "80.000"])
        self.assertEqual([block.block_id for block in page.blocks], ["p0-b0001", "p0-b0002"])
        self.assertEqual(page.blocks[0].quad, ((0.1, 0.2), (0.3, 0.2), (0.3, 0.4), (0.1, 0.4)))
        self.assertAlmostEqual(page.blocks[0].score, float(self.result["rec_scores"][0]))
        self.assertEqual(page.width, 200)
        self.assertEqual(page.height, 100)
        self.assertNotIn("confidence", page.to_dict()["blocks"][0])

    def test_rgb_is_converted_to_contiguous_bgr_without_changing_source(self):
        self.engine.recognize(self.loaded)
        native_pixels = self.predictor.predict.call_args.args[0]
        self.assertEqual(native_pixels[0, 0].tolist(), [33, 22, 11])
        self.assertEqual(native_pixels.dtype, np.uint8)
        self.assertTrue(native_pixels.flags.c_contiguous)
        self.assertEqual(self.loaded.processed.getpixel((0, 0)), (11, 22, 33))

    def test_no_grid_sort_or_transcript_replacement(self):
        self.result["rec_texts"].reverse()
        self.result["rec_polys"] = self.result["rec_polys"][::-1]
        first = self.engine.recognize(self.loaded)
        second = self.engine.recognize(self.loaded)
        self.assertEqual(first, second)
        self.assertEqual(first.blocks[0].text, "80.000")
        self.assertEqual(first.blocks[0].quad[0], (0.6, 0.2))

    def test_rotation_back_to_canonical_has_known_corners(self):
        metadata = replace(
            self.metadata, canonical=ImageInfo(100, 200, "RGB", "uint8"),
            inverse_transform=((0, -2, 100), (2, 0, 0), (0, 0, 1)),
        )
        page = _to_page(self.result, metadata)
        self.assertEqual(page.blocks[0].quad, ((0.6, 0.1), (0.8, 0.1), (0.8, 0.3), (0.6, 0.3)))

    def test_valid_detector_quad_on_odd_resize_edge_produces_contract_output(self):
        metadata = replace(
            self.metadata, canonical=ImageInfo(2007, 1000, "RGB", "uint8"),
            processed=ImageInfo(2000, 997, "RGB", "uint8"),
            inverse_transform=((2007 / 2000, 0, 0), (0, 1000 / 997, 0), (0, 0, 1)),
        )
        result = {"rec_texts": ["Mép phải"], "rec_polys": [[[1980,100],[2000,100],[2000,130],[1980,130]]], "rec_scores": [.9]}
        page = _to_page(result, metadata)
        self.assertEqual(OcrPage.from_dict(page.to_dict()), page)
        self.assertEqual(page.blocks[0].text, "Mép phải")
        self.assertEqual(page.blocks[0].score, .9)
        np.testing.assert_allclose(page.blocks[0].quad,
                                   ((1980/2000,100/997),(1,100/997),(1,130/997),(1980/2000,130/997)), rtol=0, atol=1e-15)

    def test_reflection_reverses_winding_without_inventing_corners(self):
        metadata = replace(self.metadata, inverse_transform=((-2, 0, 200), (0, 2, 0), (0, 0, 1)))
        page = _to_page(self.result, metadata)
        self.assertEqual(page.blocks[0].quad, ((0.7, 0.2), (0.9, 0.2), (0.9, 0.4), (0.7, 0.4)))

    def test_unavailable_transform_keeps_text_and_score_without_boxes(self):
        metadata = replace(self.metadata, geometry_status="unavailable", inverse_transform=None, geometry_reason="NO_MAPPING")
        page = _to_page(self.result, metadata)
        self.assertEqual(page.blocks[0].text, "Tổng tiền")
        self.assertAlmostEqual(page.blocks[0].score, 0.93)
        self.assertIsNone(page.blocks[0].quad)
        self.assertEqual(page.blocks[0].geometry_reason, "NO_MAPPING")

    def test_outside_nonfinite_and_malformed_polygons_are_rejected(self):
        for point in ((-1, 10), (101, 10), (10, 51), (float("nan"), 10), (float("inf"), 10)):
            result = deepcopy(self.result)
            result["rec_polys"] = result["rec_polys"].astype(float)
            result["rec_polys"][0, 0] = point
            self.predictor.predict.side_effect = lambda _, result=result, **kwargs: iter([result])
            with self.subTest(point=point):
                self.assert_error("OUTPUT_INVALID", lambda: self.engine.recognize(self.loaded))
        self.result["rec_polys"] = [[[0, 0], [1, 1], [2, 2]]]
        self.predictor.predict.side_effect = lambda _, **kwargs: iter([self.result])
        self.assert_error("OUTPUT_INVALID", lambda: self.engine.recognize(self.loaded))

    def test_self_crossing_polygon_and_undefined_projection_are_rejected(self):
        self.result["rec_polys"][0] = [[10, 10], [30, 20], [30, 10], [10, 20]]
        self.assert_error("OUTPUT_INVALID", lambda: self.engine.recognize(self.loaded))
        self.result["rec_polys"][0] = [[10, 10], [30, 10], [30, 20], [10, 20]]
        metadata = replace(self.metadata, inverse_transform=((1, 0, 0), (0, 1, 0), (1, 0, -10)))
        with self.assertRaisesRegex(ValueError, "projection"):
            _to_page(self.result, metadata)

    def test_missing_or_unaligned_output_is_not_silently_zipped(self):
        for key in ("rec_texts", "rec_polys", "rec_scores"):
            result = deepcopy(self.result)
            del result[key]
            self.predictor.predict.side_effect = lambda _, result=result, **kwargs: iter([result])
            with self.subTest(missing=key):
                self.assert_error("OUTPUT_INVALID", lambda: self.engine.recognize(self.loaded))
        self.result["rec_scores"] = []
        self.predictor.predict.side_effect = lambda _, **kwargs: iter([self.result])
        self.assert_error("OUTPUT_INVALID", lambda: self.engine.recognize(self.loaded))

    def test_score_remains_nullable_and_rejects_bad_native_scores(self):
        for score in (None, 0, np.float32(1)):
            self.result["rec_scores"] = [score, 0.9]
            self.assertEqual(self.engine.recognize(self.loaded).blocks[0].score, score)
        for score in (float("nan"), -0.1, 1.1, True, "0.9"):
            self.result["rec_scores"] = [score, 0.9]
            with self.subTest(score=score):
                self.assert_error("OUTPUT_INVALID", lambda: self.engine.recognize(self.loaded))

    def test_actual_empty_detection_is_allowed_but_native_failure_is_not_blank(self):
        self.result = {"rec_texts": [], "rec_polys": [], "rec_scores": []}
        self.assertEqual(self.engine.recognize(self.loaded).blocks, ())
        self.predictor.predict.side_effect = RuntimeError("private raw payload")
        error = self.assert_error("INTERNAL_ERROR", lambda: self.engine.recognize(self.loaded))
        self.assertNotIn("private raw payload", str(error))

    def test_input_dimensions_and_mode_must_match_metadata(self):
        mismatched = replace(self.loaded, metadata=replace(self.metadata, processed=ImageInfo(99, 50, "RGB", "uint8")))
        self.assert_error("INPUT_INVALID", lambda: self.engine.recognize(mismatched))
        self.predictor.predict.assert_not_called()

    def test_busy_engine_rejects_and_cannot_close_live_slot(self):
        self.engine._slot.acquire()
        try:
            self.assert_error("AI_BUSY", lambda: self.engine.recognize(self.loaded))
            self.assert_error("AI_BUSY", self.engine.close)
            self.assertTrue(self.engine.ready)
        finally:
            self.engine._slot.release()
        self.engine.close()
        self.assertFalse(self.engine.ready)
        self.assert_error("AI_NOT_READY", lambda: self.engine.recognize(self.loaded))

    def test_budget_checked_before_and_after_native_call(self):
        self.assert_error("COMPUTE_TIMEOUT", lambda: self.engine.recognize(self.loaded, remaining_budget_ms=0))
        self.predictor.predict.assert_not_called()
        clock = [0.0]
        def late_result(_, **kwargs):
            clock[0] = 1.0
            return iter([deepcopy(self.result)])
        self.predictor.predict.side_effect = late_result
        with patch("vietdoc.pipeline.ocr.paddle_adapter.time.monotonic", side_effect=lambda: clock[0]):
            self.assert_error("COMPUTE_TIMEOUT", lambda: self.engine.recognize(self.loaded, remaining_budget_ms=500))
        self.assertTrue(self.engine._slot.acquire(blocking=False))
        self.engine._slot.release()

    def test_deadline_is_not_reset_before_canonical_publication(self):
        clock = [0.0]
        def slow_conversion(result, metadata):
            page = _to_page(result, metadata)
            clock[0] = .05
            return page
        module = "vietdoc.pipeline.ocr.paddle_adapter."
        with patch(module + "time.monotonic", side_effect=lambda: clock[0]), patch(module + "_to_page", side_effect=slow_conversion):
            self.assert_error("COMPUTE_TIMEOUT", lambda: self.engine.recognize(self.loaded, remaining_budget_ms=50))
        self.assertTrue(self.engine._slot.acquire(blocking=False))
        self.engine._slot.release()

    def test_pixel_conversion_exhausting_budget_never_starts_predictor(self):
        clock = [0.0]
        contiguous = np.ascontiguousarray
        def slow_conversion(pixels):
            result = contiguous(pixels)
            clock[0] = .05
            return result
        module = "vietdoc.pipeline.ocr.paddle_adapter."
        with patch(module + "time.monotonic", side_effect=lambda: clock[0]), patch(module + "np.ascontiguousarray", side_effect=slow_conversion):
            self.assert_error("COMPUTE_TIMEOUT", lambda: self.engine.recognize(self.loaded, remaining_budget_ms=50))
        self.predictor.predict.assert_not_called()

    def test_python_allocation_failures_are_typed_oom_and_release_slot(self):
        module = "vietdoc.pipeline.ocr.paddle_adapter."
        with patch(module + "np.ascontiguousarray", side_effect=MemoryError):
            self.assert_error("MODEL_OOM", lambda: self.engine.recognize(self.loaded))
        self.predictor.predict.side_effect = MemoryError
        self.assert_error("MODEL_OOM", lambda: self.engine.recognize(self.loaded))
        self.assertTrue(self.engine._slot.acquire(blocking=False))
        self.engine._slot.release()
        engine = VietnameseOcrEngine("unused")
        with patch(module + "version", side_effect=RUNTIME_VERSIONS.__getitem__), patch(module + "_verify_model"), patch(module + "_build_predictor", side_effect=MemoryError):
            self.assert_error("MODEL_OOM", engine.load)
        self.assertFalse(engine.ready)

    def test_model_file_set_and_hash_reject_missing_changed_or_extra_files(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            file = directory / "inference.json"
            file.write_bytes(b"fictional model fixture")
            spec = {"files": {file.name: sha256(file.read_bytes()).hexdigest()}}
            _verify_model(directory, spec)
            file.write_bytes(b"changed")
            self.assert_error("MANIFEST_UNAVAILABLE", lambda: _verify_model(directory, spec))
            (directory / "unexpected.py").write_text("untrusted", encoding="utf-8")
            self.assert_error("MANIFEST_UNAVAILABLE", lambda: _verify_model(directory, spec))
        self.assert_error("MANIFEST_UNAVAILABLE", lambda: _verify_model(Path(temp), spec))

    def test_lifecycle_verifies_runtime_and_loads_predictor_once(self):
        engine = VietnameseOcrEngine("unused-local-models")
        module = "vietdoc.pipeline.ocr.paddle_adapter."
        with patch(module + "version", side_effect=RUNTIME_VERSIONS.__getitem__), patch(module + "_verify_model") as verify, patch(module + "_build_predictor", return_value=self.predictor) as build:
            self.assertIs(engine.load(), engine)
            self.assertIs(engine.load(), engine)
            self.assertEqual(verify.call_count, 2)
            build.assert_called_once()
            self.assertIsNotNone(engine.load_seconds)
        engine.close()
        with patch(module + "version", return_value="different"):
            self.assert_error("MANIFEST_UNAVAILABLE", engine.load)



class CompositePredictorTest(unittest.TestCase):
    def setUp(self):
        self.polygon = np.array([[1, 1], [9, 1], [9, 7], [1, 7]])
        self.detector = Mock()
        self.detector.predict.return_value = [{"dt_polys": [self.polygon]}]
        self.recognizer = Mock()
        self.recognizer.GetUTF8Text.return_value = "Tổng tiền\n"
        self.recognizer.MeanTextConf.return_value = 91
        self.crop = np.full((6, 8, 3), (33, 22, 11), dtype=np.uint8)
        self.cropper = Mock(return_value=[self.crop])
        self.predictor = _PaddleTessPredictor(self.detector, self.recognizer, lambda boxes: boxes, self.cropper)
        self.pixels = np.zeros((10, 10, 3), dtype=np.uint8)

    def test_detected_crop_is_rgb_and_score_is_recognizer_score_divided_by_100(self):
        seen = []
        self.recognizer.SetImage.side_effect = lambda image: seen.append(image.getpixel((0, 0)))
        result = next(self.predictor.predict(self.pixels, deadline=time.monotonic() + 10))
        self.assertEqual(result["rec_texts"], ["Tổng tiền"])
        self.assertEqual(result["rec_scores"], [0.91])
        np.testing.assert_array_equal(result["rec_polys"][0], self.polygon)
        self.assertEqual(seen, [(11, 22, 33)])
        self.recognizer.Clear.assert_called_once()
        self.assertEqual(len(self.cropper.call_args.args[1]), 1)
        self.predictor.close()
        self.recognizer.End.assert_called_once()

    def test_recognition_failure_clears_state_and_does_not_return_blank_success(self):
        self.recognizer.GetUTF8Text.side_effect = RuntimeError("native failure")
        with self.assertRaises(RuntimeError):
            list(self.predictor.predict(self.pixels, deadline=time.monotonic() + 10))
        self.recognizer.Clear.assert_called_once()

    def test_invalid_geometry_is_rejected_before_native_crop(self):
        self.polygon[0] = [-1, 1]
        with self.assertRaises(OcrError) as caught:
            list(self.predictor.predict(self.pixels, deadline=time.monotonic() + 10))
        self.assertEqual(caught.exception.code, "OUTPUT_INVALID")
        self.cropper.assert_not_called()
        self.recognizer.SetImage.assert_not_called()

    def test_empty_detection_never_calls_recognizer(self):
        self.detector.predict.return_value = [{"dt_polys": []}]
        result = next(self.predictor.predict(self.pixels, deadline=time.monotonic() + 10))
        self.assertEqual(result["rec_texts"], [])
        self.cropper.assert_not_called()
        self.recognizer.SetImage.assert_not_called()

    def _run_engine_with_clock(self, clock, budget_ms=50, expected_code="COMPUTE_TIMEOUT"):
        metadata = PreparedPage(0, ImageInfo(10, 10, "RGB", "uint8"), ImageInfo(10, 10, "RGB", "uint8"),
                                "fixture.deadline.v1", "available", ((1,0,0),(0,1,0),(0,0,1)), None)
        self.engine = VietnameseOcrEngine("unused")
        self.engine._predictor = self.predictor
        with LoadedPage(Image.new("RGB", (10,10)), Image.new("RGB", (10,10)), metadata, "0"*64) as loaded:
            with patch("vietdoc.pipeline.ocr.paddle_adapter.time.monotonic", side_effect=lambda: clock[0]):
                with self.assertRaises(OcrError) as caught:
                    self.engine.recognize(loaded, remaining_budget_ms=budget_ms)
                self.assertEqual(caught.exception.code, expected_code)
        self.assertTrue(self.engine._slot.acquire(blocking=False))
        self.engine._slot.release()
        return caught.exception

    def test_expired_first_region_never_starts_the_second_recognition(self):
        clock, starts = [0.0], []
        self.detector.predict.return_value = [{"dt_polys": [self.polygon] * 3}]

        def slow_recognition():
            starts.append(clock[0])
            self.assertTrue(self.engine._slot.locked())
            with self.assertRaises(OcrError) as busy:
                self.engine.close()
            self.assertEqual(busy.exception.code, "AI_BUSY")
            clock[0] += .1
            return "Tổng tiền"

        self.recognizer.GetUTF8Text.side_effect = slow_recognition
        self._run_engine_with_clock(clock)
        self.assertEqual(starts, [0.0])
        self.assertEqual(self.cropper.call_count, 1)
        self.recognizer.Clear.assert_called_once()

    def test_detector_exhausting_budget_prevents_crop_and_recognition(self):
        clock = [0.0]

        def slow_detector(_):
            clock[0] = .05
            yield {"dt_polys": [self.polygon]}

        self.detector.predict.side_effect = slow_detector
        self._run_engine_with_clock(clock)
        self.cropper.assert_not_called()
        self.recognizer.SetImage.assert_not_called()

    def test_crop_exhausting_budget_prevents_recognition(self):
        clock = [0.0]

        def slow_crop(*_):
            clock[0] = .05
            return [self.crop]

        self.cropper.side_effect = slow_crop
        self._run_engine_with_clock(clock)
        self.recognizer.SetImage.assert_not_called()

    def test_deadline_boundary_is_expired_and_recognizer_is_cleared(self):
        clock = [0.0]

        def boundary_recognition():
            clock[0] = .05
            return "Tổng tiền"

        self.recognizer.GetUTF8Text.side_effect = boundary_recognition
        self._run_engine_with_clock(clock)
        self.recognizer.Clear.assert_called_once()

    def test_set_image_exhausting_budget_never_starts_get_text(self):
        clock = [0.0]
        self.recognizer.SetImage.side_effect = lambda _: clock.__setitem__(0, .05)
        self._run_engine_with_clock(clock)
        self.recognizer.GetUTF8Text.assert_not_called()
        self.recognizer.Clear.assert_called_once()

    def test_native_exception_clears_recognizer_and_releases_engine_slot(self):
        self.recognizer.GetUTF8Text.side_effect = RuntimeError("private native payload")
        error = self._run_engine_with_clock([0.0], expected_code="INTERNAL_ERROR")
        self.assertNotIn("private native payload", str(error))
        self.recognizer.Clear.assert_called_once()


class OverlayAndProvisionTest(unittest.TestCase):
    def test_overlay_marks_the_canonical_polygon_without_mutating_source(self):
        from vietdoc.contracts.ocr import OcrBlock, OcrPage
        quad = ((0.2, 0.3), (0.8, 0.3), (0.8, 0.7), (0.2, 0.7))
        page = OcrPage(0, 100, 100, "fixture", (OcrBlock("b1", "Tổng tiền", quad, 0.9, None),))
        with Image.new("RGB", (100, 100), "white") as image:
            with draw_overlay(image, page) as overlay:
                self.assertEqual(overlay.getpixel((20, 30)), (255, 0, 0))
                self.assertEqual(overlay.getpixel((80, 70)), (255, 0, 0))
                self.assertEqual(overlay.getpixel((50, 50)), (255, 255, 255))
            self.assertEqual(image.getpixel((20, 30)), (255, 255, 255))
            with self.assertRaises(ValueError):
                draw_overlay(image.resize((50, 50)), page)

    def test_existing_verified_models_are_not_downloaded_or_overwritten(self):
        module = "vietdoc.pipeline.ocr.paddle_adapter."
        with TemporaryDirectory() as temporary, patch(module + "_verify_model") as verify, patch(module + "urlopen") as download:
            root = Path(temporary)
            for name in MODELS:
                (root / (name + "_infer")).mkdir()
            provision_models(root)
            self.assertEqual(verify.call_count, 2)
            download.assert_not_called()

    def test_missing_or_multiple_native_pages_are_output_invalid(self):
        engine = VietnameseOcrEngine("unused")
        engine._predictor = Mock()
        metadata = PreparedPage(0, ImageInfo(10, 10, "RGB", "uint8"), ImageInfo(10, 10, "RGB", "uint8"), "fixture", "available", ((1, 0, 0), (0, 1, 0), (0, 0, 1)), None)
        with LoadedPage(Image.new("RGB", (10, 10)), Image.new("RGB", (10, 10)), metadata, "0" * 64) as loaded:
            for outputs in ([], [{}, {}], [None]):
                engine._predictor.predict.return_value = iter(outputs)
                with self.subTest(outputs=outputs), self.assertRaises(OcrError) as caught:
                    engine.recognize(loaded)
                self.assertEqual(caught.exception.code, "OUTPUT_INVALID")



class ModelProvisionTest(unittest.TestCase):
    def _tar(self, filename, contents, kind=None):
        import io
        import tarfile
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            member = tarfile.TarInfo(filename)
            if kind:
                member.type = kind
                member.linkname = "../outside"
            else:
                member.size = len(contents)
            archive.addfile(member, None if kind else io.BytesIO(contents))
        return stream.getvalue()

    def _provision(self, root, data, files, name="PP-OCRv5_mobile_det", digest=None):
        from io import BytesIO
        module = "vietdoc.pipeline.ocr.paddle_adapter."
        model = {name: {"source": "https://official.invalid/fixture", "sha256": digest or sha256(data).hexdigest(), "files": files}}
        with patch(module + "MODELS", model), patch(module + "urlopen", return_value=BytesIO(data)):
            provision_models(root)

    def test_archive_and_direct_model_provisioning_validate_bytes(self):
        payload = b"tiny fictional model fixture, not runnable weights"
        digest = sha256(payload).hexdigest()
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self._tar("PP-OCRv5_mobile_det_infer/inference.json", payload)
            self._provision(root, archive, {"inference.json": digest})
            self.assertEqual((root / "PP-OCRv5_mobile_det_infer/inference.json").read_bytes(), payload)
            self._provision(root, payload, {"vie.traineddata": digest}, name="tessdata-vie")
            self.assertEqual((root / "tessdata-vie_infer/vie.traineddata").read_bytes(), payload)

    def test_hash_mismatch_leaves_no_installed_model(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(OcrError) as caught:
                self._provision(root, b"not the pinned model", {"inference.json": "0" * 64}, digest="0" * 64)
            self.assertEqual(caught.exception.code, "MANIFEST_UNAVAILABLE")
            self.assertEqual(list(root.iterdir()), [])

    def test_traversal_extra_members_and_links_are_not_extracted(self):
        import tarfile
        payload = b"fixture"
        for filename, kind in (("../outside", None), ("PP-OCRv5_mobile_det_infer/unexpected.py", None), ("PP-OCRv5_mobile_det_infer/inference.json", tarfile.SYMTYPE)):
            with self.subTest(filename=filename, kind=kind), TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive = self._tar(filename, payload, kind)
                with self.assertRaises(OcrError) as caught:
                    self._provision(root, archive, {"inference.json": sha256(payload).hexdigest()})
                self.assertEqual(caught.exception.code, "MANIFEST_UNAVAILABLE")
                self.assertEqual(list(root.iterdir()), [])

class OcrStageTest(unittest.TestCase):
    def setUp(self):
        self.loaded = LoadedPage(
            Image.new("RGB", (10, 10)), Image.new("RGB", (10, 10)),
            PreparedPage(0, ImageInfo(10, 10, "RGB", "uint8"), ImageInfo(10, 10, "RGB", "uint8"),
                         "fixture.v1", "available", ((1,0,0),(0,1,0),(0,0,1)), None), "0" * 64,
        )
        self.addCleanup(self.loaded.close)
        self.page = OcrPage(0, 10, 10, "fixture.v1", ())
        self.engine = Mock()
        self.engine.recognize.return_value = self.page

    def assert_images_closed(self):
        for image in (self.loaded.canonical, self.loaded.processed):
            with self.assertRaises(ValueError):
                image.getpixel((0,0))

    def test_shared_deadline_keeps_engine_lifecycle_with_caller_and_closes_images(self):
        clock = [10.0]
        def decode(*args, **kwargs):
            clock[0] += .2
            return self.loaded
        def recognize(*args, **kwargs):
            self.assertLessEqual(kwargs["remaining_budget_ms"], 800)
            clock[0] += .3
            return self.page
        self.engine.recognize.side_effect = recognize
        with patch("vietdoc.pipeline.ocr.time.monotonic", side_effect=lambda: clock[0]), patch("vietdoc.pipeline.preprocess.load_document", side_effect=decode):
            with recognize_document(b"input", self.engine, remaining_budget_ms=1000) as result:
                self.assertIs(result.loaded, self.loaded)
                self.assertIs(result.ocr, self.page)
                self.assertLessEqual(result.remaining_budget_ms, 500)
                self.assertGreaterEqual(result.remaining_budget_ms, 490)
                clock[0] += .1
                self.assertLessEqual(result.remaining_budget_ms, 400)
        self.assert_images_closed()
        self.engine.load.assert_not_called()
        self.engine.close.assert_not_called()

    def test_engine_failure_propagates_and_releases_images(self):
        self.engine.recognize.side_effect = RuntimeError("native failure")
        with patch("vietdoc.pipeline.preprocess.load_document", return_value=self.loaded), self.assertRaisesRegex(RuntimeError, "native failure"):
            with recognize_document(b"input", self.engine):
                self.fail("Must not publish a failed OCR result")
        self.assert_images_closed()

    def test_output_on_wrong_canonical_page_is_rejected_and_images_close(self):
        self.engine.recognize.return_value = replace(self.page, width=11)
        with patch("vietdoc.pipeline.preprocess.load_document", return_value=self.loaded), self.assertRaises(OcrError) as caught:
            with recognize_document(b"input", self.engine):
                self.fail("Must not publish mismatched geometry")
        self.assertEqual(caught.exception.code, "OUTPUT_INVALID")
        self.assert_images_closed()

    def test_expired_decode_budget_skips_engine_and_closes_images(self):
        clock = [0.0]
        def decode(*args, **kwargs):
            clock[0] = 2.0
            return self.loaded
        from vietdoc.pipeline.preprocess import PreprocessError
        with patch("vietdoc.pipeline.ocr.time.monotonic", side_effect=lambda: clock[0]), patch("vietdoc.pipeline.preprocess.load_document", side_effect=decode), self.assertRaises(PreprocessError) as caught:
            with recognize_document(b"input", self.engine, remaining_budget_ms=1000):
                self.fail("Must not publish an expired result")
        self.assertEqual(caught.exception.code, "COMPUTE_TIMEOUT")
        self.engine.recognize.assert_not_called()
        self.assert_images_closed()

    def test_expired_native_call_is_not_published_as_success(self):
        clock = [0.0]
        def recognize(*args, **kwargs):
            clock[0] = 2.0
            return self.page
        self.engine.recognize.side_effect = recognize
        from vietdoc.pipeline.preprocess import PreprocessError
        with patch("vietdoc.pipeline.ocr.time.monotonic", side_effect=lambda: clock[0]), patch("vietdoc.pipeline.preprocess.load_document", return_value=self.loaded), self.assertRaises(PreprocessError) as caught:
            with recognize_document(b"input", self.engine, remaining_budget_ms=1000):
                self.fail("Must not publish an expired result")
        self.assertEqual(caught.exception.code, "COMPUTE_TIMEOUT")
        self.assert_images_closed()

    def test_consumer_exception_also_releases_images(self):
        with patch("vietdoc.pipeline.preprocess.load_document", return_value=self.loaded), self.assertRaisesRegex(RuntimeError, "consumer failed"):
            with recognize_document(b"input", self.engine):
                raise RuntimeError("consumer failed")
        self.assert_images_closed()

    def test_decode_failure_skips_engine(self):
        from vietdoc.pipeline.preprocess import PreprocessError
        with patch("vietdoc.pipeline.preprocess.load_document", side_effect=PreprocessError("INPUT_INVALID", "Bad image")), self.assertRaises(PreprocessError):
            with recognize_document(b"bad", self.engine):
                self.fail("Must not return a decode failure as success")
        self.engine.recognize.assert_not_called()


@unittest.skipUnless(os.environ.get("VIETDOC_OCR_MODEL_ROOT"), "Set VIETDOC_OCR_MODEL_ROOT for real pretrained OCR")
class NativeOcrSmokeTest(unittest.TestCase):
    """20 encoding/orientation/error cases from ONE fictional page, not D1 gold."""

    def test_real_vietnamese_text_and_highlights_on_canonical_pixels(self):
        import ctypes
        from ctypes import wintypes
        from io import BytesIO
        import json
        import platform
        import statistics
        import time
        from PIL import ImageDraw, ImageFont
        import pypdfium2 as pdfium
        from vietdoc.contracts.ocr import OcrPage
        from vietdoc.pipeline.preprocess import PreprocessError, PreprocessLimits

        font_path = os.environ.get("VIETDOC_OCR_TEST_FONT")
        if not font_path:
            self.fail("Set VIETDOC_OCR_TEST_FONT to a local font with Vietnamese glyphs")
        font = ImageFont.truetype(font_path, 36)
        reference = ["Tổng tiền", "80.000"]
        base = Image.new("RGB", (800, 400), "white")
        draw = ImageDraw.Draw(base)
        draw.rectangle((20, 20, 60, 60), fill="red")
        positions = [(70, 210), (480, 210)]
        gold_boxes = [draw.textbbox(position, text, font=font) for position, text in zip(positions, reference)]
        for position, text in zip(positions, reference):
            draw.text(position, text, font=font, fill="black")
        undo = {
            2: Image.Transpose.FLIP_LEFT_RIGHT, 3: Image.Transpose.ROTATE_180,
            4: Image.Transpose.FLIP_TOP_BOTTOM, 5: Image.Transpose.TRANSPOSE,
            6: Image.Transpose.ROTATE_90, 7: Image.Transpose.TRANSVERSE,
            8: Image.Transpose.ROTATE_270,
        }
        cases = []
        for fmt in ("PNG", "JPEG"):
            for orientation in range(1, 9):
                image = base.transpose(undo[orientation]) if orientation in undo else base.copy()
                with image:
                    exif = Image.Exif()
                    exif[274] = orientation
                    stream = BytesIO()
                    image.save(stream, format=fmt, exif=exif, quality=95)
                    cases.append((f"{fmt.lower()}-exif-{orientation}", stream.getvalue(), reference, None))
        for rotation in (0, 90):
            image = base.transpose(Image.Transpose.ROTATE_90) if rotation else base.copy()
            with image:
                stream = BytesIO()
                image.save(stream, format="PDF", resolution=200.0)
                data = stream.getvalue()
            if rotation:
                with pdfium.PdfDocument(data) as document:
                    page = document[0]
                    page.set_rotation(rotation)
                    page.close()
                    stream = BytesIO()
                    document.save(stream)
                    data = stream.getvalue()
            cases.append((f"pdf-rotate-{rotation}", data, reference, None))
        with Image.new("RGB", (800, 400), "white") as blank:
            stream = BytesIO()
            blank.save(stream, format="PNG")
            cases.append(("blank-png", stream.getvalue(), [], None))
        cases.append(("corrupt-png", b"\x89PNG\r\n\x1a\ncorrupt", [], "INPUT_INVALID"))
        base.close()
        self.assertEqual(len(cases), 20)
        output = Path(os.environ["VIETDOC_OCR_SMOKE_OUTPUT"]) if os.environ.get("VIETDOC_OCR_SMOKE_OUTPUT") else None
        if output:
            output.mkdir(parents=True, exist_ok=False)
        engine = VietnameseOcrEngine(os.environ["VIETDOC_OCR_MODEL_ROOT"])
        records = []
        try:
            engine.load()
            for sample_id, data, expected_text, expected_error in cases:
                record = {"sample_id": sample_id, "expected_error": expected_error, "reference": expected_text}
                records.append(record)
                with self.subTest(sample_id=sample_id):
                    started = time.monotonic()
                    try:
                        with recognize_document(data, engine, limits=PreprocessLimits(processed_long_edge=400)) as result:
                            loaded, page = result.loaded, result.ocr
                            record.update({"ocr": page.to_dict(), "input_sha256": loaded.input_sha256, "inference_seconds": engine.last_inference_seconds})
                            self.assertEqual(OcrPage.from_dict(page.to_dict()), page)
                            if output:
                                target = output / sample_id
                                target.mkdir()
                                loaded.canonical.save(target / "canonical.png")
                                (target / "ocr.json").write_text(json.dumps(page.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
                                with draw_overlay(loaded.canonical, page) as overlay:
                                    overlay.save(target / "overlay.png")
                            self.assertEqual((page.width, page.height), (800, 400))
                            self.assertEqual([block.text for block in page.blocks], expected_text)
                            overlaps = []
                            for block, gold in zip(page.blocks, gold_boxes):
                                xs = [point[0] * page.width for point in block.quad]
                                ys = [point[1] * page.height for point in block.quad]
                                actual = (min(xs), min(ys), max(xs), max(ys))
                                intersection = max(0, min(actual[2], gold[2]) - max(actual[0], gold[0])) * max(0, min(actual[3], gold[3]) - max(actual[1], gold[1]))
                                union = (actual[2] - actual[0]) * (actual[3] - actual[1]) + (gold[2] - gold[0]) * (gold[3] - gold[1]) - intersection
                                overlaps.append(intersection / union)
                            record["ink_bbox_iou"] = overlaps
                            self.assertTrue(all(overlap >= 0.45 for overlap in overlaps), overlaps)
                            self.assertIsNone(expected_error)
                    except (PreprocessError, OcrError) as exc:
                        record["error"] = exc.code
                        self.assertEqual(exc.code, expected_error)
        finally:
            latency = [record["inference_seconds"] for record in records if "inference_seconds" in record]
            report = {
                "kind": "synthetic-format-geometry-smoke; not D1 quality evaluation",
                "ocr_stage_version": OCR_STAGE_VERSION,
                "python": platform.python_version(), "system": platform.platform(),
                "font_sha256": sha256(Path(font_path).read_bytes()).hexdigest(),
                "runtime": RUNTIME_VERSIONS, "load_seconds": engine.load_seconds,
                "inference_median_seconds": statistics.median(latency) if latency else None,
                "inference_max_seconds": max(latency) if latency else None,
                "cases": records,
            }
            if os.name == "nt":
                class Counters(ctypes.Structure):
                    _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in ("peak_rss", "rss", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile", "private")]
                counters = Counters()
                counters.cb = ctypes.sizeof(counters)
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.GetCurrentProcess.restype = wintypes.HANDLE
                psapi = ctypes.WinDLL("psapi", use_last_error=True)
                psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
                if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
                    report["process_memory_bytes"] = {name: getattr(counters, name) for name in ("rss", "peak_rss", "private")}
            if output:
                (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({k: v for k, v in report.items() if k != "cases"}, ensure_ascii=True))
            engine.close()

if __name__ == "__main__":
    unittest.main()
