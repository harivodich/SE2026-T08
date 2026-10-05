# 04 — Cấu trúc source dự kiến và ownership

## 1. Repository layout

Cây dưới là thiết kế target đầy đủ. Theo yêu cầu ngày 05/10/2026, các folder/package chính đã được tạo để team bắt đầu làm việc; xem [source hiện tại](../src/vietdoc/README.md). Các file service/adapter trong cây sẽ được thêm khi triển khai từng việc, chưa có implementation runtime.

```text
vietdoc/
├── AGENTS.md                         # quy ước ổn định, không chứa tiến độ task
├── pyproject.toml                    # core + api + worker + ml optional groups
├── uv.lock                          # dependency lock sau spike
├── specs/
│   ├── scope.md
│   ├── approval-policy.md
│   ├── errors.md
│   └── contracts/                    # schema/OpenAPI sinh từ Pydantic
├── docs/
│   ├── adr/
│   ├── uml/
│   ├── data-cards/
│   ├── model-cards/
│   └── runbooks/
├── tasks/                           # backlog, acceptance, weekly decisions
├── src/vietdoc/
│   ├── contracts/
│   │   ├── business.py               # ReceiptPayload, InvoicePayload, LineItem
│   │   ├── ocr.py                    # PreparedPage, OcrBlock, OcrPage
│   │   ├── extraction.py             # ExtractionInput, RawPrediction, PipelineResult
│   │   ├── review.py                 # Review DTO, SourceRegion, FieldMetadata
│   │   ├── jobs.py                   # JobState, JobMessage, PipelineManifest
│   │   └── errors.py                 # typed error codes
│   ├── identity/
│   │   ├── public.py
│   │   ├── service.py
│   │   └── policies.py               # ownership/RBAC
│   ├── documents/
│   │   ├── public.py
│   │   ├── entities.py
│   │   ├── service.py                # upload + head CAS
│   │   └── ports.py                  # DocumentRepository, file store
│   ├── jobs/
│   │   ├── public.py
│   │   ├── entities.py
│   │   ├── service.py                # create/claim/complete/recovery
│   │   ├── lifecycle.py
│   │   └── ports.py
│   ├── review/
│   │   ├── public.py
│   │   ├── entities.py
│   │   ├── service.py                # initial/edit/adopt/approve
│   │   ├── validation.py             # approval rules, money/date consistency
│   │   └── ports.py
│   ├── exports/
│   │   ├── public.py
│   │   ├── service.py
│   │   ├── json_exporter.py
│   │   └── ports.py
│   ├── pipeline/
│   │   ├── service.py                # pure orchestration of compute stages
│   │   ├── preprocess.py
│   │   ├── geometry.py               # inverse transforms canonical coordinates
│   │   ├── ocr/
│   │   │   ├── port.py
│   │   │   └── paddle_adapter.py
│   │   ├── extraction/
│   │   │   ├── port.py
│   │   │   ├── rule_baseline.py
│   │   │   ├── model_adapter.py
│   │   │   └── prompts/              # versioned, local templates
│   │   ├── normalization.py
│   │   ├── evidence.py
│   │   └── confidence.py             # fitted calibrator or null+flags
│   ├── data/
│   │   ├── manifest.py
│   │   ├── generator/
│   │   │   ├── render.py
│   │   │   ├── values.py
│   │   │   └── templates/{receipt,invoice}/
│   │   ├── adapters/receiptvqa.py
│   │   ├── validation.py
│   │   └── splits.py
│   ├── ml/
│   │   ├── train_extractor.py
│   │   ├── model_loading.py
│   │   ├── training_dataset.py
│   │   ├── release_manifest.py
│   │   └── configs/
│   ├── evaluation/
│   │   ├── run.py
│   │   ├── fields.py
│   │   ├── line_items.py
│   │   ├── geometry.py
│   │   └── reports.py
│   ├── infrastructure/
│   │   ├── persistence/{models,repositories,uow}.py
│   │   ├── storage/{local,s3}.py      # chỉ local được implement trong MVP
│   │   ├── queue/celery_adapter.py
│   │   ├── model_registry.py
│   │   └── observability.py
│   └── entrypoints/
│       ├── api/{app,dependencies,exception_handlers}.py
│       │   └── routes/{auth,documents,jobs,review,exports,admin}.py
│       ├── worker/{app,tasks}.py
│       ├── dispatcher/main.py
│       └── cli/{seed_users,generate_data,evaluate,publish_release}.py
├── web/
│   ├── package.json
│   ├── src/
│   │   ├── api/generated/            # từ OpenAPI
│   │   ├── features/{auth,documents,review}/
│   │   ├── components/{DocumentViewer,FieldEditor,ItemsGrid,IssuePanel}/
│   │   └── app/
│   └── tests/
├── migrations/                      # một Alembic lineage; Backend điều phối
├── tests/
│   ├── unit/{documents,jobs,review,pipeline}/
│   ├── integration/{api,queue,persistence,storage}/
│   ├── contract/
│   ├── architecture/
│   ├── e2e/
│   └── fixtures/                    # fictional tiny fixtures, không full dataset
├── datasets/{raw,processed,manifests}/ # raw/processed ignored, manifest tracked
├── artifacts/{models,evaluation}/     # model binaries ignored
├── storage/                          # runtime ignored
├── infra/{compose.yaml,Dockerfile.api,Dockerfile.worker,web.conf}
├── .github/{workflows,CODEOWNERS,PULL_REQUEST_TEMPLATE.md}
└── .env.example                     # chỉ tên biến và giá trị không nhạy cảm
```

