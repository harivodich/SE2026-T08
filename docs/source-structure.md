# Source structure và ownership đích

## Hiện có và đích

Hiện có: package Python docstring-only, SPEC local, schemas/docs/fixtures thiết kế. `backend/` mới có tài liệu hướng dẫn, chưa Maven app. Cây dưới là target, chỉ tạo file có logic khi triển khai task. Không xóa scaffold cũ trong lượt thiết kế; chúng được đánh dấu legacy để không giao nhầm người.

```text
backend/                          Java/Spring Boot; Backend owns
  pom.xml, mvnw, .mvn/             thêm khi B1.3 smoke thành công
  src/main/java/vn/vietdoc/
    VietDocApplication.java
    config/                       web vs runner profiles, security/limits
    contracts/                    Java DTO + shared-schema validation
    identity/                     auth/ownership
    documents/                    upload/metadata/head CAS
    jobs/                         durable lifecycle/runner/recovery/fence
    review/                       revision/approval/semantic validator
    exports/                      deterministic approved JSON
    aiclient/                     private compute HTTP adapter
    infrastructure/               persistence/storage/logging
  src/main/resources/
    templates/
      auth/                       login
      documents/                  list/upload/detail
      review/                     scalar/items/issues/history fragments
    static/{css,js}/               viewer.js/editor.js/status.js
    db/migration/                 Flyway V<n>__<name>.sql
  src/test/java/vn/vietdoc/        unit/integration/module checks
src/vietdoc/                      Python compute + offline AI/Data
  contracts/                      OCR/compute typed adapters, no business services
  pipeline/
    service.py                    AI-2 stage wiring, AI-1 review
    preprocess.py, geometry.py    AI-1 image/canonical transforms
    evidence.py                   AI-1 source association
    ocr/                          AI-1 engine port/adapter
    extraction/                   AI-2 rules/model/prompt adapters
    normalization.py              AI-2 locale canonical values
    confidence.py                 AI-2 calibrated scores/null
  data/{generator,adapters}/       Data, dictionary/manifests/splits/QA
  ml/                             AI-2 train/loading/releases/config
  evaluation/                     Data, independent metric/report code
  infrastructure/storage/         AI-2 attempt outputs; no DB/broker
  entrypoints/api/                AI-2 private FastAPI compute/health
  entrypoints/cli/                Data CLI + AI-2 training/eval composition
tests/
  unit/pipeline/                  Python geometry/extraction/data tests
  contract/                       language-neutral valid/invalid fixtures
  integration/api/                Python compute boundary tests
  architecture/                   Python no business DB imports
  e2e/                            cross-runtime/browser tests
  fixtures/                       tiny fictional samples only
specs/                            scope/policy/contracts/protocol
docs/team/                        per-role weekly roadmap/task/Git Flow
infra/                            app + runner + AI + PostgreSQL Compose
datasets/{raw,processed,manifests}/
artifacts/{models,evaluation}/
storage/                          originals, attempts, exports; ignored
```

Mỗi working folder mới phải có SPEC.md ngay khi có task cần tạo folder. Không tạo toàn bộ cây/class rỗng chỉ để đẹp. Backend tests/migrations không viết vào Python legacy folders.

## Legacy: không viết tính năng mới

| Vùng đang tồn tại | Đích thay thế |
|---|---|
| src/vietdoc/identity,documents,jobs,review,exports | backend/src/main/java/vn/vietdoc/<feature> |
| src/vietdoc/infrastructure/persistence,queue | Java persistence/jobs adapters |
| src/vietdoc/entrypoints/worker,dispatcher | Java job-runner profile, không Python Celery |
| web/ | backend/src/main/resources/templates và static |
| migrations/ | backend/src/main/resources/db/migration (Flyway) |
| tests/unit/documents,jobs,review; tests/integration/persistence,queue,storage | Java tests, trừ cross-runtime tests viết có chủ đích |

Legacy markers/docstrings giữ để đối chiếu và tránh destructive cleanup. Sau Java slice được kiểm, Backend có thể đề xuất PR loại scaffold cũ với diff/recovery rõ; không dùng cả hai implementations.

## Dependency rules

- Java controllers → owning services → domain/ports; adapters thực hiện I/O. Domain không import Python/model framework.
- `aiclient` chuyển protocol JSON thành DTO, kiểm ids/schema/provenance/assets; không chứa OCR algorithms.
- Python contracts không import FastAPI/Paddle/Transformers hoặc ORM. Entrypoint compose lifecycle; pipeline không business persistence.
- Data/ML/evaluation offline không gọi approval API hay tự activate model.
- HTML và REST reuse cùng business service; Java server là approval authority, không UI/Python.
- Pure helper không cần port/factory nếu không có I/O boundary thật.

## Ownership và hợp đồng cần khóa W1

| Path/boundary | Implementer | Reviewer |
|---|---|---|
| specs/contracts + protocol | Backend chỉnh shared spec; Lead thiết kế | Data/AI-1/AI-2 |
| Java DTO/app/domain/storage/runner/UI/migrations/CI | Backend | Lead; AI tại boundary |
| Python OCR/page types + preprocess/OCR/geometry/evidence | AI-1 | AI-2, Backend viewer |
| Python compute request/response types, serving/service.py | AI-2 | Backend, AI-1 |
| Python extractor/model/train/normalizer/confidence | AI-2 | AI-1, Data; Lead gate |
| Python generator/splits/evaluator + offline data CLI | Data | Hai AI; Lead metric/split |
| Python model lock/runtime | AI-2 điều phối; AI-1 OCR dependency | Backend build/deploy consumer |

Khóa page/quad/order, model input/raw output, compute multipart/result/errors, attempt asset manifest, revision/head/version, export, dataset supervision/split. Shared schema chỉ một PR writer tại một thời điểm; consumers có adapter độc lập.

## Thứ tự source increments và migration

1. B1.1/B1.2 shared examples + Java DTO; O1 page/OCR proposal; M2.3 private compute skeleton chỉ khi task implementation được giao.
2. B1.3 Java health/login/Thymeleaf minimal runnable; B2 private upload; Data20 samples; AI1 OCR thật; AI2 model/train-step smoke.
3. B3 PostgreSQL runner gọi Python thật; M2.3 connects stages; B4/B5 receipt save/approve/export W4.
4. Invoice/items W6; evidence/confidence + cancel/rerun/history W8.
5. Failure/quality/clean-env gates W10–12, buffer13–16. Có fixtures để test wiring, không dùng chúng để nghiệm thu OCR/model quality.

Không ghi start/train commands trong README khi chưa chạy được. API contracts đích ở [protocol](../specs/contracts/compute-api.md); workflow ở [team](team/workflow.md); quyết định ở [ADR-0009](adr/0009-java-python-thymeleaf.md).
