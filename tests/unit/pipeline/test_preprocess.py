"""Real image/PDF decode checks; fictional inputs are generated in memory."""

from dataclasses import replace
from hashlib import sha256
from io import BytesIO
import subprocess
import time
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
import pypdfium2 as pdfium

from vietdoc.pipeline.preprocess import (
    PreprocessError, PreprocessLimits, _load_pdf, load_document,
)


def image_bytes(mode="RGB", size=(60, 40), color="white", fmt="PNG", orientation=None):
    with Image.new(mode, size, color) as image:
        stream = BytesIO()
        options = {}
        if orientation is not None:
            exif = Image.Exif()
            exif[274] = orientation
            options["exif"] = exif
        image.save(stream, format=fmt, **options)
        return stream.getvalue()


def corner_image(orientation):
    with Image.new("RGB", (60, 40), "white") as image:
        draw = ImageDraw.Draw(image)
        for box, color in (
            ((0, 0, 9, 9), "red"), ((50, 0, 59, 9), "green"),
            ((0, 30, 9, 39), "blue"), ((50, 30, 59, 39), "yellow"),
        ):
            draw.rectangle(box, fill=color)
        exif = Image.Exif()
        exif[274] = orientation
        stream = BytesIO()
        image.save(stream, format="PNG", exif=exif)
        return stream.getvalue()


