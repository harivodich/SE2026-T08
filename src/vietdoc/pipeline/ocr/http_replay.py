"""Local, one-shot B0/v2 HTTP replay with fictional receipt/invoice images.

Uses an existing verified release. Writes only to a fresh ignored output root;
starts and reaps a loopback server. The report is verification evidence, not a
service or production performance claim.
"""
import argparse
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid

from PIL import Image, ImageDraw, ImageFont

from vietdoc.contracts.compute import ComputeContracts
from vietdoc.contracts.ocr import OcrPage, PreparedPage
from vietdoc.ml.release_manifest import load_release
from vietdoc.pipeline.composition import checked_profile
from vietdoc.pipeline.ocr.paddle_adapter import draw_overlay


BOUNDARY = b"VietDocAi1NativeReplay"


def _call(url, *, data=None, token=None, timeout=180):
    headers = {} if token is None else {"Authorization": "Bearer " + token}
    if data is not None:
        headers["Content-Type"] = "multipart/form-data; boundary=" + BOUNDARY.decode()
    try:
        response = urlopen(Request(url, data=data, headers=headers), timeout=timeout)
    except HTTPError as error:
        response = error
    with response:
        return response.code, json.loads(response.read())


def _multipart(meta, data):
    return (b"--" + BOUNDARY + b'\r\nContent-Disposition: form-data; name="request"\r\n\r\n'
            + json.dumps(meta).encode("utf-8") + b"\r\n--" + BOUNDARY
            + b'\r\nContent-Disposition: form-data; name="file"; filename="fictional.png"\r\n'
              b"Content-Type: image/png\r\n\r\n" + data + b"\r\n--" + BOUNDARY + b"--\r\n")


def _meta(data, kind, release_id):
    return dict(contract_version=1, job_id=str(uuid.uuid4()), run_id=str(uuid.uuid4()),
                attempt_id=str(uuid.uuid4()), document_type=kind, schema_version=kind + ".v1",
                language="vi", pipeline_manifest_id=release_id,
                input_sha256=sha256(data).hexdigest(), remaining_budget_ms=120000)


def _fictional(kind, font):
    lines = (["HÓA ĐƠN MẪU", "Bánh mì x 2", "Tổng tiền 80.000 đ"] if kind == "receipt" else
             ["HÓA ĐƠN GTGT MẪU", "Sản phẩm A  x 2", "Tổng tiền 80.000 đ"])
    with Image.new("RGB", (900, 700), "white") as image:
        draw = ImageDraw.Draw(image)
        for index, line in enumerate(lines):
            draw.text((55, 70 + index * 115), line, font=font, fill="black")
        with BytesIO() as output:
            image.save(output, format="PNG")
            return output.getvalue()


def _artifact(root, entry):
    key = entry["asset_key"]
    path = (root / key).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("ARTIFACT_PATH_INVALID")
    data = path.read_bytes()
    if len(data) != entry["size_bytes"] or sha256(data).hexdigest() != entry["sha256"]:
        raise ValueError("ARTIFACT_HASH_MISMATCH")
    return data


