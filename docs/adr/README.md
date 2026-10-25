# Architecture decisions

Tám ADR v1 dưới giữ quyết định của [thiết kế v1](../design/v1/07-decisions.md). Các ADR v1 đang **Proposed**, ngày 2026-10-04; bootstrap không đồng nghĩa team đã chấp nhận hoặc triển khai chúng.

| ADR | Quyết định | Status |
|---|---|---|
| [0001](0001-modular-monolith.md) | Modular monolith, processes riêng | Proposed |
| [0002](0002-durable-jobs.md) | PostgreSQL/outbox/Celery/Redis | Proposed |
| [0003](0003-revision-approval.md) | Immutable prediction/revision/approval | Proposed |
| [0004](0004-data-boundary.md) | Synthetic Việt main, public audit | Proposed |
| [0005](0005-model-spike.md) | OCR baseline và fine-tune extraction | Proposed |
| [0006](0006-geometry-confidence.md) | Canonical geometry và calibrated confidence | Proposed |
| [0007](0007-storage-polling.md) | Private local storage, UI polling | Proposed |
| [0008](0008-business-contracts.md) | Fixed business schema; Pydantic authority cũ | Proposed v1, xem 0009 |
| [0009](0009-java-python-thymeleaf.md) | Java/Thymeleaf + Python compute; PostgreSQL runner, neutral schemas | Proposed mới |

ADR-0009 là hướng thiết kế hiện hành để review. 0001/0002 và phần code-generated authority 0008 không được dùng làm quyết định implementation mới; khi 0009 được chấp nhận mới đánh dấu superseded. UI Thymeleaf đã được người dùng chọn; không suy ra acceptance các lựa chọn kỹ thuật còn lại.

Lead/team ghi acceptance hoặc thay đổi trong PR có reason/evidence. Giữ ADR đã accepted cho lịch sử; đổi quyết định tạo ADR superseding, không sửa snapshot gốc hoặc xóa quyết định cũ. Không lấy heuristic trong skill làm yêu cầu thay kiến trúc đã thống nhất.