def pdf_bytes(pages=1, width=72, height=36, rotation=0, mark=False):
    """Tiny PDF with a known red bottom-left region, no text/gold predictions."""
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b""]
    kids = []
    for _ in range(pages):
        page_id = len(objects) + 1
        kids.append(f"{page_id} 0 R")
        content_id = page_id + 1
        page = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Rotate {rotation} /Resources << >> /Contents {content_id} 0 R >>"
        content = f"1 0 0 rg 0 0 {width / 2} {height / 2} re f".encode() if mark else b""
        objects.extend([page.encode(), f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream"])
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {pages} >>".encode()
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(data)


class PreprocessTest(unittest.TestCase):
    def assert_error(self, code, data, **kwargs):
        with self.assertRaises(PreprocessError) as caught:
            load_document(data, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return str(caught.exception)

    def test_png_rgb_pixels_dimensions_and_original_hash(self):
        data = image_bytes(color=(10, 20, 30))
        original = bytes(data)
        with load_document(data, expected_sha256=sha256(data).hexdigest()) as loaded:
            self.assertEqual(loaded.canonical.mode, "RGB")
            self.assertEqual(loaded.canonical.getpixel((10, 10)), (10, 20, 30))
            self.assertEqual(loaded.canonical.size, (60, 40))
            self.assertEqual(loaded.metadata.canonical.width, 60)
            self.assertEqual(loaded.input_sha256, sha256(data).hexdigest())
            self.assertEqual(loaded.processed.tobytes(), loaded.canonical.tobytes())
            self.assertEqual(loaded.metadata.inverse_transform, ((1, 0, 0), (0, 1, 0), (0, 0, 1)))
        self.assertEqual(data, original)

    def test_jpeg_really_decodes(self):
        with load_document(image_bytes(color=(80, 120, 160), fmt="JPEG")) as loaded:
            self.assertEqual(loaded.canonical.size, (60, 40))
            self.assertTrue(all(abs(actual - expected) <= 3 for actual, expected in zip(loaded.canonical.getpixel((20, 20)), (80, 120, 160))))

    def test_all_exif_orientations_move_known_regions_to_canonical_positions(self):
        colors = {"R": (255, 0, 0), "G": (0, 128, 0), "B": (0, 0, 255), "Y": (255, 255, 0)}
        expected = {1: "RGBY", 2: "GRYB", 3: "YBGR", 4: "BYRG", 5: "RBGY", 6: "BRYG", 7: "YGBR", 8: "GYRB"}
        for orientation, corners in expected.items():
            with self.subTest(orientation=orientation), load_document(corner_image(orientation)) as loaded:
                width, height = loaded.canonical.size
                self.assertEqual((width, height), (40, 60) if orientation >= 5 else (60, 40))
                positions = ((3, 3), (width - 4, 3), (3, height - 4), (width - 4, height - 4))
                for position, name in zip(positions, corners):
                    self.assertEqual(loaded.canonical.getpixel(position), colors[name])
                self.assertIsNone(loaded.canonical.getexif().get(274))

    def test_resize_preserves_region_and_inverse_uses_actual_rounded_dimensions(self):
        limits = PreprocessLimits(processed_long_edge=30)
        with load_document(corner_image(6), limits=limits) as loaded:
            self.assertEqual(loaded.canonical.size, (40, 60))
            self.assertEqual(loaded.processed.size, (20, 30))
            self.assertEqual(loaded.metadata.inverse_transform, ((2, 0, 0), (0, 2, 0), (0, 0, 1)))
            red, green, blue = loaded.processed.getpixel((2, 2))
            # LANCZOS blends nearby white pixels; the known blue region stays here.
            self.assertLess(max(red, green), 5)
            self.assertGreater(blue, 250)
        with load_document(image_bytes(size=(101, 67)), limits=limits) as loaded:
            self.assertEqual(loaded.processed.size, (30, 20))
            matrix = loaded.metadata.inverse_transform
            self.assertAlmostEqual(30 * matrix[0][0], 101)
            self.assertAlmostEqual(20 * matrix[1][1], 67)

    def test_gray_and_transparent_inputs_become_rgb_on_white(self):
        with load_document(image_bytes(mode="L", color=128)) as loaded:
            self.assertEqual(loaded.canonical.getpixel((0, 0)), (128, 128, 128))
        with load_document(image_bytes(mode="RGBA", color=(255, 0, 0, 0))) as loaded:
            self.assertEqual(loaded.canonical.getpixel((0, 0)), (255, 255, 255))

    def test_blank_image_is_valid_pixels_not_fake_ocr(self):
        with load_document(image_bytes()) as loaded:
            self.assertEqual(loaded.canonical.getextrema(), ((255, 255),) * 3)
            self.assertFalse(hasattr(loaded, "blocks"))

    def test_single_page_pdf_renders_and_applies_page_rotation(self):
        limits = PreprocessLimits(pdf_dpi=144)
        with load_document(pdf_bytes(rotation=90, mark=True), limits=limits) as loaded:
            self.assertEqual(loaded.canonical.size, (72, 144))
            self.assertEqual(loaded.canonical.getpixel((3, 3)), (255, 0, 0))
            self.assertEqual(loaded.canonical.getpixel((68, 140)), (255, 255, 255))
            self.assertEqual(loaded.metadata.page, 0)

    def test_blank_pdf_and_exact_pixel_limit(self):
        limits = PreprocessLimits(pdf_dpi=72, max_pixels=72 * 36)
        with load_document(pdf_bytes(), limits=limits) as loaded:
            self.assertEqual(loaded.canonical.size, (72, 36))
            self.assertEqual(loaded.canonical.getpixel((0, 0)), (255, 255, 255))

    def test_multipage_pdf_rejected_without_truncation(self):
        self.assert_error("PROFILE_EXCEEDED", pdf_bytes(pages=2))

    def test_empty_pdf_is_rejected_by_native_parser_as_invalid(self):
        self.assert_error("INPUT_INVALID", pdf_bytes(pages=0))

    def test_pdf_and_raster_pixel_caps(self):
        limits = PreprocessLimits(max_pixels=100)
        self.assert_error("PROFILE_EXCEEDED", image_bytes(), limits=limits)
        self.assert_error("PROFILE_EXCEEDED", pdf_bytes(width=1_000_000, height=1_000_000), limits=limits)

    def test_byte_cap_and_hash_checked_before_decode(self):
        data = image_bytes()
        self.assert_error("INPUT_TOO_LARGE", data, limits=PreprocessLimits(max_file_bytes=len(data) - 1))
        self.assert_error("INPUT_INVALID", data, expected_sha256="0" * 64)
        with load_document(data, limits=PreprocessLimits(max_file_bytes=len(data))) as loaded:
            self.assertEqual(loaded.canonical.size, (60, 40))

    def test_corrupt_or_unsupported_input_returns_safe_typed_error(self):
        for data in (b"private-document-text", b"%PDF-1.4\ncorrupt", image_bytes()[:40], image_bytes(fmt="BMP")):
            with self.subTest(signature=data[:8]):
                message = self.assert_error("INPUT_INVALID", data)
                self.assertNotIn("private-document-text", message)
        for data in (b"", "file.png", BytesIO(b"image")):
            with self.subTest(data=type(data).__name__):
                self.assert_error("INPUT_INVALID", data)

    def test_animated_png_and_sixteen_bit_png_rejected_explicitly(self):
        with Image.new("RGB", (10, 10), "white") as first, Image.new("RGB", (10, 10), "red") as second:
            stream = BytesIO()
            first.save(stream, format="PNG", save_all=True, append_images=[second])
            self.assert_error("PROFILE_EXCEEDED", stream.getvalue())
        self.assert_error("PROFILE_EXCEEDED", image_bytes(mode="I;16", color=65535))

    def test_timeout_kills_and_reaps_real_decoder_process(self):
        processes = []
        real_popen = subprocess.Popen

        def record(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            processes.append(process)
            return process

        started = time.monotonic()
        with patch("vietdoc.pipeline.preprocess.subprocess.Popen", side_effect=record):
            self.assert_error("COMPUTE_TIMEOUT", image_bytes(), limits=PreprocessLimits(timeout_seconds=0.001))
        self.assertLess(time.monotonic() - started, 5)
        self.assertTrue(processes)
        self.assertTrue(all(process.poll() is not None for process in processes))

    def test_remaining_job_budget_is_not_reset(self):
        for budget in (0, -1, False, "1000"):
            with self.subTest(budget=budget):
                self.assert_error("COMPUTE_TIMEOUT", image_bytes(), remaining_budget_ms=budget)
        self.assert_error("COMPUTE_TIMEOUT", image_bytes(), remaining_budget_ms=1)

    def test_pdf_password_error_mapping_and_empty_password_encryption_guard(self):
        # Native error mapping; these two injected cases are not encrypted-file E2E.
        with patch.object(pdfium, "PdfDocument", side_effect=pdfium.PdfiumError("private error", err_code=pdfium.raw.FPDF_ERR_PASSWORD)):
            with self.assertRaises(PreprocessError) as caught:
                _load_pdf(b"%PDF-", PreprocessLimits())
            self.assertEqual(caught.exception.code, "PROFILE_EXCEEDED")
            self.assertNotIn("private error", str(caught.exception))
        with pdfium.PdfDocument(pdf_bytes()) as document:
            with patch.object(pdfium, "PdfDocument", return_value=document), patch.object(pdfium.raw, "FPDF_GetSecurityHandlerRevision", return_value=2):
                with self.assertRaises(PreprocessError) as caught:
                    _load_pdf(b"%PDF-", PreprocessLimits())
                self.assertEqual(caught.exception.code, "PROFILE_EXCEEDED")

    def test_limits_reject_bad_configuration(self):
        for field, value in (("max_pixels", 0), ("max_file_bytes", True), ("pdf_dpi", -1), ("processed_long_edge", 1.5), ("timeout_seconds", 0), ("timeout_seconds", float("inf"))):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                replace(PreprocessLimits(), **{field: value})


if __name__ == "__main__":
    unittest.main()
