# PR3 R05/R09/R14/R17 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, task-by-task.
> Người dùng đã yêu cầu lập plan rồi thực hiện; không spawn agents, commit/push,
> tạo PR/merge, tải model/dataset hoặc đổi GitHub settings.

**Goal:** Sửa ba lỗi runtime đã tái hiện ở `404248e`, nối AI suites vào ci-gate,
và bàn giao regression evidence cùng các integration gates chưa đóng.

**Architecture:** Giữ private FastAPI compute và neutral schemas. Slot có atomic
reserved/running/reclaimed/done handoff; chỉ worker đang chạy được trả slot của nó.
Pipeline nhận bản sao request, service kiểm output với ingress baseline riêng.
Output được kiểm JSON-safe/depth/bytes trước schema và serialize trong controlled
boundary, cùng deadline R04. CI chạy serve/test riêng với Data.

**Tech Stack:** Python, FastAPI/Starlette/AnyIO, pytest, GitHub Actions.

**Spec:** [compute protocol](../../../specs/contracts/compute-api.md),
[AI2 M2.3](../ai-2-extraction.md), feedback PR3 ngày 29/10/2026 người dùng cung cấp.

## Global Constraints

- Làm trong workspace và feature branch hiện có; giữ mọi thay đổi không liên quan.
- Không đổi shared JSON schemas, normalizer version, business DB, OCR/model pipeline.
- Input cap 20 MiB, metadata cap 16 KiB/depth 8 giữ nguyên.
- Output producer policy: tối đa 2 MiB JSON UTF-8, 32 object/array containers;
  chỉ built-in JSON types, string keys, finite floats và UTF-8 strict strings.
  Đây là lựa chọn implementation cần Backend review trước integration, không schema authority.
- Giữ worker slot đến khi compute thật kết thúc; cancellation không hard-stop GPU.
- Không coi local tests là hosted CI, model quality hoặc actual-provider E2E evidence.
- R01/R06/R13/R15 và model/baseline là gate/increment riêng; không tự chọn model,
  training config hoặc gold data để lấp các dependency chưa bàn giao.

## Approaches

Chọn lock-protected slot handoff thay vì outer-finally release vô điều kiện (có
thể chạy hai compute) hoặc acquire trong worker (tạo queue không bounded).
Chọn copy metadata trước dispatch thay vì đổi pipeline port sang recursive immutable
types; metadata v1 flat và service baseline không được alias với pipeline input.
Chọn iterative JSON preflight và bounded serialization trước schema traversal để
deep/cyclic/unsupported outputs không gây 500/recursion hoặc unbounded validation.
Không thêm blacklist C0/bidi hoặc coercion làm đổi values.

## Review Focus

- Cancel khi limiter đang hết token và cancel sau worker-start: không leak/double-release (Task 1).
- Worker vẫn có thể được dispatch sau reclaim: phải bỏ compute (Task 1).
- Non-finite ở scores/geometry, surrogate ở keys/values, cycles/depth/size: typed errors (Task 2).
- Pipeline echo IDs đã mutate: so với baseline gốc, request sau vẫn phục hồi (Task 3).
- AI assertion fail/missing module/zero tests/unexpected skip: runner và gate fail (Task 4).

## Task 1 — R05 slot handoff

Files: `src/vietdoc/entrypoints/api/app.py`, `tests/integration/api/test_compute_api.py`.
Interface: private reservation start/reclaim/finish, không đổi `create_app`/pipeline port.

- [x] Viết regression native endpoint với real multipart/AnyIO limiter và dispatch cancellation.
- [x] Chạy RED: request sau cancellation phải compute được thay vì AI_BUSY.
- [x] Implement atomic reserved/running/reclaimed/done; worker bị reclaim không chạy pipeline.
- [x] Kiểm post-start cancel vẫn busy đến worker cleanup, success/exception/timeout recovery.

## Task 2 — R09 controlled output boundary

Files: `src/vietdoc/entrypoints/api/output.py` (new), `app.py`, API tests.
Interface: `encode_output(value: Any) -> bytes`, ValueError cho invalid/bounded output;
strict serializer giữ JSONResponse encoding và cap 2 MiB/depth 32.

- [x] Viết regression invalid floats/strings/types/deep/cycle/size và valid Unicode/control values.
- [x] Chạy RED, xác nhận sai typed envelope/acceptance hiện tại.
- [x] Preflight iterative trước schema; validate và serialize trong error boundary.
- [x] Chạy API tests, giữ deadline sau validate/serialize và không false success log.

## Task 3 — R14 independent ingress correlation

