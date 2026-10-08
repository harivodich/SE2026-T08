# Private compute API v1: Java ↔ Python

Thiết kế đích, chưa endpoint implementation. Writer protocol: Backend; Python consumer/producer: AI-2; geometry reviewer: AI-1. Lead duyệt tại L1.2, shared fixture contract tests ở B1.2/M2.3.

## Transport và endpoints

Java runner gọi fixed private base URL, authenticated service credential từ environment/secret runtime. Browser không gọi Python. Local dev bind loopback; Compose private network, không public port AI/DB.

| Route | Input | Output |
|---|---|---|
| POST /internal/v1/compute | multipart: metadata JSON + file bytes | 200 compute response khi hoàn tất |
| GET /health/live | không payload | process alive |
| GET /health/ready | không payload | pinned supported manifests/model loaded + slot/runtime usable |

Một synchronous bounded compute call từ runner, không public request thread. Python concurrency1, busy503, không Python durable job queue/callback. Ready không cam kết slot luôn free; response busy vẫn hợp lệ.

Metadata theo [compute request schema](compute-request.schema.json): contract_version, job_id, run_id, attempt_id, selected document_type/schema_version, language=vi, input_sha256, pipeline_manifest_id, remaining_budget_ms. Tất cả IDs do Java tạo; model không sinh IDs. Input hash phải đúng bytes; pipeline manifest phải local allowlisted/pinned, không URL/weights path từ caller.

Java gửi remaining budget theo total job deadline DB; Python deadline bằng monotonic clock khi nhận, không reset budget giữa stages. HTTP connection/read/body limits có margin đo được; khi budget≤0 Java không gọi. AI service kiểm bytes20MiB/page1/pixels20MP/token/decode/output caps, cùng profile version sau G0. Python không dùng ngôn ngữ khác tự chuyển fallback.

## Success response

[Compute response schema](compute-response.schema.json) chứa contract_version, attempt_id, result ([extraction result](extraction-result.schema.json)), canonical_page và artifacts. Envelope IDs echo request, provenance khớp pinned manifest, business schema theo type. Result model chỉ payload; runtime envelope được service tạo.

Canonical page: page0, width/height positive, asset_key, sha256; dimensions và geometry phải consistent. Artifacts gồm kind/key/hash/size/media_type; bắt buộc canonical page/OCR ở protocol semantic checks. Output assets under `attempts/{job_id}/{attempt_id}/` trên attempt volume do service config cố định; key không absolute/path traversal/symlink. Không hỗ trợ arbitrary download URL.

Java đọc attempt assets qua storage adapter, kiểm containment/prefix và stream-copy sang vùng committed Java-only. Hash/size tính từ bytes copy, canonical decode kiểm bản copy; atomic publish private promoted keys trước DB commit, không tin declaration hoặc mở lại mutable file sau hash check. DB/viewer chỉ dùng promoted keys, không serve attempt path trực tiếp. Stale/cancelled/failed completion có thể có orphan promoted assets, trace và cleanup bounded theo manifest. Orphan assets không là approved data; cleanup dry-run theo manifest/retention được duyệt. Private attempt volume không mount originals/exports writable vào Python.

Java phải kiểm: request/response job/run/attempt/type/schema match, provenance, metadata paths tồn tại trong payload, region finite/quad order/page, no duplicate artifact keys, canonical metadata matches exactly one artifact, state/current token/unexpired lease/deadline/cancel. JSON Schema chỉ cấu trúc; không chứng minh các rules này pass.

## Errors và retry

Error envelope theo [schema](compute-error.schema.json): contract_version, attempt_id (null nếu request chưa parse), code, message, retryable. Message stable không stack trace/raw text. Java không tin retryable đơn lẻ, map allowlist theo code/status.

| Status/code | Java action |
|---|---|
| 401/403 service auth | fail config; không loop retry |
| 413 INPUT_TOO_LARGE /422 INPUT_INVALID, PROFILE_EXCEEDED | permanent fail |
| 422 MANIFEST_UNAVAILABLE, OUTPUT_INVALID | permanent/config fail; cần owner sửa |
| 503 AI_BUSY | RETRY_WAIT bounded, honor bounded Retry-After |
| 503 AI_NOT_READY | retry theo budget; alert nếu model-load lỗi |
| 500 MODEL_OOM / MODEL_LOAD_FAILED | permanent profile/config; không automatic OOM loop |
| 504 COMPUTE_TIMEOUT | terminal deadline/profile; không reset budget |
| network/connect/reset | transient bounded nếu còn deadline/attempt budget |

Giữ trace IDs, duration/error code; không log file/OCR/secret. Response body/depth cap; reject unknown contract version before domain persistence.

## Duplicate, cancellation và delivery semantics

Retry cùng job dùng attempt_id/run_id mới, immutable pinned manifest giữ nguyên. Unique run/job ở Java business DB; có thể compute lại sau response loss. Python không đảm bảo exactly-once và không là nơi quyết định job done.

Trong một AI process không cho hai request cùng attempt chạy/overwrite; duplicate active attempt reject typed AI_BUSY. Restart có thể có orphan partial outputs: attempt directory không overwrite, create temp + atomic final publication, caller retry dùng attempt mới. Không coi file tồn tại là completed result.

Cancel ở Java atomically invalidate lease/fence; Python có thể vẫn compute đến deadline. GPU slot vẫn busy cho tới cleanup thực, không tuyên bố cancellation đã free GPU. Kill/restart recovery phải kiểm ở M2.3/B3.3.

## Cross-language acceptance

Cùng tiny fixtures parse Java và Python; decimal strings/null/unknown keys/type/schema/geometry/assets/ids/version/error cases. Hai phía smoke HTTP thật; cố ý mismatch attempt/hash/provenance/path để reject. Golden fixtures không là OCR accuracy hay app E2E bằng provider thật.
