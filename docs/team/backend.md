# Backend Engineer: Java/Spring Boot + Thymeleaf

Bạn sở hữu business API/DB/job/review/approval/export/UI. Bạn không viết preprocessing/OCR/fine-tune hay Python pipeline wiring. Python serving do AI-2 (M2.3), OCR/geometry do AI-1; bạn viết Java HTTP client và kiểm completion.

Đọc [backend SPEC](../../backend/SPEC.md), [architecture](../architecture.md), [source structure](../source-structure.md), [compute contract](../../specs/contracts/compute-api.md), [approval policy](../../specs/approval-policy.md). Hiện chưa Java source/pom/app chạy; filenames dưới là đích của task, không implementation có sẵn.

## Roadmap tuần

Tuần tính từ kickoff, không ngày deadline đã cam kết. Ước lượng task là effort coding/checks ban đầu, cần refine sau B1.3; không cộng tất cả task vào tuần ghi ở title. Backend cần khoảng16–20h/tuần W1–4 để nhắm G1/W4, sau đó12–16h; nếu chỉ12h thì Lead điều chỉnh G1 sang W5–6 và dùng buffer13–16. Không chuyển backlog code sang Lead.

| Tuần | Việc chính | Output nghiệm thu |
|---|---|---|
| 1 | B1.1, B1.2 shape, B1.3 slice | Shared fixtures, Java DTO, health/Thymeleaf chạy |
| 2 | B2.1/B2.2 minimal; B3.1 create/claim | Auth/private upload, durable job, AI HTTP contract locked |
| 3 | B3.2 actual compute, B4.1, B5.1 | Receipt run thật, viewer, save CAS |
| 4 | B4.2 + B5.2 minimum | Receipt sửa field/row→approve→JSON; G1 |
| 5 | Invoice/items; B4.3 first | Two-type editor, candidate history |
| 6 | B3.3/B4.3/B5.2 | G2 two types/items; fencing/cancel/adopt tests |
| 7 | Review conflicts/evidence/history | Viewer/metadata/candidate đúng revision |
| 8 | B3.3/B5.2 feature completion | G3 đủ scope, no silent overwrite |
| 9 | B6.1 | Failure/bounds/performance reports |
| 10 | B7.1 release candidate | G4 correctness + restore rehearsal |
| 11 | B7.1 clean-env/rollback | Người khác chạy được theo runbook |
| 12 | B7.1 demo/handoff | G5 app/versions/limitations |
| 13–16 | Đóng reliability/quality gaps | Buffer, không scope mới |

## Task cards để giao từng phần

Lead chỉ giao task hiện có input; mã B không là issue đã tạo. Tách mỗi card thành PR nhỏ khi effort>1–2 buổi. Mọi task nộp actual commands/results và known failures; không gọi fixture wiring là model chạy thật.

### B1.1 — Business schema và Java DTO, tuần 1

Dependency/input: L1.1; schema hiện có. Effort dự kiến: 4–6h. Reviewer: Data/AI-2 + Lead.

1. Đọc receipt/invoice/line items và approval policy; giữ keys/null/decimal strings/30rows đúng schema trung lập.
2. Tạo Java DTO/schema-validation adapter; không sửa schema theo defaults của Jackson/JPA. URN refs resolve local, chặn remote fetch.
3. Tạo tiny positive/negative fixtures: missing/unknown key, wrong type/version, money float, null, row boundary; Data/AI-2 parse cùng fixtures.
4. Ghi date/arithmetic/state rules thuộc domain validator, không claim schema kiểm đủ; đồng bộ shared examples khi đổi contract.

Nộp: Java DTO + schema tests + fixtures + actual command.

Xong khi: Java/Data/Python consumer parse cùng format; unknown/missing keys không silently accepted.

### B1.2 — Private compute contract và Java client shape, tuần 1–2

Dependency/input: B1.1; O1.1; M1.1. Effort dự kiến: 4–6h. Reviewer: AI-1/AI-2 + Lead.

1. Review compute-api.md cùng AI-2: multipart original bytes/metadata, IDs supplied Java, response/canonical assets/provenance, errors/busy/deadline.
2. Tạo Java request/response/error DTO theo schemas; Backend là shared schema writer, AI-2 tự viết Python adapters.
3. Test receipt/invoice/type/version mismatch, asset prefix/hash/size, field paths/canonical dimensions, invalid correlation.
4. Chốt fixture dùng chung và service credential config names; không gắn file/URL tùy ý hay business DB credentials vào Python.

Nộp: Boundary DTO/fixtures + contract-review evidence.

Xong khi: AI-2 dùng fixtures để implement server; geometry examples được AI-1/Backend hiểu giống nhau.

### B1.3 — Spring Boot/Maven, Thymeleaf slice và checks, tuần 1–2

