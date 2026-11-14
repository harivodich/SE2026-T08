# VT-029 - plan trước implementation, 14/11/2026

Nguyễn Tiến Đạt, 23001863; SE2026-T08; AI-02. Baseline:
`e5326f34549a23570ecf935f469a1f0082ed8a11` (local origin/develop).
Nhánh `feature/VT-029_search_contract`. Không commit/push/merge nếu chưa được yêu cầu riêng.
Đề ghi SE2026.AI-02.1; người dùng xác nhận dùng workspace SE2026-T08.

## Prompt chính và assumptions

Yêu cầu được cung cấp nguyên văn trong Pasted text.txt: giải thích contract/invariants
trước, lập plan, test-first search/filter/pagination, contract testing, mutation nuốt
exception trả default, tải 80 tác vụ p95 <= 2.5s, PDF tối đa 8 trang chính.
Assumption: tìm filename (không tìm OCR/PII/payload), giữ nguyên type/status hiện có;
thứ tự cố định, không thêm lựa chọn sort. Đây là small API vertical slice, chưa có UI search.

## Contract trước code

GET /api/v1/documents: type/status/cursor/limit đã có, thêm q optional.
Page vẫn chỉ items và next_cursor; Document fields/nullable types giữ nguyên.
Auth owner scope ở cả query và cursor. Keyset (createdAt DESC,id DESC) với strict
less-than tránh lặp khi timestamps bằng nhau. Không hứa snapshot khi dữ liệu đổi.
Blank q tương đương omit; trim, case-insensitive theo DB lower/Locale.ROOT, không bỏ dấu;
% _ ! là literal; q tối đa 128 UTF-16 code units sau trim. Limit clamp [1,100] giữ nguyên.
Lỗi provider phải là 500 INTERNAL_ERROR, không 200 empty; foreign cursor 404.

## Problem và acceptance criteria

Người vận hành cần tìm chứng từ của mình theo tên file, kết hợp bộ lọc và duyệt
nhiều trang ổn định mà client đang đọc Page v1 không phải thay đổi.

- AC1: q optional, filename substring literal, trim/case, kết hợp AND type/status/owner.
- AC2: cursor/limit cũ và thứ tự có tie-breaker; không trùng/mất trên dataset cố định.
- AC3: request cũ và response Page/Document tương thích baseline OpenAPI; không fields mới.
- AC4: invalid filter/query/limit và foreign cursor trả lỗi; provider fault không empty success.
- AC5: harness 80 tác vụ đồng thời đo HTTP p95 với target <=2500ms, kiểm correctness từng response.

NFC1: owner isolation + parameter binding; không SQL injection/wildcard expansion.
NFC2: compatible v1, bounded pages/query, không migration hoặc dependency runtime mới.
NFC3: báo workload/hardware/warmup/errors, không suy rộng H2 sang PostgreSQL production.

## Draft AI plan và review bằng source

1. Draft: tạo search route ở Python documents. **Bác bỏ**: AGENTS.md và backend/SPEC.md
   xác định Java business authority; DocumentController.list/DocumentService.list đã chạy.
2. Draft: page/size/total với offset, sort created_at. **Bác bỏ**: DocumentService.list
   đã dùng cursor UUID, limit clamp, order createdAt DESC,id DESC; static/api.js
   gọi /documents?limit=50. Giữ Page record và keyset, chỉ thêm q optional.
3. Draft: public-api.md nói chưa implementation nên làm harness độc lập. **Sửa**:
   source/OpenAPI/WorkflowIntegrationTest có thật, JDK có sẵn /opt/pycharm/jbr;
   chạy Spring/H2 và HTTP thật. public-api.md là thiết kế đích, không baseline runtime.

Đây là tự review của agent đối chiếu repo; chưa phải review/chấp thuận của sinh viên.

## Plan đã chốt và file dự định sửa

1. Viết DocumentSearchContractTest theo request HTTP cũ/mới, lỗi, cursor và fixture
   OpenAPI baseline độc lập; chạy RED trước khi sửa source (unknown q currently ignored).
2. Patch DocumentController.java + DocumentService.java: optional q, bind escaped
   LIKE parameter, giữ overload list cũ cho Java callers. Update openapi.json và
   specs/contracts/document-search.md; không đổi Document/Page schema.
3. GREEN focused tests và regression; DocumentSearchLoadTest chạy random-port HTTP,
   H2/Flyway, 80 workers start barrier, 3 waves, 240 synthetic rows và correctness checks.
4. scripts/vt029_experiment.py: mutation trong temp copy backend, không sửa nhánh
   nộp; kiểm test failure đúng test + restore/hash; lưu logs/hash manifest.
5. docs/reviews/VT-029-README.md, evidence dưới docs/reviews/vt029-evidence/,
   scripts/vt029_report.py tạo output/pdf/BT3_23001863_VT-029.pdf và phụ lục.

Không test OCR/model/training, approve/export mới hay browser search UI không nằm
trong slice. Browser E2E search còn thiếu; HTTP E2E đi qua session/security/controller/
service/JPA/Flyway/H2, không thay real PostgreSQL hoặc browser evidence.
