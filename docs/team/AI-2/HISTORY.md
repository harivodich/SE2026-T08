# Nhật ký công việc AI-2

Cập nhật: **29/10/2026**, timezone Asia/Bangkok. Hồ sơ được tổng hợp từ Git local
và các lần làm việc trong hội thoại. Không dùng hồ sơ này thay trạng thái/approval
ở [PR #3](https://github.com/harivodich/SE2026-T08/pull/3).

## 24/10/2026 — Source nền đã có

Git local ghi nhận hai commit sau; đây là lịch sử source, không khẳng định mọi
acceptance của M1/M2 đã hoàn thành.

| Commit | Nội dung |
|---|---|
| [77eebe9](https://github.com/harivodich/SE2026-T08/commit/77eebe9) | Private compute service, contracts, release verifier, env report và Docker environments |
| [58c5b16](https://github.com/harivodich/SE2026-T08/commit/58c5b16) | Normalizer vi-VND.v1 và model output parser |

Service chưa có concrete OCR/extraction pipeline; `AI_NOT_READY` không phải kết quả
AI giả. API tests dùng test doubles để kiểm wiring, không đo chất lượng model.

## 27/10/2026 — Đọc dự án và đánh giá tiến độ

- Đọc tài liệu kiến trúc, `docs/team`, shared contracts và owning source/tests.
- Nhận diện phần đã triển khai tập trung M2.2 và HTTP boundary của M2.3.
- Phát hiện xung đột core jsonschema 4.26.0 với Data extra 4.10.3.
- Tái hiện Decimal bị rounding ở số 29–32 chữ số và Overflow với `1e1000000`.
- Focused tests trước sửa: 215 passed, 1 symlink test skipped trên Windows.

Đánh giá này không xác nhận model feasibility/G0: chưa có model adapter/inference
report hoặc train step của extractor thật trong source đã đọc.

## 27/10/2026 — Bản sửa dependency và decimal

Commit: [d608cc3](https://github.com/harivodich/SE2026-T08/commit/d608cc319e1184a6bcb097e0cffecfced91c8b42)
— `fix(ai): isolate dependency extras and preserve exact decimal values`.

Đã thay đổi:

- Core không ép validator; extra `contracts` và nhóm `serve`/`train` khai báo
  jsonschema 4.26.0 + referencing 0.37.0. Giữ nguyên Data pins và canonical fixtures.
- Canonicalization dùng Decimal construction/as_tuple chính xác, không normalize
  theo precision context; kiểm chiều dài trước exponent expansion.
- Numeric source text cap 64 Ki ký tự, canonical cap 32 ký tự theo schema.
- Version normalizer đổi thành `vi-VND.v2`; thêm regression tests số dài, context,
  exponent và parser null + VALUE_INVALID.
- Docker test chọn đúng AI/contract/architecture/API suites; copy bốn fictional
  JSON examples cần cho schema tests. Không đưa Data render dependencies vào AI image.
- Cập nhật hướng dẫn cài đặt và giới hạn policy/version.

Checks đã chạy trong phiên sửa; **không chạy lại ngày 29/10/2026**:

| Check | Kết quả lịch sử |
|---|---|
| Focused suites trên Windows | 272 passed, 1 symlink test skipped, 23 subtests passed |
| Docker Python 3.12, target test | 273 passed, 23 subtests passed; symlink case chạy được trên Linux |
| Fresh contracts/test environment | 79 passed, 23 subtests passed; pip check đạt |
| Fresh Data environment | 13 passed, 1 canonical-byte test skipped; Pillow 10.2.0/jsonschema 4.10.3; pip check đạt |
| Data integration generation/verification | Đủ 20 fictional samples: 10 receipt, 10 invoice |
| Fresh core environment | Cài package không kéo jsonschema/referencing/Pillow/FastAPI/torch; pip check đạt |
| AI test image | pip check offline đạt |
| Diff hygiene | git diff --check đạt |

Các check không phải các bộ chứng từ độc lập để cộng thành accuracy. Canonical-byte
reproduction và fresh install toàn bộ training stack chưa được kiểm trong lượt đó.
Không chạy training/model thật, không tải weights/dataset hoặc deploy.

Theo yêu cầu riêng của người dùng, đã commit và push lên nhánh AI-2; remote SHA được
kiểm khớp `d608cc3`, working tree sạch ở cuối phiên push. Đây là sự kiện đã kiểm
trong phiên trước, không phải lần kiểm live GitHub ngày 29/10/2026.

## 28/10/2026 — Đọc follow-up review và giải thích Batch A

Đã đọc file người dùng cung cấp, tên `PR3-ai2-followup-strict-review-2026-10-27 (1).md`.
Review đánh giá snapshot `d608cc3`, đóng các finding số học/dependency đã sửa và
kết luận REQUEST CHANGES cho toàn PR. Reviewer ghi còn 11 nhóm P2 và 3 nhóm P3;
đây là kết luận của báo cáo, không phải một lần tái hiện độc lập toàn bộ finding.

Đã giải thích Batch A và cách nối AI tests vào required CI gate. Chưa sửa runtime,
CI, PR body hoặc settings GitHub; chưa thực hiện các chỉ dẫn nằm trong review.

| Finding | Trạng thái source tại d608cc3 |
|---|---|
| R04 — deadline accounting | Chưa sửa; cần tính cả ingress/wait/output preparation |
| R05 — compute slot cancellation | Chưa sửa; cần atomic ownership handoff |
| R07 — storage classification | Chưa sửa; cần phân biệt input lỗi và I/O failure |
| R08 — metadata depth | Chưa sửa; cần decode boundary có depth cap |
| R09 — JSON-safe output | Chưa sửa; cần bounded serialization trước success logging |
| R10 — mandatory OCR artifact | Chưa sửa; semantic checker chưa enforce OCR kind |
| R14 — request aliasing | Chưa sửa; baseline không được alias với pipeline input |
| R17 — required CI AI suites | Chưa nối; CI Data/contracts không thay AI framework tests |

## 29/10/2026 — Tạo hồ sơ và làm rõ bốn finding

- Đối chiếu lại source/protocol/tests tại `d608cc3` cho R04/R07/R08/R10.
- Tạo [bản giải thích chi tiết](batch-a-r04-r07-r08-r10.md), index, SPEC và nhật ký này.
- Bổ sung đường dẫn từ docs/team, giữ roadmap và task cards ở vị trí cũ.
- Phạm vi lượt này chỉ là tài liệu. Không thêm regression test runtime, không tái
  hiện độc lập fault-injection của reviewer, không đánh dấu Batch A đã sửa.
- Kiểm mới: file tồn tại/UTF-8/local links, commit references và diff hygiene.

Những phần OCR/model/training còn thiếu xem [kế hoạch gốc](../ai-2-extraction.md).
Không suy ra quyền commit/push lần mới từ sự kiện push ngày 27/10.

## 29/10/2026 — Lên plan và sửa R04/R07/R08/R10

Người dùng yêu cầu plan rồi implement bốn lỗi. Đã lưu [plan](2026-10-29-four-fixes-plan.md)
trước khi sửa runtime; thực hiện inline trên feature branch, giữ các tài liệu local.

| Finding | Thay đổi | RED → GREEN đã chạy |
|---|---|---|
| R10 | check_response bắt buộc có OCR artifact, giữ các checks canonical/correlation/prefix | 2 missing-OCR tests fail → 44 contract/API tests pass |
| R07 | OSError ở parse/read/cleanup thành 503 AI_NOT_READY; malformed giữ 422, unexpected giữ INTERNAL_ERROR; cleanup không che primary error và thử close spool fallback | 7 storage tests fail, 1 control pass → 30 API tests pass |
| R08 | metadata.py scan depth trước decode, cap 8 containers, reject duplicate keys/non-finite JSON constants; decoder-limit thành ValueError/INPUT_INVALID | 6 tests fail, 3 controls pass → 36 API tests pass |
| R04 | Arrival giữ trong request scope; deadline không reset, kiểm trước dispatch/worker và sau output validate/serialize; worker hết budget không gọi pipeline | 4 tests fail, 2 controls pass → 42 API tests pass |

Thêm controls cho malformed multipart và streamed oversize. Protocol ghi rõ producer
metadata limits, storage error mapping và budget accounting; không đổi shared JSON
schemas hoặc normalizer version.

Command cuối trên Windows (PYTHONPATH=src, PYTHONDONTWRITEBYTECODE=1):

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests/unit/pipeline tests/unit/ml tests/contract tests/architecture tests/integration/api --tb=short
```

Kết quả: **297 passed, 1 skipped, 23 subtests passed**. Skip là symlink trên host
Windows. Đây là framework/fixture tests; không phải OCR/model quality hoặc Java E2E.

Đã thử `docker build -f infra/ai-service.Dockerfile --target test -t vietdoc-ai-service:four-fixes-test .`.
Build chưa bắt đầu vì không kết nối được `dockerDesktopLinuxEngine` (pipe không
tồn tại). Không dùng kết quả Docker 273 tests của commit cũ làm evidence cho code
mới. Chưa tự khởi động dịch vụ, chưa có kết quả Linux cho bản sửa này.

Self-review đối chiếu source/diff và Review Focus của plan; không có independent
reviewer hoặc peer/Lead approval trong lượt này. Các quyết định implementation:

- Giữ nguyên signature create_app; tests thay module-local clock, không thay global
  time module. Clock chỉ là test seam; runtime dùng monotonic thật.
- _close_form trả Exception hoặc None thay bool để phân biệt I/O với programming
  failure. Không log exception text/path; primary error đã có được giữ nguyên.
- Metadata depth/duplicate policy producer được ghi vào protocol để Backend review
  khi tích hợp; chưa tuyên bố Java client đã tương thích/acceptance.

R04 chỉ đóng deadline accounting, không hard-stop GPU hoặc giới hạn slow-body ingress
vô hạn. R05/R09/R14/R17 vẫn chưa đóng; invalid-output serialization hiện chưa có
toàn bộ JSON-safety/size/depth boundary của R09. Không sửa CI gate trong scope này.
Cuối lượt implementation chưa commit/push. `.env`, model/dataset và business DB không bị thay đổi.

## 29/10/2026 — Chuẩn bị bàn giao lên nhánh AI-2

Người dùng yêu cầu commit/push lên `feature/AI2-M2_ai_service_docker`.
Đã fetch nhánh đích và chạy lại đúng focused command ở trên: 297 passed,
1 symlink skipped, 23 subtests passed. Giới hạn Docker/Linux vẫn giữ nguyên.
Commit bao gồm source/tests/protocol của bốn lỗi và thư mục hồ sơ AI-2; không có
`.env`, dữ liệu/model hoặc runtime artifacts. SHA và kết quả push tra Git/remote;
phần này ghi bước chuẩn bị, không tự xác nhận push/CI/approval thành công.
