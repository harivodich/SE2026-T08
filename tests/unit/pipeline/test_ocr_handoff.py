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
from vietdoc.pipeline.preprocess import PreprocessError, load_document


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

    def test_optional_provenance_hashes_preserve_valid_and_null_values(self):
        for index, value in enumerate((None, "0123456789abcdef" * 4)):
            manifest = self.manifest([self.sample(data=self.data)])
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document.update(font_sha256=value, config_sha256=value)
            manifest.write_text(json.dumps(document), encoding="utf-8")
            snapshot = manifest.read_bytes()
            output = self.root / f"valid-provenance-{index}"
            with self.subTest(value=value):
                status, payload = self.run_cli(manifest, output)
                self.assertEqual(status, 0)
                self.assertTrue(payload["report_written"])
                report = json.loads((output / "report.json").read_text(encoding="utf-8"))
                self.assertEqual(report["manifest_sha256"], sha256(snapshot).hexdigest())
                self.assertEqual(report["font_sha256"], value)
                self.assertEqual(report["config_sha256"], value)

    def test_invalid_optional_provenance_rejected_before_cli_load_and_output(self):
        for key in ("font_sha256", "config_sha256"):
            for index, value in enumerate((True, 12, [], {}, "", "a" * 63, "a" * 65,
                                           "A" * 64, "g" * 64, "a" * 64 + "\n")):
                manifest = self.manifest([self.sample(data=self.data)])
                document = json.loads(manifest.read_text(encoding="utf-8"))
                document[key] = value
                manifest.write_text(json.dumps(document), encoding="utf-8")
                output = self.root / f"invalid-{key}-{index}"
                with self.subTest(key=key, value=value):
                    status, payload = self.run_cli(manifest, output)
                    self.assertEqual(status, 2)
                    self.assertEqual(payload, {"code":"MANIFEST_INVALID", "stage":"input", "report_written":False})
                    self.assertFalse(output.exists())
                    self.engine.load.assert_not_called()
                    self.engine.recognize.assert_not_called()
                    self.engine.close.assert_not_called()

    def test_overflow_json_numbers_rejected_even_in_nested_metadata(self):
        manifest = self.manifest([self.sample(data=self.data)])
        base = manifest.read_text(encoding="utf-8")
        for index, value in enumerate(("1e999", "-1e999", '{"nested":[1e999]}')):
            manifest.write_text(base[:-1] + ',"environment":' + value + '}', encoding="utf-8")
            output = self.root / f"overflow-{index}"
            with self.subTest(value=value):
                status, payload = self.run_cli(manifest, output)
                self.assertEqual(status, 2)
                self.assertEqual(payload, {"code":"MANIFEST_INVALID", "stage":"input", "report_written":False})
                self.assertFalse(output.exists())
                self.engine.load.assert_not_called()
                self.engine.recognize.assert_not_called()

    def test_unavailable_runtime_measurements_are_null_in_strict_report(self):
        manifest = self.manifest([self.sample(data=self.data)])
        for index, value in enumerate((float("nan"), float("inf"), float("-inf"), -1, True, "PRIVATE_TOKEN", 10**400)):
            self.engine.load_seconds = self.engine.last_inference_seconds = value
            output = self.root / f"measurement-{index}"
            with self.subTest(value=value):
                status, payload = self.run_cli(manifest, output)
                self.assertEqual(status, 0)
                self.assertTrue(payload["report_written"])
                report = json.loads((output / "report.json").read_text(encoding="utf-8"),
                                    parse_constant=lambda value: self.fail("Nonfinite JSON: " + value))
                self.assertIsNone(report["engine_load_seconds"])
                self.assertIsNone(report["samples"][0]["ocr_seconds"])
                self.assertNotIn("PRIVATE_TOKEN", json.dumps(report))

    def test_finite_runtime_measurements_preserved_without_rounding(self):
        manifest = self.manifest([self.sample(data=self.data)])
        self.engine.load_seconds = 0
        self.engine.last_inference_seconds = 1.23456789
        report = review_manifest(self.root, manifest, self.root / "finite-measurements", self.engine)
        self.assertEqual(report["engine_load_seconds"], 0)
        self.assertEqual(report["samples"][0]["ocr_seconds"], 1.23456789)

    def test_json_writer_rejects_nonfinite_before_creating_a_partial_file(self):
        for index, value in enumerate((float("nan"), float("inf"), float("-inf"))):
            target = self.root / f"invalid-json-{index}.json"
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    handoff._json(target, {"nested": [value]})
                self.assertFalse(target.exists())

    def test_json_writer_rejects_invalid_unicode_before_creating_a_file(self):
        for index, text in enumerate(("\ud800", "\udfff")):
            for location, value in (("value", {"text": text}), ("key", {text: "value"}),
                                    ("nested", {"metadata": [{"text": text}]})):
                target = self.root / f"invalid-unicode-{index}-{location}.json"
                with self.subTest(index=index, location=location):
                    with self.assertRaises(UnicodeEncodeError):
                        handoff._json(target, value)
                    self.assertFalse(target.exists())

    def test_invalid_manifest_unicode_rejected_before_output_and_engine(self):
        for index, text in enumerate(("\ud800", "\udfff")):
            for location in ("version", "key", "array", "asset_path"):
                manifest = self.manifest([self.sample(data=self.data)])
                document = json.loads(manifest.read_text(encoding="utf-8"))
                if location == "version":
                    document["version"] = text
                elif location == "key":
                    document["metadata"] = {text: "value"}
                elif location == "array":
                    document["metadata"] = {"values": [[text]]}
                else:
                    document["samples"][0]["assets"]["png"]["path"] = text + ".png"
                manifest.write_text(json.dumps(document), encoding="utf-8")
                output = self.root / f"unicode-manifest-{index}-{location}"
                with self.subTest(index=index, location=location):
                    status, payload = self.run_cli(manifest, output)
                    self.assertEqual(status, 2)
                    self.assertEqual(payload, {"code":"MANIFEST_INVALID", "stage":"input", "report_written":False})
                    self.assertFalse(output.exists())
                    self.engine.load.assert_not_called()
                    self.engine.recognize.assert_not_called()
                    self.engine.close.assert_not_called()

    def test_valid_unicode_preserves_utf8_bytes_and_manifest_snapshot_hash(self):
        for index, (text, escaped) in enumerate((("T\u1ed5ng ti\u1ec1n", False),
                                                ("To\u0302\u0309ng", True), ("\U0001f600", True))):
            manifest = self.manifest([self.sample(data=self.data)])
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document.update(version=text, metadata={text: [[text]]})
            snapshot = json.dumps(document, ensure_ascii=escaped).encode("utf-8")
            manifest.write_bytes(snapshot)
            output = self.root / f"valid-unicode-{index}"
            with self.subTest(index=index):
                status, payload = self.run_cli(manifest, output)
                self.assertEqual(status, 0)
                self.assertTrue(payload["report_written"])
                report = json.loads((output / "report.json").read_bytes().decode("utf-8"))
                self.assertEqual(report["manifest_version"], text)
                self.assertEqual(report["manifest_sha256"], sha256(snapshot).hexdigest())
                value = {"text": text, text: [text], "control": "\r\n\x00"}
                target = self.root / f"valid-unicode-{index}.json"
                handoff._json(target, value)
                self.assertEqual(target.read_bytes(), json.dumps(value, ensure_ascii=False, indent=2,
                                                                 allow_nan=False).encode("utf-8"))
                self.assertEqual(json.loads(target.read_bytes().decode("utf-8")), value)

    def test_invalid_runtime_unicode_keeps_accounting_and_no_partial_ocr_json(self):
        manifest = self.manifest([self.sample(data=self.data)])
        self.engine.recognize.side_effect = lambda *args, **kwargs: OcrPage(0, 60, 40, "fictional.\ud800", ())
        output = self.root / "runtime-unicode"
        status, payload = self.run_cli(manifest, output)
        self.assertEqual(status, 2)
        self.assertTrue(payload["report_written"])
        self.assertFalse((output / "tiny/ocr.json").exists())
        report = json.loads((output / "report.json").read_bytes().decode("utf-8"))
        self.assertEqual(report["run_status"], "aborted")
        self.assertEqual(report["counts"], {"requested":1, "native_attempted":1, "ok":0, "failed":1, "not_run":0})
        self.assertEqual(report["samples"][0]["stage"], "export")
        self.assertEqual(report["samples"][0]["error_code"], "UNEXPECTED_FAILURE")
        self.engine.close.assert_called_once()
        for image in self.images:
            with self.assertRaises(ValueError):
                image.getpixel((0, 0))

    def test_unserializable_runtime_report_returns_safe_failure_and_closes_images(self):
        manifest = self.manifest([self.sample(data=self.data)])
        output = self.root / "invalid-runtime-report"
        with patch.object(handoff, "_memory", return_value={"rss": float("nan")}):
            status, payload = self.run_cli(manifest, output)
        self.assertEqual(status, 2)
        self.assertEqual(payload, {"code":"LOCAL_REPORT_WRITE_FAILED", "stage":"export", "report_written":False})
        self.assertFalse((output / "report.json").exists())
        self.assertFalse((output / "tiny/run.json").exists())
        self.engine.close.assert_called_once()
        for image in self.images:
            with self.assertRaises(ValueError):
                image.getpixel((0, 0))

    def test_manifest_mutation_after_snapshot_keeps_digest_version_and_samples(self):
        manifest = self.manifest([self.sample(data=self.data)])
        snapshot = manifest.read_bytes()
        changed = json.dumps({"version":"mutated", "samples":[self.sample("different")]}).encode()
        original_loads, original_open = json.loads, Path.open
        reads, mutations = [], []
        def open_file(path, mode="r", *args, **kwargs):
            if path == manifest and mode in ("r", "rb"):
                reads.append(mode)
            return original_open(path, mode, *args, **kwargs)
        def parse(value, *args, **kwargs):
            parsed = original_loads(value, *args, **kwargs)
            if not mutations and value in (snapshot, snapshot.decode()):
                manifest.write_bytes(changed)
                mutations.append(True)
            return parsed
        with patch.object(Path, "open", open_file), patch.object(handoff.json, "loads", side_effect=parse):
            report = review_manifest(self.root, manifest, self.root / "snapshot", self.engine)
        self.assertEqual(mutations, [True])
        self.assertEqual(report["manifest_sha256"], sha256(snapshot).hexdigest())
        self.assertEqual(report["manifest_version"], "fictional")
        self.assertEqual([s["sample_id"] for s in report["samples"]], ["tiny"])
        self.assertEqual(len(reads), 1)
        self.assertEqual(manifest.read_bytes(), changed)

    def test_cli_uses_preflight_snapshot_even_if_engine_load_changes_file(self):
        manifest = self.manifest([self.sample(data=self.data)])
        snapshot = manifest.read_bytes()
        changed = json.dumps({"version":"mutated", "samples":[self.sample("different")]}).encode()
        self.engine.load.side_effect = lambda: manifest.write_bytes(changed)
        output = self.root / "cli-snapshot"
        status, payload = self.run_cli(manifest, output)
        self.assertEqual(status, 0)
        self.assertTrue(payload["report_written"])
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["manifest_sha256"], sha256(snapshot).hexdigest())
        self.assertEqual(report["manifest_version"], "fictional")
        self.assertEqual(report["counts"]["requested"], 1)
        self.assertEqual(report["samples"][0]["sample_id"], "tiny")
        self.engine.load.assert_called_once()

    def test_oversized_valid_manifest_rejected_before_output_and_engine(self):
        manifest = self.manifest([self.sample(data=self.data)])
        manifest.write_bytes(b" " * handoff.MAX_MANIFEST_BYTES + manifest.read_bytes())
        output = self.root / "oversized"
        with self.assertRaises(ValueError):
            review_manifest(self.root, manifest, output, self.engine)
        self.assertFalse(output.exists())
        self.engine.recognize.assert_not_called()

    def test_bad_snapshot_json_identity_path_rejected_before_cli_load(self):
        manifest = self.root / "invalid.json"
        samples = json.dumps([self.sample()]).encode()
        invalid = [b"{", b"\xff", b'{}', b'{"version":"v","samples":NaN}',
                   b'{"version":"v","version":"again","samples":'+samples+b'}',
                   json.dumps({"version":"", "samples":[self.sample()]}).encode(),
                   json.dumps({"version":"v", "samples":[self.sample("a1"), self.sample("A1")]}).encode(),
                   json.dumps({"version":"v", "samples":[{**self.sample(), "assets":{"png":{"path":"/PRIVATE/input.png", "sha256":"0"*64}}}]}).encode()]
        for index, data in enumerate(invalid):
            manifest.write_bytes(data)
            output = self.root / f"invalid-snapshot-{index}"
            with self.subTest(index=index):
                status, payload = self.run_cli(manifest, output)
                self.assertNotEqual(status, 0)
                self.assertEqual(payload, {"code":"MANIFEST_INVALID", "stage":"input", "report_written":False})
                self.assertFalse(output.exists())
                self.engine.load.assert_not_called()
                self.engine.recognize.assert_not_called()

    def test_invalid_selected_id_types_rejected_before_side_effects(self):
        manifest = self.manifest([self.sample()])
        for index, ids in enumerate(("tiny", [], [[]], [None], ["tiny","tiny"], ["unknown"])):
            output = self.root / f"selection-{index}"
            with self.subTest(ids=ids):
                with self.assertRaises(ValueError):
                    review_manifest(self.root, manifest, output, self.engine, sample_ids=ids)
                self.assertFalse(output.exists())
                self.engine.recognize.assert_not_called()

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

    def test_unusable_engine_dispatch_does_not_count_as_an_engine_call(self):
        class NonCallableEngine:
            recognize = None

        class FailedLookupEngine:
            @property
            def recognize(self):
                raise RuntimeError("PRIVATE_TOKEN D:/private/provider")

        manifest = self.manifest([self.sample(name, self.data) for name in ("one", "later")])
        for index, engine in enumerate((object(), NonCallableEngine(), FailedLookupEngine())):
            with self.subTest(engine=type(engine).__name__):
                report = review_manifest(self.root, manifest, self.root / f"dispatch-{index}", engine)
                self.assertEqual(report["run_status"], "aborted")
                self.assertEqual(report["counts"], {"requested":2,"native_attempted":0,"ok":0,"failed":1,"not_run":1})
                self.assertEqual(report["samples"][0]["stage"], "ocr")
                self.assertEqual(report["samples"][0]["error_code"], "UNEXPECTED_FAILURE")
                self.assertFalse(report["samples"][0]["native_attempted"])
                self.assertEqual(report["samples"][1]["error_code"], "BATCH_ABORTED")
                self.assertNotIn("PRIVATE_TOKEN", json.dumps(report))

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
    def test_mixed_viewer_inputs_keep_diagnostics_and_reject_wrong_hash_or_frame(self):
        from vietdoc.pipeline.ocr.preview import render_preview

        root = Path(__file__).resolve().parents[3]
        index = json.loads((root / "tests/fixtures/ocr-d1-canonical-assets.json").read_text(encoding="utf-8"))
        fixture = index["viewer_fixture"]
        golden = json.loads((root / fixture["ocr_golden"]["path"]).read_text(encoding="utf-8"))
        expected = next(c["expected"] for c in golden["cases"] if c["case_id"] == fixture["ocr_golden"]["case_id"])
        page = OcrPage.from_dict(expected)
        prepared = PreparedPage.from_dict(golden["prepared_page"])
        data = (root / fixture["canonical_png"]).read_bytes()
        self.assertEqual(sha256(data).hexdigest(), fixture["sha256"])
        cases = {case["case_id"]: case for case in fixture["cases"]}
        self.assertEqual(set(cases), {"mixed-v2", "required-total-missing", "wrong-canonical-hash", "wrong-canonical-frame"})
        with load_document(data, expected_sha256=fixture["sha256"]) as loaded:
            self.assertEqual(loaded.canonical.size, (fixture["width"], fixture["height"]))
            page.validate_against(loaded.metadata)
            page.validate_against(prepared)
            self.assertEqual([b.block_id for b in page.blocks], ["p0-b0001", "p0-b0004"])
            self.assertEqual([(r.region_id, r.reason) for r in page.unreadable_regions],
                             [("p0-b0002", "EMPTY_RECOGNITION"), ("p0-b0003", "EMPTY_RECOGNITION")])
            self.assertEqual(page.review_flags, ("OCR_UNREADABLE_REGIONS",))
            html = render_preview(loaded.canonical, page)
            for region_id in ("p0-b0001", "p0-b0002", "p0-b0003", "p0-b0004"):
                self.assertIn(region_id, html)
            missing = match_evidence(page, EvidenceRequest(**cases["required-total-missing"]["evidence_request"]), prepared=prepared)
            self.assertEqual(missing.status, "value_unavailable")
            metadata = missing.to_field_metadata()
            self.assertIsNone(metadata["raw_value"])
            self.assertEqual(metadata["source_regions"], [])
            self.assertEqual(set(metadata["review_flags"]),
                             {"SOURCE_VALUE_UNAVAILABLE", "OCR_UNREADABLE_REGIONS", "SOURCE_OCR_INCOMPLETE"})
            dimensions = cases["wrong-canonical-frame"]["declared_dimensions"]
            wrong = replace(prepared, canonical=replace(prepared.canonical, **dimensions))
            with self.assertRaises(ValueError):
                page.validate_against(wrong)
        with self.assertRaises(PreprocessError) as caught:
            load_document(data, expected_sha256=cases["wrong-canonical-hash"]["declared_sha256"])
        self.assertEqual(caught.exception.code, "INPUT_INVALID")

    def test_consumer_assets_bind_native_blocks_to_encoded_canonical_bytes(self):
        root = Path(__file__).resolve().parents[3]
        assets = json.loads((root / "tests/fixtures/ocr-d1-canonical-assets.json").read_text(encoding="utf-8"))
        self.assertEqual(assets["artifact_version"], "vietdoc.ocr-consumer-assets.v1")
        self.assertEqual(assets["provider_sha"], "7d96e93bf8315beb6fa33807231316e957671249")
        for reference in (assets["ocr_bundle"], assets["input_manifest"]):
            # Text snapshots pin LF Git blobs (.gitattributes), not checkout EOL bytes.
            blob = (root / reference["path"]).read_text(encoding="utf-8").encode("utf-8")
            self.assertEqual(sha256(blob).hexdigest(), reference["git_blob_sha256"])
        bundle = json.loads((root / assets["ocr_bundle"]["path"]).read_text(encoding="utf-8"))
        manifest = json.loads((root / assets["input_manifest"]["path"]).read_text(encoding="utf-8"))
        self.assertEqual([s["sample_id"] for s in assets["samples"]], ["d12-receipt-03", "d12-invoice-04"])
        for supplied in assets["samples"]:
            sid = supplied["sample_id"]
            observed = next(s for s in bundle["samples"] if s["sample_id"] == sid)
            entry = next(s for s in manifest["samples"] if s["sample_id"] == sid)
            data = (root / entry["assets"]["png"]["path"]).read_bytes()
            canonical = (root / supplied["canonical_png"]).read_bytes()
            expected = observed["canonical"]
            with self.subTest(sample_id=sid):
                self.assertEqual(sha256(data).hexdigest(), observed["input_sha256"])
                self.assertEqual(sha256(data).hexdigest(), entry["assets"]["png"]["sha256"])
                self.assertEqual(sha256(canonical).hexdigest(), expected["sha256"])
                self.assertNotEqual(sha256(canonical).hexdigest(), observed["input_sha256"])
                self.assertEqual(len(canonical), expected["size_bytes"])
                with load_document(data, expected_sha256=observed["input_sha256"]) as loaded, Image.open(BytesIO(canonical)) as image:
                    self.assertEqual(image.size, (expected["width"], expected["height"]))
                    self.assertEqual(image.mode, "RGB")
                    self.assertEqual(sha256(image.tobytes()).hexdigest(), expected["rgb_pixel_sha256"])
                    self.assertEqual(image.tobytes(), loaded.canonical.tobytes())
                    page = OcrPage.from_dict(observed["ocr"])
                    page.validate_against(PreparedPage.from_dict(observed["prepared"]))
                    page.validate_against(loaded.metadata)
                    # Processed dimensions are a different frame, despite valid normalized quads.
                    with self.assertRaises(ValueError):
                        replace(page, width=loaded.processed.width, height=loaded.processed.height).validate_against(loaded.metadata)

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
