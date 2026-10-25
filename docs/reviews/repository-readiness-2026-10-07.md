# VietDoc — audit sẵn sàng giao việc

> Evidence/kiểm kê của thiết kế Python-only trước redesign. Kiến trúc hiện hành và checks mới ở [redesign report](architecture-redesign-2026-10-07.md); không dùng kết quả cũ làm Java/Thymeleaf runtime proof.

> Đây là snapshot audit trước khi thêm SPEC.md từng folder/chạy tool kiểm định. Xem [verification mới](verification-2026-10-07.md) cho kết quả hiện hành; counts và unverified dưới đây là lịch sử, không còn trạng thái mới nhất.

Ngày: 07/10/2026, Asia/Saigon. Audit local tại D:\SE, không đọc lại GitHub invitations/protection/CI settings hoặc publish gì.

## 1. Kết luận

Context local đủ để Lead kickoff, gán người và giao task đầu tiên. Chưa có ứng dụng/OCR/model chạy: 25 Python files chỉ là docstring scaffold, tests/web/migrations/infra chưa có implementation. Không tuyên bố runtime, CI, training hoặc GitHub đã đồng bộ.

Trước khi giao cần xác nhận người thật cho Data/AI-1/AI-2/Backend, thời gian/hardware/cost, canonical/OCR/extraction interfaces và owner thin pipeline wiring đề xuất Backend. ADR vẫn Proposed đến khi team quyết định.

## 2. Thay đổi tổ chức tài liệu

- [Spec folder](../../specs/repository-layout.md) giải thích purpose/owner/commit policy/status theo root/modules/UI/tests/data/artifacts/runtime.
- 48 task nhỏ được chuyển nguyên input/steps/output/acceptance về doc cá nhân, mỗi người có roadmap theo tuần và Git Flow; không mất task hoặc tạo duplicate IDs.
- [Workflow chung](../team/workflow.md) giữ handoffs/gates/Git Flow dùng chung. Hai index roadmap/playbook cũ chỉ còn link tương thích, không duy trì plan dài thứ hai.
- Tasks folder bị bỏ khỏi workflow và root, hai file cũ lưu ở [history](../history/tasks-retired-2026-10-07/README.md); có thể khôi phục từ các bản này. Không xóa dữ liệu lịch sử.
- README/AGENTS/source guide/Git Flow/history links được đồng bộ; docs/design/v1 và runtime source không bị sửa.

| Doc cá nhân | Task count | Nội dung hiện có |
|---|---|---|
| `docs/team/ai-1-ocr.md` | 8 | Roadmap W1–12 + buffer, task cards, reviewer, Git Flow, checklist |
| `docs/team/ai-2-extraction.md` | 11 | Roadmap W1–12 + buffer, task cards, reviewer, Git Flow, checklist |
| `docs/team/backend.md` | 15 | Roadmap W1–12 + buffer, task cards, reviewer, Git Flow, checklist |
| `docs/team/data-engineer.md` | 8 | Roadmap W1–12 + buffer, task cards, reviewer, Git Flow, checklist |
| `docs/team/lead.md` | 6 | Roadmap W1–12 + buffer, task cards, reviewer, Git Flow, checklist |

## 3. Checks và phạm vi chứng cứ

| Check | Kết quả/phạm vi |
|---|---|
| Inventory | 164 files và 83 folders sau thêm report này, không tính .git và caches __pycache__/pyc |
| Python | AST parse 25/25; chỉ docstrings, không logic runtime; không dùng import scaffold để claim app tests pass |
| JSON/TOML | 13 JSON và pyproject parse được; pyproject Python ≥3.11, dependencies runtime rỗng đúng bootstrap |
| Schema refs | 66 references trong hai bộ active/snapshot resolve nội bộ; không fetch URN qua network |
| Decimal contract smoke | 0/45000/1.5/0.25 match; -1/01/backslash-invalid không match, đúng nonnegative decimal strings |
| Snapshot copies | 4 active schema + 20 active UML source/SVG byte-identical snapshot; snapshot diff không thay đổi |
| Markdown/HTML | 239 relative links/assets tồn tại, UTF-8/fences và HTML fragment targets pass sau report tạo |
| SVG/PlantUML | 20 SVG XML parse; 20 .puml có framing; chưa compile PlantUML hoặc xác minh layout trong lượt này |
| HTML JS | Embedded module script syntax check bằng bundled Node pass; không browser-interaction QA |
| Gitignore | .env/.env.local/raw/processed/model/evaluation/runtime/pycache probes bị ignore; .env.example/safe manifest/tiny fixtures không bị ignore |
| Credentials patterns | Không match các token/private-key patterns đã quét trong text context/source; không phải full security/PII audit |
| Git scope | develop, origin đúng SE2026-T08 URL cấu hình; không fetch/push/commit/PR/merge/deploy trong lượt này |
| Task preservation | 48 IDs unique, đúng role, task cards input/steps/output/acceptance được giữ; post-move body check |
| Formatting/diff | Whitespace/fences/links đã kiểm; unrelated edits được giữ, không stage |

