# Architecture redesign review — 2026-10-07

Rà soát bắt đầu 07/10; các checks cuối hoàn tất 08/10/2026 (Asia/Saigon).

## Kết luận và observed state

Thiết kế đích: Java/Spring Boot/Thymeleaf business backend + private Python AI compute. User đã chọn Thymeleaf; JPA/Flyway/PostgreSQL runner/private HTTP là đề xuất ADR-0009 cần Lead chấp nhận. Source khi bắt đầu chỉ25 init Python docstrings, không runnable app hoặc Java code. Working tree main sạch trước thay đổi, origin https://github.com/harivodich/SE2026-T08.git; không kiểm push permission/GitHub settings trong lượt này.

## Findings và changes

- High: Python-only architecture/shared services/Celery/React không khớp kỹ năng Backend; cập nhật boundaries, stack, jobs, source target và local SPECS.
- High: pipeline wiring từng giao Backend gây cross-language ownership sai; chuyển Python service/wiring AI-2 M2.3, AI-1 preprocess/OCR, Java integration Backend.
- High: Pydantic authority không dùng chung Java/Python; neutral schema/protocol + same fixtures và adapter parity.
- Medium: một Backend cả UI/DB/jobs là bottleneck; Thymeleaf scope3pages, capacity/gate trade-off ghi rõ, không dồn code sang Lead.
- Positive: immutable predictions/revisions, CAS/approval/export, leakage/evaluation protocol giữ nguyên.

Roadmaps/task cards trong doc từng người,49cards; không folder tasks. Private/public API design bổ sung,10UML source+SVG theo target. Legacy scaffold chỉ đánh dấu, chưa xóa. Snapshot docs/design/v1 bất biến, old verification reports giữ lịch sử và banner context.

## Verification

| Check thực chạy | Result | Giới hạn |
|---|---|---|
| Draft 2020-12, jsonschema 4.26.0 + local registry/FormatChecker | 11 schemas meta-valid; 50 v1 cases + 33 new compute cases pass | JSON shape, không Java/Python DTO/runtime |
| PlantUML 1.2026.8 local | 10 active sources compile exit0, 10 SVG generated | Target architecture, không app proof |
| Headless Chrome/Playwright SVG render | 10 SVG nonempty, 0 page errors, 0 external requests | Diagram QA, không Thymeleaf app QA |
| Visual inspection | Components/processing/deployment screenshots inspected | Vector diagram có thể zoom, không screenshot app |
| Local folder SPEC coverage | 81/81 working folders; no missing SPEC | Không tính git/cache/tooling/frozen v1 |
| Markdown internal file targets | 0 broken local targets | Không kiểm external URLs/fragment anchors |
| Task headings | 49/49 unique: Lead6/Data8/AI-1eight/AI-2twelve/Backend15 | Không issues đã tạo hoặc tasks đã Done |
| Python AST source inspection | 25 files, tất cả docstring-only; 0 Java files | Chưa runtime implementation |
| Git diff --check | exit0 | Whitespace, không runtime correctness |
| Snapshot/source/config preservation | docs/design/v1, Python .py, pyproject unchanged; staged list empty | Không commit/push trong lượt này |
| Ignore probes | Java target/.env, pycache, raw samples, model weights, runtime, local verification ignored | Không đưa artifacts/secrets vào danh sách mới |
| Secret-pattern scan | Không match private-key/token patterns trong edited context/fixtures | Basic pre-handoff check, không security audit đầy đủ |

Compiler lần đầu bắt lỗi cú pháp training activity; đã sửa và compile lại tất cả sources. Một test expectation dùng path traversal dạng bị regex chặn, đã sửa fixture thành nested traversal; 33/33 final pass. Correlation sai/duplicate assets/nested traversal có thể qua structural schema: đây là minh chứng cần Java semantic/path/hash validators, không coi schema là security boundary đầy đủ.

Verification commands trên máy này:

```powershell
.verification/python/Scripts/python.exe .verification/verify_schemas.py
.verification/python/Scripts/python.exe .verification/verify_redesign.py
git -c safe.directory=D:/SE diff --check
```

PlantUML JRE/jar, jsonschema venv, browser helper và screenshots ở .verification (ignored), không runtime dependency và không file đã commit cho team. Render trực tiếp docs/uml bằng local compiler; không sửa snapshot. Commands trên dùng tooling local đã có, không là app start/train commands.

## Chưa verify runtime

Không Java build/server/Flyway/PostgreSQL locks/CAS, Python compute endpoints/OCR/model/training, Thymeleaf browser nghiệp vụ hoặc CI execution vì các implementation chưa có. Bootstrap mới không tạo classes/TODO modules hay tải model/dataset. GitNexus không index repo SE; evidence source trực tiếp, không graph suy diễn.

## Acceptance và next tasks

Lead L1.1/L1.2 duyệt boundaries/ADR/capacity/role mapping, Data D1.1/D1.2 dictionary/samples, AI-1 O1.1/O1.2/O1.3, AI-2 M1.1/M1.2/M1.3 và M2.3, Backend B1.1/B1.2/B1.3. Mã không là issues đã tạo. Không commit/push/deploy trong lượt này, không tự tạo branch mới; tất cả edits local trên main.

Local main và origin/main tracking ref vẫn c7fabcc; develop/origin-develop tracking ref 15cef05, sau main một commit. Các ref này đọc local, không fetch/verify GitHub live. Trước team coding Lead cần đồng bộ develop với main sau khi bootstrap được duyệt/publish; lượt này không mutate branches/remote.

Không xóa source. Legacy Python business/React/Alembic giữ local SPEC chỉ đúng đích mới; cleanup đợi verified Java slice và PR riêng. Java assets cần promote verified stream-copy từ mutable attempt volume sang committed Java-owned storage, không dùng pointer tới Python-writable files làm bất biến.

Tài liệu giao việc chính: [architecture](../architecture.md), [source structure](../source-structure.md), [team](../team/README.md), [workflow](../team/workflow.md), [ADR-0009](../adr/0009-java-python-thymeleaf.md), [public API](../../specs/contracts/public-api.md), [compute protocol](../../specs/contracts/compute-api.md), [UML](../uml/README.md).
