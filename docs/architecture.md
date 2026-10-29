# Kiến trúc VietDoc: Java nghiệp vụ, Python AI

## 1. Hiện trạng và thiết kế đích

Ngày rà soát 07/10/2026: source có 25 file Python `__init__.py` chỉ docstring. Không có Java implementation/pom, server/model, UI app, migrations hay CI workflow. Cấu trúc dưới là thiết kế để triển khai, không mô tả hệ thống đã chạy. UI Thymeleaf đã được người dùng chọn; chi tiết stack/job cần Lead duyệt [ADR-0009](adr/0009-java-python-thymeleaf.md).

Một monorepo; business modular monolith bằng Java, một Python compute service. Đây là hệ thống hai runtime, không còn single-language monolith dùng chung application services.

| Thành phần | Thiết kế đích | Owner |
|---|---|---|
| Business API và HTML | Spring Boot/MVC; REST `/api/v1` + Thymeleaf | Backend |
| Auth | Spring Security, session cookie, CSRF; demo users giả | Backend |
| Business persistence | PostgreSQL; Spring Data JPA/Hibernate; Flyway | Backend |
| Job execution | Java job-runner profile riêng, PostgreSQL durable queue | Backend |
| AI transport | Private HTTP multipart request/JSON response | Java client: Backend; Python server: AI-2 |
| AI compute | FastAPI composition + preprocess/OCR/extraction/evidence | AI-2 wiring; AI-1 OCR |
| Dataset/evaluation | Python offline; manifest/splits/evaluator versioned | Data |
| Training/release | Python offline, không tranh GPU với serving khi demo | AI-2 |
| Storage | Private local volumes; Java authorize serving assets | Backend; AI chỉ attempt outputs |
| Demo deployment | Compose: app, job-runner, ai-service, postgres | Backend; AI review runtime |

Không dùng Celery/Redis/outbox/React/Alembic ở thiết kế đích. Exact JDK/Spring/dependency versions được kiểm và pin tuần 1–2, không tự cài trong lượt thiết kế. Java 21 là target đề xuất cần đối chiếu version Spring/backend environment.

## 2. Ownership và dependencies

Java feature packages: `identity`, `documents`, `jobs`, `review`, `exports`; `aiclient` là adapter I/O, `persistence/storage` là infrastructure. Controllers HTML/REST gọi cùng application services; không duplicate approval rules. Entities/DTO không là model ML.

Python: `contracts` (compute/OCR types), `pipeline`, `ml`, `data`, `evaluation`, `entrypoints/api` (private compute), `entrypoints/cli` (offline). Python không có DB credentials, không claim business jobs, không approve/export hay callback ghi business DB. Training không tự activate release.

Contract dùng schema trung lập ở [specs/contracts](../specs/contracts/README.md). Mỗi ngôn ngữ validate cùng valid/invalid fixtures. Không dùng Pydantic generated schema để tự đổi schema authoritative của Java.

Module Java không query tables module khác ngoài service/port được review. Native SQL claim/CAS đặt trong owning repository adapter dùng cùng transaction manager, không thêm ORM thứ hai. API/UI không gọi AI trực tiếp trong request xử lý người dùng.

## 3. Data flow và canonical assets

1. Browser upload PNG/JPEG/PDF + type → Java authorize, admission bounds, private original/hash → metadata 201.
2. Người dùng tạo job → Java transaction ghi `QUEUED`, pin pipeline/model manifest và request idempotency →202.
3. Runner poll DB, claim một eligible job với attempt/fence/lease; commit, rồi gửi original bytes + metadata tới Python ngoài transaction.
4. Python xác minh input/hash/limits, render canonical page, OCR → extraction → normalization → evidence/confidence. Chỉ attempt-scoped artifacts, không business state.
5. Python trả compute response. Java validate schema/correlation/provenance/safe asset paths/hash, promote verified copy sang private committed assets, rồi kiểm current fence và transaction ghi immutable run + job success + audit.
6. Chưa có head: tạo draft bằng atomic guard head-null. Đã có head (kể cả user vừa sửa): giữ head, run là candidate. Completion/save cạnh tranh phải serialize trên document row.
7. Thymeleaf viewer dùng canonical page của run mà revision dẫn tới; edit/adopt append revision, approve current head, export explicit approved snapshot.

