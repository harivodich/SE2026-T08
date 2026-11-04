"""Offline AI2 consumer of a pinned, isolated AI1 evidence snapshot.

Does not load an OCR engine, copy provider implementation, or open HTTP/DB ports.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from .baseline import METADATA_KEYS, extract_baseline
from .ocr_input import BaselineError, norm, snapshot_page

PROVIDER_SHA = "7d96e93bf8315beb6fa33807231316e957671249"
PROVIDER_FILES = ("src/vietdoc/__init__.py", "src/vietdoc/contracts/__init__.py",
                  "src/vietdoc/pipeline/__init__.py", "src/vietdoc/contracts/ocr.py",
                  "src/vietdoc/pipeline/geometry.py", "src/vietdoc/pipeline/evidence.py")
PROBE = """
import json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve() / 'src'
sys.path.insert(0, str(root))
from vietdoc.contracts import ocr
from vietdoc.pipeline import evidence, geometry
assert all(pathlib.Path(m.__file__).resolve().is_relative_to(root) for m in (ocr, evidence, geometry))
value = json.load(sys.stdin)
page = ocr.OcrPage.from_dict(value['ocr'])
prepared = ocr.PreparedPage.from_dict(value['prepared'])
results = []
for request in value['requests']:
    match = evidence.match_evidence(page, evidence.EvidenceRequest(**request), prepared=prepared)
    results.append(dict(status=match.status, candidate_block_ids=match.candidate_block_ids,
                        field_metadata=match.to_field_metadata()))
