"""Bounded PNG/JPEG/single-page PDF loading; no OCR or business persistence.

Decode/render runs in a disposable process so a native decoder can be killed on
timeout. Input is bytes, never a caller-supplied path. Output pixels are RGB uint8.
"""

from contextlib import closing
from dataclasses import asdict, dataclass
from hashlib import sha256
from io import BytesIO
import json
import math
import subprocess
import sys
import time
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from vietdoc.contracts.ocr import ImageInfo, PreparedPage


PREPROCESS_VERSION = "canonical-rgb-resize.v1"


class PreprocessError(ValueError):
    """Safe error code/message for the private compute boundary."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class PreprocessLimits:
    """Initial configurable profile; DPI/timeout still need integration benchmarks."""

    max_file_bytes: int = 20 * 1024 * 1024
    max_pixels: int = 20_000_000
    processed_long_edge: int = 2000
    pdf_dpi: int = 200
    timeout_seconds: float = 15.0

    def __post_init__(self):
        for value in (self.max_file_bytes, self.max_pixels, self.processed_long_edge, self.pdf_dpi):
            if type(value) is not int or value <= 0:
                raise ValueError("Byte/pixel/resize/DPI limits must be positive integers")
        if type(self.timeout_seconds) not in (int, float) or not math.isfinite(self.timeout_seconds):
            raise ValueError("timeout_seconds must be finite")
        if not 0 < self.timeout_seconds <= 180:
            raise ValueError("timeout_seconds must be in (0, 180]")


@dataclass(frozen=True, slots=True)
class LoadedPage:
    """Caller owns the two independent PIL images; metadata describes their pixels."""

    canonical: Image.Image
    processed: Image.Image
    metadata: PreparedPage
    input_sha256: str

    def close(self):
        self.canonical.close()
        self.processed.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def _check_size(width: int, height: int, limits: PreprocessLimits):
    if width <= 0 or height <= 0 or width * height > limits.max_pixels:
        raise PreprocessError("PROFILE_EXCEEDED", "Image exceeds the configured pixel limit")


def _rgb(image: Image.Image) -> Image.Image:
    # Transparent backgrounds become white; no alpha-induced black text canvas.
    if image.mode in ("RGBA", "LA") or "transparency" in image.info:
        with image.convert("RGBA") as rgba:
            with Image.new("RGBA", rgba.size, "white") as background:
                background.alpha_composite(rgba)
                result = background.convert("RGB")
    else:
        result = image.convert("RGB")
    result.info.clear()  # Canonical pixels already include EXIF orientation.
    return result


def _load_raster(data: bytes, limits: PreprocessLimits) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=("PNG", "JPEG")) as image:
                _check_size(*image.size, limits)
                if getattr(image, "n_frames", 1) != 1:
                    raise PreprocessError("PROFILE_EXCEEDED", "Animated/multiframe images are unsupported")
                if image.mode not in ("1", "L", "LA", "P", "RGB", "RGBA", "CMYK"):
                    raise PreprocessError("PROFILE_EXCEEDED", "Unsupported source pixel depth or color mode")
                image.load()
                with ImageOps.exif_transpose(image) as oriented:
                    _check_size(*oriented.size, limits)
                    return _rgb(oriented)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise PreprocessError("PROFILE_EXCEEDED", "Image exceeds decoder pixel limits") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        if isinstance(exc, PreprocessError):
            raise
        raise PreprocessError("INPUT_INVALID", "Image is corrupt or cannot be decoded") from exc


def _load_pdf(data: bytes, limits: PreprocessLimits) -> Image.Image:
    import pypdfium2 as pdfium

    try:
        with pdfium.PdfDocument(data) as document:
            if pdfium.raw.FPDF_GetSecurityHandlerRevision(document) != -1:
                raise PreprocessError("PROFILE_EXCEEDED", "Encrypted PDFs are unsupported")
            if len(document) != 1:
                raise PreprocessError("PROFILE_EXCEEDED", "PDF must contain exactly one page")
            with closing(document[0]) as page:
                scale = limits.pdf_dpi / 72
                width, height = page.get_size()
                if not all(math.isfinite(n) and n > 0 for n in (width, height)):
                    raise PreprocessError("INPUT_INVALID", "Invalid PDF page dimensions")
                _check_size(math.ceil(width * scale), math.ceil(height * scale), limits)
                # PDFium applies the PDF page rotation; this rendered image is canonical.
                with closing(page.render(scale=scale)) as bitmap:
                    _check_size(bitmap.width, bitmap.height, limits)
                    with bitmap.to_pil() as image:
                        return _rgb(image)
    except pdfium.PdfiumError as exc:
        if exc.err_code in (pdfium.raw.FPDF_ERR_PASSWORD, pdfium.raw.FPDF_ERR_SECURITY):
            raise PreprocessError("PROFILE_EXCEEDED", "Encrypted PDFs are unsupported") from exc
        raise PreprocessError("INPUT_INVALID", "PDF is corrupt or cannot be rendered") from exc


def _prepare(data: bytes, limits: PreprocessLimits) -> tuple[Image.Image, Image.Image, PreparedPage]:
    if data.startswith(b"%PDF-"):
        canonical = _load_pdf(data, limits)
    elif data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff"):
        canonical = _load_raster(data, limits)
    else:
        raise PreprocessError("INPUT_INVALID", "Only PNG, JPEG and single-page PDF are supported")
    try:
        width, height = canonical.size
        ratio = min(1.0, limits.processed_long_edge / max(width, height))
        size = (max(1, round(width * ratio)), max(1, round(height * ratio)))
        _check_size(*size, limits)
        processed = canonical.resize(size, Image.Resampling.LANCZOS) if size != canonical.size else canonical.copy()
        try:
            metadata = PreparedPage(
                page=0,
                canonical=ImageInfo(width, height, "RGB", "uint8"),
                processed=ImageInfo(*size, "RGB", "uint8"),
                preprocess_version=PREPROCESS_VERSION,
                geometry_status="available",
                inverse_transform=((width / size[0], 0, 0), (0, height / size[1], 0), (0, 0, 1)),
                geometry_reason=None,
            )
            return canonical, processed, metadata
        except Exception:
            processed.close()
            raise
    except Exception:
        canonical.close()
        raise


def load_document(
    data: bytes,
    *,
    limits: PreprocessLimits = PreprocessLimits(),
    remaining_budget_ms: int = 180_000,
    expected_sha256: str | None = None,
) -> LoadedPage:
    """Decode bytes within the lesser of the stage cap and remaining job budget.

    Input must already have been streamed with an admission byte limit. This
    function rechecks it, validates an optional hash, and never opens input paths.
    """
    started = time.monotonic()
    if not isinstance(limits, PreprocessLimits):
        raise ValueError("limits must be PreprocessLimits")
    if not isinstance(data, bytes) or not data:
        raise PreprocessError("INPUT_INVALID", "Input must be nonempty bytes")
    if len(data) > limits.max_file_bytes:
        raise PreprocessError("INPUT_TOO_LARGE", "Input exceeds the configured byte limit")
    if type(remaining_budget_ms) is not int or remaining_budget_ms <= 0:
        raise PreprocessError("COMPUTE_TIMEOUT", "No remaining compute budget")
    deadline = started + min(limits.timeout_seconds, remaining_budget_ms / 1000)
    digest = sha256(data).hexdigest()
    if expected_sha256 is not None and expected_sha256 != digest:
        raise PreprocessError("INPUT_INVALID", "Input SHA-256 does not match")
    timeout = deadline - time.monotonic()
    if timeout <= 0:
        raise PreprocessError("COMPUTE_TIMEOUT", "Preprocessing deadline exceeded")
    try:
        result = subprocess.run(
            [sys.executable, "-B", "-m", "vietdoc.pipeline.preprocess", "--worker", json.dumps(asdict(limits))],
            input=data, capture_output=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        # subprocess.run kills and waits for the child before raising.
        raise PreprocessError("COMPUTE_TIMEOUT", "Decode/render deadline exceeded") from exc
    except OSError as exc:
        raise PreprocessError("INTERNAL_ERROR", "Could not start the decode process") from exc
    try:
        header_bytes, pixels = result.stdout.split(b"\n", 1)
        if len(header_bytes) > 65_536:
            raise ValueError("Oversized worker metadata")
        header = json.loads(header_bytes)
        if not header["ok"]:
            raise PreprocessError(header["code"], header["message"])
        if result.returncode != 0:
            raise ValueError("Decode process exited unsuccessfully")
        metadata = PreparedPage.from_dict(header["metadata"])
        canonical_size = (metadata.canonical.width, metadata.canonical.height)
        processed_size = (metadata.processed.width, metadata.processed.height)
        for size in (canonical_size, processed_size):
            _check_size(*size, limits)
        canonical_bytes = canonical_size[0] * canonical_size[1] * 3
        processed_bytes = processed_size[0] * processed_size[1] * 3
        if len(pixels) != canonical_bytes + processed_bytes:
            raise ValueError("Incomplete worker pixels")
        canonical = Image.frombytes("RGB", canonical_size, pixels[:canonical_bytes])
        try:
            processed = Image.frombytes("RGB", processed_size, pixels[canonical_bytes:])
        except Exception:
            canonical.close()
            raise
    except (ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, PreprocessError):
            raise
        raise PreprocessError("INTERNAL_ERROR", "Invalid output from the decode process") from exc
    if time.monotonic() >= deadline:
        canonical.close()
        processed.close()
        raise PreprocessError("COMPUTE_TIMEOUT", "Preprocessing deadline exceeded")
    return LoadedPage(canonical, processed, metadata, digest)


def _worker():
    """Private byte protocol: one JSON header followed by bounded raw RGB pixels."""
    try:
        limits = PreprocessLimits(**json.loads(sys.argv[2]))
        data = sys.stdin.buffer.read(limits.max_file_bytes + 1)
        if not data or len(data) > limits.max_file_bytes:
            raise PreprocessError("INPUT_TOO_LARGE", "Invalid input byte length")
        canonical, processed, metadata = _prepare(data, limits)
        try:
            header = json.dumps({"ok": True, "metadata": metadata.to_dict()}).encode("utf-8")
            sys.stdout.buffer.write(header + b"\n")
            sys.stdout.buffer.write(canonical.tobytes())
            sys.stdout.buffer.write(processed.tobytes())
        finally:
            canonical.close()
            processed.close()
        return 0
    except Exception as exc:
        code = exc.code if isinstance(exc, PreprocessError) else "INTERNAL_ERROR"
        message = str(exc) if isinstance(exc, PreprocessError) else "Decode/render process failed"
        sys.stdout.buffer.write(json.dumps({"ok": False, "code": code, "message": message}).encode("utf-8") + b"\n")
        return 2


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--worker":
        raise SystemExit("Use load_document(bytes) from Python")
    raise SystemExit(_worker())