Original bất biến. Python ghi canonical/OCR dưới `attempts/{job_id}/{attempt_id}/` trong volume riêng; Java stream-copy attempt assets sang Java-owned committed storage, kiểm hash/size trên chính bytes đã copy và decode bản copy trước atomic publish. DB chỉ trỏ promoted keys; Python không writable committed assets. Không serve trực tiếp attempt files để tránh biến đổi/TOCTOU sau validation. Canonical page phải theo revision/run, không lấy page từ rerun mới để vẽ evidence revision cũ. Trước run đầu có thể hiển thị original preview nhưng không overlay canonical evidence lên original chưa chuẩn hóa.

## 4. Job protocol và concurrency

PostgreSQL là queue/state authority; không có commit/publish gap vì không có broker. Runner poll khoảng 1s (target), bounded executor concurrency 1, chỉ claim khi còn compute slot. Claim `FOR UPDATE SKIP LOCKED` trong transaction ngắn; HTTP không giữ DB lock/session transaction.

Một active job/document (`QUEUED/RUNNING/RETRY_WAIT`) qua partial unique constraint. Job pin immutable manifest; một committed ExtractionRun/job qua UNIQUE(job_id). Atomic queue cap cần serialized admission guard nếu nhiều web/runner instances, không check-count rồi insert mù.

Lease dự kiến 60s, heartbeat 15s từ scheduler độc lập với blocking HTTP. Heartbeat/completion đều CAS current attempt/fence, state RUNNING và lease chưa expired; quá deadline/cancel thì không commit. Recovery dùng DB time tăng fence; transient fail → RETRY_WAIT, backoff có jitter và next_attempt_at. Max 3 attempts nằm trong một total job deadline dự kiến 180s, không reset deadline mỗi retry. Limits khóa sau G0.

Response loss sau compute có thể chạy lại; không claim exactly-once execution. Late attempt assets có prefix riêng không ghi đè attempt mới. Duplicate completion cùng token/run là idempotent lookup; stale token reject. Terminal jobs không reclaim. DB outage thì không ghi success; recovery khi DB trở lại.

Cancel queued/retry → CANCELLED. Cancel running atomically chuyển terminal/invalidate fence, không chỉ UI flag; late response không commit. MVP không hứa ngắt GPU ngay: Python giữ slot tới compute dừng/timeout, Java không bypass AI busy gate. Resource timeout hard-stop cần subprocess isolation/restart policy đo G0/M2.3, không giả định async cancel dừng CUDA.

Python semaphore/admission concurrency 1, không thêm queue vô hạn; busy trả typed 503/Retry-After. Không dùng nhiều Uvicorn workers cùng load model trên một GPU. Web/runner profiles và startup wiring không được load model weights.

## 5. Business DB target

| Record | Constraints/rules |
|---|---|
| users | unique username, hashed password, active/role |
| documents | owner/type/original key/hash; head/version; head thuộc đúng document |
| processing_jobs | pinned manifest/state/stage/attempt/fence/lease/deadline/next_attempt_at; active unique/document |
| extraction_runs | unique job_id; immutable prediction/evidence/issues/provenance; attempt asset references |
| review_revisions | append-only content; parent/run cùng document; stable row metadata |
| approvals | unique revision; exact current head revalidated; warning acknowledgements |
| export_artifacts | unique revision/format/exporter version; bytes/hash ổn định |
| audit_events | append action/actor/base/new revision trong cùng transaction |
| idempotency_requests | owner/route/key + hash; same key khác request →409 |
| model_releases | immutable manifest/hash; activation chỉ job mới |

Không còn outbox_messages. Payload type-specific JSONB có schema validation trong Java; relational FK/unique/CAS vẫn cần, JSONB không thay constraints. Head/parent guards kiểm cross-document; partial unique race mapping về stable errors.

## 6. Review/approval/export

Save/adopt/approve gửi expected version + head; explicit CAS trong transaction, stale →409 và rollback revision/audit. JPA optimistic locking không tự bảo vệ mọi native/bulk update, cần kiểm đường CAS cụ thể.

