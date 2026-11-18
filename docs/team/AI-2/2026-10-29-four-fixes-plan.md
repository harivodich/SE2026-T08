# Batch A R04/R07/R08/R10 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, task-by-task;
> không spawn agents hoặc commit/push khi người dùng chưa yêu cầu riêng.

**Goal:** Sửa đúng bốn finding đã được người dùng yêu cầu, có regression RED→GREEN.

**Architecture:** Giữ FastAPI/private compute và neutral schema hiện tại. R04 dùng
arrival monotonic của request xuyên suốt ingress/worker/output preparation. R07
phân loại expected parser/I/O failures, cleanup giữ lỗi gốc. R08 giới hạn metadata
depth trước decode; R10 enforce OCR artifact tại semantic checker.

**Tech Stack:** Python/FastAPI/Starlette, jsonschema Draft 2020-12, pytest.

**Spec:** [giải thích bốn finding](batch-a-r04-r07-r08-r10.md),
[compute protocol](../../../specs/contracts/compute-api.md).

## Global Constraints

- Làm tại E:/OCR_SE trên feature branch hiện tại; giữ tài liệu local đang có.
- Không sửa business DB, model/OCR, shared schema, normalizer hoặc CI gate R17.
- R05/R09/R14 không được nhận đã sửa do chỉ thay bốn finding này.
- Giữ input byte cap 20 MiB và metadata part cap 16 KiB.
- Chọn metadata depth cap 8 (đếm containers), reject duplicate keys. Metadata v1
  là flat object; đây là producer input policy được ghi rõ, không đổi schema authority.
- Storage lỗi dùng 503 AI_NOT_READY/retryable=true theo mapping mkdir đã có;
  malformed giữ 422, oversize giữ 413, unexpected bug giữ 500 INTERNAL_ERROR.
- Giữ semaphore tới khi worker thực sự kết thúc. Không outer release vô điều kiện.
- R04 sửa budget accounting; ingress hard timeout/native GPU hard-stop không được
  claim bởi các checks này và vẫn cần cấu hình/verification riêng.
- Không commit/push, tạo worktree hoặc spawn agents; người dùng đã yêu cầu plan rồi
  thực hiện trong workspace hiện tại. Các bước Git của skill không áp dụng.

## Review Focus

- Lỗi cleanup không che primary invalid-input outcome; mọi upload đều được thử close (Task 2).
- Queue/thread wait hết budget không gọi pipeline và không leak permit (Task 4).
- Output validator/serializer làm hết budget không được log success (Task 4).
- Brackets/escaped quotes trong string không tính thành nesting (Task 3).
- Hai artifacts không OCR vẫn đúng schema nhưng phải sai semantic check (Task 1).

## Task 1 — R10: mandatory OCR artifact

Files: `src/vietdoc/contracts/compute.py`, `tests/contract/test_compute_contract.py`,
`tests/integration/api/test_compute_api.py`.

Interface: giữ `ComputeContracts.check_response(request, response) -> None`,
raise ContractError khi thiếu OCR; endpoint map thành 422 OUTPUT_INVALID.

- [x] Viết contract/API tests: đổi OCR thành raw_prediction, checker phải reject,
  endpoint 422; fixture đủ canonical/OCR vẫn pass.
- [x] Chạy `pytest ... -k missing_ocr` và thấy FAIL đúng vì hiện vẫn nhận success.
- [x] Thêm điều kiện tồn tại OCR kind sau schema validation; giữ các checks cũ.
- [x] Chạy contract/API suites: expected PASS.

## Task 2 — R07: parser/read/cleanup failures

Files: `src/vietdoc/entrypoints/api/app.py`, `tests/integration/api/test_compute_api.py`.

Interface: endpoint vẫn JSONResponse theo compute-error schema; thêm helper
`_close_form(form: FormData) -> bool` để thử cleanup toàn bộ uploads, báo I/O failure
không ghi exception text. Primary error ưu tiên hơn cleanup error phát sinh sau.

- [x] Viết fault-injection tests ENOSPC/EACCES ở parse/write/read/close, malformed,
  unexpected parser exception; assert typed error/no pipeline call/closed resources.
- [x] Chạy tests R07: expected FAIL vì 422 nhầm hoặc untyped exception.
- [x] Bắt OSError riêng, HTTPException parser/MultiPartException là malformed;
  unexpected Exception thành controlled INTERNAL_ERROR. Cleanup không return trong
  finally, không che outcome gốc; fallback close file khi async close lỗi.
