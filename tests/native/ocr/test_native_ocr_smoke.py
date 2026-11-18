"""Opt-in native encoding/orientation/error smoke: 20 cases from one fictional page."""
from hashlib import sha256
import os
from pathlib import Path
import unittest
from PIL import Image
from vietdoc.pipeline.ocr import OCR_STAGE_VERSION, recognize_document
from vietdoc.pipeline.ocr.paddle_adapter import VietnameseOcrEngine, RUNTIME_VERSIONS, OcrError, draw_overlay


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