print(json.dumps(results, ensure_ascii=True, allow_nan=False))
"""


def validate_match(page: dict, request: dict, match: dict) -> dict:
    """Check source identity/scope and nullable confidence at the consumer boundary."""
    try:
        source = snapshot_page(page)
        blocks = {block.block_id: block for block in source.blocks}
        field = match["field_metadata"]
        statuses = {"matched", "ambiguous", "not_found", "context_not_found", "geometry_unavailable", "value_unavailable"}
        if (set(match) != {"status", "candidate_block_ids", "field_metadata"}
                or match["status"] not in statuses or set(field) != METADATA_KEYS
                or field["path"] != request["path"] or field["raw_value"] != request["raw_value"]
                or field["value_origin"] != "prediction" or field["confidence"] is not None
                or field["confidence_method"] is not None):
            raise ValueError("invalid metadata identity")
        flags, regions = field["review_flags"], field["source_regions"]
        if (not isinstance(flags, list) or any(not isinstance(flag, str) for flag in flags)
                or not isinstance(regions, list) or not isinstance(match["candidate_block_ids"], list)):
            raise ValueError("invalid metadata arrays")
        required = set(source.review_flags) | ({"SOURCE_OCR_INCOMPLETE"} if source.unreadable_regions else set())
        if not required <= set(flags):
            raise ValueError("OCR diagnostics lost")
        for candidate in match["candidate_block_ids"]:
            if not isinstance(candidate, list) or not candidate or any(key not in blocks for key in candidate):
                raise ValueError("invalid candidate IDs")
        selected = []
        scope = request.get("context_block_ids", ())
        for region in regions:
            if set(region) != {"page", "quad", "ocr_block_ids"} or region["page"] != 0:
                raise ValueError("invalid region")
            ids = region["ocr_block_ids"]
            if not isinstance(ids, list) or len(ids) != 1 or ids[0] not in blocks or scope and ids[0] not in scope:
                raise ValueError("region outside scope")
            block = blocks[ids[0]]
            if block.quad is None or region["quad"] != [list(point) for point in block.quad]:
                raise ValueError("invented geometry")
            selected.append(block)
        if match["status"] == "matched":
            if not selected or len({b.block_id for b in selected}) != len(selected):
                raise ValueError("missing or duplicate source")
            if norm(" ".join(block.text for block in selected)) != norm(request["raw_value"]):
                raise ValueError("source text does not match raw value")
        elif selected:
            raise ValueError("abstention cannot publish selected regions")
        score = selected[0].score if len(selected) == 1 else None
        if field["ocr_score"] != score or (score is not None and type(field["ocr_score"]) not in (int, float)):
            raise ValueError("invented OCR score")
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise BaselineError("EVIDENCE_INVALID") from error
    return match


class ProviderEvidence:
    def __init__(self, root: Path, sha: str = PROVIDER_SHA):
        self.root, self.sha = root.resolve(), sha
        self.source_sha256: dict[str, str] = {}
        self.verify()

    def verify(self) -> None:
        try:
            if self.sha != PROVIDER_SHA:
                raise ValueError("provider must use the reviewed SHA")
            head = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"],
                                           stderr=subprocess.PIPE, timeout=10).decode().strip()
            if head != self.sha:
                raise ValueError("provider HEAD mismatch")
            for name in PROVIDER_FILES:
                path = self.root / name
                expected = subprocess.check_output(["git", "-C", str(self.root), "show", f"{self.sha}:{name}"],
                                                   stderr=subprocess.PIPE, timeout=10)
                if not path.resolve().is_relative_to(self.root) or path.read_bytes() != expected:
                    raise ValueError("provider source differs from pinned commit")
                self.source_sha256[name] = hashlib.sha256(expected).hexdigest()
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise BaselineError("OCR_PROVIDER_INVALID") from error

    def match(self, page: dict, prepared: dict, requests: list[dict]) -> list[dict]:
        self.verify()
        snapshot_page(page, prepared)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        try:
            result = subprocess.run([sys.executable, "-I", "-c", PROBE, str(self.root)],
                                    input=json.dumps(dict(ocr=page, prepared=prepared, requests=requests), allow_nan=False),
                                    capture_output=True, text=True, encoding="utf-8", env=env,
                                    cwd=self.root, timeout=30, check=True)
            matches = json.loads(result.stdout)
            if not isinstance(matches, list) or len(matches) != len(requests):
                raise ValueError("provider response count mismatch")
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise BaselineError("OCR_PROVIDER_INVALID") from error
        return [validate_match(page, request, match) for request, match in zip(requests, matches, strict=True)]

    def matcher(self, page: dict, prepared: dict):
        def match(path, raw, context_ids):
            request = dict(path=path, raw_value=raw, context_block_ids=list(context_ids), label_text=None)
            return self.match(page, prepared, [request])[0]["field_metadata"]
        return match


def evidence_checks(provider: ProviderEvidence, golden: dict) -> list[dict]:
    """Exercise real provider behavior through the validating AI2 bridge."""
    partial = golden["cases"][0]["expected"]
    prepared = golden["prepared_page"]
    complete = deepcopy(partial)
    complete.update(unreadable_regions=[], recognition_status="complete", review_flags=[])
    repeated = deepcopy(complete)
    repeated["blocks"].append(dict(complete["blocks"][1], block_id="second-amount"))
    unavailable = deepcopy(complete)
    unavailable["blocks"][1].update(quad=None, geometry_reason="mapping unavailable")
    wrapped = deepcopy(complete)
    wrapped["blocks"][0]["text"], wrapped["blocks"][1]["text"] = "Cà phê", "sữa"
    merged = deepcopy(complete)
    merged["blocks"] = [dict(complete["blocks"][1], text="Tổng tiền: 80.000")]
    cases = [
        ("partial-unscoped", partial, "80.000", [], "ambiguous"),
        ("partial-scoped", partial, "80.000", ["p0-b0004"], "matched"),
        ("repeated-unscoped", repeated, "80.000", [], "ambiguous"),
        ("repeated-scoped", repeated, "80.000", ["p0-b0004"], "matched"),
        ("wrong-scope", repeated, "80.000", ["p0-b0001"], "not_found"),
        ("missing-geometry", unavailable, "80.000", ["p0-b0004"], "geometry_unavailable"),
        ("wrapped-unscoped", wrapped, "Cà phê sữa", [], "ambiguous"),
        ("wrapped-scoped", wrapped, "Cà phê sữa", ["p0-b0004", "p0-b0001"], "matched"),
        ("merged-label-no-substring-box", merged, "80.000", [], "ambiguous"),
        ("all-unreadable", golden["cases"][1]["expected"], None, [], "value_unavailable"),
        ("no-detections", golden["cases"][2]["expected"], None, [], "value_unavailable"),
    ]
    reports = []
    for case_id, page, raw, scope, expected in cases:
        request = dict(path="/total_amount", raw_value=raw, context_block_ids=scope, label_text=None)
        actual = provider.match(page, prepared, [request])[0]
        reports.append(dict(case_id=case_id, expected_status=expected,
                            result="PASS" if actual["status"] == expected else "FAIL", **actual))
    scalar = deepcopy(partial)
    scalar["blocks"][0].update(text="Tổng tiền", quad=[[.05,.4],[.25,.4],[.25,.5],[.05,.5]])
    scalar["blocks"][1]["quad"] = [[.5,.4],[.8,.4],[.8,.5],[.5,.5]]
    result = extract_baseline(scalar, "receipt", prepared=prepared,
                              evidence_matcher=provider.matcher(scalar, prepared))
    field = next(field for field in result.field_metadata if field["path"] == "/total_amount")
    passed = (result.payload["total_amount"] == "80000"
              and [r["ocr_block_ids"] for r in field["source_regions"]] == [["p0-b0004"]]
              and "SOURCE_OCR_INCOMPLETE" in field["review_flags"])
    reports.append(dict(case_id="baseline-callback-scoped-partial", result="PASS" if passed else "FAIL",
                        payload=result.payload, field_metadata=field))
    return reports


def consume_native(bundle: dict, provider: ProviderEvidence | None = None,
                   fixtures: Path | None = None) -> list[dict]:
    """Infer only from observed OCR/prepared metadata; never open annotation files."""
    records = []
    for sample in bundle["samples"]:
        sid = sample["sample_id"]
        try:
            source = snapshot_page(sample["ocr"], sample["prepared"])
            if (not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}", sid)
                    or sample["input_sha256"] != sample["expected_input_sha256"]
                    or (source.width, source.height) != (sample["canonical"]["width"], sample["canonical"]["height"])
                    or source.artifact_version != sample["artifact_version"]
                    or source.recognition_status != sample["recognition_status"]
                    or len(source.blocks) != sample["block_count"]
                    or len(source.unreadable_regions) != sample["unreadable_count"]):
                raise BaselineError("PROVENANCE_MISMATCH")
            input_check = "NOT_RUN: input bytes not supplied"
            if fixtures is not None:
                image = fixtures / "d12" / f"{sid}.png"
                if hashlib.sha256(image.read_bytes()).hexdigest() != sample["input_sha256"]:
                    raise BaselineError("PROVENANCE_MISMATCH")
                input_check = "PASS: encoded input PNG SHA-256"
            matcher = provider.matcher(sample["ocr"], sample["prepared"]) if provider else None
            result = extract_baseline(sample["ocr"], sample["document_type"],
                                      prepared=sample["prepared"], evidence_matcher=matcher)
            record = dict(sample_id=sid, status="ok", document_type=sample["document_type"],
                          **asdict(result), ocr_diagnostics=dict(page=0, **asdict(source)),
                          canonical=sample["canonical"], input_sha256=sample["input_sha256"],
                          input_asset_verification=input_check,
                          canonical_asset_verification="NOT_RUN: encoded canonical PNG not supplied",
                          evidence_execution="PASS" if provider else "NOT_RUN",
                          provider_observations=sample["observations"])
            record["coverage"] = dict(fields=len(result.field_metadata),
                                       filled=sum(value is not None for value in _field_values(result.payload)),
                                       fields_with_source=sum(bool(f["source_regions"]) for f in result.field_metadata),
                                       table_rows=len(result.payload["items"]))
            checks = []
            if provider:
                for example in sample["evidence_examples"]:
                    page, prepared = sample["ocr"], sample["prepared"]
                    if example["kind"].startswith("injected unavailable mapping"):
                        page, prepared = deepcopy(page), deepcopy(prepared)
                        for block in page["blocks"]:
                            block.update(quad=None, geometry_reason="injected unavailable mapping")
                        prepared.update(geometry_status="unavailable", inverse_transform=None,
                                        geometry_reason="injected unavailable mapping")
                    actual = provider.match(page, prepared, [example["request"]])[0]
                    checks.append(dict(expected_status=example["status"],
                                       result="PASS" if actual["status"] == example["status"] else "FAIL", **actual))
            record["native_evidence_checks"] = checks
            records.append(record)
        except BaselineError as error:
            records.append(dict(sample_id=sid, status="failed", error=error.code))
        except (KeyError, TypeError, ValueError):
            records.append(dict(sample_id=sid, status="failed", error="OCR_INPUT_INVALID"))
        except OSError:
            records.append(dict(sample_id=sid, status="failed", error="INPUT_STORAGE_UNAVAILABLE"))
    return records


def _field_values(payload: dict):
    for key, value in payload.items():
        if key != "items":
            yield value
    for item in payload["items"]:
        yield from item.values()