Files: `app.py`, API tests.
Interface: giữ `ComputeInput.request`, dùng deep copy của validated metadata.

- [x] Viết mutating pipeline tests run/job/attempt/type/schema/manifest, output schema-valid.
- [x] Chạy RED (run ID/manifest được 200 là lỗi); copy trước dispatch.
- [x] Chạy GREEN, kiểm response với ingress baseline gốc và request mới phục hồi.

## Task 4 — R17 AI runner và required CI

Files: `scripts/ci/ai.py` (new), `scripts/ci/gate.py`, `.github/workflows/ci.yml`,
`tests/unit/test_ci_gate.py`, `tests/unit/test_ci_ai.py` (new), `docs/cicd.md`,
`infra/ai-service.Dockerfile`, `.dockerignore` và `infra/README.md`.
Interface: `python -m scripts.ci.ai --junitxml PATH`; fixture-only suites không cần weights.

- [x] Viết gate regression bắt buộc ai success; runner probe bằng pytest thật:
  assertion failure, empty/missing tests và unexpected skip đều nonzero.
- [x] Chạy RED rồi implement inventory checks và pytest plugin fail-closed.
- [x] Thêm Ubuntu Python 3.12 job fresh `.[serve,test]`, pip check, AI suites và JUnit upload.
- [x] Nối ai vào ci/release needs; giữ Data env riêng và main release fail-closed.
- [x] Chạy runner/gate/probes local.
- [ ] Hosted run đúng SHA và hosted failing assertion probe: cần commit/push riêng, chưa claim đóng R17.

## Task 5 — hồ sơ và verification

- [x] Cập nhật protocol producer limits, README/HISTORY và draft PR body theo source cuối.
- [x] Ghi owner/acceptance R01/R06/R13/R15, P3 R11/R12 và model/baseline ngoài increment này.
- [x] Chạy focused suite, pip check, workflow lint nếu tooling/network khả dụng.
- [x] Inspect diff/schema compatibility/secrets/unrelated changes và self-review riêng.

## Execution ledger

Pre-flight: Tasks 1–3 cùng endpoint; giữ slot đến worker kết thúc, giữ deadline R04,
typed errors R07/R08/R10 và output snapshot baseline. Task 4 thu thập cả regression
Tasks 1–3. Không thay schema hoặc trộn Data dependencies.

Ruling: Thực hiện inline trong feature workspace hiện có và dùng file này làm ledger;
user đã yêu cầu plan rồi thực hiện, AGENTS không cho tự spawn/commit/push.

