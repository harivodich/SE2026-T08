"""Run pinned OCR evidence consumer checks offline, without model inference."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess

from vietdoc.pipeline.extraction.baseline import BASELINE_VERSION, extract_baseline
from vietdoc.pipeline.extraction.ocr_consumer import PROVIDER_SHA, ProviderEvidence, batch_summary, consume_native, evidence_checks
from vietdoc.pipeline.extraction.ocr_input import BaselineError, snapshot_page


# Hand-reviewed assertions for fictional consumer cases, NOT recognition gold.
GOLDEN_EXPECTATIONS = {
    "mixed-empty-whitespace": ("partial", ["p0-b0002", "p0-b0003"]),
    "all-unreadable": ("unreadable", ["p0-b0001"]),
    "blank-no-detections": ("complete", []),
}


def evaluate_expectations(actual: dict, expectations: list[dict]) -> list[dict]:
    checks = []
    for check in expectations:
        value = actual
        try:
            for part in check["path"].strip("/").split("/"):
                value = value[int(part)] if isinstance(value, list) else value[part.replace("~1", "/").replace("~0", "~")]
            passed = type(value) is type(check["expected"]) and value == check["expected"]
        except (KeyError, IndexError, TypeError, ValueError):
            value, passed = "MISSING", False
        checks.append(dict(**check, actual=value, result="PASS" if passed else "FAIL"))
    return checks


def golden_reports(golden: dict, provider=None) -> list[dict]:
    records = []
    for case in golden["cases"]:
        identity = dict(case_id=case["case_id"], quality_status="NOT_EVALUATED")
        try:
            page = snapshot_page(case["expected"], golden["prepared_page"])
            result = extract_baseline(case["expected"], "receipt", prepared=golden["prepared_page"],
                                      evidence_matcher=provider.matcher(case["expected"], golden["prepared_page"]) if provider else None)
            record = dict(**identity, execution_status="PASS", ocr_diagnostics=asdict(page), **asdict(result))
            oracle = GOLDEN_EXPECTATIONS.get(case["case_id"])
            expectations = [] if oracle is None else [
                dict(path="/payload/total_amount", expected=None),
                dict(path="/payload/items", expected=[]),
                dict(path="/field_states/~1total_amount", expected="unknown"),
                dict(path="/ocr_diagnostics/recognition_status", expected=oracle[0]),
            ]
            checks = evaluate_expectations(record, expectations)
            if oracle is not None:
                ids = [r.region_id for r in page.unreadable_regions]
                checks.append(dict(path="/ocr_diagnostics/unreadable_region_ids", expected=oracle[1],
                                   actual=ids, result="PASS" if ids == oracle[1] else "FAIL"))
            record.update(checks=checks, status=("FAIL" if any(c["result"] == "FAIL" for c in checks)
                                                else "PASS" if checks else "NOT_EVALUATED"))
        except (BaselineError, ValueError, KeyError, TypeError):
            record = dict(**identity, execution_status="FAIL", status="FAIL", error="GOLDEN_INPUT_INVALID", checks=[])
        records.append(record)
    return records


def publish_report(output: Path, report: dict) -> int:
    native = report.get("native_results", [])
    failed = (any(r["status"] == "FAIL" for r in report.get("golden_results", []))
              or any(c["result"] != "PASS" for c in report.get("evidence_checks", []))
              or any(r["status"] != "ok" or any(c["result"] != "PASS" for c in r.get("native_evidence_checks", [])) for r in native))
    report["summary"] = dict(status="FAIL" if failed else "PASS", native=batch_summary(native),
                           quality_status="NOT_EVALUATED")
    output.mkdir(parents=True, exist_ok=False)
    (output / "consumer-report.json").write_bytes(
        (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))
    return int(failed)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-root", type=Path, required=True)
    parser.add_argument("--provider-sha", default=PROVIDER_SHA)
    parser.add_argument("--fixtures", type=Path, default=Path(__file__).resolve().parents[4] / "tests/fixtures")
    parser.add_argument("--output", type=Path, required=True, help="New directory, never overwritten")
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise FileExistsError("output directory already exists")
        provider = ProviderEvidence(args.provider_root, args.provider_sha)
        source = json.loads((args.fixtures / "ocr-ai2-source.json").read_text(encoding="utf-8"))
        if source["provider_sha"] != provider.sha:
            raise BaselineError("PROVENANCE_MISMATCH")
        fixtures, fixture_hashes = {}, {}
        for name in ("ocr-artifact-v2.json", "ocr-d1-native-handoff.json"):
            data = (args.fixtures / name).read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            recorded = source["files"][f"tests/fixtures/{name}"]
            original = subprocess.check_output(["git", "-C", str(provider.root), "show",
                                                f"{provider.sha}:tests/fixtures/{name}"], timeout=10)
            if digest != recorded["sha256"] or data != original:
                raise BaselineError("PROVENANCE_MISMATCH")
            fixture_hashes[name] = digest
            fixtures[name] = json.loads(data)
        golden, bundle = fixtures["ocr-artifact-v2.json"], fixtures["ocr-d1-native-handoff.json"]
        checks = evidence_checks(provider, golden)
        golden_results = golden_reports(golden, provider)
        native = consume_native(bundle, provider, args.fixtures)
        root = Path(__file__).resolve().parents[4]
        consumer_head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], timeout=10).decode().strip()
        dirty = bool(subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], timeout=10).strip())
        files = [*root.joinpath("src/vietdoc/pipeline/extraction").glob("*.py"),
                 root / "src/vietdoc/pipeline/normalization.py", root / "src/vietdoc/contracts/compute.py",
                 root / "pyproject.toml", Path(__file__),
                 *root.joinpath("specs/contracts").glob("*.schema.json")]
        hashes = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        report = dict(artifact_version="vietdoc.ocr-consumer-report.v2",
                      observed_at_utc=datetime.now(timezone.utc).isoformat(),
                      consumer_head=consumer_head, consumer_worktree_dirty=dirty,
                      consumer_source_sha256=hashes, model_version=BASELINE_VERSION,
                      python=platform.python_version(), dependencies={p: version(p) for p in ("jsonschema", "referencing")},
                      provider_sha=provider.sha, provider_source_sha256=provider.source_sha256,
                      fixture_sha256=fixture_hashes, actual_ocr_run=False,
                      historical_provider_counts=bundle["run_summary"]["counts"],
                      historical_provider_provenance={key: bundle["run_summary"][key]
                                                      for key in ("manifest_version", "manifest_sha256", "versions")},
                      evidence_checks=checks, golden_results=golden_results, native_results=native,
                      limitations=["Observed native JSON replay, not a new OCR/model run or D1 benchmark",
                                   "Golden partial cases are separate from the two complete native v2 pages",
                                   "Default-v2/Backend policy/HTTP/hosted CI acceptance remains pending"])
        status = publish_report(args.output, report)
    except FileExistsError:
        parser.exit(2, "OCR consumer failed: output directory already exists\n")
    except (BaselineError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        code = error.code if isinstance(error, BaselineError) else "CONSUMER_SETUP_FAILED"
        if not args.output.exists():
            try:
                args.output.mkdir(parents=True, exist_ok=False)
                (args.output / "consumer-report.json").write_text(json.dumps(dict(
                    artifact_version="vietdoc.ocr-consumer-report.v2", error=code,
                    summary=dict(status="FAIL", incomplete=True, quality_status="NOT_EVALUATED"))), encoding="utf-8")
            except OSError:
                pass
        parser.exit(2, f"OCR consumer failed: {code}\n")
    print(json.dumps(dict(evidence_passed=sum(c["result"] == "PASS" for c in checks),
                          evidence_total=len(checks), native_ok=sum(r["status"] == "ok" for r in native),
                          native_total=len(native), output=str(args.output))))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
