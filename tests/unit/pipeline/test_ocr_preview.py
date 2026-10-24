"""Self-contained preview must preserve canonical pixels and treat OCR as data."""

from base64 import b64decode
from html.parser import HTMLParser
from io import BytesIO
import json
import unittest

from PIL import Image

from vietdoc.contracts.ocr import OcrBlock, OcrPage
from vietdoc.pipeline.ocr.preview import render_preview


class PreviewParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.images, self.scripts, self.payload = [], [], ""
        self.in_payload = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "img":
            self.images.append(attrs)
        if tag == "script":
            self.scripts.append(attrs)
            self.in_payload = attrs.get("id") == "ocr-data"

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_payload = False

    def handle_data(self, data):
        if self.in_payload:
            self.payload += data


class OcrPreviewTest(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGB", (200, 100), (11, 22, 33))
        self.addCleanup(self.image.close)
        self.block = OcrBlock("p0-b0001", "Tổng tiền", ((.1,.2),(.4,.2),(.4,.4),(.1,.4)), .93, None)
        self.page = OcrPage(0, 200, 100, "fictional.v1", (self.block,))

    def test_embedded_pixels_and_ocr_are_exact_and_require_no_external_assets(self):
        parsed = PreviewParser(render_preview(self.image, self.page, transcript="Tổng tiền"))
        self.assertEqual(len(parsed.images), 1)
        source = parsed.images[0]["src"]
        self.assertTrue(source.startswith("data:image/png;base64,"))
        with Image.open(BytesIO(b64decode(source.split(",", 1)[1]))) as embedded:
            self.assertEqual(embedded.size, self.image.size)
            self.assertEqual(embedded.tobytes(), self.image.tobytes())
        self.assertEqual(json.loads(parsed.payload), {"ocr": self.page.to_dict(), "transcript": "Tổng tiền"})
        self.assertTrue(all("src" not in script for script in parsed.scripts))
        self.assertEqual(self.image.getpixel((0,0)), (11,22,33))

    def test_ocr_and_transcript_cannot_break_out_of_data_script(self):
        attack = '</script><img src=x onerror="alert(1)"> & Tổng tiền'
        block = OcrBlock("unsafe-id</script>", attack, self.block.quad, None, None)
        page = OcrPage(0, 200, 100, attack, (block,))
        html = render_preview(self.image, page, transcript=attack)
        parsed = PreviewParser(html)
        self.assertEqual(len(parsed.images), 1)
        self.assertEqual(len(parsed.scripts), 2)
        self.assertNotIn(attack, html)
        self.assertEqual(json.loads(parsed.payload)["ocr"], page.to_dict())
        self.assertEqual(json.loads(parsed.payload)["transcript"], attack)
        self.assertNotIn("innerHTML", html)

    def test_blank_and_missing_geometry_are_preserved_in_payload(self):
        for blocks in ((), (OcrBlock("b", "Có chữ", None, None, "NO_MAPPING"),)):
            page = OcrPage(0, 200, 100, "fictional.v1", blocks)
            data = json.loads(PreviewParser(render_preview(self.image, page)).payload)
            self.assertEqual(data["ocr"], page.to_dict())
            self.assertIsNone(data["transcript"])

    def test_wrong_image_dimensions_mode_or_transcript_type_are_rejected(self):
        for mode, size in (("RGB", (100, 200)), ("L", (200, 100))):
            with Image.new(mode, size) as image, self.assertRaises(ValueError):
                render_preview(image, self.page)
        with self.assertRaises(ValueError):
            render_preview(self.image, self.page, transcript=123)


if __name__ == "__main__":
    unittest.main()
