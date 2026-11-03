"""Run pinned OCR evidence consumer checks offline, without model inference."""

import argparse
import json
from pathlib import Path

from vietdoc.pipeline.extraction.ocr_consumer import PROVIDER_SHA, ProviderEvidence, evidence_checks
from vietdoc.pipeline.extraction.ocr_input import BaselineError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-root", type=Path, required=True)
    parser.add_argument("--provider-sha", default=PROVIDER_SHA)
    parser.add_argument("--fixtures", type=Path, default=Path(__file__).resolve().parents[4] / "tests/fixtures")
    parser.add_argument("--output", type=Path, required=True, help="New directory, never overwritten")
    args = parser.parse_args(argv)
    try:
        provider = ProviderEvidence(args.provider_root, args.provider_sha)
        golden = json.loads((args.fixtures / "ocr-artifact-v2.json").read_text(encoding="utf-8"))
        checks = evidence_checks(provider, golden)
        report = dict(provider_sha=provider.sha, provider_source_sha256=provider.source_sha256,
                      actual_ocr_run=False, evidence_checks=checks)
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / "consumer-report.json").write_bytes(
            (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))
    except (BaselineError, OSError, ValueError) as error:
        parser.exit(2, f"OCR consumer failed: {error}\n")
    print(json.dumps(dict(evidence_passed=sum(c["result"] == "PASS" for c in checks),
                          evidence_total=len(checks), output=str(args.output))))
    return int(any(c["result"] != "PASS" for c in checks))


if __name__ == "__main__":
    raise SystemExit(main())
