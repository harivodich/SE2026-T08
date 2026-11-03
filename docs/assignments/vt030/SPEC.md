# BT3 VT-030 - scope và test-first plan

Sinh viên: Nguyễn Hoàng Hải, MSSV 23001870, SE2026-T08, Lead. Baseline develop `729be6fe493dc00e1d7cb87e7db94b94c79a0816`. Nhánh `codex/bt3-vt030-async-idempotency`. URL đề cũ SE2026.AI-02.1 đã đổi thành SE2026-T08; giữ mapping để đối chiếu. Đây là increment cá nhân, không merge khi nhóm chưa review.

## Problem

Người dùng gửi job OCR/extraction dài và cần theo dõi trạng thái. Khi response bị mất, retry cùng thao tác không được tạo thêm job, run, transaction nghiệp vụ hoặc audit hoàn tất. Baseline đã có DB job/worker và UI polling; thiếu đường dẫn monitor rõ trong response202. Bài chọn thêm monitor Location ở API và kiểm đặc tính idempotency hiện có thay vì dựng một queue mới.

## Acceptance criteria

- AC1: POST jobs đã authorize/CSRF trả202, body identity đúng, Location tương đối `/api/v1/jobs/{job_id}`; không cần chờ inference. GET monitor giữ state/stage từ persisted job. Responses có no-store.
- AC2: cùng document và Idempotency-Key hợp lệ trả cùng job/run reservation, không thêm CREATE_JOB audit. Cùng key ở document khác là hai thao tác riêng. Key khác khi có active job trả409, không insert.
- AC3: transient failure/retry/lease recovery/cancel vẫn chỉ một logical job và tối đa một committed run; stale/duplicate completion không tạo thêm run/audit. Thông báo bên ngoài chưa có module nên không claim exactly-once notification.
- AC4: anonymous401, foreign owner404, thiếu CSRF403, malformed key400; không tạo side effects trên request bị từ chối. `result_run_id` tiếp tục là string đã reserve, không đồng nghĩa kết quả tồn tại.
- AC5: harness200 concurrent clients, đủ200 outcomes, p95 admission <=5000ms và0unexpected errors ở môi trường được đo; mọi lỗi tính vào mẫu. Không mở rộng kết luận sang200GPU inferences hoặc production PostgreSQL/TCP nếu chưa đo.

## Constraints / invariant

Java là business DB writer; không chạy inference trong web request hoặc DB transaction. Không thay body/schema/ID ownership; additive HTTP header thôi. Không lộ file/OCR/token trong evidence nộp. Per-sample keys/IDs và DB isolation độc lập.

Invariant chính: retry cùng `(document_id, request_key)` không làm tăng số logical job hoặc CREATE_JOB audit; duplicate/stale completion không tăng committed run/JOB_COMPLETED. At-least-once computation có thể xảy ra, không claim exactly-once execution.

## Plan trước implementation

1. Đọc controller/services/OpenAPI và contract; giữ baseline và branch riêng.
2. AI viết tests trước; chạy baseline và xem assertion fail đúng lý do. Nếu lỗi test/harness thì lưu lại, sửa oracle rồi chạy red lại trước patch.
3. Patch nhỏ `DocumentController`: ResponseEntity202+Location+no-store, GET status no-store; thêm OpenAPI header docs. Không viết lại `JobService`, queue, scheduler hoặc React.
4. Chạy tests; deliberate mapping `document_id <- job.id` trong mapper tạm thời, chạy tests bắt lỗi rồi restore bytes. Không giữ bug trong nhánh nộp.
5. Coverage, flakiness order/time,200-client harness và HTTP/browser evidence nếu môi trường cho phép. Ghi limitations theo từng layer.
6. Inspect diff/secrets; README, traceability, AI Usage Log, reflection và PDF<=8main pages; link branch. Nhóm review trước merge.

## Review plan bằng repository thật

- Bác bỏ nullable `result_run_id`: OpenAPI Job required string; `JobService.create` reserve UUID trước compute. Đổi body làm breaking change không cần thiết; kiểm existence của ExtractionRun riêng.
- Bác bỏ dựng queue/worker mới: `JobService`, `JobWorker`, locks/fences và polling UI đã có. Chỉ thêm Location/cache contract và tests; không làm trùng backlog Backend.
- Bác bỏ p95 toàn OCR/model: `JobService` single worker/demo; HTTP compute còn fail-fast. Đo admission/status trên harness, không lấy số đó tuyên bố inference SLA.
- Sửa test cache quá chặt: SecurityConfig đã có `no-cache, no-store, max-age=0, must-revalidate`; assertion phải kiểm directive `no-store`, không ép nguyên chuỗi đúng một giá trị.

Các review trên là quyết định triển khai từ source; không là lời đảm bảo mọi behavior đã pass. Evidence từng lần chạy được lưu cùng lệnh, thời gian và JUnit report.
