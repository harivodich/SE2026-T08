# 02 — Kiến trúc hệ thống

## 1. Kiến trúc đề xuất

Modular monolith, một repository, một schema nghiệp vụ PostgreSQL. API, dispatcher và inference worker có entrypoint riêng nhưng dùng chung source/contracts. Các module sở hữu dữ liệu của mình và trao đổi qua public service/contract. Không cần HTTP giữa các module nội bộ.

| Thành phần | Quyết định | Lý do và chi phí |
|---|---|---|
| API | FastAPI + Pydantic, Python 3.11 | Typed boundary; không import/load weights trong API |
| Persistence | PostgreSQL + SQLAlchemy 2 + Alembic | Transaction, FK, JSONB và compare-and-swap; một ORM |
| Queue | Celery + Redis | Worker ngoài API; cần xử lý redelivery và cấu hình visibility timeout |
| Dispatcher | Process nhẹ, poll outbox và recovery | Đóng khoảng hở DB commit/publish; thêm một process để vận hành |
| Storage | `StoragePort`, local private volume trước | Ít hạ tầng; sau này thay bằng S3-compatible adapter |
| Web | React + TypeScript + Vite | Viewer/editor ba màn hình; Backend sở hữu UI scope nhỏ |
| OCR | PaddleOCR adapter, bật tiếng Việt | Khóa package/model revision sau spike; không dựa default model động |
| Extraction | Rule baseline + VLM adapter fine-tuned | Cùng output/schema để so sánh; model cụ thể là quyết định tuần 2 |
| Observability | Structured logs + job metrics | Có trace IDs; không triển khai ELK/Kubernetes trong MVP |
| Deployment | Docker Compose trên Linux/WSL2 | Môi trường tái lập; GPU worker dùng profile riêng khi có GPU |

FastAPI khuyến nghị công cụ như Celery cho computation nặng ở process khác: [Background tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/). PaddleOCR có `vi`, nhưng mức hỗ trợ phụ thuộc OCR version: [tài liệu chính thức](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html). Version/package trong thiết kế chưa phải lockfile đã kiểm chứng.

## 2. Ranh giới và ownership

| Module | Sở hữu | Public operations |
|---|---|---|
| `identity` | User và quyền | authenticate, authorize_document |
| `documents` | Document, file metadata, head pointer, version | upload, get, compare_and_swap_head |
| `jobs` | ProcessingJob, lease/attempt, OutboxMessage | create, claim, heartbeat, complete, fail, cancel |
| `review` | ReviewRevision, Approval | create_initial, edit, adopt, approve, get_snapshot |
| `exports` | ExportArtifact | export_approved_revision |
| `pipeline` | CPU/GPU computation, không sở hữu DB entity | process_document → PipelineResult |
| `ml` | Training/inference adapter và model manifest | load_release, predict; train/evaluate offline |
| `data` | Generator, adapters, dataset manifest | generate, normalize, validate, split |
| `evaluation` | Metric, holdout, reports | evaluate_artifacts; không viết state nghiệp vụ |
| `infrastructure` | DB session/UoW, broker, storage, logging | Adapter cho ports; không chứa approval rule |

`contracts` là dữ liệu trao đổi chung, không là nơi gom business logic. Một UnitOfWork có thể commit nhiều module trong transaction; quyền ghi entity vẫn đi qua service của module sở hữu. ORM models chỉ ở persistence adapter; route không query DB trực tiếp; pipeline/model không tự ghi result state.

Audit được append qua một `AuditPort` trong cùng transaction với thay đổi business. Module khác không sửa audit cũ. Đây là audit application-level, không phải bằng chứng chống admin DB thay đổi dữ liệu.

## 3. Luồng thành phần

Browser → API → application services → UoW/PostgreSQL và storage.

Job service commit job + outbox → dispatcher → Redis → worker → pipeline → OCR/extraction/validation → completion service → PostgreSQL.

Worker gọi cùng application services với API; không gọi HTTP ngược API. Dispatcher không chạy model. Training process tách khỏi serving, đọc dataset snapshot và xuất model release manifest.

## 4. Queue semantics và fencing

Không hứa exactly-once execution. Có thể execute lại, nhưng **một committed ExtractionRun cho mỗi job** nhờ UNIQUE(job_id) và transaction/fencing.

Job creation dùng partial UNIQUE(document_id) cho các trạng thái nonterminal `QUEUED`, `RUNNING`, `RETRY_WAIT`. Lần tạo trùng trả active job hoặc 409 theo request key, không song song inference cùng document.

