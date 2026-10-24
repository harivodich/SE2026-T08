"""Pinned Paddle text detection + Vietnamese Tesseract recognition, CPU only.

Models are explicitly provisioned; load/inference never downloads weights. The
service owns model_root and lifecycle. Input is a LoadedPage, never a request URL.
"""

from hashlib import sha256
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
from threading import Lock
import time
from urllib.request import urlopen

import numpy as np
from PIL import Image, ImageDraw

from vietdoc.contracts.ocr import OcrBlock, OcrPage, PreparedPage
from vietdoc.pipeline.preprocess import LoadedPage


RUNTIME_VERSIONS = {
    "paddleocr": "3.3.2", "paddlex": "3.3.13", "paddlepaddle": "3.3.1",
    "numpy": "2.2.6", "tesserocr": "2.12.0",
    "opencv-contrib-python": "4.10.0.84", "shapely": "2.2.0", "pyclipper": "1.4.0",
}
MODELS = {
    "PP-OCRv5_mobile_det": {
        "source": "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv5_mobile_det_infer.tar",
        "sha256": "50446e5d01ac2a73d5319c89513281f6578414c888c602f9af13f93feefffc58",
        "files": {
            "inference.json": "05feef1acb00aa4cd7362b15f7f501fc4f99d7b1fa73c1c871e0c7b1504b0f5c",
            "inference.pdiparams": "afa1820cb16c1fd0dad589d0f8b389139061c1ef6d68019685fd07be997dda5b",
            "inference.yml": "98069072e1b6b37d727fd9d9f11725faa46d6ea0de012f2ed26caea011c37699",
        },
    },
    "tessdata-vie": {
        "source": "https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/e12c65a915945e4c28e237a9b52bc4a8f39a0cec/vie.traineddata",
        "sha256": "b6b49293d95d0b6dbd8780174627e82c75be957b6f4ed9862155540d6b00bb45",
        "files": {"vie.traineddata": "b6b49293d95d0b6dbd8780174627e82c75be957b6f4ed9862155540d6b00bb45"},
    },
}
MODEL_SET_ID = "ppocrv5-det-tess-vie-50446e5d01ac-b6b49293d95d"
OCR_VERSION = (
    MODEL_SET_ID + ";paddleocr=3.3.2;paddlex=3.3.13;paddle=3.3.1;"
    "tesserocr=2.12.0;tesseract=5.5.3;cv=4.10.0.84;shapely=2.2.0;clipper=1.4.0;meantextconf/100;cpu4.v1"
)
MAX_BLOCKS = 1000
MAX_TEXT_CHARS = 50_000