Dependency/input: B1.1; L1.2 architecture decision. Effort dự kiến: 6–8h. Reviewer: Lead; AI-2 runtime consumer.

1. Chọn JDK/Spring versions được hỗ trợ, smoke actual environment rồi pin Maven wrapper/BOM; không dùng version latest động.
2. Tạo app runnable health + một Thymeleaf page; tách web/job-runner profiles, chưa gọi inference trong web handler.
3. Config actual variables có bounds; .env.example chỉ khi dùng thật; secrets local ignored. Flyway duy nhất, ddl-auto validate khi có schema.
4. Thêm tests/build commands đã chạy; đề xuất CI Java/Python jobs theo task có code, minimal permissions, không viết CI fake pass.
5. Mỗi Java working folder mới có SPEC ngay nơi code đặt, không tạo classes TODO hàng loạt.

Nộp: Runnable minimal Java slice + wrapper/config/tests/checks.

Xong khi: Maven build/test/start và page/health verified; README lệnh đúng môi trường đã thử.

### B2.1 — Persistence, session auth và private storage, tuần 2–3

Dependency/input: B1.3; B1.1. Effort dự kiến: 8–12h. Reviewer: Lead.

1. Implement feature repositories/UoW bằng JPA; Flyway db/migration cho increment cần dùng, FK/head/document/unique constraints.
2. Spring Security session fake demo users, hashed passwords, owner guard cho document/job/run/revision/page/export.
3. CSRF token cho forms/JS mutations; stable JSON auth/errors ở /api/v1, HTML login theo web boundary.
4. Original/export private keys server-generated, path containment/hash/size; failed transaction/staging có registry để cleanup bounded.
5. Test user2 không đọc/ghi user1, CSRF missing rejected, migrate clean/existing DB; không auto schema create production.

Nộp: Auth/repositories/Flyway/storage + integration tests.

Xong khi: Private assets không public static; permission enforced server-side, không chỉ UI hide buttons.

### B2.2 — Upload/list/detail và page access, tuần 2–3

Dependency/input: B2.1; O1.1/O1.2 profile. Effort dự kiến: 6–10h. Reviewer: AI-1 + Lead.

1. POST documents multipart file/type trả201; streaming byte limit, signature/decoder, image pixels, PDF encrypted/page count dưới resource bounds.
2. Java admission kiểm rẻ trước job; Python canonical render kiểm lại. Không hứa viewer geometry từ original preview.
3. Lưu original immutable/hash, list/detail authorized; canonical route lấy đúng run của revision, chưa có run thì báo pending.
4. Phối hợp O1 decode policy để không Java accepted mà Python silently xử lý ngoài profile.
5. Test corrupt/wrong signature/oversize/multipage/path/ownership; PDF inspection timeout rõ, no user filename path.

Nộp: Upload/list/detail/page endpoints + documented examples.

Xong khi: Fake images/PDF hợp lệ upload được; ngoài profile fail rõ, no model in request thread.

### B3.1 — PostgreSQL job lifecycle và runner claim, tuần 2–3

Dependency/input: B2.1/B2.2; B1.2. Effort dự kiến: 8–12h. Reviewer: Lead; AI-2 boundary.

1. Tạo job QUEUED + idempotency + pinned manifest/audit transaction; public create trả202. Active unique/document và queue cap serialized.
2. Runner profile poll DB, eligible next_attempt_at/deadline; FOR UPDATE SKIP LOCKED + fresh attempt/fence/lease trong transaction ngắn.
3. Commit claim trước HTTP; bounded executor concurrency1; scheduler heartbeat độc lập, không giữ DB transaction khi inference.
4. Implement state transition/claim/heartbeat/complete/fail CAS; duplicate/terminal/exhausted guards ngay từ đầu.
5. Test hai claims, rollback, idempotency same/different hash, partial unique/queue cap races với PostgreSQL thật, không mock lock semantics.

Nộp: Job service/runner/repositories/migrations/tests.

Xong khi: Job không mất khi web restart; đúng current token, no lock held through compute; không outbox/Redis.

### B3.2 — Java → Python HTTP và atomic completion, tuần 3–4

Dependency/input: B3.1; M2.3; O1.3; M2.1. Effort dự kiến: 6–10h. Reviewer: AI-1/AI-2 + Lead.

1. Implement fixed private HTTP client streaming original bytes, metadata IDs/hash/remaining budget; service auth và response body/time caps.
2. Map typed errors, schema/correlation/provenance/safe attempt prefix; stream-copy sang committed storage Java-only, hash/size trên bytes copy, decode bản copy, atomic publish. DB/viewer dùng promoted keys, không mutable Python attempt path.
3. Completion CAS current unexpired lease/deadline/cancel, unique run/job; transaction run/state/audit.
4. Atomic document guard: initial draft chỉ head-null; head tồn tại nhận candidate, kể cả user save xảy ra trong compute.
5. Test fixtures cho network/bad response wiring, then receipt actual OCR/extraction provider E2E; Python không ghi business DB.