Không có JSON Schema compiler chuẩn đầy đủ trong Python tooling/bundle hiện có; không install dependencies ngoài scope. Parse/resolve/decimal smoke không thay full conforming validation. B1.1/B1.2 phải có compiler/positive-negative contract tests khi triển khai types. Không có app source nên API/DB/CAS/worker/inference/ML tests chưa thể chạy.

## 4. Những phần chưa có: task cần triển khai, không phải scaffold bị thiếu

| Phần chưa implement | Owner/task | Cách đóng gap |
|---|---|---|
| Pydantic models và schema validator tests | Backend B1.1/B1.2 | Typed code/source-of-truth, valid/invalid cases, consumer review |
| App/deps/lock/CI executable checks | Backend B1.3 | Runtime config/dependency groups và commands thực đã smoke |
| Auth/upload/private storage/DB/migrations | Backend B2.1/B2.2 | Slice chạy được + ownership/input/migration tests |
| Jobs/outbox/fence/worker/dispatcher | Backend B3.1–B3.3 | Actual compute integration + failure/recovery tests |
| Preprocess/OCR/geometry/evidence | AI-1 O1–O5 | Engine thật, overlay/errors/versioned configs |
| Model feasible/fine-tune/inference/confidence | AI-2 M1–M6 | Train-step/pilot/runs/artifacts/eval với actual hardware |
| Dataset/gold/splits/evaluator | Data D1–D5 | Generator/QA/versioned manifests, no leakage/PII |
| Review/CAS/approve/export/rerun | Backend B4.1–B4.3 | Immutable snapshots/races/checksums/human guards |
| Web/package.json/UI tests | Backend B5.1/B5.2 | Usable viewer/editor, actual APIs, conflict/history flows |
| Compose/Dockerfiles/runbooks/restore | Backend B6/B7 | Tạo cùng services chạy thật, clean-env/restore evidence |
| CODEOWNERS/protection/required checks | Lead + Backend khi có identities/checks | Gán người thật, kiểm quyền/settings; không tự gọi policy là đã bật |
| Hardware/capacity/ADR acceptance | Lead kickoff/G0 | Quyết định có reason/evidence, không guess GPU hoặc tự đổi status |

Các folders model-cards/data-cards/runbooks/workflows hoặc .env.example/lockfiles được tạo khi task có artifact/config thật. Không thêm blank fake implementations để làm đầy cây.

## 5. Kiểm kê từng folder

Mỗi folder hiện hữu (trừ Git internals/caches) dưới đây đã đối chiếu với spec/ownership. Purpose chi tiết ở spec, file-level check ở bảng tiếp theo. Docs/reviews chứa report hiện tại; tasks không còn ở root.

- `.github`
- `artifacts`
- `artifacts/evaluation`
- `artifacts/models`
- `datasets`
- `datasets/manifests`
- `datasets/processed`
- `datasets/raw`
- `docs`
- `docs/adr`
- `docs/design`
- `docs/design/v1`
- `docs/design/v1/examples`
- `docs/design/v1/schemas`
- `docs/design/v1/uml`
- `docs/history`
- `docs/history/tasks-retired-2026-10-07`
- `docs/reviews`
- `docs/team`
- `docs/uml`
- `infra`
- `migrations`
- `migrations/versions`
- `specs`
- `specs/contracts`
- `src`
- `src/vietdoc`
- `src/vietdoc/contracts`
- `src/vietdoc/data`
- `src/vietdoc/data/adapters`
- `src/vietdoc/data/generator`
- `src/vietdoc/data/generator/templates`
- `src/vietdoc/data/generator/templates/invoice`
- `src/vietdoc/data/generator/templates/receipt`
- `src/vietdoc/documents`
- `src/vietdoc/entrypoints`
- `src/vietdoc/entrypoints/api`
- `src/vietdoc/entrypoints/api/routes`
- `src/vietdoc/entrypoints/cli`
- `src/vietdoc/entrypoints/dispatcher`
- `src/vietdoc/entrypoints/worker`
- `src/vietdoc/evaluation`
- `src/vietdoc/exports`
- `src/vietdoc/identity`
- `src/vietdoc/infrastructure`
- `src/vietdoc/infrastructure/persistence`
- `src/vietdoc/infrastructure/queue`
- `src/vietdoc/infrastructure/storage`
- `src/vietdoc/jobs`
- `src/vietdoc/ml`
- `src/vietdoc/ml/configs`
- `src/vietdoc/pipeline`
- `src/vietdoc/pipeline/extraction`
- `src/vietdoc/pipeline/extraction/prompts`
- `src/vietdoc/pipeline/ocr`
- `src/vietdoc/review`
- `storage`
- `tests`
- `tests/architecture`
- `tests/contract`
- `tests/e2e`
- `tests/fixtures`
- `tests/integration`
- `tests/integration/api`
- `tests/integration/persistence`
- `tests/integration/queue`
- `tests/integration/storage`
- `tests/unit`
- `tests/unit/documents`
- `tests/unit/jobs`
- `tests/unit/pipeline`
- `tests/unit/review`
- `web`
- `web/src`
- `web/src/api`
- `web/src/api/generated`
- `web/src/app`
- `web/src/components`
- `web/src/features`
- `web/src/features/auth`
- `web/src/features/documents`
- `web/src/features/review`
- `web/tests`

