"""Build and safely receive bounded non-final pilot inputs; never grant approval."""

import argparse
import hashlib
import shutil
import stat
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

from PIL import Image

from .adapters.records import training_packet
from .duplicate_review import VERSION as REVIEW_VERSION
from .duplicate_review import candidates
from .generator import d22
from .generator.handoff import member_name
from .manifest import asset_path, encoded, read_json, require, sha
from .pilot import plan_files
from .splits import duplicate_report

VERSION = "vietdoc.pilot-input-packet.v1"
ARCHIVE = "pilot-inputs.zip"
SCHEMA = "specs/contracts/business.schema.json"
MAX_BYTES = 1024 * 1024 * 1024
MAX_MEMBER_BYTES = 50 * 1024 * 1024


def _safe_names(names):
    folded = set()
    reserved = {"CON", "PRN", "AUX", "NUL"} | {
        f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)
    }
    for name in names:
        member_name(name)
        require(not any(c in name for c in '<>"|?*\x7f'), "unsafe portable bundle path")
        require(name.casefold() not in folded, "duplicate/casefold bundle path")
        for part in name.split("/"):
            require(
                not part.endswith((" ", "."))
                and part.split(".")[0].upper() not in reserved,
                "unsafe Windows bundle path",
            )
        folded.add(name.casefold())


def _no_links(path):
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            require(
                not stat.S_ISLNK(info.st_mode)
                and not getattr(info, "st_file_attributes", 0) & 0x400,
                "linked packet path",
            )


def _validate_records(root):
    manifest = root / "dataset/manifest.json"
    data = read_json(manifest)
    require(
        data.get("version") == d22.VERSION and data.get("final_frozen") is False,
        "requires non-frozen D22 inputs",
    )
    require(0 < len(data["samples"]) <= 200, "packet sample bound [1,200]")
    require(
        all(
            s["split"] in ("train", "dev") and not s["family_id"].endswith(("08", "09"))
            for s in data["samples"]
        ),
        "final family/member forbidden",
    )
    expected = {
        SCHEMA,
        "dataset/manifest.json",
        "dataset/manifest.sha256",
        "dataset/report.json",
        "records.json",
        "review.json",
        "plan.json",
        "qa.json",
    }
    expected.update(
        "dataset/" + a["path"] for s in data["samples"] for a in s["assets"].values()
    )
    names = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    require(names == expected, "unexpected/missing snapshot member")
    screening = duplicate_report(data["samples"])
    require(
        read_json(root / "dataset/report.json")["leakage"] == screening,
        "duplicate screening drift",
    )
    actual = training_packet(root, manifest)
    require(
        read_json(root / "records.json") == actual, "records join/status/gold drift"
    )
    qa = read_json(root / "qa.json")
    require(
        qa.get("training_clearance") is False and qa.get("human_review") == "pending",
        "packet cannot assert approval",
    )
    pixel_records = []
    for sample in data["samples"]:
        with Image.open(
            asset_path(manifest.parent, sample["assets"]["png"]["path"])
        ) as image:
            pixel_records.append(
                {
                    "sample_id": sample["sample_id"],
                    "mode": image.mode,
                    "size": list(image.size),
                    "dtype": "uint8",
                    "layout": "HWC",
                    "range": [0, 255],
                    "pixel_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
                }
            )
    require(qa["pixels"] == pixel_records, "decoded image pixel drift")
    require(
        read_json(root / "plan.json")
        == plan_files(manifest, root / "dataset/report.json", root / "review.json"),
        "membership plan drift",
    )
    return actual


def pack(snapshot, output):
    """Archive all validated input members, retaining quarantined risk members."""
    snapshot, output = Path(snapshot), Path(output)
    require(not output.exists(), "output already exists")
    _no_links(snapshot.absolute())
    packet = _validate_records(snapshot)
    names = sorted(
        p.relative_to(snapshot).as_posix() for p in snapshot.rglob("*") if p.is_file()
    )
    _safe_names(names)
    files = {}
    for name in names:
        path = asset_path(snapshot, name)
        _no_links(path)
        files[name] = {"sha256": sha(path), "size": path.stat().st_size}
    require(
        all(f["size"] <= MAX_MEMBER_BYTES for f in files.values())
        and sum(f["size"] for f in files.values()) <= MAX_BYTES,
        "packet byte bound",
    )
    output.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(
        output / ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for name, record in files.items():
            content = asset_path(snapshot, name).read_bytes()
            require(
                hashlib.sha256(content).hexdigest() == record["sha256"],
                "snapshot changed",
            )
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    transfer = {
        "artifact_version": VERSION,
        "archive": ARCHIVE,
        "archive_sha256": sha(output / ARCHIVE),
        "files": files,
        "counts": packet["counts"],
        "manifest": packet["manifest"],
        "approval": "not_granted",
        "training_clearance": False,
        "scope": "real OCR/QA inputs including quarantined members; not training membership",
    }
    (output / "transfer.json").write_bytes(encoded(transfer))
    return transfer


def verify(bundle, output):
    """Check all members before extraction and rejoin records in a fresh root."""
    bundle, output = Path(bundle).absolute(), Path(output).absolute()
    _no_links(bundle)
    _no_links(bundle / "transfer.json")
    _no_links(output)
    require(not output.exists(), "output already exists")
    data = read_json(bundle / "transfer.json")
    require(
        data.get("artifact_version") == VERSION and data.get("archive") == ARCHIVE,
        "unsupported packet",
    )
    archive_path = asset_path(bundle, ARCHIVE)
    require(sha(archive_path) == data["archive_sha256"], "archive checksum mismatch")
    files = data["files"]
    require(isinstance(files, dict) and 1 <= len(files) <= 1300, "member count bound")
    _safe_names(files)
    for record in files.values():
        require(
            type(record["size"]) is int
            and 0 <= record["size"] <= MAX_MEMBER_BYTES
            and isinstance(record["sha256"], str)
            and len(record["sha256"]) == 64,
            "invalid member inventory",
        )
    require(sum(r["size"] for r in files.values()) <= MAX_BYTES, "packet byte bound")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="pilot-receiver-", dir=output.parent
    ) as temporary:
        stage = Path(temporary)
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            _safe_names([i.filename for i in infos])
            require(
                len(infos) == len(files) and {i.filename for i in infos} == set(files),
                "missing/unknown archive member",
            )
            for info in infos:
                record = files[info.filename]
                require(
                    stat.S_ISREG(info.external_attr >> 16)
                    and not info.flag_bits & 1
                    and info.file_size == record["size"],
                    "nonregular/encrypted/size mismatch member",
                )
                content = archive.read(info)
                require(
                    hashlib.sha256(content).hexdigest() == record["sha256"],
                    "member checksum mismatch",
                )
                path = stage / info.filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        packet = _validate_records(stage)
        require(
            packet["counts"] == data["counts"]
            and packet["manifest"] == data["manifest"],
            "transfer count/manifest drift",
        )
        stage.rename(output)
    return {
        "verified": True,
        "members": len(files),
        "counts": packet["counts"],
        "approval": "not_granted",
        "training_clearance": False,
    }


