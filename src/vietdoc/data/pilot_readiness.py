"""Emit a hash-bound, machine-readable pilot readiness decision.

This module reports the state of a prepared snapshot; it never grants pilot
approval, changes membership, or treats predictions as gold.  The artifact is
intended for handoff gates so each consumer can see the same blockers without
re-running an ad-hoc interpretation of ``pilot.py``.

Archive and member readiness require real on-disk hash verification (fail-closed
by default).  Caller-supplied booleans in an asset manifest are never sufficient
to report verified readiness or advance a plan to ``ready_for_consumer_ack``.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .manifest import encoded, read_json, require, sha
from .pilot import plan_files

VERSION = "vietdoc.pilot-readiness.v1"
STATES = {"blocked_membership", "prepared_not_approved", "ready_for_consumer_ack"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_ZIP_MEMBER_BYTES = 50 * 1024 * 1024


def _ref(path: Path) -> dict[str, str]:
    return {"name": path.name, "sha256": sha(path)}


def _is_link(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return path.is_symlink()
    return (
        stat.S_ISLNK(info.st_mode)
        or path.is_symlink()
        or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    )


def _no_links(path: Path) -> bool:
    current = Path(path)
    if not current.is_absolute():
        current = current.absolute()
    return not any(_is_link(part) for part in (current, *current.parents))


def _safe_relative_posix(raw: object) -> PurePosixPath | None:
    if not isinstance(raw, str) or not raw:
        return None
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        return None
    if "\\" in raw or ":" in raw:
        return None
    rel = PurePosixPath(raw)
    if rel.is_absolute() or not rel.parts or any(part in ("", ".", "..") for part in raw.split("/")):
        return None
    return rel


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contained_regular_file(base: Path, raw_rel: object) -> Path | None:
    rel = _safe_relative_posix(raw_rel)
    if rel is None or not _no_links(base):
        return None
    try:
        resolved_base = base.resolve(strict=True)
    except OSError:
        return None
    if not resolved_base.is_dir():
        return None
    current = base
    for part in rel.parts:
        current = current / part
        if _is_link(current):
            return None
    try:
        resolved = current.resolve(strict=True)
    except OSError:
        return None
    if not resolved.is_relative_to(resolved_base) or not resolved.is_file():
        return None
    return current


def _contained_directory(base: Path, raw_rel: object) -> Path | None:
    if raw_rel == ".":
        if not _no_links(base):
            return None
        try:
            resolved = base.resolve(strict=True)
        except OSError:
            return None
        return base if resolved.is_dir() else None
    rel = _safe_relative_posix(raw_rel)
    if rel is None or not _no_links(base):
        return None
    try:
        resolved_base = base.resolve(strict=True)
    except OSError:
        return None
    if not resolved_base.is_dir():
        return None
    current = base
    for part in rel.parts:
        current = current / part
        if _is_link(current):
            return None
    try:
        resolved = current.resolve(strict=True)
    except OSError:
        return None
    if not resolved.is_relative_to(resolved_base) or not resolved.is_dir():
        return None
    return current


def _label_statuses(asset_manifest: dict[str, Any] | None) -> dict[str, int] | None:
    if not isinstance(asset_manifest, dict):
        return None
    counts = asset_manifest.get("counts", {}).get("label_statuses")
    if not isinstance(counts, dict) or any(not isinstance(k, str) or type(v) is not int or v < 0
                                           for k, v in counts.items()):
        return None
    return dict(sorted(counts.items()))


def _verify_archive_on_disk(
    asset: dict[str, Any],
    asset_dir: Path,
    archive_path: Path | str | None,
) -> tuple[bool, Path | None, str | None, str | None]:
    if asset.get("archive_verified") is False:
        return False, None, None, "archive_marked_unverified"
    expected_sha = asset.get("archive_sha256")
    if not isinstance(expected_sha, str) or not _SHA256.fullmatch(expected_sha):
        return False, None, None, "archive_sha256_invalid"

    candidate: Path | None
    if archive_path is not None:
        raw_candidate = Path(archive_path)
        if not _no_links(raw_candidate):
            return False, None, None, "archive_missing_or_unsafe"
        try:
            resolved = raw_candidate.resolve(strict=True)
        except OSError:
            return False, None, None, "archive_missing_or_unsafe"
        if not resolved.is_file():
            return False, None, None, "archive_missing_or_unsafe"
        candidate = raw_candidate
    elif "archive_path" in asset:
        candidate = _contained_regular_file(asset_dir, asset.get("archive_path"))
        if candidate is None:
            return False, None, None, "archive_missing_or_unsafe"
    else:
        return False, None, None, "archive_path_missing"

    try:
        actual_sha = _sha_file(candidate)
    except OSError:
        return False, candidate, None, "archive_io_error"
    if actual_sha != expected_sha:
        return False, candidate, actual_sha, "archive_sha256_mismatch"
    return True, candidate, actual_sha, None


def _expected_member_assets(
    manifest_data: dict[str, Any],
    selected_ids: set[str],
) -> tuple[list[tuple[str, str]] | None, str | None]:
    samples = manifest_data.get("samples")
    if not isinstance(samples, list):
        return None, "manifest_samples_invalid"
    by_id = {
        sample["sample_id"]: sample
        for sample in samples
        if isinstance(sample, dict) and isinstance(sample.get("sample_id"), str)
    }
    expected_assets: list[tuple[str, str]] = []
    seen_paths: dict[str, str] = {}
    for sid in sorted(selected_ids):
        sample = by_id.get(sid)
        if not isinstance(sample, dict):
            return None, "selected_sample_missing_from_manifest"
        assets = sample.get("assets")
        if not isinstance(assets, dict) or not assets:
            return None, "selected_sample_assets_missing"
        for asset_name in sorted(assets):
            entry = assets[asset_name]
            if not isinstance(entry, dict):
                return None, "selected_sample_asset_invalid"
            rel = entry.get("path")
            digest = entry.get("sha256")
            if _safe_relative_posix(rel) is None or not isinstance(digest, str) or not _SHA256.fullmatch(digest):
                return None, "selected_sample_asset_invalid"
            if rel in seen_paths and seen_paths[rel] != digest:
                return None, "selected_sample_asset_conflict"
            seen_paths[rel] = digest
            expected_assets.append((rel, digest))
    return expected_assets, None


def _check_declared_members(
    asset: dict[str, Any],
    expected_map: dict[str, str],
) -> str | None:
    declared = asset.get("members")
    if declared is None:
        return None
    if isinstance(declared, dict):
        items = list(declared.items())
    elif isinstance(declared, list):
        items = []
        for entry in declared:
            if not isinstance(entry, dict):
                return "asset_manifest_members_invalid"
            items.append((entry.get("path"), entry.get("sha256")))
    else:
        return "asset_manifest_members_invalid"
    for rel, digest in items:
        if _safe_relative_posix(rel) is None or not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            return "asset_manifest_members_invalid"
        if rel in expected_map and expected_map[rel] != digest:
            return "asset_manifest_member_sha256_mismatch"
    return None


def _verify_members_in_zip(
    archive_file: Path,
    expected_assets: list[tuple[str, str]],
    archive_prefix: object = None,
) -> tuple[bool, int, str | None]:
    prefix_str = ""
    if archive_prefix is not None and archive_prefix != "":
        prefix_rel = _safe_relative_posix(archive_prefix)
        if prefix_rel is None:
            return False, 0, "unsafe_archive_prefix"
        prefix_str = prefix_rel.as_posix() + "/"

    try:
        with zipfile.ZipFile(archive_file, "r") as zf:
            entries: dict[str, zipfile.ZipInfo] = {}
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if _safe_relative_posix(info.filename) is None:
                    return False, 0, "unsafe_archive_member_path"
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    return False, 0, "unsafe_archive_member_symlink"
                if info.filename in entries:
                    return False, 0, "duplicate_archive_member"
                entries[info.filename] = info

            verified = 0
            for rel_path, expected_sha in expected_assets:
                member_name = prefix_str + rel_path
                info = entries.get(member_name)
                if info is None:
                    return False, verified, "member_missing_or_unsafe"
                if info.file_size > _MAX_ZIP_MEMBER_BYTES:
                    return False, verified, "member_size_exceeded"
                digest = hashlib.sha256()
                total = 0
                with zf.open(info, "r") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        total += len(chunk)
                        if total > _MAX_ZIP_MEMBER_BYTES:
                            return False, verified, "member_size_exceeded"
                        digest.update(chunk)
                if digest.hexdigest() != expected_sha:
                    return False, verified, "member_sha256_mismatch"
                verified += 1
            return True, verified, None
    except (OSError, zipfile.BadZipFile, RuntimeError):
        return False, 0, "archive_zip_invalid"


def _verify_members_on_disk(
    manifest_data: dict[str, Any],
    selected_ids: set[str],
    asset: dict[str, Any],
    manifest_dir: Path,
    asset_dir: Path,
    verified_archive: Path | None,
) -> tuple[bool, int, int, str, str | None]:
    if asset.get("members_verified") is False:
        return False, 0, 0, "none", "members_marked_unverified"
    if not selected_ids:
        return False, 0, 0, "none", "no_selected_members"

    expected_assets, err = _expected_member_assets(manifest_data, selected_ids)
    if err is not None or not expected_assets:
        return False, 0, 0, "none", err or "no_selected_members"

    expected_map = dict(expected_assets)
    decl_err = _check_declared_members(asset, expected_map)
    if decl_err is not None:
        return False, 0, len(expected_assets), "none", decl_err

    member_source_pref = asset.get("member_source")
    if member_source_pref not in (None, "disk", "archive_zip"):
        return False, 0, len(expected_assets), "none", "unsupported_member_source"

    explicit_assets_dir = asset.get("assets_dir")
    use_zip = False
    if explicit_assets_dir is not None:
        if member_source_pref == "archive_zip":
            return False, 0, len(expected_assets), "none", "conflicting_member_source"
        member_root = _contained_directory(asset_dir, explicit_assets_dir)
        if member_root is None:
            return False, 0, len(expected_assets), "disk", "unsafe_assets_dir"
    elif member_source_pref == "archive_zip":
        if verified_archive is None:
            return False, 0, len(expected_assets), "archive_zip", "archive_unverified_for_zip_members"
        use_zip = True
        member_root = manifest_dir
    else:
        member_root = manifest_dir
        if (
            verified_archive is not None
            and _contained_regular_file(member_root, expected_assets[0][0]) is None
            and zipfile.is_zipfile(verified_archive)
        ):
            use_zip = True

    if use_zip:
        assert verified_archive is not None
        ok, count, zerr = _verify_members_in_zip(
            verified_archive,
            expected_assets,
            archive_prefix=asset.get("archive_prefix"),
        )
        return ok, count, len(expected_assets), "archive_zip", zerr

    verified = 0
    for rel_path, expected_sha in expected_assets:
        target = _contained_regular_file(member_root, rel_path)
        if target is None:
            return False, verified, len(expected_assets), "disk", "member_missing_or_unsafe"
        try:
            actual_sha = _sha_file(target)
        except OSError:
            return False, verified, len(expected_assets), "disk", "member_io_error"
        if actual_sha != expected_sha:
            return False, verified, len(expected_assets), "disk", "member_sha256_mismatch"
        verified += 1
    return True, verified, len(expected_assets), "disk", None


def readiness_files(
    root: Path | str,
    manifest_path: Path | str,
    report_path: Path | str,
    review_path: Path | str,
    plan_path: Path | str,
    asset_manifest_path: Path | str | None = None,
    *,
    archive_path: Path | str | None = None,
    verify_disk: bool = True,
) -> dict[str, Any]:
    """Validate the current plan and return a non-approving readiness report.

    ``asset_manifest_path`` is optional because a metadata plan can be produced
    before the renderer archive is available.  In that case archive/member
    verification stays explicitly false and the state cannot advance to the
    consumer-ACK boundary.

    When ``verify_disk`` is True (default, fail-closed), archive and selected
    member hashes are verified on disk (or inside the verified archive zip).
    Caller booleans in ``asset_manifest_path`` alone can never report verified
    readiness; setting ``verify_disk=False`` also keeps verification false.
    """
    require(type(verify_disk) is bool, "verify_disk must be a boolean")
    del root  # kept in the API to mirror pilot_records; D2.2 asset paths are manifest-relative
    paths = [Path(p) for p in (manifest_path, report_path, review_path, plan_path)]
    initial_hashes = [sha(p) for p in paths]
    expected = plan_files(*paths[:3])
    actual = read_json(paths[3])
    require(actual == expected, "pilot plan drift from current inputs")
    manifest_data = read_json(paths[0])
    asset_path = Path(asset_manifest_path) if asset_manifest_path is not None else None
    asset_hash = sha(asset_path) if asset_path is not None else None
    asset = read_json(asset_path) if asset_path is not None else None
    if asset_path is not None:
        require(isinstance(asset, dict), "asset manifest must be an object")

    counts = expected["counts"]
    review = expected["review"]
    unresolved = int(expected["unresolved_candidates"])
    type_split_complete = not expected["missing_type_split_support"]
    selected_ids = {sid for split_ids in expected["members"].values() for sid in split_ids}

    # A readiness claim must be bound to the exact pilot manifest AND backed by
    # real on-disk hash verification.  Bare caller booleans are never trusted.
    asset_manifest_bound = bool(
        isinstance(asset, dict)
        and asset.get("manifest_sha256") == initial_hashes[0]
    )

    archive_verified = False
    members_verified = False
    verified_archive_file: Path | None = None
    verified_archive_sha: str | None = None
    verified_member_files = 0
    expected_member_files = 0
    member_source = "none"
    verification_errors: list[str] = []

    if asset_path is None:
        verification_errors.append("asset_manifest_not_supplied")
    elif not asset_manifest_bound:
        verification_errors.append("asset_manifest_unbound")
    elif not verify_disk:
        verification_errors.append("disk_verification_disabled")
    else:
        assert isinstance(asset, dict)
        archive_verified, verified_archive_file, verified_archive_sha, arch_err = _verify_archive_on_disk(
            asset,
            asset_path.parent,
            archive_path,
        )
        if arch_err is not None:
            verification_errors.append(arch_err)
        members_verified, verified_member_files, expected_member_files, member_source, mem_err = (
            _verify_members_on_disk(
                manifest_data,
                selected_ids,
                asset,
                paths[0].parent,
                asset_path.parent,
                verified_archive_file if archive_verified else None,
            )
        )
        if mem_err is not None:
            verification_errors.append(mem_err)

    require(all(sha(p) == h for p, h in zip(paths, initial_hashes)), "readiness inputs changed")
    if asset_path is not None:
        require(sha(asset_path) == asset_hash, "asset manifest changed during readiness check")

    technical_ready = (
        expected["status"] == "prepared_not_approved"
        and unresolved == 0
        and type_split_complete
        and verify_disk
        and archive_verified
        and members_verified
    )
    state = "ready_for_consumer_ack" if technical_ready else expected["status"]
    require(state in STATES, "unsupported readiness state")

    dispositions = review.get("dispositions", {})
    label_statuses = _label_statuses(asset)
    inputs: dict[str, Any] = {
        "manifest": _ref(paths[0]),
        "report": _ref(paths[1]),
        "review": _ref(paths[2]),
        "plan": _ref(paths[3]),
    }
    if asset_path is not None:
        inputs["asset_manifest"] = _ref(asset_path)
    if archive_verified and verified_archive_file is not None and verified_archive_sha is not None:
        inputs["archive"] = {"name": verified_archive_file.name, "sha256": verified_archive_sha}

    return {
        "artifact_version": VERSION,
        "state": state,
        "approval": "not_granted",
        "scope": "metadata/readiness reporting only; no visual approval, pilot freeze, consumer ACK or training acceptance",
        "counts": {
            "before": counts["before"],
            "after": counts["after"],
            "unresolved_candidates": unresolved,
            "pending_dispositions": int(dispositions.get("pending", 0)),
            "ambiguous_dispositions": int(dispositions.get("ambiguous", 0)),
            "label_statuses": label_statuses,
        },
        "membership": {
            "missing_type_split_support": list(expected["missing_type_split_support"]),
            "risk_components": len(expected["risk_components"]),
            "excluded_decisions": len(expected["excluded"]),
        },
        "verification": {
            "archive_verified": archive_verified,
            "members_verified": members_verified,
            "asset_manifest_bound": asset_manifest_bound,
            "asset_manifest_supplied": asset_path is not None,
            "verify_disk": verify_disk,
            "member_verification_source": member_source,
            "verified_member_files": verified_member_files,
            "expected_member_files": expected_member_files,
            "errors": verification_errors,
        },
        "prerequisites": [
            "external visual/content/lineage review and reviewer identity",
            "archive and every selected member hash verified",
            "AI1 OCR handoff and AI2 consumer ACK",
            "Lead approval of grouping/splits before any pilot use",
        ],
        "inputs": inputs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--asset-manifest", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument(
        "--verify-disk",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Verify archive and selected member hashes on disk (fail-closed; default: enabled).",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "output already exists")
    result = readiness_files(
        args.root,
        args.manifest,
        args.report,
        args.review,
        args.plan,
        args.asset_manifest,
        archive_path=args.archive,
        verify_disk=args.verify_disk,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(encoded(result))
    print(encoded({"state": result["state"], "approval": result["approval"]}).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