class OcrError(ValueError):
    """Stable safe code/message; native exceptions stay outside the wire response."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_link(path: Path) -> bool:
    # Includes Windows junctions, also when running on Python 3.11.
    return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)


def _verify_model(directory: Path, spec: dict) -> None:
    if not directory.is_dir() or _is_link(directory):
        raise OcrError("MANIFEST_UNAVAILABLE", "Pinned model directory is unavailable")
    if {entry.name for entry in directory.iterdir()} != set(spec["files"]):
        raise OcrError("MANIFEST_UNAVAILABLE", "Pinned model file set does not match")
    for name, expected in spec["files"].items():
        path = directory / name
        if not path.is_file() or _is_link(path) or _file_hash(path) != expected:
            raise OcrError("MANIFEST_UNAVAILABLE", "Pinned model checksum does not match")


def provision_models(model_root: Path) -> None:
    """Explicit offline-setup action, never called by load/recognize.

    Fixed official URLs, size caps, exact file/hash checks, no extractall and no
    overwrite of an existing invalid model. Hashes pin observed upstream bytes.
    """
    root = Path(model_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    for name, spec in MODELS.items():
        destination = root / (name + "_infer")
        if destination.exists():
            _verify_model(destination, spec)
            continue
        with TemporaryDirectory(prefix=".ocr-download-", dir=root) as temporary:
            temp = Path(temporary)
            download = temp / "download"
            with urlopen(spec["source"], timeout=30) as response, download.open("xb") as stream:
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > 20 * 1024 * 1024:
                        raise OcrError("MANIFEST_UNAVAILABLE", "Model download exceeds pinned size cap")
                    stream.write(chunk)
            if _file_hash(download) != spec["sha256"]:
                raise OcrError("MANIFEST_UNAVAILABLE", "Model download checksum does not match")
            staged = temp / "model"
            staged.mkdir()
            if name == "tessdata-vie":
                download.rename(staged / "vie.traineddata")
            else:
                with tarfile.open(download) as archive:
                    expected = {name + "_infer/" + filename for filename in spec["files"]}
                    files = [member for member in archive.getmembers() if not member.isdir()]
                    if {member.name for member in files} != expected or len(files) != len(expected):
                        raise OcrError("MANIFEST_UNAVAILABLE", "Unexpected model archive file set")
                    for member in files:
                        if not member.isfile() or not 0 < member.size <= 20 * 1024 * 1024:
                            raise OcrError("MANIFEST_UNAVAILABLE", "Invalid model archive member")
                        with archive.extractfile(member) as source:
                            (staged / Path(member.name).name).write_bytes(source.read())
            _verify_model(staged, spec)
            staged.rename(destination)


def _ordered_quad(points: np.ndarray) -> tuple:
    points = [tuple(float(n) for n in point) for point in points]
    area = sum(points[i][0] * points[(i + 1) % 4][1] - points[(i + 1) % 4][0] * points[i][1] for i in range(4))
    if area < 0:
        points.reverse()
    first = min(range(4), key=lambda i: (points[i][1], points[i][0]))
    points = tuple(points[first:] + points[:first])
    # Reuse contract validation for convexity/degeneracy; this is not a source box.
    OcrBlock("geometry-check", "geometry-check", points, None, None)
    return points


def _source_quad(polygon, width: int, height: int) -> np.ndarray:
    raw = np.asarray(polygon)
    if raw.shape != (4, 2) or raw.dtype.kind not in "fiu" or not np.isfinite(raw).all():
        raise ValueError("Invalid detector quad")
    raw = raw.astype(np.float64)
    normalized = raw / (width, height)
    if (normalized < 0).any() or (normalized > 1).any():
        raise ValueError("Detector quad is outside the processed image")
    _ordered_quad(normalized)
    return raw


def _canonical_quad(polygon, metadata: PreparedPage) -> tuple | None:
    raw = _source_quad(polygon, metadata.processed.width, metadata.processed.height)
    if metadata.geometry_status == "unavailable":
        return None
    projected = np.column_stack((raw, np.ones(4))) @ np.asarray(metadata.inverse_transform).T
    denominator = projected[:, 2]
    if not np.isfinite(projected).all() or (np.abs(denominator) < 1e-12).any():
        raise ValueError("Undefined canonical projection")
    # A polygon crossing the projective horizon cannot have a finite image box.
    if (denominator > 0).any() and (denominator < 0).any():
        raise ValueError("Canonical projection crosses a horizon")
    canonical = projected[:, :2] / denominator[:, None]
    normalized = canonical / (metadata.canonical.width, metadata.canonical.height)
    if not np.isfinite(normalized).all() or (normalized < 0).any() or (normalized > 1).any():
        raise ValueError("Mapped quad is outside the canonical image")
    return _ordered_quad(normalized)


def _to_page(result, metadata: PreparedPage) -> OcrPage:
    texts, polygons, scores = (result[key] for key in ("rec_texts", "rec_polys", "rec_scores"))
    if not len(texts) == len(polygons) == len(scores) or len(texts) > MAX_BLOCKS:
        raise ValueError("Unaligned or oversized OCR output")
    if any(not isinstance(text, str) for text in texts) or sum(map(len, texts)) > MAX_TEXT_CHARS:
        raise ValueError("Invalid or oversized OCR text")
    blocks = []
    for index, (text, polygon, score) in enumerate(zip(texts, polygons, scores), start=1):
        if score is not None:
            if isinstance(score, (bool, np.bool_)) or not isinstance(score, (int, float, np.integer, np.floating)):
                raise ValueError("Invalid recognition score")
            score = float(score)
        quad = _canonical_quad(polygon, metadata)
        blocks.append(OcrBlock(f"p0-b{index:04d}", text, quad, score, metadata.geometry_reason if quad is None else None))
    page = OcrPage(0, metadata.canonical.width, metadata.canonical.height, OCR_VERSION, tuple(blocks))
    page.validate_against(metadata)
    return page


class _PaddleTessPredictor:
    def __init__(self, detector, recognizer, sorter, cropper):
        self.detector, self.recognizer = detector, recognizer
        self.sorter, self.cropper = sorter, cropper

    def predict(self, pixels):
        for detected in self.detector.predict(pixels):
            polygons = detected["dt_polys"]
            if len(polygons) > MAX_BLOCKS:
                raise OcrError("OUTPUT_INVALID", "Too many detected text regions")
            try:
                for polygon in polygons:
                    _source_quad(polygon, pixels.shape[1], pixels.shape[0])
            except (ValueError, TypeError, OverflowError) as exc:
                raise OcrError("OUTPUT_INVALID", "Detector returned invalid text geometry") from exc
            polygons = self.sorter(polygons)
            texts, scores = [], []
            total_chars = 0
            for polygon in polygons:
                crop = self.cropper(pixels, [polygon])[0]
                with Image.fromarray(np.ascontiguousarray(crop[:, :, ::-1])) as image:
                    try:
                        self.recognizer.SetImage(image)
                        text = self.recognizer.GetUTF8Text().strip()
                        score = self.recognizer.MeanTextConf() / 100.0
                    finally:
                        self.recognizer.Clear()
                total_chars += len(text)
                if total_chars > MAX_TEXT_CHARS:
                    raise OcrError("OUTPUT_INVALID", "OCR text exceeds output cap")
                texts.append(text)
                scores.append(score)
            yield {"rec_texts": texts, "rec_polys": polygons, "rec_scores": scores}

    def close(self):
        self.recognizer.End()
        self.detector = None


def _build_predictor(root: Path):
    if os.environ.get("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "").lower() != "true":
        raise OcrError("MODEL_LOAD_FAILED", "Disable Paddle model source checks before loading local models")
    from paddleocr import TextDetection
    from paddlex.inference.pipelines.components import CropByPolys, SortQuadBoxes
    import tesserocr

    if not tesserocr.tesseract_version().startswith("tesseract 5.5.3\n"):
        raise OcrError("MANIFEST_UNAVAILABLE", "Native Tesseract version does not match pinned runtime")
    detector = TextDetection(
        model_name="PP-OCRv5_mobile_det", model_dir=str(root / "PP-OCRv5_mobile_det_infer"),
        limit_side_len=960, limit_type="max", device="cpu", cpu_threads=4, enable_mkldnn=False,
    )
    recognizer = tesserocr.PyTessBaseAPI(
        path=str(root / "tessdata-vie_infer"), lang="vie",
        psm=tesserocr.PSM.SINGLE_LINE, oem=tesserocr.OEM.LSTM_ONLY,
    )
    return _PaddleTessPredictor(detector, recognizer, SortQuadBoxes(), CropByPolys("quad"))


class VietnameseOcrEngine:
    """One reusable CPU engine/slot. AI-2 owns service readiness/deadline isolation.

    A running native call retains its slot until it really returns. The budget is
    checked before/after inference, not advertised as hard native cancellation.
    """

    def __init__(self, model_root: Path):
        self.model_root = Path(model_root).resolve()
        self._predictor = None
        self._slot = Lock()
        self.load_seconds = None
        self.last_inference_seconds = None

    @property
    def ready(self) -> bool:
        return self._predictor is not None

    def load(self):
        if not self._slot.acquire(blocking=False):
            raise OcrError("AI_BUSY", "OCR engine slot is busy")
        try:
            if self.ready:
                return self
            started = time.monotonic()
            for package, expected in RUNTIME_VERSIONS.items():
                if version(package) != expected:
                    raise OcrError("MANIFEST_UNAVAILABLE", "OCR runtime version does not match pinned manifest")
            for name, spec in MODELS.items():
                _verify_model(self.model_root / (name + "_infer"), spec)
            self._predictor = _build_predictor(self.model_root)
            self.load_seconds = time.monotonic() - started
            return self
        except OcrError:
            raise
        except MemoryError as exc:
            raise OcrError("MODEL_OOM", "OCR memory allocation failed") from exc
        except Exception as exc:
            raise OcrError("MODEL_LOAD_FAILED", "Pinned OCR engine could not be loaded") from exc
        finally:
            self._slot.release()

    def recognize(self, loaded: LoadedPage, *, remaining_budget_ms: int = 180_000) -> OcrPage:
        if not self._slot.acquire(blocking=False):
            raise OcrError("AI_BUSY", "OCR engine slot is busy")
        try:
            if not self.ready:
                raise OcrError("AI_NOT_READY", "OCR engine has not been loaded")
            if type(remaining_budget_ms) is not int or remaining_budget_ms <= 0:
                raise OcrError("COMPUTE_TIMEOUT", "OCR budget has expired")
            started = time.monotonic()
            metadata = loaded.metadata
            for image, descriptor in ((loaded.canonical, metadata.canonical), (loaded.processed, metadata.processed)):
                if image.mode != "RGB" or descriptor.color_order != "RGB" or image.size != (descriptor.width, descriptor.height):
                    raise OcrError("INPUT_INVALID", "Prepared pixels do not match RGB image metadata")
            pixels = np.ascontiguousarray(np.asarray(loaded.processed)[:, :, ::-1])
            try:
                outputs = iter(self._predictor.predict(pixels))
                missing = object()
                result = next(outputs, missing)
                if result is missing or next(outputs, missing) is not missing:
                    raise OcrError("OUTPUT_INVALID", "Expected one OCR page")
            except OcrError:
                raise
            except MemoryError as exc:
                raise OcrError("MODEL_OOM", "OCR memory allocation failed") from exc
            except Exception as exc:
                raise OcrError("INTERNAL_ERROR", "OCR engine inference failed") from exc
            finally:
                self.last_inference_seconds = time.monotonic() - started
            if self.last_inference_seconds * 1000 >= remaining_budget_ms:
                raise OcrError("COMPUTE_TIMEOUT", "OCR budget expired during native inference")
            try:
                return _to_page(result, metadata)
            except (ValueError, KeyError, TypeError, OverflowError) as exc:
                raise OcrError("OUTPUT_INVALID", "OCR output violates the page contract") from exc
        except MemoryError as exc:
            raise OcrError("MODEL_OOM", "OCR memory allocation failed") from exc
        finally:
            self._slot.release()

    def close(self):
        if not self._slot.acquire(blocking=False):
            raise OcrError("AI_BUSY", "OCR engine slot is busy")
        try:
            if self._predictor is not None:
                predictor, self._predictor = self._predictor, None
                predictor.close()
        finally:
            self._slot.release()


def draw_overlay(canonical: Image.Image, page: OcrPage) -> Image.Image:
    """Draw actual canonical quads and IDs/scores, without vendor font downloads."""
    if canonical.mode != "RGB" or canonical.size != (page.width, page.height):
        raise ValueError("Overlay must use the matching canonical RGB image")
    image = canonical.copy()
    draw = ImageDraw.Draw(image)
    for block in page.blocks:
        if block.quad is None:
            continue
        points = [(x * page.width, y * page.height) for x, y in block.quad]
        draw.line(points + [points[0]], fill="red", width=2)
        label = block.block_id + ("" if block.score is None else f" {block.score:.2f}")
        x, y = min(points, key=lambda point: (point[1], point[0]))
        draw.text((x, max(0, y - 14)), label, fill="red")
    return image


def main() -> int:
    """Small local smoke CLI; service integration is owned by AI-2."""
    import argparse
    from vietdoc.pipeline.preprocess import PreprocessError, PreprocessLimits, load_document

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--download", action="store_true", help="Explicitly provision pinned pretrained weights")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/evaluation/ocr-smoke"))
    parser.add_argument("--processed-long-edge", type=int, default=2000)
    parser.add_argument("--transcript", type=Path, help="Optional UTF-8 reference; never used by OCR")
    args = parser.parse_args()
    engine = VietnameseOcrEngine(args.model_root)
    try:
        if args.download:
            provision_models(args.model_root)
        if args.input is None:
            if args.download:
                return 0
            parser.error("input is required unless provisioning models")
        limits = PreprocessLimits(processed_long_edge=args.processed_long_edge)
        with args.input.open("rb") as stream:
            data = stream.read(limits.max_file_bytes + 1)
        reference = None
        if args.transcript:
            with args.transcript.open("r", encoding="utf-8-sig") as stream:
                reference = stream.read(MAX_TEXT_CHARS + 1)
            if len(reference) > MAX_TEXT_CHARS:
                raise ValueError("Transcript exceeds text cap")
        engine.load()  # Warm lifecycle startup happens outside a job's deadline.
        started = time.monotonic()
        with load_document(data, limits=limits, remaining_budget_ms=180_000) as loaded:
            remaining = 180_000 - math.ceil((time.monotonic() - started) * 1000)
            page = engine.recognize(loaded, remaining_budget_ms=remaining)
            args.output_dir.mkdir(parents=True, exist_ok=False)
            loaded.canonical.save(args.output_dir / "canonical.png")
            with draw_overlay(loaded.canonical, page) as overlay:
                overlay.save(args.output_dir / "overlay.png")
            (args.output_dir / "ocr.json").write_text(json.dumps(page.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            summary = {
                "ocr_version": OCR_VERSION, "input_sha256": loaded.input_sha256,
                "prepared": loaded.metadata.to_dict(), "load_seconds": engine.load_seconds,
                "inference_seconds": engine.last_inference_seconds,
                "score_method": "Tesseract MeanTextConf (0..100) / 100; not field correctness",
                "block_count": len(page.blocks),
            }
            if reference is not None:
                # Whitespace only; do not strip Vietnamese accents or change prediction.
                summary["transcript_exact_after_whitespace"] = " ".join(reference.split()) == " ".join(" ".join(block.text for block in page.blocks).split())
            (args.output_dir / "run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({k: v for k, v in summary.items() if k != "prepared"}, ensure_ascii=True))
        return 0
    except (OcrError, PreprocessError) as exc:
        print(json.dumps({"code": exc.code, "message": str(exc)}))
        return 2
    except (OSError, ValueError):
        print(json.dumps({"code": "INPUT_INVALID", "message": "Check local input, transcript, limits and a new output directory"}))
        return 2
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
