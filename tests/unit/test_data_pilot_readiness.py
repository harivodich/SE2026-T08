"""Readiness reporting is hash-bound, disk-verified, and never an approval."""

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from vietdoc.data.duplicate_review import VERSION as REVIEW_VERSION
from vietdoc.data.manifest import encoded, sha
from vietdoc.data.pilot import plan_files
from vietdoc.data.pilot_readiness import readiness_files
from vietdoc.data.splits import duplicate_report

ROOT = Path(__file__).resolve().parents[2]
MANIFESTS = ROOT / "datasets/manifests"


def _build_prepared_snapshot(base_dir: Path) -> tuple[Path, Path, Path, Path, list[tuple[str, bytes]]]:
    """Create a minimal prepared_not_approved D2.2 fixture (0 unresolved, complete type/split)."""
    specs = [
        ("r-train-01", "receipt", "train", "0000000000000000"),
        ("r-dev-01", "receipt", "dev", "ffffffffffffffff"),
        ("i-train-01", "invoice", "train", "00000000ffffffff"),
        ("i-dev-01", "invoice", "dev", "ffff0000ffff0000"),
    ]
    samples = []
    member_files: list[tuple[str, bytes]] = []
    for idx, (base_id, doc_type, split, dhash) in enumerate(specs):
        sid = f"{base_id}-clean"
        png_bytes = f"synthetic-png-{sid}-{idx}".encode()
        gold_bytes = encoded({"sample": sid, "type": doc_type})
        png_name = f"{sid}.png"
        gold_name = f"{sid}.gold.json"
        (base_dir / png_name).write_bytes(png_bytes)
        (base_dir / gold_name).write_bytes(gold_bytes)
        member_files.extend([(png_name, png_bytes), (gold_name, gold_bytes)])
        samples.append(
            {
                "sample_id": sid,
                "base_id": base_id,
                "family_id": f"{doc_type}-fam-{split}",
                "source_group": f"src-{doc_type}-{split}",
                "assignment_group": f"grp-{doc_type}-{split}",
                "document_type": doc_type,
                "split": split,
                "quality": "clean",
                "dhash": dhash,
                "content_sha256": hashlib.sha256(f"content-{sid}".encode()).hexdigest(),
                "content_tokens": [hashlib.sha256(f"tok-{sid}-{idx}".encode()).hexdigest()],
                "assets": {
                    "png": {"path": png_name, "sha256": hashlib.sha256(png_bytes).hexdigest()},
                    "gold.json": {"path": gold_name, "sha256": hashlib.sha256(gold_bytes).hexdigest()},
                },
            }
        )

    report = {"leakage": duplicate_report(samples)}
    report_path = base_dir / "report.json"
    report_path.write_bytes(encoded(report))

    manifest = {
        "version": "d2.2.v1",
        "final_frozen": False,
        "report": {"path": "report.json", "sha256": sha(report_path)},
        "samples": samples,
    }
    manifest_path = base_dir / "manifest.json"
    manifest_path.write_bytes(encoded(manifest))

    review = {
        "version": REVIEW_VERSION,
        "manifest": {"name": "manifest.json", "sha256": sha(manifest_path)},
        "report": {"name": "report.json", "sha256": sha(report_path)},
        "dispositions": [],
    }
    review_path = base_dir / "review.json"
    review_path.write_bytes(encoded(review))

    plan = plan_files(manifest_path, report_path, review_path)
    assert plan["status"] == "prepared_not_approved"
    plan_path = base_dir / "plan.json"
    plan_path.write_bytes(encoded(plan))
    return manifest_path, report_path, review_path, plan_path, member_files


