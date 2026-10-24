"""OCR adapters and canonical geometry; engine construction is explicit."""

from typing import TYPE_CHECKING, Protocol

from vietdoc.contracts.ocr import OcrPage

if TYPE_CHECKING:
    from vietdoc.pipeline.preprocess import LoadedPage


class OcrPort(Protocol):
    def recognize(self, loaded: "LoadedPage", *, remaining_budget_ms: int = 180_000) -> OcrPage:
        """Return detected source text regions on the canonical page."""
        ...
