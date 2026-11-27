"""Emit small fictional OCR/evidence cases for independent consumer review.

The images and OCR are hand-authored test data, never native quality evidence.
Every case has an input/canonical image, typed OCR and transform, expected
evidence outcome, hashes, and a preview overlay where geometry is available.
"""
import argparse
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import shutil

from PIL import Image, ImageDraw, ImageFont

from vietdoc.contracts.ocr import ImageInfo, OcrBlock, OcrPage, PreparedPage, UnreadableRegion
from vietdoc.pipeline.evidence import EvidenceRequest, match_evidence
from vietdoc.pipeline.ocr.paddle_adapter import draw_overlay


def _block(block_id, text, x, y, width=.3, score=.8):
    return OcrBlock(block_id, text, ((x, y), (x + width, y),
        (x + width, y + .05), (x, y + .05)), score, None)


def _bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def build(*, output_root, font_path):
    output, font_path = Path(output_root), Path(font_path)
    if output.exists() or not output.parent.is_dir():
        raise ValueError("OUTPUT_EXISTS_OR_PARENT_MISSING")
    font = ImageFont.truetype(str(font_path), 23)
    info = ImageInfo(800, 600, "RGB", "uint8")
    prepared = PreparedPage(0, info, info, "fictional.consumer.v1", "available",
                            ((1, 0, 0), (0, 1, 0), (0, 0, 1)), None)
    blocks = (
        _block("description", "Bánh mì", .1, .1),
        _block("line-amount", "45.000", .65, .1, score=.87),
        _block("wrap", "loại nhỏ", .1, .16),
        _block("total-label", "Tổng tiền", .1, .7),
        _block("total-amount", "45.000", .65, .7, score=.93),
    )
    page = OcrPage(0, 800, 600, "fictional-ocr.v2", blocks, artifact_version=2)
    partial = replace(page, blocks=(blocks[0],), unreadable_regions=(
        UnreadableRegion("unreadable-amount", blocks[1].quad, 0, None),))
    unavailable = replace(page, blocks=(replace(blocks[0], quad=None,
                                                 geometry_reason="NO_MAPPING"),))
    blank = replace(page, blocks=())
    cases = [
        ("matched-total", page, prepared, EvidenceRequest("/total_amount", "45.000",
            ("total-label", "total-amount"), "Tổng tiền"), "matched", ("total-amount",)),
        ("ambiguous-total", page, prepared, EvidenceRequest("/total_amount", "45.000"),
            "ambiguous", ()),
        ("wrapped-description", page, prepared, EvidenceRequest("/items/0/description",
            "Bánh mì loại nhỏ", ("description", "wrap")), "matched", ("description", "wrap")),
        ("partial-readable", partial, prepared, EvidenceRequest("/items/0/description",
            "Bánh mì", ("description",)), "matched", ("description",)),
        ("geometry-unavailable", unavailable, prepared, EvidenceRequest("/items/0/description",
            "Bánh mì"), "geometry_unavailable", ()),
        ("no-detection", blank, prepared, EvidenceRequest("/total_amount", "45.000"),
            "not_found", ()),
    ]
    output.mkdir()
    manifest = dict(artifact_version="vietdoc.ai1-consumer-packet.v1", synthetic=True,
                    font_sha256=sha256(font_path.read_bytes()).hexdigest(), cases=[])
    for index, (name, ocr, transform, request, status, selected) in enumerate(cases, 1):
        ocr.validate_against(transform)
        result = match_evidence(ocr, request, prepared=transform)
        actual_ids = tuple(block.block_id for block in result.blocks)
        if result.status != status or actual_ids != selected:
            raise ValueError("EVIDENCE_EXPECTATION_MISMATCH:" + name)
        metadata = result.to_field_metadata()
        region_ids = tuple(region["ocr_block_ids"][0] for region in metadata["source_regions"])
        if (region_ids != selected or metadata["confidence"] is not None or
                metadata["confidence_method"] is not None or
                (name == "partial-readable" and "OCR_UNREADABLE_REGIONS" not in metadata["review_flags"]) or
                (name == "geometry-unavailable" and
                 result.candidate_block_ids != (("description",),))):
            raise ValueError("EVIDENCE_METADATA_MISMATCH:" + name)
        folder = output / name
        folder.mkdir()
        with Image.new("RGB", (800, 600), "white") as image:
            draw = ImageDraw.Draw(image)
            for block in ocr.blocks:
                if block.quad is not None:
                    draw.text((round(block.quad[0][0] * 800), round(block.quad[0][1] * 600)),
                              block.text, font=font, fill="black")
            if name == "geometry-unavailable":
                draw.text((80, 60), "Bánh mì", font=font, fill="black")
            for region in ocr.unreadable_regions:
                if region.quad is not None:
                    x, y = region.quad[0]
                    draw.rectangle((round(x * 800), round(y * 600),
                                    round(region.quad[2][0] * 800), round(region.quad[2][1] * 600)),
                                   fill="lightgray")
            with BytesIO() as stream:
                image.save(stream, format="PNG")
                input_bytes = stream.getvalue()
            with draw_overlay(image, ocr) as overlay:
                overlay.save(folder / "overlay.png")
        (folder / "input.png").write_bytes(input_bytes)
        (folder / "canonical.png").write_bytes(input_bytes)
        (folder / "ocr.json").write_bytes(_bytes(ocr.to_dict()))
        (folder / "prepared.json").write_bytes(_bytes(transform.to_dict()))
        expected = dict(case_id=name, document_type="receipt" if index % 2 else "invoice",
                        sample_id="fictional-" + name, run_id="fictional-run-" + str(index),
                        artifact_version=2, request=dict(path=request.path,
                            raw_value=request.raw_value, context_block_ids=list(request.context_block_ids),
                            label_text=request.label_text), status=result.status,
                        candidate_block_ids=[list(candidate) for candidate in result.candidate_block_ids],
                        selected_block_ids=list(actual_ids), field_metadata=metadata,
                        canonical_size=[800, 600], files={filename: dict(sha256=sha256(
                            (folder / filename).read_bytes()).hexdigest(), size_bytes=(folder / filename).stat().st_size)
                            for filename in ("input.png", "canonical.png", "ocr.json", "prepared.json", "overlay.png")})
        (folder / "expected.json").write_bytes(_bytes(expected))
        manifest["cases"].append(dict(case_id=name, expected_sha256=sha256(
            (folder / "expected.json").read_bytes()).hexdigest()))
    # Keep negative cases separate so consumers cannot mistake them for accepted artifacts.
    manifest["negative_controls"] = []
    source = output / "matched-total"
    for name in ("wrong-frame", "wrong-canonical-hash"):
        folder = output / name
        folder.mkdir()
        for filename in ("input.png", "canonical.png", "ocr.json", "prepared.json", "overlay.png"):
            shutil.copyfile(source / filename, folder / filename)
        if name == "wrong-frame":
            wrong = replace(prepared, canonical=ImageInfo(799, 600, "RGB", "uint8"))
            (folder / "prepared.json").write_bytes(_bytes(wrong.to_dict()))
            boundary = "OcrPage.validate_against"
        else:
            boundary = "consumer asset SHA-256 verifier"
        files = {filename: dict(sha256=sha256((folder / filename).read_bytes()).hexdigest(),
                                size_bytes=(folder / filename).stat().st_size)
                 for filename in ("input.png", "canonical.png", "ocr.json", "prepared.json", "overlay.png")}
        if name == "wrong-canonical-hash":
            files["canonical.png"]["sha256"] = "0" * 64
        declared = dict(case_id=name, document_type="receipt", sample_id="fictional-" + name,
                        run_id="fictional-negative-" + name, expected="reject", boundary=boundary,
                        files=files)
        (folder / "expected.json").write_bytes(_bytes(declared))
        manifest["negative_controls"].append(dict(case_id=name,
            expected_sha256=sha256((folder / "expected.json").read_bytes()).hexdigest()))
    try:
        page.validate_against(replace(prepared, canonical=ImageInfo(799, 600, "RGB", "uint8")))
    except ValueError:
        pass
    else:
        raise ValueError("WRONG_FRAME_ACCEPTED")
    declared_hash = json.loads((output / "wrong-canonical-hash/expected.json").read_bytes())["files"]["canonical.png"]["sha256"]
    if sha256((output / "wrong-canonical-hash/canonical.png").read_bytes()).hexdigest() == declared_hash:
        raise ValueError("WRONG_HASH_CONTROL_NOT_DISTINCT")
    (output / "manifest.json").write_bytes(_bytes(manifest))
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--font-path", required=True, type=Path)
    result = build(**vars(parser.parse_args(argv)))
    print(json.dumps(dict(cases=len(result["cases"]), synthetic=True)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