Approval revalidate bằng Java domain validator: schema, ngày/giờ semantic, total non-null/nonambiguous, blockers, completeness, warnings. Python issues là evidence hỗ trợ, không approval authority. Save sau approve tạo draft mới; export approved cũ vẫn giữ snapshot. Serialize decimal strings, deterministic key ordering/UTF-8, timestamp lấy persisted snapshot chứ không tạo mới mỗi export.

## 7. Security, limits, provenance

Public session cookie HttpOnly/SameSite/Secure phù hợp deploy; CSRF cả form lẫn JS mutations. Render OCR/model text escaped (`th:text`/DOM textContent), không raw HTML/eval. Object authorization cho page/job/run/revision/export; không serve storage thành static directory.

Private AI network + service credential runtime (không Git/log); fixed base URL, no arbitrary URL/file path from input. Byte/page/pixel/decode/depth/output/token caps cả Java admission và Python decode. File names không là filesystem paths. AI artifacts untrusted: containment, symlink/path traversal, hash/size/content type/canonical dimensions/prefix check trước commit.

Job pin pipeline manifest gồm OCR/preprocess/model/processor/normalizer/calibrator/schema versions/hashes. Missing release →fail rõ; không remote latest runtime. Activation/rollback do Java admin flow hoặc controlled operational command, AI training không tự đổi production.

Profile targets chưa đo: 5operators, queue20, 20MiB,20MP,1page,30rows, compute p95≤120s, deadline180s, API metadata p95≤500ms. Không hứa GPU memory trước spike. Logs chỉ IDs/stage/time/error, không document text/secrets.

## 8. Failure matrix và verification owner

| Inject | Expected | Task |
|---|---|---|
| App chết sau commit job | Runner vẫn tìm job DB | B3.1/B6.1 |
| Hai runner claim đồng thời | Một current lease; không giữ lock qua HTTP | B3.1 |
| Runner chết giữa HTTP | Lease expiry/retry bounded; stale response không commit | B3.3/B6.1 |
| Python hoàn tất nhưng mất response | Retry có thể compute lại, một committed run/job | B3.2/M2.3 |
| Cancel trong inference | Terminal fence chặn completion; UI không claim GPU đã dừng | B3.3/M2.3 |
| DB outage lúc complete | Không success giả; recovery có bounds | B6.1 |
| AI busy/OOM/invalid output | Busy transient; OOM/config/output-invalid không retry vô hạn | M2.3/B3.3 |
| Save/approve/adopt/first completion race | CAS/row guard; head không bị ghi đè | B4.1–B4.3 |
| Asset prefix/hash/symlink sai | Reject, không publish unsafe artifact | B3.2 |
| Session/CSRF/XSS/owner khác | Reject/escaped; browser giữ local edits khi409 | B2.1/B5.2/B6.1 |

Fitness checks cần viết theo implementation: Java module rules (ArchUnit hoặc equivalent), Python no business persistence imports/DB creds, schema cross-language, migration lineage, actual-provider E2E. Sửa vi phạm ở owning service/adapter, không thêm wrapper che cycle. Docs/UML validation không thay các checks runtime này.

## 9. Delivery và migration

Giữ scaffold legacy read-only (có SPEC chỉ đường), tạo Java code khi B1.3 bắt đầu; không tạo classes TODO. Target structure ở [source-structure](source-structure.md), task/weekly output ở [doc từng người](team/README.md). Java 12–16h/tuần là rủi ro chính: ưu tiên receipt vertical slice W4, ít UI polish; không dồn code về Lead. W13–16 dùng reliability/ML gap, không thêm scope.

[Spring MVC/Thymeleaf](https://docs.spring.io/spring-boot/reference/web/servlet.html) và [Flyway](https://docs.spring.io/spring-boot/how-to/data-initialization.html) hỗ trợ stack đề xuất; [PostgreSQL SKIP LOCKED](https://www.postgresql.org/docs/current/sql-select.html) dành cho queue-like consumers. Các lựa chọn trong tài liệu là thiết kế của VietDoc, chưa có benchmark triển khai.