class PilotReadinessTest(unittest.TestCase):
    def test_current_snapshot_is_blocked_and_never_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = []
            for name in ("d22-smoke-v01.json", "d22-report-v01.json", "d22-duplicate-review-20261122-batch01.json"):
                target = root / name
                target.write_bytes((MANIFESTS / name).read_bytes())
                paths.append(target)
            plan = root / "plan.json"
            plan.write_bytes(encoded(plan_files(*paths)))
            result = readiness_files(root, *paths, plan)
            self.assertEqual(result["state"], "blocked_membership")
            self.assertEqual(result["approval"], "not_granted")
            self.assertEqual(result["counts"]["unresolved_candidates"], 71)
            self.assertFalse(result["verification"]["archive_verified"])

    def test_false_archive_flags_cannot_advance_a_blocked_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = []
            for name in ("d22-smoke-v01.json", "d22-report-v01.json", "d22-duplicate-review-20261122-batch01.json"):
                target = root / name
                target.write_bytes((MANIFESTS / name).read_bytes())
                paths.append(target)
            plan = root / "plan.json"
            plan.write_bytes(encoded(plan_files(*paths)))
            asset = root / "assets.json"
            asset.write_bytes(encoded({"archive_verified": True, "members_verified": True,
                                       "counts": {"label_statuses": {"present": 1}}}))
            result = readiness_files(root, *paths, plan, asset)
            self.assertEqual(result["state"], "blocked_membership")
            self.assertEqual(result["counts"]["label_statuses"], {"present": 1})

    def test_caller_booleans_alone_cannot_advance_prepared_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path, report_path, review_path, plan_path, member_files = _build_prepared_snapshot(root)
            for rel_name, _ in member_files:
                (root / rel_name).unlink()
            asset = root / "assets.json"
            asset.write_bytes(
                encoded(
                    {
                        "manifest_sha256": sha(manifest_path),
                        "archive_verified": True,
                        "archive_sha256": "a" * 64,
                        "members_verified": True,
                    }
                )
            )
            result = readiness_files(root, manifest_path, report_path, review_path, plan_path, asset)
            self.assertEqual(result["state"], "prepared_not_approved")
            self.assertEqual(result["approval"], "not_granted")
            self.assertTrue(result["verification"]["asset_manifest_bound"])
            self.assertFalse(result["verification"]["archive_verified"])
            self.assertFalse(result["verification"]["members_verified"])
            self.assertIn("archive_path_missing", result["verification"]["errors"])
            self.assertIn("member_missing_or_unsafe", result["verification"]["errors"])

    def test_verify_disk_false_fails_closed_even_with_real_files_and_booleans(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path, report_path, review_path, plan_path, _ = _build_prepared_snapshot(root)
            archive = root / "pilot.zip"
            archive.write_bytes(b"real-archive-bytes")
            asset = root / "assets.json"
            asset.write_bytes(
                encoded(
                    {
                        "manifest_sha256": sha(manifest_path),
                        "archive_path": "pilot.zip",
                        "archive_sha256": sha(archive),
                        "archive_verified": True,
                        "members_verified": True,
                    }
                )
            )
            result = readiness_files(
                root,
                manifest_path,
                report_path,
                review_path,
                plan_path,
                asset,
                verify_disk=False,
            )
            self.assertEqual(result["state"], "prepared_not_approved")
            self.assertEqual(result["approval"], "not_granted")
            self.assertFalse(result["verification"]["verify_disk"])
            self.assertFalse(result["verification"]["archive_verified"])
            self.assertFalse(result["verification"]["members_verified"])
            self.assertIn("disk_verification_disabled", result["verification"]["errors"])

    def test_verified_disk_archive_and_members_advance_without_granting_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path, report_path, review_path, plan_path, member_files = _build_prepared_snapshot(root)
            archive = root / "pilot-archive.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                for rel_name, content in member_files:
                    zf.writestr(rel_name, content)
            asset = root / "assets.json"
            asset.write_bytes(
                encoded(
                    {
                        "manifest_sha256": sha(manifest_path),
                        "archive_path": "pilot-archive.zip",
                        "archive_sha256": sha(archive),
                        "counts": {"label_statuses": {"present": 8}},
                    }
                )
            )
            result = readiness_files(root, manifest_path, report_path, review_path, plan_path, asset)
            self.assertEqual(result["state"], "ready_for_consumer_ack")
            self.assertEqual(result["approval"], "not_granted")
            self.assertTrue(result["verification"]["archive_verified"])
            self.assertTrue(result["verification"]["members_verified"])
            self.assertEqual(result["verification"]["member_verification_source"], "disk")
            self.assertEqual(result["verification"]["verified_member_files"], len(member_files))
            self.assertEqual(result["verification"]["expected_member_files"], len(member_files))
            self.assertEqual(result["verification"]["errors"], [])
            self.assertEqual(result["inputs"]["archive"]["sha256"], sha(archive))

    def test_verified_zip_archive_verifies_members_without_loose_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src"
            src.mkdir()
            manifest_path, report_path, review_path, plan_path, member_files = _build_prepared_snapshot(src)

            zip_only = root / "zip_only"
            zip_only.mkdir()
            for p in (manifest_path, report_path, review_path, plan_path):
                (zip_only / p.name).write_bytes(p.read_bytes())
            archive = zip_only / "pilot-bundle.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                for rel_name, content in member_files:
                    zf.writestr(rel_name, content)
            asset = zip_only / "assets.json"
            asset.write_bytes(
                encoded(
                    {
                        "manifest_sha256": sha(zip_only / "manifest.json"),
                        "archive_path": "pilot-bundle.zip",
                        "archive_sha256": sha(archive),
                    }
                )
            )
            result = readiness_files(
                zip_only,
                zip_only / "manifest.json",
                zip_only / "report.json",
                zip_only / "review.json",
                zip_only / "plan.json",
                asset,
            )
            self.assertEqual(result["state"], "ready_for_consumer_ack")
            self.assertEqual(result["approval"], "not_granted")
            self.assertTrue(result["verification"]["archive_verified"])
            self.assertTrue(result["verification"]["members_verified"])
            self.assertEqual(result["verification"]["member_verification_source"], "archive_zip")
            self.assertEqual(result["verification"]["verified_member_files"], len(member_files))

    def test_tampered_archive_member_missing_or_traversal_fails_closed(self):
        cases = (
            "tampered_archive",
            "tampered_loose_member",
            "missing_loose_member",
            "archive_traversal",
            "tampered_zip_member",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                work = root / "work"
                work.mkdir()
                manifest_path, report_path, review_path, plan_path, member_files = _build_prepared_snapshot(work)
                archive = work / "pilot.zip"
                with zipfile.ZipFile(archive, "w") as zf:
                    for rel_name, content in member_files:
                        zf.writestr(rel_name, content)
                asset_payload = {
                    "manifest_sha256": sha(manifest_path),
                    "archive_path": "pilot.zip",
                    "archive_sha256": sha(archive),
                    "archive_verified": True,
                    "members_verified": True,
                }

                if case == "tampered_archive":
                    archive.write_bytes(archive.read_bytes() + b"x")
                    expected_error = "archive_sha256_mismatch"
                elif case == "tampered_loose_member":
                    (work / member_files[0][0]).write_bytes(b"corrupted-member")
                    expected_error = "member_sha256_mismatch"
                elif case == "missing_loose_member":
                    (work / member_files[0][0]).unlink()
                    expected_error = "member_missing_or_unsafe"
                elif case == "archive_traversal":
                    outside = root / "escape.zip"
                    outside.write_bytes(archive.read_bytes())
                    asset_payload["archive_path"] = "../escape.zip"
                    expected_error = "archive_missing_or_unsafe"
                else:
                    # Remove loose files so verification reads from zip, then tamper one zip member
                    # and recompute archive_sha256 so the archive hash passes while member hash fails.
                    for rel_name, _ in member_files:
                        (work / rel_name).unlink()
                    with zipfile.ZipFile(archive, "w") as zf:
                        for idx, (rel_name, content) in enumerate(member_files):
                            zf.writestr(rel_name, b"tampered" if idx == 0 else content)
                    asset_payload["archive_sha256"] = sha(archive)
                    expected_error = "member_sha256_mismatch"

                asset = work / "assets.json"
                asset.write_bytes(encoded(asset_payload))
                result = readiness_files(work, manifest_path, report_path, review_path, plan_path, asset)
                self.assertEqual(result["state"], "prepared_not_approved")
                self.assertEqual(result["approval"], "not_granted")
                self.assertIn(expected_error, result["verification"]["errors"])
                if case == "tampered_zip_member":
                    self.assertTrue(result["verification"]["archive_verified"])
                    self.assertFalse(result["verification"]["members_verified"])

    def test_blocked_plan_remains_blocked_even_with_verified_disk_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = []
            for name in ("d22-smoke-v01.json", "d22-report-v01.json", "d22-duplicate-review-20261122-batch01.json"):
                target = root / name
                target.write_bytes((MANIFESTS / name).read_bytes())
                paths.append(target)
            plan = root / "plan.json"
            plan.write_bytes(encoded(plan_files(*paths)))
            archive = root / "blocked-snapshot.zip"
            archive.write_bytes(b"archive-for-blocked-snapshot")
            asset = root / "assets.json"
            asset.write_bytes(
                encoded(
                    {
                        "manifest_sha256": sha(paths[0]),
                        "archive_path": "blocked-snapshot.zip",
                        "archive_sha256": sha(archive),
                    }
                )
            )
            result = readiness_files(root, *paths, plan, asset)
            self.assertEqual(result["state"], "blocked_membership")
            self.assertEqual(result["approval"], "not_granted")
            self.assertTrue(result["verification"]["archive_verified"])
            self.assertFalse(result["verification"]["members_verified"])
            self.assertIn("no_selected_members", result["verification"]["errors"])


if __name__ == "__main__":
    unittest.main()