def replay(*, release_root, output_root, font_path):
    release_root, output, font_path = map(Path, (release_root, output_root, font_path))
    if output.exists() or not output.parent.is_dir():
        raise ValueError("OUTPUT_EXISTS_OR_PARENT_MISSING")
    release_id = "b0-native-v2-ai1-r5"
    release = load_release(release_root, release_id)
    checked_profile(release, ocr_artifact_version=2)
    font_bytes = font_path.read_bytes()
    font = ImageFont.truetype(str(font_path), 44)
    output.mkdir()
    attempts = output / "attempts"
    attempts.mkdir()
    token = uuid.uuid4().hex + uuid.uuid4().hex
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = "http://127.0.0.1:" + str(port)
    env = dict(os.environ, VIETDOC_SERVICE_TOKEN=token, VIETDOC_HOST="127.0.0.1",
               VIETDOC_PORT=str(port), VIETDOC_MODELS_DIR=str(release_root.resolve()),
               VIETDOC_ATTEMPTS_DIR=str(attempts.resolve()),
               VIETDOC_PIPELINE_MANIFEST_ID=release_id,
               PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK="true", DISABLE_MODEL_SOURCE_CHECK="True")
    report = dict(artifact_version="vietdoc.ai1-http-replay.v1", status="failed",
                  release_id=release_id, release_manifest_sha256=sha256(
                      (release_root / release_id / "manifest.json").read_bytes()).hexdigest(),
                  font_sha256=sha256(font_bytes).hexdigest(), samples=[], failure=None,
                  limitations=["fictional examples do not measure dataset accuracy",
                               "loopback single-process timing is not a production SLA"])
    with (output / "server.log").open("wb") as log:
        process = subprocess.Popen([sys.executable, "-B", "-m", "scripts.serve_compute_candidate",
                                    "--extractor", "b0", "--ocr-artifact-version", "2"],
                                   cwd=Path(__file__).resolve().parents[4], env=env,
                                   stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise ValueError("SERVER_EXITED_BEFORE_READY")
                try:
                    code, ready = _call(base + "/health/ready", timeout=3)
                    if code == 200 and ready["status"] == "READY":
                        break
                except (OSError, URLError, ValueError):
                    pass
                time.sleep(.1)
            else:
                raise ValueError("SERVER_NOT_READY")
            bad = b"invalid image"
            bad_meta = _meta(bad, "receipt", release_id)
            code, failure = _call(base + "/internal/v1/compute",
                                  data=_multipart(bad_meta, bad), token=token)
            report["failure"] = dict(http_status=code, code=failure.get("code"),
                                     attempt_id=bad_meta["attempt_id"])
            if code != 422 or failure.get("code") != "INPUT_INVALID":
                raise ValueError("BAD_INPUT_NOT_REJECTED")
            if _call(base + "/health/ready")[0] != 200:
                raise ValueError("SERVER_NOT_RECOVERED")
            for kind in ("receipt", "invoice"):
                data = _fictional(kind, font)
                meta = _meta(data, kind, release_id)
                (output / (kind + "-input.png")).write_bytes(data)
                started = time.monotonic()
                code, response = _call(base + "/internal/v1/compute",
                                       data=_multipart(meta, data), token=token)
                if code != 200:
                    raise ValueError("HTTP_COMPUTE_FAILED:" + str(code) + ":" + str(response.get("code")))
                ComputeContracts().check_response(meta, response)
                entries = response["artifacts"]
                kinds = [entry["kind"] for entry in entries]
                if len(kinds) != 4 or set(kinds) != {"canonical_page", "ocr", "transform", "raw_prediction"}:
                    raise ValueError("ARTIFACT_KIND_SET_MISMATCH")
                (output / (kind + "-response.json")).write_text(
                    json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
                artifacts = {entry["kind"]: _artifact(output, entry) for entry in entries}
                page = OcrPage.from_dict(json.loads(artifacts["ocr"]))
                prepared = PreparedPage.from_dict(json.loads(artifacts["transform"]))
                page.validate_against(prepared)
                if page.artifact_version != 2 or page.width != response["canonical_page"]["width"] or \
                        page.height != response["canonical_page"]["height"]:
                    raise ValueError("OCR_GEOMETRY_MISMATCH")
                canonical = Image.open(BytesIO(artifacts["canonical_page"]))
                with canonical, draw_overlay(canonical, page) as overlay:
                    overlay.save(output / (kind + "-overlay.png"))
                report["samples"].append(dict(document_type=kind, input_sha256=meta["input_sha256"],
                    attempt_id=meta["attempt_id"], http_status=code,
                    duration_seconds=time.monotonic() - started,
                    recognition_status=page.recognition_status, block_count=len(page.blocks),
                    unreadable_count=len(page.unreadable_regions), canonical_size=[page.width, page.height],
                    artifact_kinds=sorted(artifacts),
                    ocr_sha256=sha256(artifacts["ocr"]).hexdigest()))
            report["status"] = "completed"
        except (OSError, ValueError, KeyError, TypeError) as error:
            report["error_code"] = str(error)
        finally:
            if process.poll() is None:
                report["server_shutdown"] = "harness_terminate"
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    report["server_shutdown"] = "harness_kill_after_timeout"
                    process.kill()
                    process.wait(timeout=5)
            else:
                report["server_shutdown"] = "unexpected_exit"
                report["status"] = "failed"
                report["error_code"] = report.get("error_code", "SERVER_EXITED_BEFORE_HARNESS_SHUTDOWN")
            report["server_exit_code"] = process.returncode
    (output / "replay.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                        encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("release-root", "output-root", "font-path"):
        parser.add_argument("--" + name, required=True, type=Path)
    result = replay(**vars(parser.parse_args(argv)))
    print(json.dumps(dict(status=result["status"], error_code=result.get("error_code"),
                          samples=len(result["samples"]))))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