Baseline: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider
tests/unit/pipeline tests/unit/ml tests/contract tests/architecture
tests/integration/api tests/unit/test_ci_gate.py` → 308 passed, 1 Windows symlink
skipped, 52 subtests passed. Python 3.13.5; pip check không broken requirements.
Linux job sẽ dùng Python 3.12; local evidence không thay Linux/hosted evidence.

Task 1: complete — RED 2 failures/1 control pass (dispatch/real limiter) → GREEN
47 API tests. BoundedSemaphore kiểm double-release; native multipart endpoint,
không TCP. Late worker sau reclaim không gọi pipeline; post-start cancel vẫn busy.

Task 2: complete — RED 6 failures/10 controls pass → GREEN 63 API tests. Biên
2 MiB (tính cả quotes), escape expansion và depth 32/33 cũng được kiểm trực tiếp.
Ruling: serialize bounded trước schema traversal và dùng Response với bytes đã
encode; deadline test theo seam encode_output thay JSONResponse.render. Không
encode hai lần hoặc tin schema để chứng minh JSON-safe. Giá trị Unicode/C0/bidi
hợp lệ được giữ nguyên. Typed error không log output/exception text.

Task 3: RED 6 schema-valid mutations đều trả 200. Deep copy tách pipeline input
khỏi service baseline → GREEN 70 API tests.

Task 4: code complete — gate RED vì missing ai vẫn pass → GREEN 23 runner/gate
tests, 35 subtests. Probes pytest thật bao pass/fail, skip/xfail, module skip,
missing/empty module, collect-only/deselection; summary counter regression RED
3 passed thay 1 → GREEN và báo subtests riêng. Chưa hosted run, R17 chưa đóng acceptance.

Verification Windows: runner explicit symlink-skip → 347 passed, 1 skipped,
58 subtests, 348 collected, no policy failures; contracts 9/9, CI unittest 12/12,
pip check pass. `scripts.ci.lint` (actionlint/zizmor pinned) exit 0, no findings.
Bare pytest toàn repo không collect được Data vì env AI không có PIL; không cài
gộp Data/AI để ép xanh. Đây là limitation môi trường, không claim toàn repo pass.

Ruling: Docker engine có sẵn; nối test target vào runner chung, allowlist chỉ thêm
scripts/ci và COPY vào test stage. Đây là verification R17/Linux cùng policy;
không thay runtime stage, khởi động service hoặc tải model. Nếu Docker không chạy
được phải giữ Linux acceptance pending, không dùng Windows skip làm bằng chứng Linux.

Final verification: thêm 2 worker exception/timeout capacity controls → API 72/72.
Windows Python 3.13.5: **349 passed, 1 symlink skipped, 58 subtests passed**, 350
collected; explicit local skip policy, no policy failures. Linux Docker Python
3.12.15: **350 passed, 0 skipped, 58 subtests passed**, no policy failures;
pip check pass, test image build exit 0. Image manifest list:
`sha256:5a699e21cae82e9a515c2c0ac7cb01de447a91008815fece8dcc29b51ea5feb0`.
JUnit local ignored: `test-results/ai-followup-windows.xml` và
`test-results/ai-followup-linux.xml`; Linux XML được copy từ test image bằng
container tạm không khởi động, container đã được xóa.

Final review: self-review riêng trên tracked diff và 4 new files; không có peer
approval (AGENTS không cho tự spawn). Slot handoff/cancel race, typed output/depth/
bytes/deadline, original correlation baseline và CI missing/skip/failure policy
đã đối chiếu với tests. Shared schemas/normalizer/Flyway không đổi; git diff --check
pass. Không có secrets, dataset/model binaries, runtime artifacts hoặc unrelated
edits trong source diff. R11/R12 và các integration gates là deferred đã nêu,
không tự đóng hoặc phát sinh thêm policy. Hosted R17 vẫn pending.

## Handoff gates còn mở

| Finding | Owner | Acceptance trước integration/traffic |
|---|---|---|
| R01 | Backend + AI2, Lead duyệt | Chốt multipart `request`/`file`, content types và Java/Python HTTP fixture chung; tên hiện tại không tự bị coi sai |
| R06 | AI2 + Backend | Admission/slow-body/resource budget, concurrent upload tests, bounded cleanup và health behavior; không claim ingress hard timeout đã sửa |
| R13 | AI2 định nghĩa failure port, Backend review mapping | Typed stage Timeout/OOM/storage failures độc lập web/model, allowlist/status/retry và deadline-while-error policy |
| R15 | Backend + AI2, Lead policy | Canonical UUID grammar/reject-or-normalize tại neutral boundary, cùng fixtures; không lowercase sau khi tạo path |
| R11/R12 | AI2, Backend/Lead review | P3 chưa sửa: isolate malformed manifest, Windows drive/colon/resolved containment/link/reparse tests |
| R17 | Backend/Lead + AI2 | Hosted actual run trên head mới và assertion-fail probe làm ci-gate fail; local Docker không thay GitHub evidence |

R01/R06/R13 có thể deferred khi nhận framework shell nếu owner/gate được chấp thuận
và chưa bật traffic tích hợp. Không nhận chúng là closed bởi các fixes runtime này.
Baseline/model là increment riêng: cần Data gold + AI1 OCR fixture cùng sample_id,
candidate/license/revisions và hardware/resource budget đã duyệt trước model smoke
hoặc training. Không dùng prediction làm gold, không tune final holdout.

## Draft PR body (chưa đăng GitHub)

Target: `develop`. PR cung cấp Python AI framework: exact decimal normalization
`vi-VND.v2`, parser, private compute endpoint, verified release loading,
attempt-scoped storage boundary, Docker service/train environments và fixtures.
Follow-up sửa deadline/storage/metadata/OCR declaration (R04/R07/R08/R10), rồi
cancel slot ownership, bounded JSON-safe output và independent correlation baseline
(R05/R09/R14); job AI fixtures được nối vào required ci-gate (R17 code).

Scope là framework; pipeline OCR/extractor thật, actual-provider Java HTTP,
baseline quality, model smoke/training/G0/G1 chưa được nghiệm thu. Không gán
legacy test counts hoặc Windows-only evidence cho source mới. Verification mới
và hạn chế được ghi tại HISTORY; hosted run đúng SHA vẫn cần sau commit/push.
R01/R06/R13/R15 giữ owner/gate ở trên, R11/R12 là P3 còn mở. Output producer cap
2 MiB/depth 32 cần Backend review khi tích hợp; neutral schemas không đổi.
