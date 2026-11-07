"""Offline handoff wiring: tiny fictional bytes, never native quality claims."""

from hashlib import sha256
from copy import deepcopy
from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from PIL import Image

from vietdoc.contracts.ocr import OcrPage, PreparedPage
from vietdoc.pipeline.evidence import EvidenceRequest, match_evidence
from vietdoc.pipeline.ocr import OcrError
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
        with self.assertRaises(FileExistsError):
            review_manifest(self.root, manifest, output, self.engine)

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
