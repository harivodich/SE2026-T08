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


def pdf_bytes(pages=1, width=72, height=36, rotation=0, mark=False, text=False, security=None):
    """Controlled PDF geometry; optional 7pt digits are a synthetic render oracle."""
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b""]
    kids = []
    for _ in range(pages):
        page_id = len(objects) + 1
        kids.append(f"{page_id} 0 R")
        content_id = page_id + 1
        resources = "/Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >>" if text else ""
        page = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Rotate {rotation} /Resources << {resources} >> /Contents {content_id} 0 R >>"
        content = f"1 0 0 rg 0 0 {width / 2} {height / 2} re f".encode() if mark else b""
        if text:
            content += b"\n0 0 0 rg BT /F1 7 Tf 8 12 Td (80.000) Tj ET"
        objects.extend([page.encode(), f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream"])
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {pages} >>".encode()
    encryption = ""
    if security is not None:
        # Blank streams need no encrypted content bytes. Fixed synthetic R2 entries
        # exercise both password-error and empty-password security-handler paths.
        if mark or text:
            raise ValueError("Encrypted fixture supports blank content only")
        owner, user = security
        encryption = f" /Encrypt {len(objects) + 1} 0 R /ID [<00112233445566778899aabbccddeeff><00112233445566778899aabbccddeeff>]"
        objects.append(f"<< /Filter /Standard /V 1 /R 2 /Length 40 /O <{owner}> /U <{user}> /P -4 >>".encode())
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R{encryption} >>\nstartxref\n{xref}\n%%EOF\n".encode())
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

    def test_real_encrypted_pdfs_are_valid_but_rejected_by_bounded_loader(self):
        # PDF Standard security revision 2, fixed ID, owner password "owner".
        # Algorithms 2-4: https://github.com/py-pdf/pypdf/blob/main/pypdf/_encryption.py
        cases = (
            ("", "c92422687facee686e373f10b5c7d04738053152f7e2ee30e11c69ec442576ab",
             "adb43c8d5c0a904ecd6878928abf0a1ef65fa75e1632b2134005fa3b1d844c68"),
            ("reader", "93fe0d5254ab4c9644693f33c07cb54f587dce1e2682fe9ecea6107a1ef630dd",
             "957f0931bc330bb01345f392f2d0fa815eb4eeff85ca0de90cb5f460e26ee612"),
        )
        for password, owner, user in cases:
            with self.subTest(empty_password=not password):
                data = pdf_bytes(security=(owner, user))
                # Independent positive control: real parser, right password, real render.
                with pdfium.PdfDocument(data, password=password) as document:
                    self.assertEqual(len(document), 1)
                    self.assertEqual(pdfium.raw.FPDF_GetSecurityHandlerRevision(document), 2)
                    page = document[0]
                    try:
                        bitmap = page.render(scale=1)
                        try:
                            self.assertEqual((bitmap.width, bitmap.height), (72, 36))
                        finally:
                            bitmap.close()
                    finally:
                        page.close()
                if password:
                    with self.assertRaises(pdfium.PdfiumError) as caught:
                        pdfium.PdfDocument(data)
                    self.assertEqual(caught.exception.err_code, pdfium.raw.FPDF_ERR_PASSWORD)
                # Production disposable decoder, no PdfDocument/security API mocks.
                self.assert_error("PROFILE_EXCEEDED", data)

    def test_limits_reject_bad_configuration(self):
        for field, value in (("max_pixels", 0), ("max_file_bytes", True), ("pdf_dpi", -1), ("processed_long_edge", 1.5), ("timeout_seconds", 0), ("timeout_seconds", float("inf"))):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                replace(PreprocessLimits(), **{field: value})

    def test_d2_point_size_pdf_exceeds_current_profile_before_rasterization(self):
        # Data MediaBox is in points, not pixels. 200 DPI exceeds 20 MP.
        limits = PreprocessLimits()
        self.assertEqual(limits.pdf_dpi, 200)
        self.assertEqual(limits.max_pixels, 20_000_000)
        self.assertGreater((1500 * 200 / 72) * (2600 * 200 / 72), limits.max_pixels)
        self.assert_error("PROFILE_EXCEEDED", pdf_bytes(width=1500, height=2600), limits=limits)

    def test_pdf_profile_rejection_never_renders_and_lower_dpi_is_explicit(self):
        # Controlled MediaBox reproducer, not Data's missing representative PDF.
        data = pdf_bytes(width=1500, height=2600, text=True)
        with patch.object(pdfium.PdfPage, "render", side_effect=AssertionError("must reject before render")) as render:
            with self.assertRaises(PreprocessError) as caught:
                _load_pdf(data, PreprocessLimits())
            self.assertEqual(caught.exception.code, "PROFILE_EXCEEDED")
            render.assert_not_called()
        # An explicit diagnostic override does not change the default profile.
        with load_document(data, limits=PreprocessLimits(pdf_dpi=72)) as loaded:
            self.assertEqual(loaded.canonical.size, (1500, 2600))
            self.assertEqual(loaded.processed.size, (1154, 2000))
        self.assertEqual(PreprocessLimits().pdf_dpi, 200)

    def test_rotated_pdf_small_text_matches_source_character_geometry(self):
        from vietdoc.pipeline.geometry import processed_quad
        from vietdoc.pipeline.ocr.paddle_adapter import _to_page

        # PDF character boxes precede raster/OCR; expected rotation is calculated
        # here without calling the pipeline's projection/ordering implementation.
        for rotation in (0, 90, 180, 270):
            data = pdf_bytes(rotation=rotation, text=True)
            with self.subTest(rotation=rotation), pdfium.PdfDocument(data) as document:
                page = document[0]
                try:
                    self.assertEqual(page.get_mediabox(), (0, 0, 72, 36))
                    self.assertEqual(page.get_rotation(), rotation)
                    textpage = page.get_textpage()
                    try:
                        self.assertEqual(textpage.get_text_range(), "80.000")
                        boxes = [textpage.get_charbox(i) for i in range(6)]
                    finally:
                        textpage.close()
                finally:
                    page.close()
                left, bottom = min(b[0] for b in boxes), min(b[1] for b in boxes)
                right, top = max(b[2] for b in boxes), max(b[3] for b in boxes)
                corners = ((left, bottom), (right, bottom), (right, top), (left, top))
                transforms = {
                    0: lambda x, y: (x / 72, 1 - y / 36),
                    90: lambda x, y: (y / 36, x / 72),
                    180: lambda x, y: (1 - x / 72, y / 36),
                    270: lambda x, y: (1 - y / 36, 1 - x / 72),
                }
                normalized = [transforms[rotation](x, y) for x, y in corners]
                expected = (min(p[0] for p in normalized), min(p[1] for p in normalized),
                            max(p[0] for p in normalized), max(p[1] for p in normalized))
                with load_document(data, limits=PreprocessLimits(processed_long_edge=73)) as loaded:
                    self.assertEqual(loaded.canonical.size, (100, 200) if rotation % 180 else (200, 100))
                    self.assertEqual(loaded.processed.size, (36, 73) if rotation % 180 else (73, 36))
                    self.assertEqual(loaded.metadata.page, 0)
                    left, top, right, bottom = expected
                    oracle = ((left, top), (right, top), (right, bottom), (left, bottom))
                    pw, ph = loaded.processed.size
                    detected = [[x * pw, y * ph] for x, y in oracle]
                    ocr = _to_page({"rec_texts": ["80.000"], "rec_scores": [.91],
                                    "rec_polys": [detected]}, loaded.metadata)
                    ocr.validate_against(loaded.metadata)
                    block = ocr.blocks[0]
                    self.assertEqual((block.block_id, block.text, block.score), ("p0-b0001", "80.000", .91))
                    for measured_point, oracle_point in zip(block.quad, oracle):
                        for measured, reference in zip(measured_point, oracle_point):
                            self.assertAlmostEqual(measured, reference, places=14)
                    for actual_point, detected_point in zip(processed_quad(block.quad, loaded.metadata), detected):
                        for measured, reference in zip(actual_point, detected_point):
                            self.assertAlmostEqual(measured, reference, delta=1e-7)
                    with loaded.canonical.convert("L") as gray:
                        with gray.point(lambda value: 255 if value < 128 else 0) as ink:
                            actual = ink.getbbox()
                    self.assertIsNotNone(actual)
                    width, height = loaded.canonical.size
                    for measured, reference in zip(actual, (expected[0] * width, expected[1] * height,
                                                            expected[2] * width, expected[3] * height)):
                        self.assertAlmostEqual(measured, reference, delta=1.5)


if __name__ == "__main__":
    unittest.main()
