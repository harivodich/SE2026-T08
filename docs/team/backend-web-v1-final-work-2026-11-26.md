# Backend/Web — phần việc còn lại đến V1

Đây là nhiệm vụ tiếp theo, không thay review cũ bằng một checklist mới. Đối
chiếu finding/task trước với source đã merge. Backend sở hữu Java API/DB/jobs,
Thymeleaf/review/viewer/export và CI; không train model hoặc viết OCR trong Java.

## Đầu vào đã gỡ phụ thuộc

- Required CI đã bao Web/Java và Docker smoke; không bỏ gate để merge.
- Private compute B0/v1 vẫn default; có opt-in B0/v2 partial và explicit local
  Qwen adapter. `scripts/serve_compute_candidate.py --help` dùng stdlib, không
  tải model. API/config/error packet đã có, không phải đợi AI2 chọn model xong.
- Các tests HTTP với controlled OCR chạy real decode/extract/artifact/contract;
  Java nhận warning scope `/`, giữ qua edit và vẫn chặn missing required field.
  Không coi fixture tests là actual model/PG/native acceptance.
- Pilot/native OCR/IDs/hashes và D22 model failure examples đã đóng gói. M0/M1
  chưa đạt raw serving; không activate hoặc quảng cáo là model V1 tốt.

## B1 — Tiếp nhận protocol và error handling

1. Chạy Java shared-schema, AiClient, artifact promotion tests cùng Python
   consumer suite. Unknown schema/version/type, duplicate JSON keys, correlation,
   digest/dimensions/path mismatch reject đúng boundary.
2. Kiểm auth token/service secret startup, oversized/malformed multipart, busy,
   unavailable, timeout/OOM, invalid output và bounded retry-after. Không expose
   raw OCR, stacktrace, hostpaths hoặc token qua lỗi/log/UI.
3. Complete/partial/all-unreadable/no-detection: giữ readable fields, warnings,
   provenance. Không auto-approve null required fields. Warning scope `/` chỉ
   dành issues; không chấp nhận nó như field metadata hoặc reviewed field.
4. Test lost response/retry, service restart/readiness, unavailable manifest;
   business runner dùng stable error semantics, không biến invalid output thành
   transient retry vô hạn hoặc âm thầm fallback demo.

**Đạt:** real HTTP client contract và regression pass, có error matrix/payload
fixture cho AI2 mà không phải trao đổi miệng thêm. Commit client/tests coherent.

## B2 — PostgreSQL và jobs chạy bền

1. Test PostgreSQL thật/Flyway trên empty DB và supported upgrade, seed demo tách
   business data, durable job/revision constraints. Không dùng H2 thay evidence PG.
2. Claim cạnh tranh, lease expiry/recovery, retry backoff/deadline, cancel/fencing,
   stale completion, double completion, crash trước/sau artifact promotion.
3. Transaction không ôm HTTP compute. Chỉ current lease/fence được CAS-complete;
   Python không DB credentials/callback/state writer.
4. Test ownership/security và idempotency upload/createJob/save/approve/export;
   cùng key khác request phải reject đúng, stale head/version trả409.
5. Artifact hash/path/size/canonical/run binding phải verify trước commit. Copy
   bất biến sang Java-owned storage; viewer không serve mutable Python attempt.
6. Cleanup/reconciliation chỉ xóa unreferenced owned artifacts theo policy, không
   đụng committed revisions, active attempts hoặc dùng path người dùng để xóa.

**Đạt:** PG integration receipt có engine/version/migration/source, race/failure
cases thực. Commit theo transaction/runner/promotion increments có tests.

## B3 — Browser workflow, privacy và dữ liệu không mất

1. Receipt/invoice: upload → job/poll → review/edit → save → approve → export;
   switch document, pagination/table 0/1/30 rows, empty/null/decimal values.
2. Autosave/draft/focus/caret: stale response/error/retry, tab switching, network
   lost response và reload. Không ghi đè edits mới bằng polling cũ; retry mutation
   phải giữ cùng key cho cùng request, request khác dùng key khác.
3. Hai tab/two users, head changed, stale save/adopt/approve:409 hiển thị rõ,
   không mất draft và không auto-resolve last-write-wins.
4. CSRF/auth/ownership/XSS escaping, filenames/OCR text/scripts và JSON error
   rendering; unauthorized artifact/exports không đọc được qua đoán URL.
5. Warning/required blocker/partial OCR phải hiểu được bằng tiếng Việt, keyboard
   và screen reader dùng được. Confirmation không là bypass business validator.
6. Evidence highlight phải đúng canonical dimensions/run/revision, zoom/rotate/
   resize; unavailable/ambiguous evidence không vẽ giả. Rerun tạo candidate,
   không tự thay head đang review.

**Đạt:** browser tests có actual screenshot/trace cho success/conflict/failure,
không chỉ DOM text mocks. Commit UI logic và test cùng increment.

## B4 — Approve/export và audit

1. Approve current revision, revalidate blockers, confirmed review và mọi warning;
   sửa field không tự xóa document warning chưa được acknowledge.
2. Export đúng explicit approved revision/exporter version; cùng input cùng
   bytes/checksum; revision mới không đổi export cũ. Test Unicode/CSV injection/
   decimal/null/table ordering theo formats đã chốt.
3. Audit nhận đúng actor/action/revision/job/run; không log credential/raw PII.
   Test rerun/adopt/correction giữ immutable prediction và provenance.
4. Tái dùng business services giữa HTML/REST; không tạo hai approval rules khác nhau.

**Đạt:** approve/export regression và deterministic artifacts, không phải việc
đợi model chính xác rồi mới test được. Commit policy/regression có nghĩa.

## B5 — Actual provider và release runner

1. Chạy B0 native thật trên receipt+invoice qua Java → PG → Python → canonical
   promotion → review/approve/export. Fixture HTTP, native OCR và PG receipts
   phải phân biệt rõ. Dùng owned test folder/DB, secret runtime không vào Git.
2. Viết/hoàn thiện một runner nhận candidate release/config/pins từ arguments:
   missing/corrupt/unaccepted candidate phải fail, không tự download/activate.
3. Thử runner ngay với B0 release và negative model fixtures. Sau khi AI2 có
   frozen accepted candidate, thay input artifacts rồi chạy cùng runner, không
   chờ Backend viết thêm integration code hoặc đổi API.
4. CI build/test/scan/package image pin digest; CD staging có health/readiness,
   migration, smoke và rollback. Chỉ triển khai vào host được Lead cho phép;
   không đổi nvit-train thành production hoặc mở public AI/DB.
5. Tách PR gate với release-to-main gate; release dùng merge commit theo Git Flow
   đã chốt, không squash mất lịch sử. Không tự merge main hoặc bypass failed CI.

**Đạt:** runnable B0 native E2E, candidate acceptance command đã kiểm, rollback
runbook/receipt và container inventory; model quality/final gate vẫn cần kết
quả thật của candidate, không được ghi sẵn pass.

## Bàn giao

PR vào develop, CI head cuối xanh. Gửi task/finding cũ → commits/files/tests,
commands/results/versions/pins, screenshot/trace/PG/native receipts và giới hạn.
Chia commit theo các thay đổi có thể review, không chia nhân tạo để tăng số.
Không commit raw dataset/model, runtime DB/storage, secrets hoặc screenshots có
PII. B1–B4 và runner B5 làm ngay bằng inputs đã có; model mới chỉ là parameter
cho nghiệm thu release cuối, không chặn implementation của Backend/Web.
