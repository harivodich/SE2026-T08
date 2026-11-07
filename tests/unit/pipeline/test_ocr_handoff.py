"""Offline handoff wiring: tiny fictional bytes, never native quality claims."""

from hashlib import sha256
from copy import deepcopy
from dataclasses import replace
from contextlib import redirect_stdout
from io import BytesIO, StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from vietdoc.contracts.ocr import OcrPage, PreparedPage
from vietdoc.pipeline.evidence import EvidenceRequest, match_evidence
from vietdoc.pipeline.ocr import OcrError
from vietdoc.pipeline.ocr import handoff
from vietdoc.pipeline.ocr.handoff import review_manifest
from vietdoc.pipeline.ocr.paddle_adapter import VietnameseOcrEngine, _to_page
from vietdoc.pipeline.geometry import canonical_quad
from vietdoc.pipeline.preprocess import load_document


class HandoffTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        with Image.new("RGB", (60, 40), "white") as image, BytesIO() as stream:
            image.save(stream, format="PNG")
            self.data = stream.getvalue()
        self.engine = Mock()
        self.engine.load_seconds = None
        self.engine.last_inference_seconds = None
        self.images = []

        def recognize(loaded, *, remaining_budget_ms):
            self.assertGreater(remaining_budget_ms, 0)
            self.images.append(loaded.canonical)
            return OcrPage(0, 60, 40, "fictional.test", ())

        self.engine.recognize.side_effect = recognize

    def manifest(self, samples):
        path = self.root / "manifest.json"
        path.write_text(json.dumps({"version": "fictional", "samples": samples}), encoding="utf-8")
        return path

    def sample(self, name="tiny", data=None, digest=None):
        if data is not None:
            (self.root / (name + ".png")).write_bytes(data)
        return {"sample_id": name, "document_type": "receipt", "assets": {
            "png": {"path": name + ".png", "sha256": digest or sha256(self.data).hexdigest()}}}

    def run_cli(self, manifest, output):
        stream = StringIO()
        argv = ["ocr-handoff", "--root", str(self.root), "--manifest", str(manifest),
                "--output-dir", str(output), "--model-root", "unused-local-models"]
        with patch("sys.argv", argv), patch("vietdoc.pipeline.ocr.paddle_adapter.VietnameseOcrEngine", return_value=self.engine), redirect_stdout(stream):
            status = handoff.main()
        return status, json.loads(stream.getvalue())

    def test_unexpected_engine_failure_aborts_with_complete_accounting_and_safe_cli(self):
        private = "PRIVATE_TOKEN D:/private/document.png"
        manifest = self.manifest([self.sample(name, self.data) for name in ("one", "two", "later")])
        self.engine.recognize.side_effect = [OcrPage(0,60,40,"fictional.test",()), ValueError(private)]
        output = self.root / "aborted"
        status, payload = self.run_cli(manifest, output)
        self.assertNotEqual(status, 0)
        self.assertTrue(payload["report_written"])
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["run_status"], "aborted")
        self.assertEqual(report["report_version"], "vietdoc.ocr-handoff.v2")
        self.assertEqual(report["counts"], {"requested":3,"native_attempted":2,"ok":1,"failed":1,"not_run":1})
        self.assertEqual([s["sample_id"] for s in report["samples"]], ["one", "two", "later"])
        self.assertEqual(report["samples"][1]["stage"], "ocr")
        self.assertEqual(report["samples"][1]["error_code"], "UNEXPECTED_FAILURE")
        self.assertEqual(report["samples"][2]["error_code"], "BATCH_ABORTED")
        self.assertFalse(report["samples"][2]["native_attempted"])
        self.assertEqual(self.engine.recognize.call_count, 2)
        self.engine.close.assert_called_once()
        for text in (json.dumps(payload), json.dumps(report)):
            self.assertNotIn(private, text)
            self.assertNotIn("Traceback", text)

    def test_typed_failures_keep_later_samples_and_distinct_stages(self):
        bad = b"not an image"
        manifest = self.manifest([self.sample("missing"), self.sample("corrupt", bad, sha256(bad).hexdigest()),
                                  self.sample("ocrbad", self.data), self.sample("exportbad", self.data), self.sample("last", self.data)])
        self.engine.recognize.side_effect = [OcrError("MODEL_OOM", "safe"), OcrPage(0,60,40,"fictional.test",()), OcrPage(0,60,40,"fictional.test",())]
        original = handoff._json
        def write(path, data):
            if path.parent.name == "exportbad" and path.name == "ocr.json":
                raise PermissionError("PRIVATE_TOKEN D:/private/output")
            return original(path, data)
        with patch.object(handoff, "_json", side_effect=write):
            report = review_manifest(self.root, manifest, self.root / "stages", self.engine)
        self.assertEqual(report["run_status"], "completed")
        self.assertEqual(report["counts"], {"requested":5,"native_attempted":3,"ok":1,"failed":3,"not_run":1})
        self.assertEqual([s["stage"] for s in report["samples"]], ["input","preprocess","ocr","export","export"])
        self.assertEqual([s.get("error_code") for s in report["samples"]], ["INPUT_ARTIFACT_UNAVAILABLE","INPUT_INVALID","MODEL_OOM","LOCAL_EXPORT_FAILED",None])

    def test_per_sample_record_storage_failure_retains_final_accounting(self):
        manifest = self.manifest([self.sample(name, self.data) for name in ("one", "later")])
        original = handoff._json
        def write(path, data):
            if path.parent.name == "one" and path.name == "run.json":
                raise OSError("PRIVATE_TOKEN D:/private/output")
            return original(path, data)
        output = self.root / "record-failure"
        with patch.object(handoff, "_json", side_effect=write):
            status, payload = self.run_cli(manifest, output)
        self.assertNotEqual(status, 0)
        self.assertTrue(payload["report_written"])
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["counts"], {"requested":2,"native_attempted":2,"ok":1,"failed":1,"not_run":0})
        self.assertEqual(report["samples"][0]["record_write_error"], "LOCAL_EXPORT_FAILED")
        self.assertFalse((output / "one/run.json").exists())
        self.assertEqual(report["samples"][1]["status"], "ok")
        for image in self.images:
            with self.assertRaises(ValueError): image.getpixel((0,0))

    def test_final_report_storage_failure_exits_safely_without_claiming_written(self):
        manifest = self.manifest([self.sample(data=self.data)])
        original = handoff._json
        def write(path, data):
            if path.name == "report.json":
                raise OSError("PRIVATE_TOKEN D:/private/output")
            return original(path, data)
        output = self.root / "report-failure"
        with patch.object(handoff, "_json", side_effect=write):
            status, payload = self.run_cli(manifest, output)
        self.assertNotEqual(status, 0)
        self.assertFalse(payload["report_written"])
        self.assertEqual(payload["code"], "LOCAL_REPORT_WRITE_FAILED")
        self.assertEqual(payload["stage"], "export")
        self.assertNotIn("PRIVATE_TOKEN", json.dumps(payload))
        self.assertFalse((output / "report.json").exists())

    def test_output_directory_failure_is_safe_and_never_calls_engine(self):
        manifest = self.manifest([self.sample(data=self.data)])
        with patch.object(Path, "mkdir", side_effect=PermissionError("PRIVATE_TOKEN D:/private/output")):
            status, payload = self.run_cli(manifest, self.root / "denied")
        self.assertNotEqual(status, 0)
        self.assertEqual(payload, {"code":"OUTPUT_DIRECTORY_UNAVAILABLE", "stage":"export", "report_written":False})
        self.engine.recognize.assert_not_called()

    def test_bare_memory_failure_aborts_and_close_failure_never_prints_traceback(self):
        manifest = self.manifest([self.sample(name, self.data) for name in ("one", "later")])
        self.engine.recognize.side_effect = MemoryError("PRIVATE_TOKEN D:/private/native")
        output = self.root / "memory-fatal"
        status, payload = self.run_cli(manifest, output)
        self.assertNotEqual(status, 0)
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["run_status"], "aborted")
        self.assertEqual(report["abort_code"], "LOCAL_MEMORY_EXHAUSTED")
        self.assertEqual(report["counts"], {"requested":2,"native_attempted":1,"ok":0,"failed":1,"not_run":1})
        self.engine.close.side_effect = RuntimeError("PRIVATE_TOKEN D:/private/close")
        status, payload = self.run_cli(manifest, self.root / "close-fatal")
        self.assertNotEqual(status, 0)
        self.assertEqual(payload, {"code":"ENGINE_CLOSE_FAILED", "stage":"engine_close", "report_written":True})

    def test_input_and_ocr_os_errors_are_not_reported_as_export_errors(self):
        manifest = self.manifest([self.sample(data=self.data)])
        self.engine.recognize.side_effect = FileNotFoundError("PRIVATE_TOKEN D:/private/model")
        report = review_manifest(self.root, manifest, self.root / "ocr-io", self.engine)
        self.assertEqual(report["samples"][0]["stage"], "ocr")
        self.assertEqual(report["samples"][0]["error_code"], "LOCAL_OCR_IO_ERROR")
        original = Path.open
        def open_file(path, *args, **kwargs):
            if path == self.root / "tiny.png":
                raise PermissionError("PRIVATE_TOKEN D:/private/input")
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", open_file):
            report = review_manifest(self.root, manifest, self.root / "input-io", self.engine)
        self.assertEqual(report["samples"][0]["stage"], "input")
        self.assertEqual(report["samples"][0]["error_code"], "LOCAL_INPUT_IO_ERROR")
        self.assertEqual(report["counts"]["native_attempted"], 0)

    def test_success_and_missing_keep_denominator_and_engine_owned_by_caller(self):
        manifest = self.manifest([self.sample(data=self.data), self.sample("missing")])
        output = self.root / "review"
        report = review_manifest(self.root, manifest, output, self.engine)
        self.assertEqual(report["counts"], {"requested": 2, "native_attempted": 1, "ok": 1, "failed": 0, "not_run": 1})
        self.assertEqual(report["samples"][1]["error_code"], "INPUT_ARTIFACT_UNAVAILABLE")
        canonical = output / "tiny/canonical.png"
        self.assertEqual(sha256(canonical.read_bytes()).hexdigest(), report["samples"][0]["canonical"]["sha256"])
        self.assertNotEqual(report["samples"][0]["canonical"]["sha256"], "0" * 64)
        with Image.open(canonical) as image:
            self.assertEqual(image.size, (60, 40))
        with self.assertRaises(ValueError):
            self.images[0].getpixel((0, 0))
        self.engine.load.assert_not_called()
        self.engine.close.assert_not_called()
        before = (output / "report.json").read_bytes()
        with self.assertRaises(handoff.HandoffError) as caught:
            review_manifest(self.root, manifest, output, self.engine)
        self.assertEqual(caught.exception.code, "OUTPUT_DIRECTORY_UNAVAILABLE")
        self.assertEqual((output / "report.json").read_bytes(), before)
        self.assertEqual(self.engine.recognize.call_count, 1)

    def test_bad_hash_and_corrupt_input_never_call_engine(self):
        manifest = self.manifest([self.sample(data=self.data, digest="0" * 64), self.sample("corrupt", b"not an image", sha256(b"not an image").hexdigest())])
        report = review_manifest(self.root, manifest, self.root / "review", self.engine)
        self.assertEqual(report["counts"], {"requested": 2, "native_attempted": 0, "ok": 0, "failed": 2, "not_run": 0})
        self.assertEqual([s["error_code"] for s in report["samples"]], ["INPUT_INVALID"] * 2)
        self.engine.recognize.assert_not_called()

    def test_native_error_recorded_and_later_sample_still_processed(self):
        manifest = self.manifest([self.sample(data=self.data), self.sample("next", self.data)])
        self.engine.recognize.side_effect = [OcrError("MODEL_OOM", "safe failure"), OcrPage(0, 60, 40, "fictional.test", ())]
        report = review_manifest(self.root, manifest, self.root / "review", self.engine)
        self.assertEqual(report["counts"], {"requested": 2, "native_attempted": 2, "ok": 1, "failed": 1, "not_run": 0})
        self.assertEqual(report["samples"][0]["error_code"], "MODEL_OOM")

    def test_fixture_fallback_is_explicit_and_does_not_bypass_hash(self):
        manifest = self.manifest([self.sample()])
        fixture = self.root / "tests/fixtures/d12/tiny.png"
        fixture.parent.mkdir(parents=True)
        fixture.write_bytes(self.data)
        report = review_manifest(self.root, manifest, self.root / "fallback", self.engine, fixture_fallback=True)
        self.assertEqual(report["counts"]["ok"], 1)
        self.assertTrue(report["samples"][0]["fixture_fallback"])
        fixture.write_bytes(b"changed")
        report = review_manifest(self.root, manifest, self.root / "changed", self.engine, fixture_fallback=True)
        self.assertEqual(report["counts"]["native_attempted"], 0)
        self.assertEqual(report["samples"][0]["error_code"], "INPUT_INVALID")

    def test_invalid_manifest_and_path_rejected_before_output(self):
        for samples in ([None], [self.sample("../escape")], [self.sample(), self.sample()]):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                review_manifest(self.root, self.manifest(samples), self.root / "review", self.engine)
        sample = self.sample()
        for path in ("../escape.png", "C:/escape.png", "a\\b.png"):
            sample["assets"]["png"]["path"] = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                review_manifest(self.root, self.manifest([sample]), self.root / "review", self.engine)
        self.assertFalse((self.root / "review").exists())

    def test_casefold_aliases_rejected_before_output_and_engine_on_every_os(self):
        for index, ids in enumerate((("a1", "A1"), ("Receipt_7", "RECEIPT_7"))):
            output = self.root / f"alias-{index}"
            manifest = self.manifest([self.sample(name) for name in ids])
            with self.subTest(ids=ids):
                with self.assertRaises(ValueError):
                    review_manifest(self.root, manifest, output, self.engine)
                self.assertFalse(output.exists())
                self.engine.recognize.assert_not_called()

    def test_portable_identity_preserves_original_case_in_report_and_directory(self):
        manifest = self.manifest([self.sample("AbC_1", self.data)])
        output = self.root / "case-preserved"
        report = review_manifest(self.root, manifest, output, self.engine)
        self.assertEqual(report["samples"][0]["sample_id"], "AbC_1")
        self.assertTrue((output / "AbC_1/ocr.json").is_file())
        self.assertEqual(report["counts"]["native_attempted"], 1)

    def test_v2_handoff_keeps_mixed_unreadable_and_no_detection_semantics(self):
        golden = json.loads((Path(__file__).resolve().parents[2] / "fixtures/ocr-artifact-v2.json").read_text(encoding="utf-8"))
        with Image.new("RGB", (100, 100), "white") as image, BytesIO() as stream:
            image.save(stream, format="PNG")
            data = stream.getvalue()
        for case in golden["cases"]:
            name = case["case_id"]
            manifest = self.manifest([self.sample(name, data, sha256(data).hexdigest())])
            self.engine.recognize.side_effect = lambda loaded, **kwargs: _to_page(case["provider"], loaded.metadata, artifact_version=2)
            output = self.root / (name + "-review")
            with self.subTest(case=name):
                report = review_manifest(self.root, manifest, output, self.engine)
                actual = json.loads((output / name / "ocr.json").read_text(encoding="utf-8"))
                expected = {**case["expected"], "ocr_version": actual["ocr_version"]}
                self.assertEqual(actual, expected)
                self.assertEqual(report["counts"]["ok"], 1)
                self.assertEqual(report["samples"][0]["recognition_status"], expected["recognition_status"])
                missing = match_evidence(OcrPage.from_dict(actual), EvidenceRequest("/total_amount", None)).to_field_metadata()
                self.assertEqual(missing["value_origin"], "prediction")
                self.assertEqual(missing["source_regions"], [])
                for flag in expected["review_flags"]:
                    self.assertIn(flag, missing["review_flags"])
                    self.assertIn(flag, (output / name / "preview.html").read_text(encoding="utf-8"))

    def test_v2_invalid_provider_score_or_geometry_remains_typed_failure(self):
        valid = {"rec_texts": [""], "rec_polys": [[[10,10],[20,10],[20,20],[10,20]]], "rec_scores": [0]}
        for index, key, value in ((0, "rec_scores", [float("nan")]), (1, "rec_polys", [[[0,0],[1,0],[1,1]]])):
            provider = {**deepcopy(valid), key: value}
            engine = VietnameseOcrEngine("unused-local-models", artifact_version=2)
            engine._predictor = Mock()
            engine._predictor.predict.side_effect = lambda *args, **kwargs: iter([provider])
            manifest = self.manifest([self.sample(data=self.data)])
            with self.subTest(key=key):
                report = review_manifest(self.root, manifest, self.root / f"invalid-{index}", engine)
                self.assertEqual(report["counts"], {"requested":1, "native_attempted":1, "ok":0, "failed":1, "not_run":0})
                self.assertEqual(report["samples"][0]["error_code"], "OUTPUT_INVALID")
                self.assertFalse(engine._slot.locked())