`s3.py` ở cây là vị trí tương lai, không tạo implementation rỗng. Hạn chế thêm repository/interface nếu chỉ một helper pure; các ports trên được dùng ở I/O hoặc model boundary thật.

## 2. Dependency rules

1. `contracts` không import entrypoints, database, Celery, Paddle, Transformers.
2. Business entities/services không import FastAPI decorators, ORM hoặc GPU libraries; chỉ contracts và ports cần thiết.
3. `pipeline` dùng contracts + compute adapters; không import modules persistence hoặc gọi services review/export.
4. `data/ml/evaluation` không gọi production API để training; dùng dataset snapshot/artifacts.
5. Routes gọi public services, không model inference/SQL trong handler.
6. Worker task chỉ claim → compute → completion service. Không lặp business rules riêng của API.
7. Cross-module calls qua `public.py`; UoW injection từ entrypoint composition root.
8. `infrastructure/persistence` implement owning-module ports; dùng chung SQLAlchemy session, không thêm ORM khác.

DAG mong muốn: contracts ở đáy; services/ports phụ thuộc contracts; adapters phụ thuộc ports/contracts; entrypoints compose services/adapters. `review` được dùng `documents.public`; `exports` được dùng `review.public`; `jobs` điều phối `documents.public` và `review.public` nhưng review không gọi jobs. Status UI lấy API composition, không tạo cycle modules.

## 3. CODEOWNERS và integration ownership

| Path | Implementer chính | Reviewer bắt buộc |
|---|---|---|
| contracts, specs, ADR | Backend implement contract; Lead thiết kế | Lead + consumer bị ảnh hưởng |
| data/generator/adapters/splits | Data Engineer | AI-1/AI-2 + Lead khi schema/split đổi |
| preprocess/geometry/ocr/evidence | AI-1 | AI-2 khi input đổi; Backend khi UI bbox đổi |
| extraction/model adapter/ml/confidence | AI-2 | AI-1 + Lead |
| evaluation | Data Engineer | Cả hai AI; Lead metric/release gate |
| identity/documents/jobs/review/exports/persistence/API/web | Backend | Lead; AI reviewer cho integration contract |
| infra/CI/migrations | Backend | Lead; model worker config cần AI-2 |

Lead **không có backlog coding thường xuyên**. Lead quyết scope/contract, review, merge và điều phối conflict; Backend chịu phần code bootstrap/CI. Nếu Backend quá tải UI, giảm polish hoặc xin bổ sung người, không âm thầm dồn code cho Lead.

## 4. Các unit interfaces cần khóa tuần 1

- OCR → extraction: text, ordering, canonical geometry, limits.
- Model → pipeline: raw output, finish reason, timing; JSON schema không phụ thuộc vendor model.
- Pipeline → jobs: payload/evidence/issues/provenance; terminal errors typed.
- Review → frontend: revision/head/version, stable row IDs, issues severity.
- Export → consumer: approved snapshot, schema version, decimal strings.
- Dataset → training: source IDs, template families, split, label status và evidence.

## 5. Trình tự xây source

1. Backend tạo contracts + upload/job metadata + rule baseline pipeline, AI-1 đưa một OCR fixture đúng contract. Data tạo 10–20 fictional documents có labels.
2. Chạy vertical slice trên một receipt: upload → xử lý thật → review → approve → JSON; không chờ model fine-tune mới tích hợp.
3. AI-1 thay OCR fixture bằng engine thật; AI-2 thêm model adapter đã chạy smoke; tests fixture không được dùng để báo AI accuracy.
4. Mở invoice và line items bằng cùng orchestration, không fork backend thứ hai.
5. Hoàn thiện outbox/recovery/CAS, model release manifest và evaluation gates trước release.

CLI names là đề xuất; command cụ thể chỉ ghi README khi code đã thực thi thành công. Không copy chạy snippets training ngoài repo mà không audit dependencies/model licensing.
