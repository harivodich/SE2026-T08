"""AI1 replay through actual Data renderer validation; no native inference/gold benchmark."""
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from vietdoc.data.generator import d22, integration
from vietdoc.data.manifest import encoded, read_json, sha
from vietdoc.pipeline.ocr import diagnose

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures"


class DiagnosticDataBoundaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="ai1-replay-data-")
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name)
        (cls.root / "specs/contracts").mkdir(parents=True)
        shutil.copyfile(ROOT / "specs/contracts/business.schema.json",
                        cls.root / "specs/contracts/business.schema.json")
        cls.d1 = cls.root / "d1"
        cls.d1.mkdir()
        manifest = read_json(FIXTURES / "d12/manifest.json")
        for entry in manifest["samples"]:
            for suffix, asset in entry["assets"].items():
                name = "d1/" + entry["sample_id"] + "." + suffix
                shutil.copyfile(ROOT / asset["path"], cls.root / name)
                asset["path"] = name
        (cls.d1 / "manifest.json").write_bytes(encoded(manifest))

        # Same bounded, real D2.2 fixture recipe as PilotRecordsTest. Keep the
        # actual format, lineage, assets, sidecars and separate dataset identity.
        cls.d22 = cls.root / "d22"
        cls.d22.mkdir()
        font = integration.resolve_font()
        config = dict(read_json(d22.DEFAULT_CONFIG), rows=[1], font_sha256=sha(font))
        config["augmentations"] = config["augmentations"][:1]
        planned = [r for r in d22.plan(config, 2202) if r["family_id"] in
                   {"receipt-f00", "receipt-f06", "invoice-f00", "invoice-f06", "receipt-f08"}]
        entries = []
        with patch.object(d22, "plan", return_value=planned):
            for entry, files in d22.generated(ROOT, config, 2202, font):
                entries.append(entry)
                for suffix, content in files.items():
                    (cls.d22 / entry["assets"][suffix]["path"]).write_bytes(content)
        (cls.d22 / "report.json").write_bytes(encoded(d22.report_for(entries, config)))
        manifest = dict(d22.provenance(ROOT, config, 2202, font), samples=entries,
                        report=dict(path="report.json", sha256=sha(cls.d22 / "report.json")))
        (cls.d22 / "manifest.json").write_bytes(encoded(manifest))

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ai1-replay-case-")
        self.addCleanup(temporary.cleanup)
        self.case = Path(temporary.name)

    def inputs(self, manifest, page):
        for sample in read_json(manifest)["samples"]:
            path = self.case / "inputs/native" / (sample["sample_id"] + "-measured-1/ocr.json")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(encoded(page))

    def replay(self, manifest, output):
        with redirect_stdout(StringIO()):
            diagnose.replay(self.root, manifest, sha(manifest), self.case / "inputs", output, ["png"])
        directory = output / "diagnostic-png"
        return read_json(directory / "predictions.json"), read_json(directory / "report.json")

    def test_d1_and_versioned_d22_public_cli_normal_and_optimized(self):
        blank = dict(page=0, width=100, height=100, ocr_version="fictional.replay.v1", blocks=[])
        for kind, folder in (("d1", self.d1), ("d22", self.d22)):
            manifest = folder / "manifest.json"
            source = read_json(manifest)
            self.inputs(manifest, blank)
            for optimized in (False, True):
                with self.subTest(kind=kind, optimized=optimized):
                    output = self.case / f"{kind}-{optimized}"
                    command = [sys.executable, *(["-O"] if optimized else []), "-m",
                        "vietdoc.pipeline.ocr.diagnose", "--data-root", str(self.root),
                        "--manifest", str(manifest), "--manifest-sha256", sha(manifest),
                        "--input-root", str(self.case / "inputs"), "--output-dir", str(output), "--groups", "png"]
                    run = subprocess.run(command, capture_output=True,
                                         env=dict(os.environ, PYTHONPATH=str(ROOT / "src")))
                    self.assertEqual(run.returncode, 0, run.stderr.decode("utf-8", errors="replace"))
                    predictions = read_json(output / "diagnostic-png/predictions.json")
                    report = read_json(output / "diagnostic-png/report.json")
                    expected = source.get("dataset_version", source["version"])
                    self.assertEqual(predictions["dataset_version"], expected)
                    self.assertEqual(predictions["dataset_manifest_sha256"], sha(manifest))
                    self.assertEqual(report["inputs"]["dataset_version"], expected)
                    self.assertEqual(report["inputs"]["manifest_format_version"], source["version"])
                    self.assertEqual(report["inputs"]["gold_validation"]["status"], "validated")
                    self.assertEqual(report["accounting"]["outcomes"], {"ok": len(source["samples"])})
                    self.assertTrue(all(r["ocr_text"] == "" and
                        r["ocr_diagnostics"]["artifact_version"] == 1 and
                        r["ocr_diagnostics"]["recognition_status"] == "complete" and
                        r["ocr_diagnostics"]["review_flags"] == [] for r in predictions["predictions"]))
                    if kind == "d22":
                        self.assertNotEqual(expected, source["version"])
                        self.assertEqual(len(source["samples"]), 10)

    def test_partial_unreadable_and_blank_remain_distinct_through_file_evaluator(self):
        manifest = self.d1 / "manifest.json"
        golden = read_json(FIXTURES / "ocr-artifact-v2.json")
        for case in golden["cases"]:
            with self.subTest(case=case["case_id"]):
                page = case["expected"]
                self.inputs(manifest, page)
                predictions, report = self.replay(manifest, self.case / case["case_id"])
                unreadable = page["recognition_status"] == "unreadable"
                self.assertEqual(report["accounting"]["outcomes"], {"failed" if unreadable else "ok": 2})
                counts = report["ocr"]["all"]["counts"]
                self.assertEqual(counts["eligible_samples"], 2)
                self.assertEqual(counts.get("missing_or_failed_ocr", 0), 2 if unreadable else 0)
                self.assertEqual(report["ocr"]["all"]["cer"]["support"], 2)
                for record in predictions["predictions"]:
                    self.assertEqual(record["ocr_text"], "\n".join(b["text"] for b in page["blocks"]))
                    self.assertIn("ocr_diagnostics", record)
                    self.assertEqual(record["ocr_diagnostics"], page)
                    self.assertEqual(report["source_ocr_states"][record["sample_id"]],
                                     {k: page[k] for k in ("artifact_version", "recognition_status", "review_flags")})
                    self.assertEqual(record["payload"], {})
                    if unreadable:
                        self.assertEqual(record["error"], "OCR_UNREADABLE_REGIONS")

    def test_versioned_d22_public_entrypoint(self):
        manifest = self.d22 / "manifest.json"
        self.inputs(manifest, dict(page=0, width=100, height=100,
                                   ocr_version="fictional.replay.v1", blocks=[]))
        output = self.case / "entrypoint"
        with redirect_stdout(StringIO()), patch("sys.stderr", StringIO()):
            status = diagnose.main(["--data-root", str(self.root), "--manifest", str(manifest),
                "--manifest-sha256", sha(manifest), "--input-root", str(self.case / "inputs"),
                "--output-dir", str(output), "--groups", "png"])
        self.assertEqual(status, 0, "Valid D2.2 identity must reach a successful file evaluator report")
        self.assertEqual(read_json(output / "diagnostic-png/report.json")["inputs"]["dataset_version"],
                         read_json(manifest)["dataset_version"])

    def test_unknown_version_rejected_before_output_at_real_boundary(self):
        manifest = self.d1 / "manifest.json"
        page = deepcopy(read_json(FIXTURES / "ocr-artifact-v2.json")["cases"][0]["expected"])
        page["artifact_version"] = 99
        self.inputs(manifest, page)
        output = self.case / "unsupported"
        with self.assertRaisesRegex(ValueError, "Only explicit OCR artifact v2"):
            self.replay(manifest, output)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
