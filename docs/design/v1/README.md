# VietDoc — Hồ sơ thiết kế v1

Ngày thiết kế: 04/10/2026. Trạng thái: **đề xuất để team triển khai**, chưa phải phần mềm đã xây dựng hoặc benchmark đã đo.

## Quyết định chính

Xây hệ thống OCR và trích xuất chứng từ **tiếng Việt**, gồm `receipt` và `invoice`, với field đơn và bảng chi tiết. Người dùng đối chiếu nguồn, sửa, xác nhận rồi xuất JSON. Dữ liệu synthetic/sample; không nhận tài liệu riêng tư thật trong bản đồ án.

- Kiến trúc: modular monolith, cùng repository; API, dispatcher và worker là process khác nhau.
- Stack đề xuất: Python 3.11, FastAPI/Pydantic, SQLAlchemy 2/Alembic, PostgreSQL, Celery/Redis, React/TypeScript/Vite; file qua storage adapter, local volume trong bản đầu.
- PostgreSQL là nguồn trạng thái chính. Redis chuyển thông điệp; inference chạy trong worker. Model không ghi database.
- Prediction bất biến; sửa tạo revision mới. Approval và export luôn chỉ rõ revision.
- Training tập trung extraction; OCR dùng model có sẵn trước. Model cụ thể và resource budget khóa sau spike tuần 2.
- Lộ trình: 12 tuần scope bắt buộc + 4 tuần chất lượng/hoàn thiện; không phụ thuộc việc lấy được dataset ngoài.

## Cách đọc

| Tài liệu | Nội dung |
|---|---|
| [01 — Scope và workflow](01-scope-workflows.md) | Yêu cầu, use case, luồng thành công/lỗi, chính sách review |
| [02 — Kiến trúc](02-architecture.md) | Thành phần, dữ liệu, queue, concurrency, vận hành và failure modes |
| [03 — Contracts](03-contracts.md) | Schema, API, errors, OCR/extraction interfaces và versioning |
| [04 — Source structure](04-source-structure.md) | Cây source dự kiến, ownership, dependency rules, trình tự triển khai |
| [05 — Plan và teamwork](05-delivery-plan.md) | 16 tuần, backlog, acceptance, PR/merge/conflict workflow |
| [06 — Data, training, evaluation](06-data-ml-evaluation.md) | Synthetic, dữ liệu bổ trợ, fine-tune, split, metric và release gate |
| [07 — ADR](07-decisions.md) | Quyết định, trade-off, phương án thay thế và khả năng đảo ngược |
| [08 — UML](08-uml-guide.md) | Mười góc nhìn UML và cách đọc |
| [09 — Nguồn](09-sources.md) | Tài liệu chính thức và giới hạn xác minh |

`schemas/` chứa JSON Schema tham chiếu; `examples/` chỉ chứa giá trị giả lập. `uml/` chứa nguồn PlantUML và SVG trình bày. Đây là hồ sơ thiết kế, không tạo các module app rỗng hoặc giả lập implementation để coi như sản phẩm đã chạy.

## Giả định cần kiểm tra

1. Lead + 1 Data Engineer + 2 AI Engineer + 1 Backend Engineer; Backend làm UI tối giản, không có frontend engineer riêng.
2. Chưa có repo sản phẩm trong workspace đang xét; cấu trúc là thiết kế greenfield.
3. Chưa biết GPU, VRAM, thời gian làm mỗi tuần và server triển khai. Các số latency/metric/dataset là mục tiêu lập kế hoạch, không phải kết quả thực nghiệm.
4. ReceiptVQA có nhãn QA, không có sẵn toàn bộ JSON nghiệp vụ. Truy cập và chất lượng gói phải audit; pipeline không chờ nguồn này.
5. Một trang, chữ in, hai loại tài liệu. Nhận PDF có text vẫn render cùng pipeline cho bản đầu để giữ một đường xử lý.

## Điều kiện hoàn thành

Hai loại tài liệu chạy xuyên suốt; có model extraction fine-tuned, so sánh baseline/fine-tune, đánh giá bố cục mới, revision/approval/export nhất quán, kiểm thử retry/concurrency và handoff tái lập được. Nếu spike hoặc fine-tune không đạt, phải báo cáo bằng chứng và phần chưa hoàn thành; không được đổi định nghĩa hoàn thành âm thầm.
