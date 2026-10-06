# VietDoc

Hệ thống trích xuất và kiểm duyệt dữ liệu chứng từ tiếng Việt từ ảnh/PDF.

## Trạng thái

Repository có tài liệu thiết kế và khung thư mục để team bắt đầu viết code. Các package Python hiện là scaffold; API, OCR/model và giao diện sẽ được triển khai từng phần theo việc được giao.

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
| [Spec ngay trong folder](SPEC.md) | Mở SPEC.md của folder đang làm: purpose/owner/content/checks |
| [Architecture](docs/architecture.md) | Modules, queue, persistence và failure modes |
| [Source structure](docs/source-structure.md) | Cấu trúc đích và ranh giới module |
| [Source hiện tại](src/vietdoc/README.md) | Viết code vào đâu, phần nào thuộc ai |
| [Hướng dẫn từng vai trò](docs/team/README.md) | Roadmap tuần, task chi tiết, output và Git Flow từng người |
| [Workflow team](docs/team/workflow.md) | Bàn giao, Git Flow thực hành và gate nghiệm thu |
| [ADR index](docs/adr/README.md) | Tám quyết định đang Proposed |
| [UML](docs/uml/README.md) | Mười nguồn PlantUML và SVG |
| [Git Flow](docs/git-flow.md) | Branch, PR, review và merge |
| [Audit readiness](docs/reviews/repository-readiness-2026-10-07.md) | Kiểm kê file/folder, checks và phần chưa xác minh |
| [Xác minh thực tế](docs/reviews/verification-2026-10-07.md) | Validator chuẩn, compiler UML, browser QA và runtime discovery |
| [Bộ thiết kế gốc](docs/design/v1/README.md) | Snapshot nguyên trạng để đối chiếu |
| [HTML tổng hợp](docs/design/v1/index.html) | Mở bằng trình duyệt để đọc và xem diagram |

## Kiến trúc đề xuất

Modular monolith, cùng source/contracts; API, dispatcher và inference worker chạy riêng. PostgreSQL giữ business/job state, Redis chuyển job, private storage giữ artifacts. Stack đề xuất: Python 3.11, FastAPI/Pydantic, SQLAlchemy/Alembic, Celery/Redis và React/TypeScript. Model, dependencies và GPU budget sẽ chốt sau spike tuần 2.

## Bắt đầu trên Windows

1. Clone repo: `git clone https://github.com/harivodich/SE2026-T08.git` rồi mở thư mục đó trong Codex.
2. `main` giữ bản chung ổn định; `develop` dùng tích hợp. Khi nhận một việc, tách branch từ `develop` theo [Git Flow](docs/git-flow.md).
3. Mở SPEC.md ngay trong folder định sửa và [doc cá nhân](docs/team/README.md) để biết roadmap/task/Git Flow. Mỗi PR một việc; consumer review trước, Lead duyệt cuối.
4. Lead giao task nhỏ; tiến độ/acceptance/evidence ở GitHub Issue/PR hoặc phiếu giao trực tiếp, không folder tasks và không mở sẵn toàn bộ backlog.

Nếu chạy bằng một tài khoản sandbox khác chủ sở hữu thư mục và gặp `dubious ownership`, dùng exception chỉ cho lệnh với đúng repo đã xác minh: `git -c safe.directory=D:/SE status`. Không dùng wildcard hoặc sửa Git config global. Repo dùng TLS backend OpenSSL ở config local; kiểm chứng chứng chỉ vẫn bật.

## Source và cấu hình

`pyproject.toml` khai báo package `vietdoc`, Python ≥3.11, chưa thêm dependencies runtime. Các folder đã tạo theo thiết kế; chỉ thêm file có logic khi triển khai việc tương ứng. Chưa có lệnh chạy server hoặc training.

```text
src/vietdoc/   Python: contracts, nghiệp vụ, OCR/extraction, data, training, API/worker
web/           React/TypeScript khi bắt đầu làm giao diện
tests/         Unit, integration, contract và end-to-end
migrations/    Alembic migrations do Backend quản lý
infra/         Docker Compose và cấu hình triển khai
datasets/      Raw/processed ở local; manifest nhỏ có thể commit
artifacts/     Model và kết quả chạy ở local
storage/       File người dùng/runtime ở local
specs/         Scope, schema và approval policy
docs/          Thiết kế, UML, Git Flow và lịch sử
```

`.gitignore` loại secrets, môi trường ảo, caches, datasets raw/processed, weights, runtime storage và outputs. File `.gitkeep` chỉ giữ thư mục trống; không chứa dữ liệu. Tiny fictional fixtures và manifests cần được review trước khi commit.

Schema/diagram hiện là reference design. Khi có code, Pydantic sinh JSON Schema/OpenAPI; cập nhật contracts và docs bị ảnh hưởng trong cùng PR. Giữ `docs/design/v1` làm snapshot, không sửa nó để khớp code mới.

## Giới hạn xác minh

Báo cáo trong snapshot là kết quả của lượt thiết kế trước. SVG đã render; `.puml` chưa compile bằng PlantUML. Các con số accuracy/latency/dataset là mục tiêu chưa đo. Ghi chép cũ nằm trong [lịch sử bootstrap](docs/history/bootstrap-2026-10-04.md).