Claim là CAS row với `lease_token`, `lease_until`, `attempt_count`, `stage`. Heartbeat cập nhật chỉ khi token còn current. Default dự kiến lease 60s, heartbeat 15s; deadline 180s, tối đa 3 attempts. Timeout thực khóa sau spike.

Dispatcher lấy outbox bằng short transaction `FOR UPDATE SKIP LOCKED`; publish message chỉ `job_id`, không chứa file/text. Publish OK mới mark delivered. Recovery định kỳ tìm job QUEUED/RETRY_WAIT chưa được claim quá dispatch grace hoặc RUNNING lease expired, tăng fence/requeue trong transaction và tạo outbox mới. Recovery cũng bounded theo attempts/deadline.

Celery: idempotent task, `acks_late`, prefetch 1. `task_reject_on_worker_lost` cần thử kill test, không bật cùng retry OOM vô hạn. Redis visibility timeout dự kiến 900s, lớn hơn runtime tối đa; DB recovery không phụ thuộc việc chờ redelivery Redis. [Celery task semantics](https://docs.celeryq.dev/en/stable/userguide/tasks.html), [Redis caveats](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html).

Attempt artifacts ghi dưới `documents/{id}/jobs/{job_id}/attempts/{lease_token}/...`. Late worker không overwrite artifact attempt mới. Chỉ DB committed pointer được viewer sử dụng; orphan cleanup theo manifest, không quét/xóa broad path.

## 5. Data model và constraints

| Table | Fields chính | Invariants |
|---|---|---|
| `users` | id, username, password_hash, role, active | username unique; không lưu plain password |
| `documents` | id, owner_id, type, file_key, sha256, head_revision_id, version, created_at | Head phải thuộc document; version increment trên head/approval change |
| `processing_jobs` | id, document_id, manifest_id, state, stage, attempt_count, lease_token/until, cancel_requested, error_code, deadline_at | Một job active/document; terminal không reclaim |
| `extraction_runs` | id, job_id, schema_version, prediction_json, ocr_key, page_key, model_provenance, metrics | job_id unique; prediction bất biến |
| `review_revisions` | id, document_id, extraction_run_id, parent_id, payload_json, metadata_json, creator_id, reason, created_at | Append-only content; parent cùng document; stable row IDs |
| `approvals` | id, revision_id, actor_id, warning_ack_json, reason, created_at | revision_id unique; approve current head |
| `export_artifacts` | id, revision_id, format, exporter_version, storage_key, sha256 | unique(revision_id,format,exporter_version); snapshot approved |
| `outbox_messages` | id, job_id, event_type, delivered_at, next_delivery_at | At-least-once publish; row lock dispatch |
| `audit_events` | id, actor_id/system_actor, document_id, action, base/new revision, details, created_at | Append only; details không lộ secret |
| `idempotency_requests` | owner_id, route, key, request_hash, resource_id, expires_at | unique(owner_id,route,key); khác hash →409 |
| `model_releases` | id, manifest_key/hash, schema_version, lifecycle, active_since | Manifest immutable; một active release/profile |

JSONB lưu payload type-specific để tránh entity-attribute-value hàng nghìn row. Validation giữ bên application; DB FK/unique/CAS giữ invariants quan hệ. Tables không phải ER schema pháp lý của chứng từ.

Document head có thể null lúc upload. Tạo revision rồi gán head trong transaction; dùng composite FK hoặc explicit guard để ngăn reference revision của document khác. `parent_id` và `extraction_run_id` cũng có guard document ownership.

## 6. Review concurrency

API GET trả `document_version`. Save/adopt/approve yêu cầu expected version và head ID. CAS UPDATE documents WHERE id AND version=:expected; 0 rows →409. Transaction rollback toàn revision/audit nếu CAS fail.

Payload revision không sửa in-place. Approval là row riêng, không thay payload. Save sau approve tạo draft head mới; export revision cũ vẫn hợp lệ nếu người dùng chọn rõ. Approval phải kiểm rules với đúng payload snapshot và increment document version để serialize với save/adopt.

SQLAlchemy có `version_id_col`, nhưng chỉ bảo vệ một số đường ORM flush; explicit CAS vẫn cần cho updates ngoài đường đó. [Version counter](https://docs.sqlalchemy.org/en/20/orm/versioning.html). Không dựa chỉ frontend disable button.

## 7. Storage và model provenance

Private local volume `storage/` được mount API/worker; browser chỉ lấy qua authorized API route, không static public directory. S3 adapter sau này cần sửa deployment ADR, không sửa pipeline business contract.

Object classes: original input, canonical page, preprocess image/transform, OCR JSON, raw/model output, prediction JSON, approved export. DB chỉ lưu keys/hash/size. Model release là folder read-only: weights/adapter/tokenizer/processor + immutable manifest.

Job pin release ID lúc tạo. Worker loader cache tối đa một release nếu chỉ một GPU; load release khác là cold start được đo. Không dùng `latest` remote revision runtime. API activation không sửa weights; new release → new manifest ID. Existing job giữ version cũ hoặc fail actionable nếu artifact không còn.

Original input bất biến. Canonical page sau EXIF/PDF render là hệ tọa độ viewer. Preprocess giữ inverse transform từ processed → canonical. Missing transform/evidence → source bbox null, không vẽ vùng sai.

## 8. Resource và deployment profile

Target demo: 5 operator đồng thời, 1 inference job/GPU, queue cap 20 active jobs toàn instance, file ≤20 MiB, 1 page, ≤20 MP, ≤30 rows. API metadata p95 mục tiêu ≤500ms ở 5 clients, không tính upload/inference. Pipeline p95 mục tiêu ≤120s, deadline ≤180s sau hardware spike. Đây là target, chưa có số đo.

CPU profile chạy rule baseline và OCR, có thể dùng extraction checkpoint nhỏ nếu thực nghiệm đủ nhanh. GPU profile chạy model đã chọn; không tuyên bố GPU X GB đủ trước phép đo. Serving/training không tranh cùng GPU khi demo; worker model warm-up trước buổi nghiệm thu.

Celery CUDA process được thử với pool `solo`/concurrency 1 trong spike; chặn load model trước unsafe fork. CPU OCR ban đầu tránh chiếm VRAM extraction. Không scale nhiều worker GPU khi chưa có capacity/memory evidence.

Docker Compose services: `web` (static/reverse proxy), `api`, `dispatcher`, `worker`, `postgres`, `redis`. PostgreSQL/Redis không expose ra internet. Browser cùng origin `/api/v1`, giảm CORS complexity. Health API, DB readiness và worker heartbeat/model readiness tách nhau.

## 9. Security và vận hành cần có

File signature/decode, size/pixel/page cap, PDF subprocess timeout, object-key path safety; prompt coi text tài liệu là dữ liệu, model không có tools/network. Không URL-fetch tùy ý. Local samples fictional; public samples chỉ dùng sau audit nguồn/PII/terms.

Access token giữ trong memory, expiration ngắn; API authorize từng document/run/revision/page/export. Admin actions audit. Secrets environment, `.env` không commit. Logs có request_id/job_id/document_id/stage/duration/error_code, không raw OCR hoặc nội dung mẫu nhạy cảm.

Metrics: queue age, jobs by state/stage, attempts, OCR/extraction latency, JSON parse failure, OOM, missing field rate, validation issues, manual correction rate. Không biến số corrections thành model accuracy nếu thiếu ground truth.

Backup PostgreSQL + storage manifest cùng epoch demo. Restore rehearsal xác minh FK và file hashes. Rollback app container/tag và active model release; migration expand-compatible trước, không rollback DB bằng thao tác phá dữ liệu.

Retention MVP không có auto-delete dữ liệu user. Cleanup chỉ staging/attempt orphan được registry xác định; TTL đề xuất 24h staging và 7 ngày orphan attempts, admin dry-run/review trước delete. Dữ liệu approved cần chính sách riêng khi productionize.

## 10. Failure matrix cần test

| Failure injection | Expected outcome |
|---|---|
| API chết sau DB commit job, trước publish | Outbox dispatcher vẫn publish |
| Dispatcher chết sau publish, trước mark | Duplicate message; một committed run |
| Redis mất message/restart | DB reconciliation requeue job chưa claim |
| Worker chết giữa inference | Lease expires, attempt mới; stale token không commit |
| DB outage khi completion | Không ACK success; retry/recovery giữ idempotency |
| Approve và save cạnh tranh | Một transaction thành công; còn lại 409 |
| Rerun thành công sau user đã sửa | Candidate riêng; head user không bị thay |
| Storage mất object | Job fail rõ; không trả result fake |
| Model output chứa lệnh/injection | Bị coi là text; không gọi tool hoặc thực thi |

## 11. Fitness rules và remediation

CI AST/import check: contracts không import FastAPI/ORM/model frameworks; pipeline không import business persistence; routes chỉ gọi public services; modules không import private internals nhau. Cycle detection phải dựa imports thực, không graph hard-code.

Behavior checks: one committed run/job, approval revision unchanged, export checksum stable, version conflict, bbox inverse transform. Vi phạm boundary: chuyển logic về owning service/adapter rồi update contract; không tạo wrapper không cần thiết. CI failure phải nêu file/import hoặc invariant cụ thể để reviewer sửa được.
