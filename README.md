# VietDoc

Trích xuất và kiểm duyệt receipt/invoice tiếng Việt một trang: ảnh/PDF → OCR → extraction → validation → người dùng sửa/duyệt → JSON.

## Trạng thái và stack

Repository c? Java/Spring Boot/Thymeleaf foundation manual/demo, Data generator/fixtures v? OCR pretrained ti?ng Vi?t c?a AI-1 theo [proposal](docs/ocr-input-proposal.md). Java qu?n l? business state; Python ??m nhi?m Data/compute. Actual Java?Python OCR/extraction v? canonical viewer v?n c?n consumer integration. PostgreSQL durable jobs, JPA/Flyway; kh?ng d?ng React/Celery/Redis/Alembic cho MVP m?i.

UI Thymeleaf được người dùng chọn. Chi tiết job/transport/persistence được đề xuất trong [ADR-0009](docs/adr/0009-java-python-thymeleaf.md), cần Lead duyệt; không đổi Proposed thành Accepted vì đã có docs.

## Mở đúng hướng dẫn

| Cần làm | Đọc |
|---|---|
| Quy ước | [AGENTS](AGENTS.md), [SPEC ngay folder](SPEC.md) |
| Phạm vi/approval | [Scope](specs/scope.md), [policy](specs/approval-policy.md) |
| Kiến trúc/cấu trúc | [Architecture](docs/architecture.md), [source target](docs/source-structure.md) |
| Java ↔ Python | [Schemas](specs/contracts/README.md), [private compute protocol](specs/contracts/compute-api.md) |
| Giao việc từng người | [Team index](docs/team/README.md), [workflow/gates](docs/team/workflow.md) |
| Java Backend/UI | [backend SPEC](backend/SPEC.md), [Backend roadmap](docs/team/backend.md) |
| Python AI/Data | [Python README](src/vietdoc/README.md), SPEC trong module |
| UML | [10 UML views](docs/uml/README.md) |
| Quyết định/Git | [ADR index](docs/adr/README.md), [Git Flow](docs/git-flow.md) |
| Evidence của lượt redesign | [Review/verification](docs/reviews/architecture-redesign-2026-10-07.md) |
| Đối chiếu bản cũ | [Snapshot v1](docs/design/v1/README.md), không active stack |

## Scope và bất biến

Receipt/invoice, chữ in, một trang, selected type,≤30rows; money/quantity decimal strings, thiếu/mơ hồ null+issue. Prediction/revisions bất biến; save/adopt append draft, stale409; approve exact current head; export explicit approved revision, stable bytes/hash. Rerun candidate không ghi đè edits. Synthetic/sample đã audit; no real PII/raw dataset/weights in Git.

## Bắt đầu

1. Clone `https://github.com/harivodich/SE2026-T08.git` và mở folder trong Codex.
2. Mở doc vai trò + SPEC local; Lead giao một task đủ input/acceptance, không toàn bộ backlog và không folder tasks.
3. Bootstrap khung có thể làm trên main khi Lead yêu cầu riêng. Khi team coding bắt đầu, Lead đồng bộ develop với main đã kiểm; feature/bug→PR develop→peer review→Lead duyệt. Không tự suy ra quyền commit/push.
4. Python?3.11: extra `data` cho renderer, `ai1` cho loader, `ai1-ocr` cho OCR; d?ng environments ri?ng theo [Python README](src/vietdoc/README.md). Java Maven/Thymeleaf foundation v? commands ? [Backend README](backend/README.md).

Working roots: `backend/` Java; `src/vietdoc/` AI/Data; `tests/` Python/shared/E2E; `infra/` deploy config. `web/`, `migrations/` và Python business scaffold cũ có SPEC legacy; không viết implementation mới tại đó. Giữ chúng để đối chiếu, chưa xóa.

Dataset/model/runtime/secret/cache/build outputs bị ignore; tiny fictional fixtures/manifests phải review trước commit. Snapshot v1 bất biến. Docs/schema/UML checks không chứng minh app/model đã chạy; xem verification report mới.
