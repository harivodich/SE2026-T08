# ADR-0009: Java business backend, Thymeleaf và Python compute

## Status

Proposed — 2026-10-07. Người dùng đã chọn Backend Java/Spring Boot và UI Spring Boot/Thymeleaf; các chi tiết persistence/job/transport dưới đây là đề xuất cần Lead duyệt ở L1.2. Không tự chuyển các ADR cũ thành Accepted.

Thay thế hướng thiết kế của ADR [0001](0001-modular-monolith.md), [0002](0002-durable-jobs.md), phần Pydantic source-of-truth của [0008](0008-business-contracts.md) nếu được chấp nhận. Domain invariants ở 0003–0007 vẫn cần giữ.

## Context

Source hiện có 25 package init chỉ chứa docstring, không có logic chạy, Maven project hay UI app. Backend quen Java; Data/hai AI dùng Python; một Backend cũng phải làm UI trong 3–4 tháng. Thiết kế shared Python services/Celery/React không còn khớp phân công.

## Decision đề xuất

Một monorepo, business modular monolith Java (Spring MVC, Spring Security, Spring Data JPA, Flyway), Thymeleaf cùng origin. Python FastAPI chỉ là compute boundary, không có quyền business DB. Java application dùng hai profile/process: web và job-runner; Python ai-service là process riêng.

Job durable ở PostgreSQL: runner poll/claim trong transaction ngắn, release lock, gọi compute HTTP ngoài transaction; heartbeat độc lập, completion có lease/fence/unique(job_id). Không dùng Redis/Celery/outbox trong MVP vì không có broker publish. Có thể duplicate computation nhưng chỉ một committed run/job.

Contract trung lập là JSON Schema Draft 2020-12 + protocol docs; Java DTO/Python models là adapters kiểm bằng cùng fixtures, không thay schema âm thầm. UI Thymeleaf có JavaScript nhỏ cho polling/viewer/editor/conflict, không React/npm app.

AI-2 sở hữu Python serving lifecycle và pipeline wiring (M2.3); AI-1 sở hữu preprocess/OCR/geometry/evidence; Backend chỉ implement Java HTTP client và business completion.

## Alternatives và trade-offs

- Giữ Python-only: ít language boundary, nhưng Backend phải học mới cả framework và UI.
- Spring + Python Celery: thêm broker/protocol/outbox; Java không thể gửi JSON tùy ý và coi đó là Celery task.
- Spring + Python private HTTP + DB queue: phù hợp demo một host/concurrency 1, nhưng phải tự kiểm lease/retry/deadline/response-loss. Polling có độ trễ và cần index/cleanup.
- React: viewer thuận lợi nhưng thêm toolchain vào workload một Backend. Thymeleaf vẫn cần JS và browser tests; không mặc định đơn giản hóa toàn bộ editor.

Không thêm Kafka/Kubernetes, distributed cache, arbitrary extraction, live ERP.

## Migration, verification và reversibility

1. Giữ snapshot v1 bất biến; đánh dấu legacy scaffold chứ không xóa source người dùng.
2. Backend B1.1–B1.3 khóa shared fixtures, tạo Java slice; AI-2 M2.3 tạo private compute.
3. B3.1–B3.3 kiểm polling/fencing/cancel trước quality gate; actual receipt E2E W4.
4. B5.1/B5.2 kiểm Thymeleaf two-tab conflict, overlay, CSRF/XSS, không client-only approval.
5. B6.1 kiểm lost response/runner kill/DB down/busy GPU; B7.1 clean-env/restore.
6. Test Java và Python riêng, contract cross-language chung. Chưa có implementation thì chưa claim các checks runtime pass.

Trước khi có implementation có thể sửa đề xuất qua review. Sau triển khai, thay transport cần ADR mới; giữ business schema/revision policy và chuyển từng adapter, không merge unrelated implementations.

## Sources

Thiết kế là suy luận theo team/scope; framework docs chỉ xác nhận khả năng: [Spring MVC/Thymeleaf](https://docs.spring.io/spring-boot/reference/web/servlet.html), [Flyway initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html), [PostgreSQL SKIP LOCKED](https://www.postgresql.org/docs/current/sql-select.html). Exact Spring/JDK/dependency versions phải smoke và pin ở B1.3, không chọn theo trang latest động.