Nộp: Java aiclient/result ingestion + actual-provider output + tests.

Xong khi: Receipt run/canonical/OCR/prediction thật lưu đúng; duplicate/late response không tạo sai run/head.

### B3.3 — Recovery, retry và cancellation, tuần 3–8

Dependency/input: B3.1/B3.2; M2.3. Effort dự kiến: 6–10h chia increments. Reviewer: AI-2 + Lead.

1. Recovery expired lease/runner chết, invalidate fence atomic theo DB time; reclaim không reset total deadline.
2. Retry allowlist busy/network/transient, bounded max3/backoff/jitter/deadline; OOM/config/invalid output permanent.
3. Cancel queued/retry terminal; running terminal+fence revoke, late response reject. UI báo logical cancel, không GPU-stop giả.
4. Status stage/error/attempt rõ; MVP stages RUNNING/terminal đủ, không invent live OCR progress nếu không có signal.
5. Test runner kill/lost response/cancel-vs-complete/DB outage/AI busy và restart; phối hợp AI slot cleanup, no infinite queue.

Nộp: Recovery/cancel/status/config + failure tests.

Xong khi: Recover hoặc fail actionable bounded; một committed run/job, duplicate computation được report đúng.

### B4.1 — Revision get/save và CAS, tuần 3–4

Dependency/input: B1.1; B2.1; B3.2 hoặc valid integration fixture. Effort dự kiến: 6–10h. Reviewer: Lead.

1. GET head/version/prediction/metadata; save full payload/base head/expected version/reason.
2. Java structural/domain validation; append revision + CAS document + audit transaction, rollback khi409.
3. Preserve immutable run/revision, stable row IDs metadata ngoài business JSON; không last-write-wins.
4. Test two saves cùng version, owner/parent/run cross-document, save cạnh tranh initial completion; assert no orphan revision/audit.

Nộp: Review APIs/services + PostgreSQL concurrency tests.

Xong khi: Một request thắng, stale409; human edits không bị overwritten, schema errors422.

### B4.2 — Approve snapshot và deterministic export, tuần 4–5

Dependency/input: B4.1; approval-policy. Effort dự kiến: 6–10h. Reviewer: Lead; Data sample gold.

1. Approve exact current head/version, revalidate snapshot total/nonambiguity/date/rules; completeness confirmation và warning ack IDs.
2. Approval unique/revision + CAS version + audit atomic; save-vs-approve race test, no silent admin bypass.
3. Export explicit approved revision + exporter version; UTF-8/decimal strings/key ordering, persisted snapshot timestamps.
4. Test blocker/missing total/unapproved/stale/owner; repeated bytes/hash identical, approved cũ còn export sau draft mới.

Nộp: Approval/export services/APIs + checksum/race tests.

Xong khi: Receipt W4 approve/export dùng được, invoice W5–6; UI không authority.

### B4.3 — Rerun/candidate/adopt/history, tuần 5–7

Dependency/input: B3.2/B3.3; B4.1. Effort dự kiến: 6–8h. Reviewer: Lead; AI-2 consumer.

1. Rerun creates new job/run pinned release; existing head untouched.
2. Run/revision/approval history; adopt candidate cùngdocument/owner, CAS append draft revision mới.
3. Canonical image theo adopted run, không overlay evidence cũ lên canonical mới; old approved revision/export vẫn truy được.
4. Test rerun completion sau edit, adopt/save race, wrong run/document, old approved export snapshot unchanged.

Nộp: History/adopt endpoints + tests.

Xong khi: Chỉ người dùng chọn adopt mới đổi head; model không tự overwrite.

### B5.1 — Thymeleaf upload/list/viewer/status, tuần 2–4

Dependency/input: B1.3; B2.2; B3.2 khi actual integration. Effort dự kiến: 5–8h. Reviewer: AI-1 overlay; Lead UX.

1. Templates auth/documents list/upload/detail, reuse same services; same-origin session, CSRF forms.
2. JS polling stable status/error; bounded interval/backoff khi page hidden/unload, no leaked timers.
3. Canonical image zoom/pan + SVG/canvas overlay normalized quad; original preview không vẽ evidence kháccoords.
4. Escape OCR/model/user strings; no th:utext/innerHTML raw; owner routes stream assets.
5. Browser check fake receipt/PDF, loading/failed/auth expiry/mobile, actual provider nối trước G1.

Nộp: Thymeleaf templates/static JS + browser evidence.

Xong khi: Operator upload/xem run thật được; no React app/npm types pipeline.