## 6. Kiểm kê từng file

Git status là trạng thái local lúc audit, không đồng nghĩa file đã publish GitHub. Marker/source scaffold chỉ syntax/context ready. Files ở snapshot/history là reference/historical, không runtime authority.

| File | Local Git | Check/classification |
|---|---|---|
| `.gitattributes` | Tracked (có thể có local edits) | Context/config reviewed |
| `.github/PULL_REQUEST_TEMPLATE.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `.gitignore` | Tracked (có thể có local edits) | Context/config reviewed |
| `AGENTS.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `artifacts/evaluation/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `artifacts/models/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `artifacts/README.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `datasets/manifests/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `datasets/processed/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `datasets/raw/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `datasets/README.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/adr/0001-modular-monolith.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/adr/0002-durable-jobs.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/adr/0003-revision-approval.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/adr/0004-data-boundary.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/adr/0005-model-spike.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/adr/0006-geometry-confidence.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/adr/0007-storage-polling.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/adr/0008-business-contracts.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/adr/README.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/architecture.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/design/v1/01-scope-workflows.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/design/v1/02-architecture.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/design/v1/03-contracts.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/design/v1/04-source-structure.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/design/v1/05-delivery-plan.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/design/v1/06-data-ml-evaluation.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/design/v1/07-decisions.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/design/v1/08-uml-guide.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/design/v1/09-sources.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/design/v1/examples/export.json` | Tracked (có thể có local edits) | JSON parse OK |
| `docs/design/v1/examples/extraction-result.json` | Tracked (có thể có local edits) | JSON parse OK |
| `docs/design/v1/examples/invoice.json` | Tracked (có thể có local edits) | JSON parse OK |
| `docs/design/v1/examples/receipt.json` | Tracked (có thể có local edits) | JSON parse OK |
| `docs/design/v1/index.html` | Tracked (có thể có local edits) | HTML parse/assets/fragments checked; browser not run |
| `docs/design/v1/README.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/design/v1/schemas/business.schema.json` | Tracked (có thể có local edits) | JSON parse OK |
| `docs/design/v1/schemas/export.schema.json` | Tracked (có thể có local edits) | JSON parse OK |
| `docs/design/v1/schemas/extraction-result.schema.json` | Tracked (có thể có local edits) | JSON parse OK |
| `docs/design/v1/schemas/job-message.schema.json` | Tracked (có thể có local edits) | JSON parse OK |
| `docs/design/v1/uml/01-use-cases.puml` | Tracked (có thể có local edits) | PlantUML framing OK; compiler not run |
| `docs/design/v1/uml/01-use-cases.svg` | Tracked (có thể có local edits) | SVG XML OK; not PlantUML verification |
| `docs/design/v1/uml/02-components.puml` | Tracked (có thể có local edits) | PlantUML framing OK; compiler not run |
| `docs/design/v1/uml/02-components.svg` | Tracked (có thể có local edits) | SVG XML OK; not PlantUML verification |
| `docs/design/v1/uml/03-processing-sequence.puml` | Tracked (có thể có local edits) | PlantUML framing OK; compiler not run |
| `docs/design/v1/uml/03-processing-sequence.svg` | Tracked (có thể có local edits) | SVG XML OK; not PlantUML verification |
| `docs/design/v1/uml/04-review-sequence.puml` | Tracked (có thể có local edits) | PlantUML framing OK; compiler not run |
| `docs/design/v1/uml/04-review-sequence.svg` | Tracked (có thể có local edits) | SVG XML OK; not PlantUML verification |
| `docs/design/v1/uml/05-job-state.puml` | Tracked (có thể có local edits) | PlantUML framing OK; compiler not run |
| `docs/design/v1/uml/05-job-state.svg` | Tracked (có thể có local edits) | SVG XML OK; not PlantUML verification |
| `docs/design/v1/uml/06-review-state.puml` | Tracked (có thể có local edits) | PlantUML framing OK; compiler not run |
| `docs/design/v1/uml/06-review-state.svg` | Tracked (có thể có local edits) | SVG XML OK; not PlantUML verification |
| `docs/design/v1/uml/07-domain-classes.puml` | Tracked (có thể có local edits) | PlantUML framing OK; compiler not run |
| `docs/design/v1/uml/07-domain-classes.svg` | Tracked (có thể có local edits) | SVG XML OK; not PlantUML verification |
| `docs/design/v1/uml/08-activity-workflow.puml` | Tracked (có thể có local edits) | PlantUML framing OK; compiler not run |
| `docs/design/v1/uml/08-activity-workflow.svg` | Tracked (có thể có local edits) | SVG XML OK; not PlantUML verification |
| `docs/design/v1/uml/09-deployment.puml` | Tracked (có thể có local edits) | PlantUML framing OK; compiler not run |
| `docs/design/v1/uml/09-deployment.svg` | Tracked (có thể có local edits) | SVG XML OK; not PlantUML verification |
| `docs/design/v1/uml/10-training-activity.puml` | Tracked (có thể có local edits) | PlantUML framing OK; compiler not run |
| `docs/design/v1/uml/10-training-activity.svg` | Tracked (có thể có local edits) | SVG XML OK; not PlantUML verification |
| `docs/design/v1/verification.json` | Tracked (có thể có local edits) | JSON parse OK |
| `docs/design/v1/verification.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/git-flow.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/history/bootstrap-2026-10-04.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/history/tasks-retired-2026-10-07/current.md` | Local untracked | UTF-8/fences/local links checked; context |
| `docs/history/tasks-retired-2026-10-07/README.md` | Local untracked | UTF-8/fences/local links checked; context |
| `docs/history/week-01-original.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/reviews/repository-readiness-2026-10-07.md` | Local untracked | Dated audit/inventory; checked after creation |
| `docs/source-structure.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `docs/team/ai-1-ocr.md` | Local untracked | UTF-8/fences/local links checked; context |
| `docs/team/ai-2-extraction.md` | Local untracked | UTF-8/fences/local links checked; context |
| `docs/team/backend.md` | Local untracked | UTF-8/fences/local links checked; context |
| `docs/team/data-engineer.md` | Local untracked | UTF-8/fences/local links checked; context |
| `docs/team/execution-playbook.md` | Local untracked | UTF-8/fences/local links checked; context |
| `docs/team/lead.md` | Local untracked | UTF-8/fences/local links checked; context |
| `docs/team/README.md` | Local untracked | UTF-8/fences/local links checked; context |
| `docs/team/roadmap.md` | Local untracked | UTF-8/fences/local links checked; context |
| `docs/team/workflow.md` | Local untracked | UTF-8/fences/local links checked; context |
| `docs/uml/01-use-cases.puml` | Tracked (có thể có local edits) | PlantUML framing OK; compiler not run |
| `docs/uml/01-use-cases.svg` | Tracked (có thể có local edits) | SVG XML OK; not PlantUML verification |
| `docs/uml/02-components.puml` | Tracked (có thể có local edits) | PlantUML framing OK; compiler not run |
| `docs/uml/02-components.svg` | Tracked (có thể có local edits) | SVG XML OK; not PlantUML verification |
| `docs/uml/03-processing-sequence.puml` | Tracked (có thể có local edits) | PlantUML framing OK; compiler not run |
| `docs/uml/03-processing-sequence.svg` | Tracked (có thể có local edits) | SVG XML OK; not PlantUML verification |
| `docs/uml/04-review-sequence.puml` | Tracked (có thể có local edits) | PlantUML framing OK; compiler not run |
| `docs/uml/04-review-sequence.svg` | Tracked (có thể có local edits) | SVG XML OK; not PlantUML verification |
| `docs/uml/05-job-state.puml` | Tracked (có thể có local edits) | PlantUML framing OK; compiler not run |
| `docs/uml/05-job-state.svg` | Tracked (có thể có local edits) | SVG XML OK; not PlantUML verification |
| `docs/uml/06-review-state.puml` | Tracked (có thể có local edits) | PlantUML framing OK; compiler not run |
| `docs/uml/06-review-state.svg` | Tracked (có thể có local edits) | SVG XML OK; not PlantUML verification |
| `docs/uml/07-domain-classes.puml` | Tracked (có thể có local edits) | PlantUML framing OK; compiler not run |
| `docs/uml/07-domain-classes.svg` | Tracked (có thể có local edits) | SVG XML OK; not PlantUML verification |
| `docs/uml/08-activity-workflow.puml` | Tracked (có thể có local edits) | PlantUML framing OK; compiler not run |
| `docs/uml/08-activity-workflow.svg` | Tracked (có thể có local edits) | SVG XML OK; not PlantUML verification |
| `docs/uml/09-deployment.puml` | Tracked (có thể có local edits) | PlantUML framing OK; compiler not run |
| `docs/uml/09-deployment.svg` | Tracked (có thể có local edits) | SVG XML OK; not PlantUML verification |
| `docs/uml/10-training-activity.puml` | Tracked (có thể có local edits) | PlantUML framing OK; compiler not run |
| `docs/uml/10-training-activity.svg` | Tracked (có thể có local edits) | SVG XML OK; not PlantUML verification |
| `docs/uml/README.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `infra/README.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `migrations/README.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `migrations/versions/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `pyproject.toml` | Tracked (có thể có local edits) | TOML parse OK; no runtime dependencies |
| `README.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `specs/approval-policy.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `specs/contracts/business.schema.json` | Tracked (có thể có local edits) | JSON parse OK |
| `specs/contracts/export.schema.json` | Tracked (có thể có local edits) | JSON parse OK |
| `specs/contracts/extraction-result.schema.json` | Tracked (có thể có local edits) | JSON parse OK |
| `specs/contracts/job-message.schema.json` | Tracked (có thể có local edits) | JSON parse OK |
| `specs/contracts/README.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `specs/repository-layout.md` | Local untracked | UTF-8/fences/local links checked; context |
| `specs/scope.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `src/vietdoc/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/contracts/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/data/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/data/adapters/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/data/generator/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/data/generator/templates/invoice/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `src/vietdoc/data/generator/templates/receipt/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `src/vietdoc/documents/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/entrypoints/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/entrypoints/api/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/entrypoints/api/routes/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/entrypoints/cli/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/entrypoints/dispatcher/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/entrypoints/worker/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/evaluation/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/exports/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/identity/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/infrastructure/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/infrastructure/persistence/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/infrastructure/queue/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/infrastructure/storage/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/jobs/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/ml/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/ml/configs/README.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `src/vietdoc/pipeline/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/pipeline/extraction/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/pipeline/extraction/prompts/README.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `src/vietdoc/pipeline/ocr/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `src/vietdoc/README.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `src/vietdoc/review/__init__.py` | Tracked (có thể có local edits) | AST OK; docstring scaffold, no implementation |
| `storage/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `tests/architecture/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `tests/contract/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `tests/e2e/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `tests/fixtures/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `tests/integration/api/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `tests/integration/persistence/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `tests/integration/queue/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `tests/integration/storage/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `tests/README.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `tests/unit/documents/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `tests/unit/jobs/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `tests/unit/pipeline/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `tests/unit/review/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `web/README.md` | Tracked (có thể có local edits) | UTF-8/fences/local links checked; context |
| `web/src/api/generated/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `web/src/app/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `web/src/components/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `web/src/features/auth/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `web/src/features/documents/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `web/src/features/review/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |
| `web/tests/.gitkeep` | Tracked (có thể có local edits) | UTF-8 scaffold marker reviewed; not implementation |

## 7. Giao việc đầu tiên

1. Lead L1.1/L1.2: scope/owners/interfaces và capacity/hardware.
2. Data D1.1/D1.2: dictionary, fake gold và 20 samples QA.
3. AI-1 O1.1/O1.2/O1.3: canonical contract, loader/preprocess, actual OCR.
4. AI-2 M1.1/M1.2/M1.3: license/resources/infer/train-step; baseline theo capacity, không đợi UI.
5. Backend B1.1/B1.2/B1.3: typed contracts/tests, app/config/checks.

Chưa tạo issues, chưa gán usernames, chưa stage/commit/push. Cần thao tác riêng để đưa tài liệu local mới lên repo cho teammates đọc.