def build(root, output, config_path, font, seed=20261126, base_limit=40):
    root, output, font = Path(root), Path(output), Path(font)
    config = d22.validate_config(read_json(config_path))
    assignments = d22.plan(config, seed)
    require(
        type(base_limit) is int and 1 <= base_limit <= 40, "pilot base limit [1,40]"
    )
    require(
        len(assignments) <= base_limit
        and len(assignments) * (1 + len(config["augmentations"])) <= 200,
        "pilot population bound",
    )
    require(
        all(r["split"] in ("train", "dev") for r in assignments),
        "final family forbidden",
    )
    require(not output.exists(), "output already exists")
    output.mkdir(parents=True)
    snapshot = output / "snapshot"
    (snapshot / "specs/contracts").mkdir(parents=True)
    shutil.copyfile(root / SCHEMA, snapshot / SCHEMA)
    manifest = d22.build(
        root, snapshot / "dataset", config_path, seed, font, base_limit
    )
    # Exact rerender verifies encoded bytes, labels, geometry, transcript and pixels.
    canonical = d22.validate(root, snapshot / "dataset/manifest.json", font)
    records = training_packet(snapshot, snapshot / "dataset/manifest.json")
    (snapshot / "records.json").write_bytes(encoded(records))
    pairs = candidates(
        snapshot / "dataset/manifest.json", snapshot / "dataset/report.json"
    )
    review = {
        "version": REVIEW_VERSION,
        "manifest": {
            "name": "manifest.json",
            "sha256": sha(snapshot / "dataset/manifest.json"),
        },
        "report": {
            "name": "report.json",
            "sha256": sha(snapshot / "dataset/report.json"),
        },
        "dispositions": [
            {
                "candidate_id": key,
                "base_ids": pair["base_ids"],
                "disposition": "pending",
                "reason": "Automated screening only; image/content/lineage review required.",
                "reviewer": "AI-assisted Data automation; no human verdict",
                "evidence": {"image": False, "content": False, "lineage": False},
            }
            for key, pair in pairs.items()
        ],
    }
    (snapshot / "review.json").write_bytes(encoded(review))
    plan = plan_files(
        snapshot / "dataset/manifest.json",
        snapshot / "dataset/report.json",
        snapshot / "review.json",
    )
    (snapshot / "plan.json").write_bytes(encoded(plan))
    pixels = []
    for sample in manifest["samples"]:
        with Image.open(
            snapshot / "dataset" / sample["assets"]["png"]["path"]
        ) as image:
            pixels.append(
                {
                    "sample_id": sample["sample_id"],
                    "mode": image.mode,
                    "size": list(image.size),
                    "dtype": "uint8",
                    "layout": "HWC",
                    "range": [0, 255],
                    "pixel_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
                }
            )
    qa = {
        "artifact_version": VERSION,
        "review_kind": "AI-assisted automated; no human approval",
        "canonical_rerender": canonical,
        "records_join_samples": len(records["records"]),
        "pixels": pixels,
        "requested_bases": len(assignments),
        "generated_bases": canonical["base_documents"],
        "requested_variants": len(assignments) * (1 + len(config["augmentations"])),
        "generated_variants": len(manifest["samples"]),
        "exclusions": read_json(snapshot / "dataset/report.json")["exclusions"],
        "row_counts": dict(Counter(str(r["row_count"]) for r in assignments)),
        "overflow": "renderer fails explicitly on clipping; no dropped text/rows",
        "unresolved_pairs": len(pairs),
        "membership_status": plan["status"],
        "human_review": "pending",
        "consumer_ack": "pending",
        "training_clearance": False,
    }
    (snapshot / "qa.json").write_bytes(encoded(qa))
    return pack(snapshot, output / "packet")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    builder = sub.add_parser("build")
    for key in ("root", "output", "config", "font"):
        builder.add_argument("--" + key, type=Path, required=True)
    builder.add_argument("--seed", type=int, default=20261126)
    builder.add_argument("--base-limit", type=int, default=40)
    receiver = sub.add_parser("verify")
    receiver.add_argument("--bundle", type=Path, required=True)
    receiver.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "build":
        result = build(
            args.root, args.output, args.config, args.font, args.seed, args.base_limit
        )
        result = {k: v for k, v in result.items() if k != "files"}
    else:
        result = verify(args.bundle, args.output)
    print(encoded(result).decode(), end="")


if __name__ == "__main__":
    main()
