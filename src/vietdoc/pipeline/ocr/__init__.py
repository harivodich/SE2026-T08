"""OCR adapters and canonical geometry; engine construction is explicit."""

from contextlib import contextmanager
from dataclasses import dataclass
import time
from typing import TYPE_CHECKING, Protocol

from vietdoc.contracts.ocr import OcrPage


OCR_STAGE_VERSION = "bounded-preprocess-ocr.v1"

if TYPE_CHECKING:
    from vietdoc.pipeline.preprocess import LoadedPage, PreprocessLimits


class OcrError(ValueError):
    """Stable safe code/message; native exceptions stay outside the wire response."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class OcrPort(Protocol):
    def recognize(self, loaded: "LoadedPage", *, remaining_budget_ms: int = 180_000) -> OcrPage:
        """Return detected source text regions on the canonical page."""
        ...


@dataclass(frozen=True, slots=True)
class OcrStageResult:
    """Images live only inside recognize_document's context; metadata is immutable."""

    loaded: "LoadedPage"
    ocr: OcrPage
    deadline: float

    @property
    def remaining_budget_ms(self) -> int:
        """Live remaining budget for the next compute stage, never a fresh budget."""
        return max(0, int((self.deadline - time.monotonic()) * 1000))


@contextmanager
def recognize_document(
    data: bytes,
    engine: OcrPort,
    *,
    limits: "PreprocessLimits | None" = None,
    remaining_budget_ms: int = 180_000,
    expected_sha256: str | None = None,
):
    """AI-1 compute entrypoint for an already-loaded, caller-owned OCR engine.

    Decode, infer and validate under one deadline. No model load/download, DB,
    storage or extraction. The caller consumes canonical pixels inside the with
    block, then both PIL images close on success and all exceptional exits.
    Native inference cancellation/isolation remains the service's responsibility.
    """
    from vietdoc.pipeline.preprocess import PreprocessError, PreprocessLimits, load_document

    if type(remaining_budget_ms) is not int or remaining_budget_ms <= 0:
        raise PreprocessError("COMPUTE_TIMEOUT", "No remaining OCR stage budget")
    deadline = time.monotonic() + remaining_budget_ms / 1000
    with load_document(
        data, limits=PreprocessLimits() if limits is None else limits,
        remaining_budget_ms=max(0, int((deadline - time.monotonic()) * 1000)),
        expected_sha256=expected_sha256,
    ) as loaded:
        budget = max(0, int((deadline - time.monotonic()) * 1000))
        if budget <= 0:
            raise PreprocessError("COMPUTE_TIMEOUT", "OCR stage budget expired after preprocessing")
        page = engine.recognize(loaded, remaining_budget_ms=budget)
        try:
            if not isinstance(page, OcrPage):
                raise ValueError("Expected OcrPage")
            page.validate_against(loaded.metadata)
        except ValueError as exc:
            raise OcrError("OUTPUT_INVALID", "OCR stage output does not match canonical page metadata") from exc
        result = OcrStageResult(loaded, page, deadline)
        if result.remaining_budget_ms <= 0:
            raise PreprocessError("COMPUTE_TIMEOUT", "OCR stage budget expired during recognition")
        yield result