- [x] Chạy API suite: expected PASS; valid request sau lỗi vẫn chạy.

## Task 3 — R08: bounded metadata decoding

Files: `src/vietdoc/entrypoints/api/metadata.py` (mới, logic giới hạn JSON),
`src/vietdoc/entrypoints/api/app.py`, `tests/integration/api/test_compute_api.py`.

Interface: `decode_metadata(text: str) -> Any`; ValueError cho malformed/depth/duplicate
hoặc decoder-limit errors; `MAX_METADATA_DEPTH = 8`. Endpoint map INPUT_INVALID.

- [x] Viết tests nesting 5000, dưới/trên cap, malformed, duplicate keys, brackets và
  escaped quotes trong string; request tiếp theo phải chạy.
- [x] Chạy tests R08: expected FAIL trên RecursionError/duplicate acceptance.
- [x] Scanner tuyến tính hiểu string/escape, sau đó json.loads với duplicate-key
  hook; convert RecursionError thành ValueError. Không tăng recursion limit global.
- [x] Chạy API suite: expected PASS, không đổi valid metadata.

## Task 4 — R04: one arrival-based deadline

Files: `src/vietdoc/entrypoints/api/app.py`, `tests/integration/api/test_compute_api.py`.

Interface: `create_app(settings=None, pipeline=None, *, clock=time.monotonic)`;
clock callable trả monotonic seconds, mặc định runtime thật, test dùng clock điều khiển.

- [x] Viết tests advance clock lúc đọc form/chờ thread/compute/validate/serialize;
  assert 504, no success log, no dispatch khi đã quá hạn; happy path giữ deadline gốc.
- [x] Chạy tests R04: expected FAIL vì deadline reset và check output thiếu.
- [x] Middleware giữ arrival trong request scope; tính deadline từ arrival sau
  metadata validation. Check trước acquire/dispatch và đầu worker, worker finally
  trả permit kể cả hết budget. Check sau validation và response construction trước log.
- [x] Chạy API suite: expected PASS; busy/attempt reuse vẫn đúng.

## Verification và hồ sơ

- [x] Chạy focused Windows suites bằng .venv: pipeline/ml/contract/architecture/API.
- [ ] Build Docker ai-service target test: Linux full focused suites, bao symlink.
- [x] Rà diff/schema compatibility, local docs links và git diff --check.
- [x] Cập nhật HISTORY/README/trạng thái giải thích với RED/GREEN thực và limitations.
- [x] Self-review riêng; không có independent reviewer trong lượt này.

Ghi kết quả execution bên dưới và trong HISTORY; không coi checkbox là evidence tự đủ.

## Execution ledger

Pre-flight: Task 1 và 4 cùng check_response/output path; giữ schema validation trước
OCR semantic rule. Task 2/3/4 cùng endpoint input path; giữ primary error khi cleanup,
clock bắt đầu trước form parse. Không có conflict ownership cần đổi kiến trúc.

Ruling: dùng plan/HISTORY làm ledger thay shell helpers tạo scratch/commits của skill,
để giữ workflow Windows và quyền Git hiện hành. Thực hiện inline theo yêu cầu người dùng.

Task 1 complete: RED 2 missing-OCR failures → GREEN 44 contract/API tests.
Task 2 complete: RED 7 failures/1 control pass → GREEN 30 API tests.
Task 3 complete: RED 6 failures/3 controls pass → GREEN 36 API tests.
Task 4 complete: RED 4 failures/2 controls pass → GREEN 42 API tests.

Ruling: `_close_form` trả `Exception | None` thay bool để giữ classification OSError
và unexpected error riêng; signature mới không có caller bên ngoài endpoint.
Ruling: giữ nguyên create_app signature, thay module-local time trong tests thay vì
thêm public clock parameter; không đụng clock global của AnyIO và runtime không đổi.

Final focused suite trên Windows: 297 passed, 1 symlink skipped, 23 subtests passed.
Docker check chưa chạy: Docker Desktop Linux engine pipe không tồn tại; lệnh build
đã thử và fail trước khi build. Không có fresh Linux evidence cho bản sửa này.
Final review: self-review (không spawn agents theo AGENTS); không có peer approval.
Lượt implementation không commit/push; bàn giao Git theo yêu cầu riêng sau đó.
R05/R09/R14/R17 còn mở; giữ giới hạn ingress hard-timeout/GPU hard-stop
như Global Constraints. Kết quả và commands đầy đủ ở HISTORY.
