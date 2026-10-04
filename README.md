# VietDoc

Hệ thống trích xuất và kiểm duyệt dữ liệu chứng từ tiếng Việt từ ảnh/PDF.

## Trạng thái

Repository đang ở giai đoạn **bootstrap tài liệu và Git**, chưa có ứng dụng, API, model hoặc môi trường runtime. Không có lệnh chạy server/training đã được kiểm chứng. Repo GitHub được liên kết bằng `origin`; thiết lập remote không đồng nghĩa đã push hoặc có quyền ghi.

## Phạm vi

- Hai loại: `receipt` và `invoice`, nhiều bố cục, chữ in, một trang.
- JPEG/PNG/PDF → OCR → extraction theo schema → validation → review/sửa → approve → JSON.
- Field đơn và bảng tối đa 30 dòng; field thiếu hoặc mơ hồ là `null` kèm issue.
- Prediction bất biến, sửa tạo revision mới, rerun không ghi đè head đã chỉnh.
- Synthetic/sample đã audit; không đưa dữ liệu cá nhân thật vào demo.

## Đọc trước khi làm việc

| Tài liệu | Mục đích |
|---|---|
| [AGENTS.md](AGENTS.md) | Quy ước cho người và agent |
| [Scope](specs/scope.md) | FR/NFR, input/output và non-goals |
| [Approval policy](specs/approval-policy.md) | Save, conflict, approve và export |
| [Contracts](specs/contracts/README.md) | Bốn JSON Schema tham chiếu |
| [Architecture](docs/architecture.md) | Modules, queue, persistence và failure modes |
| [Source structure](docs/source-structure.md) | Cây source target; chưa phải code đã tạo |
| [ADR index](docs/adr/README.md) | Tám quyết định đang Proposed |
| [UML](docs/uml/README.md) | Mười nguồn PlantUML và SVG |
| [Tuần 1](tasks/week-01.md) | Owner, dependencies và acceptance |
| [Bộ thiết kế gốc](docs/design/v1/README.md) | Snapshot nguyên trạng để đối chiếu |
| [HTML tổng hợp](docs/design/v1/index.html) | Mở bằng trình duyệt để đọc và xem diagram |

## Kiến trúc đề xuất

Modular monolith, cùng source/contracts; API, dispatcher và inference worker chạy riêng. PostgreSQL giữ business/job state, Redis chuyển job, private storage giữ artifacts. Stack đề xuất: Python 3.11, FastAPI/Pydantic, SQLAlchemy/Alembic, Celery/Redis và React/TypeScript. Model, dependencies và GPU budget sẽ chốt sau spike tuần 2.

## Bắt đầu trên Windows

1. Mở `D:\SE` làm thư mục project local trong Codex. Đọc `AGENTS.md` và task có owner trước khi sửa.
2. Kiểm tra `git status --short --branch` và `git remote -v`.
3. Sau bootstrap commit, tạo branch ngắn theo task: `git switch -c feat/w1-<module>`.
4. Làm một increment nhỏ, chạy focused checks và đưa evidence vào PR. Lead review/merge theo dependency; commit/push/PR cần yêu cầu riêng.

Nếu chạy bằng một tài khoản sandbox khác chủ sở hữu thư mục và gặp `dubious ownership`, dùng exception chỉ cho lệnh với đúng repo đã xác minh: `git -c safe.directory=D:/SE status`. Không dùng wildcard hoặc sửa Git config global. Repo dùng TLS backend OpenSSL ở config local; kiểm chứng chứng chỉ vẫn bật.

## Source và cấu hình

Không có skeleton module rỗng, dependency lock hoặc `.env.example` trong bootstrap này. Backend tạo source/config khi làm vertical slice đầu tiên; chỉ ghi command vào README sau khi chạy thành công. Cấu trúc chi tiết nằm ở tài liệu source structure.

Schema/diagram hiện là reference design. Khi có code, Pydantic sinh JSON Schema/OpenAPI; cập nhật contracts và docs bị ảnh hưởng trong cùng PR. Giữ `docs/design/v1` làm snapshot, không sửa nó để khớp code mới.

## Giới hạn xác minh

Báo cáo trong snapshot là kết quả của **lượt thiết kế trước**, không phải test ứng dụng hiện tại. SVG đã render; `.puml` chưa compile bằng PlantUML. Các con số accuracy/latency/dataset là mục tiêu chưa đo. Xem [handoff bootstrap](tasks/bootstrap.md) để biết kiểm tra của lượt này.