class D1GeometryHandshakeTest(unittest.TestCase):
    def test_observed_native_evidence_examples_keep_ids_or_abstain(self):
        root = Path(__file__).resolve().parents[3]
        bundle = json.loads((root / "tests/fixtures/ocr-d1-native-handoff.json").read_text(encoding="utf-8"))
        statuses = set()
        for sample in bundle["samples"]:
            page = OcrPage.from_dict(sample["ocr"])
            for example in sample["evidence_examples"]:
                source = page
                if example["kind"].startswith("injected"):
                    source = replace(page, blocks=tuple(replace(b, quad=None, geometry_reason="fixture mapping unavailable") for b in page.blocks))
                request = EvidenceRequest(**example["request"])
                result = match_evidence(source, request)
                self.assertEqual(result.status, example["status"])
                self.assertEqual(result.to_field_metadata(), example["field_metadata"])
                if result.status != "matched":
                    self.assertEqual(result.to_field_metadata()["source_regions"], [])
                statuses.add(result.status)
        self.assertTrue({"matched", "ambiguous", "geometry_unavailable"}.issubset(statuses))

    def test_renderer_local_rectangles_map_by_independent_png_identity_oracle(self):
        # Version: d1-png-identity-pixel-edge.v1. Not an OCR quality evaluator.
        root = Path(__file__).resolve().parents[3]
        manifest = json.loads((root / "tests/fixtures/d12/manifest.json").read_text(encoding="utf-8"))
        for sample in manifest["samples"]:
            png, sidecar = (sample["assets"][name] for name in ("png", "regions.json"))
            data = (root / png["path"]).read_bytes()
            region_bytes = (root / sidecar["path"]).read_bytes()
            self.assertEqual(sha256(region_bytes).hexdigest(), sidecar["sha256"])
            regions = json.loads(region_bytes)
            self.assertEqual((regions["page"], regions["width"], regions["height"]), (0, 1500, 2600))
            self.assertEqual(regions["transform"], "identity; PNG is the rendered page")
            self.assertEqual((regions["origin"], regions["units"]), ("top-left", "pixels"))
            with load_document(data, expected_sha256=png["sha256"]) as loaded, Image.open(BytesIO(data)) as original:
                self.assertEqual(loaded.canonical.size, original.size)
                self.assertEqual(loaded.canonical.tobytes(), original.tobytes())
                self.assertEqual(loaded.processed.size, (1154, 2000))
                for region in regions["regions"]:
                    left, top, right, bottom = region["bbox_px"]
                    expected = ((left/1500, top/2600), (right/1500, top/2600),
                                (right/1500, bottom/2600), (left/1500, bottom/2600))
                    processed = tuple((x*1154, y*2000) for x, y in expected)
                    actual = canonical_quad(processed, loaded.metadata)
                    for point, oracle in zip(actual, expected):
                        for value, reference in zip(point, oracle):
                            self.assertAlmostEqual(value, reference, places=14)


if __name__ == "__main__":
    unittest.main()
