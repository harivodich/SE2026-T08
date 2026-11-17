"""Source-bound adapter to the accepted AI1 in-process evidence mapper."""
from dataclasses import dataclass

from vietdoc.contracts.ocr import OcrPage, PreparedPage
from vietdoc.pipeline.evidence import EvidenceRequest, match_evidence

from .ocr_consumer import validate_match
from .ocr_input import BaselineError, snapshot_page


@dataclass(frozen=True)
class BoundEvidence:
    page: OcrPage
    prepared: PreparedPage

    def __post_init__(self):
        self.page.validate_against(self.prepared)
        snapshot_page(self.page, self.prepared)

    def __call__(self, path: str, raw: str, context_ids: tuple[str, ...]) -> dict:
        try:
            request = EvidenceRequest(path, raw, context_block_ids=context_ids)
            match = match_evidence(self.page, request, prepared=self.prepared)
            result = dict(status=match.status, candidate_block_ids=[list(ids) for ids in match.candidate_block_ids],
                          field_metadata=match.to_field_metadata())
            source_request = dict(path=path, raw_value=raw, context_block_ids=list(context_ids))
            return validate_match(self.page.to_dict(), source_request, result)["field_metadata"]
        except (ValueError, TypeError, KeyError) as error:
            raise BaselineError("EVIDENCE_INVALID") from error
