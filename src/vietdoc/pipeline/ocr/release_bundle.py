"""Assemble verified B0/v1 and opt-in B0/v2 releases from existing OCR bytes.

The original configuration ZIP and four pinned model files are inputs. No
download, overwrite, or mutation of the historical B0/v1 release is allowed.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import stat
import sys
from tempfile import TemporaryDirectory
import zipfile

from vietdoc.data.manifest import require, sha
from vietdoc.ml.release_manifest import load_release
from vietdoc.pipeline.composition import PROFILE, checked_profile
from vietdoc.pipeline.ocr.paddle_adapter import MODELS, _verify_model


CONFIG_ZIP_SHA256 = "03a549e4b171574b6d1c9420fa90454546b52891f6ee4686a67f7936f78fee91"
ORIGINAL_MANIFEST_SHA256 = "b068daed7889becb4b7531bdf7a057dbe05ad3f7f82938d9b8fbfbe71d39890a"
ORIGINAL_PROFILE_SHA256 = "0f44cb5f9bd6253bb0ce632165ce6aff1c7be5983a1def5bc1a62ca42e29e4ef"
V1 = "b0-native-v1"
V2 = "b0-native-v2-ai1-r5"
ZIP_MEMBERS = {V1 + "/pipeline.json", V1 + "/manifest.json",
               "README-GUI-AI1.md", "TIN-NHAN-GUI-AI1.md", "verification.json"}


def _config(zip_path):
    require(sha(zip_path) == CONFIG_ZIP_SHA256, "CONFIG_ZIP_PIN_MISMATCH")
    with zipfile.ZipFile(zip_path) as archive:
        members = archive.infolist()
        require(len(members) == len(ZIP_MEMBERS) and {m.filename for m in members} == ZIP_MEMBERS,
                "CONFIG_ZIP_MEMBERS_MISMATCH")
        require(all(not m.is_dir() and m.file_size <= 8192 and m.file_size > 0 and
                    stat.S_IFMT(m.external_attr >> 16) == stat.S_IFREG for m in members),
                "CONFIG_ZIP_UNSAFE_MEMBER")
        profile = archive.read(V1 + "/pipeline.json")
        manifest = archive.read(V1 + "/manifest.json")
    require(sha256(profile).hexdigest() == ORIGINAL_PROFILE_SHA256 and
            sha256(manifest).hexdigest() == ORIGINAL_MANIFEST_SHA256,
            "CONFIG_MEMBER_PIN_MISMATCH")
    return profile, manifest


def _model_entries(model_root):
    entries = []
    for model, spec in MODELS.items():
        source = model_root / (model + "_infer")
        _verify_model(source, spec)
        for filename, digest in spec["files"].items():
            path = source / filename
            entries.append(dict(path=f"ocr/{model}_infer/{filename}",
                                size_bytes=path.stat().st_size, sha256=digest))
    return sorted(entries, key=lambda entry: entry["path"])


def assemble(*, config_zip, model_root, output_root):
    """Verify every input, stage both releases, verify again, then publish once."""
    config_zip, model_root, output = map(Path, (config_zip, model_root, output_root))
    require(not output.exists() and output.parent.is_dir(), "OUTPUT_EXISTS_OR_PARENT_MISSING")
    profile, original_manifest = _config(config_zip)
    entries = _model_entries(model_root)
    declaration = json.loads(original_manifest.decode("utf-8"))
    require(declaration == dict(manifest_version=1, pipeline_manifest_id=V1,
                                files=[dict(path="pipeline.json", size_bytes=len(profile),
                                            sha256=ORIGINAL_PROFILE_SHA256), *entries]),
            "ORIGINAL_ENGINE_INVENTORY_MISMATCH")
    generated_profile = json.dumps(dict(PROFILE, profile_version=2, ocr_artifact_version=2),
                                   ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    generated_entry = dict(path="pipeline.json", size_bytes=len(generated_profile),
                           sha256=sha256(generated_profile).hexdigest())
    with TemporaryDirectory(prefix=".ai1-release-", dir=output.parent) as temporary:
        stage = Path(temporary) / "releases"
        stage.mkdir()
        for release_id, config, manifest in ((V1, profile, original_manifest),
                (V2, generated_profile, json.dumps(dict(manifest_version=1,
                    pipeline_manifest_id=V2, files=[generated_entry, *entries]),
                    ensure_ascii=False, indent=2).encode("utf-8") + b"\n")):
            target = stage / release_id
            target.mkdir()
            (target / "pipeline.json").write_bytes(config)
            (target / "manifest.json").write_bytes(manifest)
            for entry in entries:
                relative = Path(entry["path"])
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(model_root / relative.relative_to("ocr"), destination)
            release = load_release(stage, release_id)
            checked_profile(release, ocr_artifact_version=2 if release_id == V2 else 1)
            require({item.path for item in release.files} == {"pipeline.json", *(e["path"] for e in entries)}
                    and {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()} ==
                    {"manifest.json", "pipeline.json", *(e["path"] for e in entries)},
                    "RELEASE_FILE_SET_MISMATCH")
            _model_entries(target / "ocr")
        require(sha(config_zip) == CONFIG_ZIP_SHA256 and _model_entries(model_root) == entries,
                "INPUT_CHANGED_DURING_ASSEMBLY")
        stage.rename(output)
    return dict(config_zip_sha256=CONFIG_ZIP_SHA256, original_manifest_sha256=ORIGINAL_MANIFEST_SHA256,
                original_profile_sha256=ORIGINAL_PROFILE_SHA256,
                releases={release_id: dict(manifest_sha256=sha(output / release_id / "manifest.json"),
                                           profile_sha256=sha(output / release_id / "pipeline.json"))
                          for release_id in (V1, V2)})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("config-zip", "model-root", "output-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    try:
        result = assemble(**vars(parser.parse_args(argv)))
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile):
        print("RELEASE_ASSEMBLY_INVALID_OR_IO_ERROR", file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
