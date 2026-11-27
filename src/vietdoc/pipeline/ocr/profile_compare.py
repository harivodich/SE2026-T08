"""Compare two pinned native OCR handoffs over the same exposed dev IDs.

This is an offline diagnostic. It does not activate a profile or decide model
acceptance. The Data evaluator supplies the proposed OCR policy and counts.
"""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

from vietdoc.contracts.ocr import OcrPage, PreparedPage
from vietdoc.data.manifest import asset_path, require, sha
from vietdoc.evaluation.scalar_ocr import VERSION as EVALUATOR_VERSION, evaluate, load_bundle
from vietdoc.evaluation.policy import POLICY
from vietdoc.pipeline.ocr.audit import _image, _pinned, _rates
from vietdoc.pipeline.ocr.diagnose import _read, _write
from vietdoc.pipeline.ocr.triage import _verify_overlay


def _membership(ids):
    return sha256(("\n".join(sorted(ids)) + "\n").encode("utf-8")).hexdigest()


def _bounded_json(path):
    with path.open("rb") as stream:
        raw = stream.read(8 * 1024 * 1024 + 1)
    require(len(raw) <= 8 * 1024 * 1024, "JSON_BYTE_CAP")
    return _read(raw), sha256(raw).hexdigest()


def compare(*, data_root, manifest, manifest_sha256, baseline_root, baseline_report_sha256,
            candidate_root, candidate_report_sha256, membership_sha256, output_dir):
    """Verify paired inputs/outputs before publishing a fresh diagnostic report."""
    data_root, manifest, baseline_root, candidate_root, output = map(
        Path, (data_root, manifest, baseline_root, candidate_root, output_dir))
    require(not output.exists(), "OUTPUT_EXISTS")
    require(re.fullmatch(r"[0-9a-f]{64}", membership_sha256 or ""), "INVALID_MEMBERSHIP_PIN")
    require(sha(manifest) == manifest_sha256, "MANIFEST_PIN_MISMATCH")
    require(manifest.resolve().is_relative_to(data_root.resolve()), "MANIFEST_OUTSIDE_ROOT")
    source, gold, gold_pins, validation = load_bundle(data_root, manifest)
    samples = {sample["sample_id"]: sample for sample in source["samples"]}
    gold_by_id = {sample["sample_id"]: sample for sample in gold}
    roots = (baseline_root, candidate_root)
    reports = tuple(_pinned(root / "report.json", pin) for root, pin in zip(
        roots, (baseline_report_sha256, candidate_report_sha256), strict=True))
    rows = []
    for report in reports:
        require(report["manifest_sha256"] == manifest_sha256 and
                report["manifest_version"] == source["version"], "REPORT_BINDING_MISMATCH")
        records = report["samples"]
        require(isinstance(records, list) and records and len(records) <= 200,
                "INVALID_POPULATION")
        by_id = {row["sample_id"]: row for row in records}
        require(len(by_id) == len(records) and all(sid in samples and samples[sid]["split"] == "dev"
                for sid in by_id), "NON_DEV_OR_DUPLICATE_ID")
        counts = dict(requested=len(records),
                      native_attempted=sum(row["native_attempted"] for row in records),
                      **{state: sum(row["status"] == state for row in records)
                         for state in ("ok", "failed", "not_run")})
        require(report["counts"] == counts and report["observed_engine_calls"] ==
                sum(row["engine_calls"] for row in records), "ACCOUNTING_MISMATCH")
        rows.append(by_id)
    ids = set(rows[0])
    require(ids == set(rows[1]) and _membership(ids) == membership_sha256,
            "MEMBERSHIP_MISMATCH")
    baseline_profile, candidate_profile = (report["profile"] for report in reports)
    require(baseline_profile["processed_long_edge"] == 2000 and
            candidate_profile["processed_long_edge"] == 2600 and
            {k: v for k, v in baseline_profile.items() if k != "processed_long_edge"} ==
            {k: v for k, v in candidate_profile.items() if k != "processed_long_edge"} and
            all(reports[0][key] == reports[1][key] for key in
                ("provider", "python", "hardware", "versions", "font_sha256", "config_sha256")),
            "PAIR_PROFILE_MISMATCH")
    summaries = [defaultdict(Counter), defaultdict(Counter)]
    gold_base = manifest.parent if source["version"] in {"d2.1.v1", "d2.2.v1"} else data_root
    cases, snapshots = [], [(manifest, manifest_sha256)]
    snapshots.extend((asset_path(gold_base, pin["path"]), pin["sha256"]) for pin in gold_pins)
    for sid in sorted(ids):
        sample = samples[sid]
        expected_source = sample["assets"]["png"]["sha256"]
        source_path = asset_path(manifest.parent, sample["assets"]["png"]["path"])
        require(sha(source_path) == expected_source, "INPUT_PIN_MISMATCH")
        snapshots.append((source_path, expected_source))
        paired = []
        for profile_index, root in enumerate(roots):
            run = rows[profile_index][sid]
            require(run["document_type"] == sample["document_type"] and
                    run["expected_input_sha256"] == expected_source and
                    not run.get("fixture_fallback", False), "INPUT_BINDING_MISMATCH")
            page = None
            if run["status"] == "ok":
                record_path = asset_path(root, sid + "/run.json")
                record, record_hash = _bounded_json(record_path)
                require(record == run, "RUN_REPORT_MISMATCH")
                ocr_path = asset_path(root, sid + "/ocr.json")
                prepared_path = asset_path(root, sid + "/prepared.json")
                ocr, ocr_hash = _bounded_json(ocr_path)
                metadata, prepared_hash = _bounded_json(prepared_path)
                page = OcrPage.from_dict(ocr)
                prepared = PreparedPage.from_dict(metadata)
                page.validate_against(prepared)
                require(page.artifact_version == 2 and page.ocr_version == run["ocr_version"]
                        and page.recognition_status == run["recognition_status"] and
                        prepared.to_dict() == run["prepared"] and
                        prepared.processed.width == run["prepared"]["processed"]["width"] and
                        prepared.processed.height == run["prepared"]["processed"]["height"],
                        "OCR_STATE_MISMATCH")
                require(prepared.canonical.width == run["canonical"]["width"] and
                        prepared.canonical.height == run["canonical"]["height"],
                        "CANONICAL_FRAME_MISMATCH")
                canonical = _image(asset_path(root, sid + "/canonical.png"),
                                   (page.width, page.height), run["canonical"])
                processed_path = asset_path(root, sid + "/processed.png")
                processed = _image(processed_path,
                                   (prepared.processed.width, prepared.processed.height))
                _verify_overlay(root, sid, run["canonical"], page.to_dict(), snapshots)
                snapshots.extend(((record_path, record_hash), (ocr_path, ocr_hash),
                                  (prepared_path, prepared_hash), (processed_path, processed["sha256"])))
                require(canonical == run["canonical"], "CANONICAL_PIN_MISMATCH")
                hypothesis = "\n".join(block.text for block in page.blocks)
                text_sha = sha256(hypothesis.encode("utf-8")).hexdigest()
            else:
                canonical, hypothesis, text_sha = None, "", None
            prediction = dict(sample_id=sid,
                              status="failed" if page is None or page.recognition_status == "unreadable" else "ok",
                              payload={}, ocr_text=hypothesis)
            scored = evaluate([gold_by_id[sid]], dict(artifact_version="vietdoc.predictions.v1",
                predictions=[prediction], model_version="observed-only",
                normalizer_version="not-applicable", ocr_version=page.ocr_version if page else "unavailable"))
            counts = scored["ocr"]["all"]["counts"]
            for group in ("all", sample["document_type"], sample["augmentation"]["name"],
                          str(sample["row_count"])):
                summaries[profile_index][group].update(counts)
            paired.append(dict(status=run["status"], recognition_status=page.recognition_status if page else "unavailable",
                               ocr_version=page.ocr_version if page else None, blocks=len(page.blocks) if page else 0,
                               canonical=canonical, text_sha256=text_sha,
                               ocr_sha256=ocr_hash if page else None,
                               character_edits=counts.get("character_edits", 0),
                               word_edits=counts.get("word_edits", 0),
                               reference_characters=counts.get("reference_characters", 0),
                               reference_words=counts.get("reference_words", 0),
                               duration_seconds=run.get("duration_seconds"),
                               stage_seconds=run.get("stage_seconds"), memory_bytes=run.get("memory_bytes")))
        if all(row["canonical"] is not None for row in paired):
            require(paired[0]["canonical"] == paired[1]["canonical"], "CANONICAL_CHANGED_BY_PROFILE")
        if all(row["ocr_version"] is not None for row in paired):
            require(paired[0]["ocr_version"] == paired[1]["ocr_version"], "MODEL_VERSION_MISMATCH")
        cases.append(dict(sample_id=sid, document_type=sample["document_type"],
                          variant=sample["augmentation"]["name"], row_count=sample["row_count"],
                          source_sha256=expected_source, baseline=paired[0], candidate=paired[1]))
    snapshots.extend((root / "report.json", pin) for root, pin in zip(
        roots, (baseline_report_sha256, candidate_report_sha256), strict=True))
    require(all(sha(path) == pin for path, pin in snapshots), "SOURCE_CHANGED_DURING_COMPARE")
    result = dict(artifact_version="vietdoc.ocr-profile-compare.v1", scope="exposed dev, Proposed OCR diagnostic",
                  membership_sha256=membership_sha256, sample_ids=sorted(ids),
                  compare_source_sha256=sha(Path(__file__)), evaluator_version=EVALUATOR_VERSION,
                  evaluator_policy=POLICY,
                  input_pins=dict(manifest_sha256=manifest_sha256, baseline_report_sha256=baseline_report_sha256,
                                  candidate_report_sha256=candidate_report_sha256),
                  data_validation=validation, profiles=dict(baseline=baseline_profile, candidate=candidate_profile),
                  accounting=dict(baseline=reports[0]["counts"], candidate=reports[1]["counts"]),
                  metrics={name: {group: _rates(counts) for group, counts in sorted(summary.items())}
                           for name, summary in zip(("baseline", "candidate"), summaries, strict=True)},
                  cases=cases, decision="manual review required; no default change",
                  limitations=["Proposed transcript/order policy", "no detection matching/recall claim",
                               "runtime timings compare only on the pinned same host/runtime"])
    output.mkdir(parents=True, exist_ok=False)
    _write(output / "compare.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("data-root", "manifest", "baseline-root", "candidate-root", "output-dir"):
        parser.add_argument("--" + key, type=Path, required=True)
    for key in ("manifest-sha256", "baseline-report-sha256", "candidate-report-sha256",
                "membership-sha256"):
        parser.add_argument("--" + key, required=True)
    try:
        result = compare(**vars(parser.parse_args(argv)))
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        print("PROFILE_COMPARE_INVALID_OR_IO_ERROR", file=sys.stderr)
        return 2
    print(f"PROFILE_COMPARE_WRITTEN samples={len(result['cases'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
