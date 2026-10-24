"""Private compute HTTP service (FastAPI). Not a public business API.

POST /internal/v1/compute checks service auth, body limits, request schema, input
hash and the pinned release before any compute (specs/contracts/compute-api.md).
Without a wired pipeline the service answers 503 AI_NOT_READY; it never fabricates
extraction output. One compute slot, compute runs off the event loop.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from vietdoc.contracts.compute import REQUEST_SCHEMA, ComputeContracts, ContractError
from vietdoc.entrypoints.api.settings import Settings
from vietdoc.infrastructure.logging import configure_logging
from vietdoc.ml.release_manifest import Release, discover_releases
from vietdoc.pipeline.service import ComputeInput, ComputePipeline

log = logging.getLogger("vietdoc.ai_service")

MAX_METADATA_BYTES = 16 * 1024
MULTIPART_OVERHEAD = 64 * 1024
RETRY_AFTER_SECONDS = "5"
NO_PIPELINE = "extraction pipeline is not implemented yet (M2.1/M2.3)"


class _BodyTooLarge(Exception):
    pass


class BodyLimit:
    """Rejects declared or streamed request bodies above `limit` bytes."""

    def __init__(self, app: Any, limit: int) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > self.limit:
            response = JSONResponse(_too_large_body(), status_code=413)
            await response(scope, receive, send)
            return
        received = 0

        async def limited_receive() -> dict:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.limit:
                    raise _BodyTooLarge
            return message

        await self.app(scope, limited_receive, send)


def _too_large_body() -> dict[str, Any]:
    return {
        "contract_version": 1,
        "attempt_id": None,
        "code": "INPUT_TOO_LARGE",
        "message": "Request body exceeds the input limit",
        "retryable": False,
    }


@dataclass
class ServiceState:
    releases: dict[str, Release] = field(default_factory=dict)
    release_errors: dict[str, str] = field(default_factory=dict)
    attempts_writable: bool = False
    slot: threading.Semaphore = field(default_factory=lambda: threading.Semaphore(1))


def _writable(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / f".probe-{uuid.uuid4()}"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def _authorized(header: str | None, token: str) -> bool:
    if not token or not header or not header.startswith("Bearer "):
        return False
    return secrets.compare_digest(header[7:].encode(), token.encode())


def _attempt_id(metadata: Any) -> str | None:
    value = metadata.get("attempt_id") if isinstance(metadata, dict) else None
    try:
        return value if isinstance(value, str) and str(uuid.UUID(value)) == value else None
    except ValueError:
        return None


def create_app(settings: Settings | None = None, pipeline: ComputePipeline | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)
    contracts = ComputeContracts(settings.contracts_dir)
    state = ServiceState()

    def ready_reasons() -> list[str]:
        reasons = []
        if not settings.service_token:
            reasons.append("service token is not configured")
        if not state.releases:
            reasons.append("no verified release under the models directory")
        if not state.attempts_writable:
            reasons.append("attempts directory is not writable")
        reasons.extend(pipeline.ready_reasons() if pipeline is not None else [NO_PIPELINE])
        return reasons

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        state.releases, state.release_errors = await run_in_threadpool(discover_releases, settings.models_dir)
        state.attempts_writable = await run_in_threadpool(_writable, settings.attempts_dir)
        log.info(
            "startup",
            extra={
                "releases": sorted(state.releases),
                "release_errors": state.release_errors,
                "reasons": ready_reasons(),
            },
        )
        yield
        log.info("shutdown")

    app = FastAPI(
        title="VietDoc private compute",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(BodyLimit, limit=settings.max_input_bytes + MULTIPART_OVERHEAD)

    @app.middleware("http")
    async def access_log(request: Request, call_next: Any) -> Any:
        request_id = str(uuid.uuid4())
        started = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        log.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 1),
            },
        )
        return response

    def fail(
        status: int,
        code: str,
        message: str,
        retryable: bool,
        attempt_id: str | None = None,
        retry_after: bool = False,
    ) -> JSONResponse:
        log.info("compute_rejected", extra={"code": code, "status": status, "attempt_id": attempt_id})
        headers = {"Retry-After": RETRY_AFTER_SECONDS} if retry_after else None
        body = contracts.error_body(code, message[:500], retryable, attempt_id)
        return JSONResponse(body, status_code=status, headers=headers)

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "UP"}

    @app.get("/health/ready")
    def ready() -> JSONResponse:
        reasons = ready_reasons()
        body = {
            "status": "NOT_READY" if reasons else "READY",
            "releases": sorted(state.releases),
            "reasons": reasons,
        }
        return JSONResponse(body, status_code=503 if reasons else 200)

    @app.post("/internal/v1/compute")
    async def compute(request: Request) -> JSONResponse:
        if not _authorized(request.headers.get("authorization"), settings.service_token):
            return fail(401, "SERVICE_AUTH_FAILED", "Service credential is missing or invalid", False)
        try:
            form = await request.form(max_files=1, max_fields=1, max_part_size=MAX_METADATA_BYTES)
        except _BodyTooLarge:
            return fail(413, "INPUT_TOO_LARGE", "Request body exceeds the input limit", False)
        except Exception:
            return fail(422, "INPUT_INVALID", "Multipart body could not be parsed", False)
        try:
            metadata, upload = form.get("request"), form.get("file")
            if not isinstance(metadata, str) or not isinstance(upload, UploadFile):
                return fail(422, "INPUT_INVALID", "Multipart needs a 'request' JSON field and one 'file' part", False)
            try:
                meta = json.loads(metadata)
            except ValueError:
                return fail(422, "INPUT_INVALID", "Request metadata is not valid JSON", False)
            attempt_id = _attempt_id(meta)
            try:
                contracts.validate(REQUEST_SCHEMA, meta)
            except ContractError as error:
                return fail(422, "INPUT_INVALID", f"Request metadata invalid at {error.path}", False, attempt_id)
            document = await upload.read(settings.max_input_bytes + 1)
        finally:
            await form.close()

        if len(document) > settings.max_input_bytes:
            return fail(413, "INPUT_TOO_LARGE", "Document exceeds the input limit", False, attempt_id)
        if not document:
            return fail(422, "INPUT_INVALID", "Document part is empty", False, attempt_id)
        if hashlib.sha256(document).hexdigest() != meta["input_sha256"]:
            return fail(422, "INPUT_INVALID", "input_sha256 does not match the uploaded bytes", False, attempt_id)
        release = state.releases.get(meta["pipeline_manifest_id"])
        if release is None:
            return fail(422, "MANIFEST_UNAVAILABLE", "Pinned pipeline manifest is not available", False, attempt_id)
        if pipeline is None or ready_reasons():
            return fail(503, "AI_NOT_READY", "Compute pipeline is not ready", True, attempt_id, retry_after=True)
        if not state.slot.acquire(blocking=False):
            return fail(503, "AI_BUSY", "Compute slot is busy", True, attempt_id, retry_after=True)

        ids = {"job_id": meta["job_id"], "run_id": meta["run_id"], "attempt_id": attempt_id}
        attempt_dir = settings.attempts_dir / meta["job_id"] / meta["attempt_id"]
        try:
            attempt_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            state.slot.release()
            return fail(503, "AI_BUSY", "Attempt already submitted; use a new attempt_id", False, attempt_id)
        except OSError:
            state.slot.release()
            return fail(503, "AI_NOT_READY", "Attempt storage is unavailable", True, attempt_id, retry_after=True)

        deadline = time.monotonic() + meta["remaining_budget_ms"] / 1000
        job = ComputeInput(meta, document, release, attempt_dir, deadline)

        def run() -> dict[str, Any]:
            try:
                return pipeline.run(job)
            finally:
                state.slot.release()  # slot frees only when compute really ends

        started = time.monotonic()
        try:
            response = await run_in_threadpool(run)
        except Exception:
            log.exception("compute_failed", extra=ids)
            return fail(500, "INTERNAL_ERROR", "Compute failed", False, attempt_id)
        if time.monotonic() > deadline:
            return fail(504, "COMPUTE_TIMEOUT", "Compute exceeded the remaining budget", False, attempt_id)
        try:
            contracts.check_response(meta, response)
        except ContractError as error:
            log.warning("output_invalid", extra={**ids, "path": error.path})
            return fail(422, "OUTPUT_INVALID", "Pipeline output failed contract validation", False, attempt_id)
        log.info(
            "compute_succeeded",
            extra={**ids, "duration_ms": round((time.monotonic() - started) * 1000, 1)},
        )
        return JSONResponse(response)

    return app
