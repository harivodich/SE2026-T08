"""Opt-in offline inference adapter; no HTTP wiring, IDs, confidence or evidence."""
from dataclasses import dataclass, field
import json

from jsonschema import Draft202012Validator

from vietdoc.contracts.compute import ComputeContracts
from vietdoc.ml.ocr_adapter import business_schema
from vietdoc.ml.qwen_config import MLFailure
from vietdoc.pipeline.extraction.output_parser import parse_model_output, MAX_RAW_CHARS


@dataclass(frozen=True)
class InferenceResult:
    error: str | None = None
    stage: str | None = None
    payload: dict | None = None
    raw_output: str | None = field(default=None,repr=False)
    raw_json_valid: bool = False
    raw_schema_valid: bool = False
    normalized_schema_valid: bool = False
    parsed_payload: dict | None = field(default=None,repr=False)
    normalization_issues: tuple = ()
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    seconds: float | None = None
    provenance: dict = field(default_factory=dict)


def _check_utf8(value):
    if isinstance(value, str):
        value.encode('utf-8', errors='strict')
    elif isinstance(value, list):
        for item in value:
            _check_utf8(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            key.encode('utf-8', errors='strict')
            _check_utf8(item)


class QwenInference:
    def __init__(self,loader):
        self.loader = loader
        self.contracts = ComputeContracts(loader.config.schema_path.parent)

    def run(self,page,prepared,provenance,document_type,*,deadline):
        try:
            selected = business_schema(self.loader.config,document_type)
            generated = self.loader.generate(page,prepared,provenance,document_type,deadline=deadline)
        except MLFailure as error:
            return InferenceResult(error=error.code,stage=error.stage)
        raw = generated.raw
        metadata = dict(raw_output=raw,input_tokens=generated.input_tokens,
            output_tokens=generated.output_tokens,finish_reason=generated.finish_reason,
            seconds=generated.seconds,provenance=generated.provenance)
        parsed = parse_model_output(raw,document_type,self.contracts,finish_reason=generated.finish_reason)
        if len(raw) <= MAX_RAW_CHARS and ('<think' in raw or '</think>' in raw):
            return InferenceResult(error='UNEXPECTED_REASONING',stage='parse',**metadata)
        raw_json_valid = raw_schema_valid = False
        if parsed.status not in ('truncated','too_large','malformed_json') and not parsed.fenced:
            # Strict original bytes: a fenced object is not raw JSON. The existing
            # parser has already rejected duplicates/nonfinite/depth violations.
            try:
                raw.encode('utf-8',errors='strict')
                original = json.loads(raw,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                _check_utf8(original)
                raw_json_valid = True
                raw_schema_valid = Draft202012Validator(selected).is_valid(original)
            except (ValueError,RecursionError):
                pass
        normalized = parsed.status=='ok'
        failure = {'truncated':'TRUNCATED_JSON','too_large':'OUTPUT_TOO_LARGE',
            'no_json':'INVALID_SCHEMA' if raw_json_valid else 'MALFORMED_JSON',
            'malformed_json':'MALFORMED_JSON',
            'schema_invalid':'INVALID_SCHEMA'}.get(parsed.status)
        if failure is None and not raw_schema_valid:
            failure = 'RAW_SCHEMA_INVALID'
        return InferenceResult(error=failure,stage='parse' if failure else None,
            payload=parsed.payload if failure is None else None,
            raw_json_valid=raw_json_valid,raw_schema_valid=raw_schema_valid,
            normalized_schema_valid=normalized,parsed_payload=parsed.payload,
            normalization_issues=parsed.issues,**metadata)
