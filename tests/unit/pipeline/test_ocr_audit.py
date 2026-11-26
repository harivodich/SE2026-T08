"""Audit correlation/accounting against real handoff/bridge, fictional OCR only."""
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from PIL import Image, PngImagePlugin

from vietdoc.contracts.ocr import OcrPage
from vietdoc.data.manifest import encoded, read_json, sha
from vietdoc.ml.ocr_handoff import export_handoff
from vietdoc.pipeline.ocr import audit as module
from vietdoc.pipeline.ocr import OcrError
from vietdoc.pipeline.ocr.handoff import review_manifest
from vietdoc.pipeline.ocr.triage import build_ledger
from vietdoc.pipeline.ocr import triage as triage_module

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


class NativeAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        cls.base = Path(temporary.name)
        cls.source = cls.base / "data"
        cls.source.mkdir()
        samples = []
        for i in range(6):
            sid = f"sample-{i}"
            path = cls.source / (sid + ".png")
            with Image.new("RGB", (100, 100), (255, 255, 255 - i)) as image:
                image.save(path)
            samples.append(dict(sample_id=sid, document_type="receipt" if i % 2 == 0 else "invoice",
                base_id=f"base-{i}", family_id="family", split="train" if i < 3 else "dev", row_count=i,
                augmentation=dict(name="fictional"), assets=dict(png=dict(path=path.name, sha256=sha(path)))))
        cls.manifest = cls.source / "manifest.json"
        cls.manifest.write_bytes(encoded(dict(version="fictional", samples=samples)))
        cls.pages = [c["expected"] for c in read_json(FIXTURES / "ocr-artifact-v2.json")["cases"]]
        # partial, unreadable, two blank pages, typed OCR failure, missing input.
        cls.pages.append(deepcopy(cls.pages[-1]))
        calls = iter(cls.pages + [None])
        engine = Mock(load_seconds=0.1, last_inference_seconds=0.02)

        def recognize(*args, **kwargs):
            value = next(calls)
            if value is None: raise OcrError("MODEL_OOM", "fictional typed error")
            return OcrPage.from_dict(value)

        engine.recognize.side_effect = recognize
        cls.native = cls.base / "native"
        missing = cls.source / "sample-5.png"
        withheld = missing.read_bytes()
        missing.rename(cls.source / "withheld.png")
        cls.report = review_manifest(cls.source, cls.manifest, cls.native, engine)
        missing.write_bytes(withheld)
        release = cls.base / "release"
        release.mkdir()
        model = release / "fictional.bin"
        model.write_bytes(b"fictional fixture only")
        engine_manifest = release / "manifest.json"
        engine_manifest.write_bytes(encoded(dict(manifest_version=1, pipeline_manifest_id="fixture.v1",
            files=[dict(path=model.name, sha256=sha(model), size_bytes=model.stat().st_size)])))
        cls.cache = cls.base / "cache"
        export_handoff(cls.native, engine_manifest, cls.cache)
        cls.gold = [dict(sample_id=s["sample_id"], document_type=s["document_type"], gold={}, labels={},
            transcript="C\u00f3 ch\u1eef 80.000", transcript_scope="full_page") for s in samples]

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.case = Path(temporary.name)
        self.output = self.case / "output"
        self.index = self.cache / "index.json"

    def run_audit(self, **options):
        params = dict(data_root=self.source, manifest=self.manifest, manifest_sha256=sha(self.manifest),
            handoff_root=self.native, report_sha256=sha(self.native / "report.json"),
            indices=[(self.index, sha(self.index))], output_dir=self.output)
        params.update(options)
        # Isolate Data renderer validation in AI fixture env. Actual Data boundary
        # is exercised on the received 160-file population, never claimed here.
        with patch.object(module, "load_bundle", return_value=(read_json(self.manifest), self.gold, [],
                                                               {"status": "fixture-only"})):
            return module.audit(**params)

    def test_failed_not_run_unreadable_and_blank_keep_all_denominators(self):
        result = self.run_audit()
        self.assertEqual(result["counts"], dict(requested=6, native_attempted=5, ok=4, failed=1, not_run=1))
        self.assertEqual(result["recognition"], dict(partial=1, unreadable=1, complete=2, unavailable=2))
        self.assertEqual(result["no_detections"], 2)
        self.assertEqual(len(result["samples"]), 6)
        for rows in result["slices"].values():
            self.assertEqual(sum(r["samples"] for r in rows.values()), 6)
            self.assertEqual(sum(r["ocr"]["cer"]["support"] for r in rows.values()), 6)
        counts = [r["ocr"]["counts"] for r in result["samples"]]
        self.assertEqual(sum(c.get("missing_or_failed_ocr", 0) for c in counts), 3)
        self.assertEqual(result["samples"][0]["ocr"]["cer"]["numerator"], 0)
        self.assertEqual(read_json(self.output / "report.json"), result)

    def test_tampered_canonical_is_not_confused_with_processed_frame(self):
        copied = self.case / "native"
        shutil.copytree(self.native, copied)
        with Image.new("RGB", (100, 100), "black") as image:
            image.save(copied / "sample-0/canonical.png")
        with self.assertRaisesRegex(ValueError, "CANONICAL_PIN_MISMATCH"):
            self.run_audit(handoff_root=copied)
        self.assertFalse(self.output.exists())

    def test_final_and_dropped_population_are_rejected_before_scoring(self):
        manifest = read_json(self.manifest)
        manifest["samples"][0]["split"] = "final"
        path = self.case / "manifest.json"
        path.write_bytes(encoded(manifest))
        with self.assertRaisesRegex(ValueError, "NON_PILOT_SPLIT"):
            self.run_audit(data_root=self.case, manifest=path, manifest_sha256=sha(path))
        native = self.case / "native"
        native.mkdir()
        report = deepcopy(self.report)
        report["samples"].pop()
        report_path = native / "report.json"
        report_path.write_bytes(encoded(report))
        with self.assertRaisesRegex(ValueError, "POPULATION_MISMATCH"):
            self.run_audit(handoff_root=native, report_sha256=sha(report_path))
        self.assertFalse(self.output.exists())

    def test_cache_ocr_byte_tampering_rejects_before_output(self):
        copied = self.case / "cache"
        shutil.copytree(self.cache, copied)
        path = copied / "sample-0/ocr.json"
        path.write_bytes(path.read_bytes() + b" ")
        index = copied / "index.json"
        with self.assertRaisesRegex(ValueError, "PIN_MISMATCH"):
            self.run_audit(indices=[(index, sha(index))])
        self.assertFalse(self.output.exists())

    def test_rebound_invalid_quad_cannot_bypass_ocr_contract(self):
        copied = self.case / "cache"
        shutil.copytree(self.cache, copied)
        path = copied / "sample-0/ocr.json"
        page = read_json(path)
        page["blocks"][0]["quad"] = [[0, 0]] * 4
        path.write_bytes(encoded(page))
        index_path = copied / "index.json"
        index = read_json(index_path)
        index["samples"]["sample-0"]["hashes"]["ocr_sha256"] = sha(path)
        index_path.write_bytes(encoded(index))
        with self.assertRaisesRegex(ValueError, "nondegenerate"):
            self.run_audit(indices=[(index_path, sha(index_path))])
        self.assertFalse(self.output.exists())

    def test_pin_mismatch_rejects_before_output(self):
        for name in ("manifest_sha256", "report_sha256"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "PIN_MISMATCH"):
                self.run_audit(**{name: "0" * 64})
            self.assertFalse(self.output.exists())

    def test_missing_or_duplicate_cache_ids_reject_before_output(self):
        original = read_json(self.index)
        missing = deepcopy(original)
        missing["samples"].pop("sample-0")
        path = self.case / "index.json"
        path.write_bytes(encoded(missing))
        with self.assertRaisesRegex(ValueError, "CACHE_ACCOUNTING_MISMATCH"):
            self.run_audit(indices=[(path, sha(path))])
        with self.assertRaisesRegex(ValueError, "CACHE_ID_MISMATCH"):
            self.run_audit(indices=[(self.index, sha(self.index))] * 2)
        self.assertFalse(self.output.exists())

    def test_changed_cache_profile_or_path_cannot_rebind_native(self):
        for case in ("profile", "path"):
            copied = self.case / case
            shutil.copytree(self.cache, copied)
            index = read_json(self.index)
            if case == "profile": index["profile"]["profile"]["processed_long_edge"] += 1
            else: index["samples"]["sample-0"]["paths"]["ocr"] = "../private.json"
            path = copied / "index.json"
            path.write_bytes(encoded(index))
            with self.subTest(case=case), self.assertRaisesRegex(ValueError,
                    "PROFILE_PIN_MISMATCH" if case == "profile" else "CACHE_PATH_MISMATCH"):
                self.run_audit(indices=[(path, sha(path))])
            self.assertFalse(self.output.exists())

    def test_existing_output_preserves_user_content(self):
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_bytes(b"user content")
        with self.assertRaisesRegex(ValueError, "OUTPUT_EXISTS"):
            self.run_audit()
        self.assertEqual(sentinel.read_bytes(), b"user content")

    def test_rebound_cache_canonical_metadata_must_match_verified_image(self):
        copied = self.case / "cache"
        shutil.copytree(self.cache, copied)
        path = copied / "index.json"
        mutations = dict(width=999, height=999, size_bytes=999, sha256="0" * 64,
                         rgb_pixel_sha256="0" * 64, source_hash_recorded=False)
        for key, value in mutations.items():
            index = read_json(self.index)
            index["samples"]["sample-0"]["canonical"][key] = value
            path.write_bytes(encoded(index))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "CACHE_CANONICAL_MISMATCH"):
                self.run_audit(indices=[(path, sha(path))])
            self.assertFalse(self.output.exists())

    def test_rebound_cache_counts_reject_false_accounting(self):
        path = self.case / "index.json"
        original = read_json(self.index)
        for key, value in [(k, 999) for k in original["counts"]] + [("failed", True)]:
            index = deepcopy(original)
            index["counts"][key] = value
            path.write_bytes(encoded(index))
            with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, "CACHE_ACCOUNTING_MISMATCH"):
                self.run_audit(indices=[(path, sha(path))])
            self.assertFalse(self.output.exists())

    def test_rebound_exclusions_must_preserve_native_identity_and_failure(self):
        original = read_json(self.index)
        path = self.case / "index.json"
        for key, value in dict(sample_id="unknown", document_type="invoice", status="ok",
                               stage="wrong", reason="NOT_SELECTED", error_code=None).items():
            index = deepcopy(original)
            index["excluded"][0][key] = value
            path.write_bytes(encoded(index))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "CACHE_EXCLUSIONS_MISMATCH"):
                self.run_audit(indices=[(path, sha(path))])
            self.assertFalse(self.output.exists())
        index = deepcopy(original)
        index["excluded"][1] = deepcopy(index["excluded"][0])
        path.write_bytes(encoded(index))
        with self.assertRaisesRegex(ValueError, "CACHE_EXCLUSIONS_MISMATCH"):
            self.run_audit(indices=[(path, sha(path))])

    def test_partitioned_indices_account_for_unselected_and_failed_samples(self):
        copied = self.case / "cache"
        shutil.copytree(self.cache, copied)
        original = read_json(self.index)
        indices = []
        for i, selected in enumerate(({"sample-0", "sample-1"}, {"sample-2", "sample-3"})):
            index = deepcopy(original)
            index["samples"] = {sid: e for sid, e in original["samples"].items() if sid in selected}
            for run in self.report["samples"]:
                if run["status"] == "ok" and run["sample_id"] not in selected:
                    index["excluded"].append(dict(sample_id=run["sample_id"], document_type=run["document_type"],
                        status="ok", stage=run.get("stage", "export"), reason="NOT_SELECTED", error_code=None))
            index["counts"].update(exported=2, excluded=4)
            path = copied / f"index-{i}.json"
            path.write_bytes(encoded(index))
            indices.append((path, sha(path)))
        with self.assertRaisesRegex(ValueError, "CACHE_COVERAGE_MISMATCH"):
            self.run_audit(indices=indices[:1])
        self.assertFalse(self.output.exists())
        result = self.run_audit(indices=indices)
        self.assertEqual(result["counts"], dict(requested=6, native_attempted=5, ok=4, failed=1, not_run=1))

    def test_cli_rejects_non_object_report_without_traceback_or_output(self):
        native = self.case / "native"
        native.mkdir()
        path = native / "report.json"
        for value in ([], None, "report", 7, True):
            path.write_bytes(encoded(value))
            errors = StringIO()
            args = ["--data-root", str(self.source), "--manifest", str(self.manifest),
                "--manifest-sha256", sha(self.manifest), "--handoff-root", str(native),
                "--report-sha256", sha(path), "--index", str(self.index), sha(self.index),
                "--output-dir", str(self.output)]
            with self.subTest(value=value), patch("sys.stderr", errors), redirect_stdout(StringIO()):
                self.assertEqual(module.main(args), 2)
            self.assertEqual(errors.getvalue().strip(), "AUDIT_INPUT_INVALID_OR_IO_ERROR")
            self.assertFalse(self.output.exists())

    def test_cli_rejects_bad_pin_without_exposing_input_paths(self):
        errors = StringIO()
        args = ["--data-root", str(self.source), "--manifest", str(self.manifest),
            "--manifest-sha256", "0" * 64, "--handoff-root", str(self.native),
            "--report-sha256", sha(self.native / "report.json"), "--index", str(self.index), sha(self.index),
            "--output-dir", str(self.output)]
        with patch("sys.stderr", errors), redirect_stdout(StringIO()):
            status = module.main(args)
        self.assertEqual(status, 2)
        self.assertEqual(errors.getvalue().strip(), "AUDIT_INPUT_INVALID_OR_IO_ERROR")
        self.assertFalse(self.output.exists())


class TriageLedgerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        cls.base = Path(temporary.name)
        cls.source = cls.base / "data"
        cls.source.mkdir()
        samples = []
        for i in range(8):
            sid = f"case-{i}"
            png = cls.source / (sid + ".png")
            with Image.new("RGB", (100, 100), "white") as image:
                image.save(png)
            transcript = cls.source / (sid + ".txt")
            transcript.write_text("Independent annotation", encoding="utf-8")
            regions = cls.source / (sid + ".regions.json")
            regions.write_bytes(encoded(dict(convention="fictional", regions=[])))
            assets = {key: dict(path=path.name, sha256=sha(path)) for key, path in
                      (("png", png), ("txt", transcript), ("regions.json", regions))}
            samples.append(dict(sample_id=sid, document_type="receipt" if i < 4 else "invoice",
                base_id=sid, family_id="fictional", split="dev", row_count=(0, 12, 30, 30)[i % 4],
                augmentation=dict(name=("clean", "mild", "crop", "unreadable")[i % 4]), assets=assets))
        cls.manifest = cls.source / "manifest.json"
        cls.manifest.write_bytes(encoded(dict(version="fictional", samples=samples)))
        page = OcrPage.from_dict(read_json(FIXTURES / "ocr-artifact-v2.json")["cases"][0]["expected"])
        engine = Mock(load_seconds=0.1, last_inference_seconds=0.02)
        engine.recognize.return_value = page
        cls.native = cls.base / "native"
        review_manifest(cls.source, cls.manifest, cls.native, engine)
        release = cls.base / "release"
        release.mkdir()
        model = release / "fictional.bin"
        model.write_bytes(b"fixture only")
        engine_manifest = release / "manifest.json"
        engine_manifest.write_bytes(encoded(dict(manifest_version=1, pipeline_manifest_id="fixture.v1",
            files=[dict(path=model.name, sha256=sha(model), size_bytes=model.stat().st_size)])))
        cls.cache = cls.base / "cache"
        export_handoff(cls.native, engine_manifest, cls.cache)
        cls.gold = [dict(sample_id=s["sample_id"], document_type=s["document_type"], gold={}, labels={},
            transcript="Independent annotation", transcript_scope="full_page") for s in samples]

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.case = Path(temporary.name)
        self.output = self.case / "output"

    def run_ledger(self, **overrides):
        index = self.cache / "index.json"
        options = dict(sample_ids=[f"case-{i}" for i in range(8)], data_root=self.source,
            manifest=self.manifest, manifest_sha256=sha(self.manifest), handoff_root=self.native,
            report_sha256=sha(self.native / "report.json"), indices=[(index, sha(index))], output_dir=self.output)
        options.update(overrides)
        with patch.object(module, "load_bundle", return_value=(read_json(self.manifest), self.gold, [],
                                                               {"status": "fixture-only"})):
            return build_ledger(**options)

    def test_keeps_expected_and_observed_separate_without_causal_or_pairing_claim(self):
        result = self.run_ledger()
        self.assertEqual(len(result["cases"]), 8)
        for case in result["cases"]:
            original = read_json(self.native / case["sample_id"] / "ocr.json")
            self.assertEqual(case["observed"], original)
            self.assertEqual(case["expected"]["transcript"], "Independent annotation")
            self.assertNotEqual(case["observed"]["blocks"][0]["text"], case["expected"]["transcript"])
            self.assertEqual(case["diagnosis"]["stage"], "unknown")
            self.assertEqual(case["diagnosis"]["certainty"], "unclassified")
            verification = case["overlay_verification"]
            self.assertEqual(verification["sha256"], sha(self.native / case["evidence"]["overlay"]))
            self.assertEqual(verification["method"], "draw_overlay-rgb-exact.v1")
        self.assertEqual(read_json(self.output / "triage.json"), result)
        self.assertEqual(read_json(self.output / "report.json")["counts"]["requested"], 8)

    def test_duplicate_train_unknown_and_missing_coverage_reject_before_output(self):
        for ids in (["case-0"] * 8, [f"case-{i}" for i in range(7)] + ["unknown"]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.run_ledger(sample_ids=ids)
            self.assertFalse(self.output.exists())
        for mutation in ("train", "coverage"):
            manifest = read_json(self.manifest)
            if mutation == "train": manifest["samples"][0]["split"] = "train"
            else:
                for s in manifest["samples"]: s["row_count"] = 1
            path = self.case / "manifest.json"
            path.write_bytes(encoded(manifest))
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "TRIAGE_REQUIRES_EXPOSED_DEV|TRIAGE_COVERAGE_MISSING"):
                self.run_ledger(manifest=path, manifest_sha256=sha(path))
            self.assertFalse(self.output.exists())

    def test_corrupt_cache_and_annotation_leave_no_packet(self):
        native = self.case / "native"
        shutil.copytree(self.native, native)
        (native / "case-0/ocr.json").write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "CACHE_NATIVE_MISMATCH"):
            self.run_ledger(handoff_root=native)
        self.assertFalse(self.output.exists())
        data = self.case / "data"
        shutil.copytree(self.source, data)
        (data / "case-0.txt").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "ANNOTATION_PIN_MISMATCH"):
            self.run_ledger(data_root=data, manifest=data / "manifest.json")
        self.assertFalse(self.output.exists())
        self.assertEqual(sorted(p.name for p in self.case.iterdir()), ["data", "native"])

    def test_existing_packet_is_preserved(self):
        self.output.mkdir()
        path = self.output / "keep.txt"
        path.write_bytes(b"user")
        with self.assertRaisesRegex(ValueError, "OUTPUT_EXISTS"):
            self.run_ledger()
        self.assertEqual(path.read_bytes(), b"user")

    def test_missing_corrupt_wrong_pixels_or_frame_overlay_never_publishes(self):
        for mutation in ("missing", "corrupt", "wrong_pixels", "wrong_size", "wrong_mode"):
            native = self.case / mutation
            shutil.copytree(self.native, native)
            overlay = native / "case-0/overlay.png"
            if mutation == "missing":
                overlay.rename(native / "case-0/withheld.png")
            elif mutation == "corrupt":
                overlay.write_bytes(b"not a PNG")
            else:
                with Image.new("RGBA" if mutation == "wrong_mode" else "RGB",
                               (90, 100) if mutation == "wrong_size" else (100, 100), "black") as image:
                    image.save(overlay)
            error = {"missing": "missing asset", "wrong_pixels": "OVERLAY_CONTENT_MISMATCH",
                     "wrong_size": "OVERLAY_FRAME_MISMATCH", "wrong_mode": "OVERLAY_FRAME_MISMATCH"}
            with self.subTest(mutation=mutation):
                if mutation == "corrupt":
                    with self.assertRaises(Image.UnidentifiedImageError):
                        self.run_ledger(handoff_root=native)
                else:
                    with self.assertRaisesRegex(ValueError, error[mutation]):
                        self.run_ledger(handoff_root=native)
                self.assertFalse(self.output.exists())
                self.assertFalse(any(p.name.startswith("tmp") for p in self.case.iterdir()))

    def test_equivalent_overlay_png_encoding_is_accepted_with_actual_hash(self):
        native = self.case / "native"
        shutil.copytree(self.native, native)
        path = native / "case-0/overlay.png"
        before = sha(path)
        with Image.open(path) as image:
            copy = image.copy()
        with copy:
            metadata = PngImagePlugin.PngInfo()
            metadata.add_text("note", "same RGB pixels, independent encoder")
            copy.save(path, pnginfo=metadata, compress_level=0)
        self.assertNotEqual(sha(path), before)
        result = self.run_ledger(handoff_root=native)
        self.assertEqual(result["cases"][0]["overlay_verification"]["sha256"], sha(path))

    def test_overlay_changed_after_snapshot_is_rejected_before_publish(self):
        native = self.case / "native"
        shutil.copytree(self.native, native)
        path = native / "case-0/overlay.png"
        render = triage_module.draw_overlay

        def render_then_mutate(*args):
            result = render(*args)
            path.write_bytes(b"changed after snapshot")
            return result

        with patch.object(triage_module, "draw_overlay", side_effect=render_then_mutate):
            with self.assertRaisesRegex(ValueError, "SOURCE_CHANGED_DURING_TRIAGE"):
                self.run_ledger(handoff_root=native)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