### B5.2 — Scalar/items editor, conflict và approval controls, tuần 3–7

Dependency/input: B4.1/B4.2; B5.1; O4.1. Effort dự kiến: 6–12h chia increments. Reviewer: AI-1 evidence; Lead policy.

1. Render/edit scalar + items add/edit/delete giữ strings/null; number input không chuyển tiền sang binary float.
2. JS giữ local edit buffer và version, gọi same-origin APIs kèm CSRF;409 không auto-reload mất dữ liệu hoặc auto-resubmit.
3. Hiển thị issues, completeness/warnings controls; approve/export explicit revision, candidate/adopt/history rõ.
4. Click field/item source overlay nếu available; null confidence/ambiguous evidence báo đúng; no fabricated box.
5. Browser E2E two tabs save/approve/adopt, malicious text escaped, row edit/export. Giữ UI 3 màn hình tối giản.

Nộp: Editor/history fragments + JS + browser tests/screenshots.

Xong khi: Không cần manual SQL để demo; stale edits giữ được, server guards luôn có.

### B6.1 — Failure/security/resource/performance evidence, tuần 6–9

Dependency/input: B3/B4/B5 increments; M2.3/O5. Effort dự kiến: 8–12h. Reviewer: AI-2 runtime + Lead.

1. Inject app/runner/Python crash, response loss, DB outage, cancellation race, expired token theo architecture failure matrix.
2. Kiểm owner/CSRF/XSS/paths/symlinks/hash/model-text-as-data; logs IDs-only và credential redaction.
3. Check byte/page/pixel/response/token/deadline/queue admission/capacity, no endless OOM/transient retries.
4. Đo API responsive khi inference, cold/warm time/memory/capacity, readiness; ghi hardware/config/number observations.
5. Run relevant Java/Python/contract/browser suites, Flyway checksum/migration compatibility; giữ failures rõ không skip để pass.

Nộp: Failure/concurrency/boundary tests + measured report.

Xong khi: Domain invariants pass riêng ML accuracy; không tuyên bố production-ready.

### B7.1 — Clean environment, restore/rollback/handoff, tuần 10–12

Dependency/input: O5.1; M6.1; D5.1; B6.1. Effort dự kiến: 8–12h. Reviewer: Lead + consumer khác máy.

1. Compose app/web-profile, job-runner/runner-profile, ai-service,postgres; privateAI/DB, model readonly, restricted attempt volume.
2. Receive pinned model/processor/OCR/schema manifests; activation only new jobs, old pinned releases giữ được hoặc fail rõ.
3. Backup DB + originals/approved exports + hashes; restore rehearsal, forward migration, không destructive rollback đã applied.
4. Runbook từ commands thật: install/migrate/seed/start/health/smoke/stop/restore/model rollback; no hidden local config/secrets.
5. Người khác demo hai types + invalid/stale/rerun/export cũ; artifacts lớn ngoàiGit, deploy/publish cần quyền riêng.

Nộp: Release candidate + actual runbook + clean-env/restore evidence.

Xong khi: G5 reproduction không phụ thuộc máy tác giả; limitations, quyền còn thiếu được ghi.

## Folder và kiểm thử

Java features/tests ở `backend/`; Thymeleaf `src/main/resources/templates`, JS/CSS `static`, Flyway `db/migration`. Python legacy business/web/Alembic scaffold chỉ tham chiếu, không code song song. Public contracts schema ở `specs/contracts`, cross-runtime fixtures/browser ở `tests/contract`/`tests/e2e`; CI/Compose do bạn implement khi có runnable increments.

JUnit/Spring tests cho Java, PostgreSQL integration cho locks/CAS/Flyway, Python producer contract tests do AI-2, browser E2E cross-runtime. Chưa có commands executable của app, không invent Maven/Python test success.

## Git Flow cho Backend

1. Khi team coding bắt đầu: feature/SE-<issue>_<snake_case> từ develop; một output/PR, stage cụ thể.
2. Shared schema/Flyway/lock/config báo consumer và Lead trước; không sửa Python algorithm thay AI.
3. Focused checks/diff/secrets/compatibility; ghi actual output, failures/versions/hardware.
4. PR develop, peer consumer review, Lead duyệt/merge; code thay sau approve phải review lại.
5. Shared branch merge origin/develop, không force-push/ours-theirs toàn file; retest semantic conflict.
6. Sau merge consumer smoke rồi Done; release/hotfix theo [Git Flow](../git-flow.md). Bootstrap main chỉ theo Lead yêu cầu riêng; không tự commit/push/deploy.

## Bàn giao mỗi increment

Runnable source, input/output fixtures/versions, tests/commands đã chạy, API/errors/migration affected, tiny synthetic screenshots, known failures, consumer check. UI và docs không thay domain concurrency tests hoặc ML holdout reports.
