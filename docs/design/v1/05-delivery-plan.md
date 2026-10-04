# 05 — Plan 12–16 tuần và workflow team

## 1. Khung thời gian

Tuần là relative từ kickoff, không giả định ngày bắt đầu. Giả định ban đầu mỗi IC có khoảng 12–16 giờ/tuần và Lead 4–8 giờ/tuần cho thiết kế/review. Đây là giả định capacity, cần đối chiếu lịch thực trước khi cam kết. Nếu mỗi IC dưới 8 giờ/tuần thì giảm UI/hạ tầng polish hoặc kéo dài; không bỏ line items/approval khỏi scope âm thầm.

Mốc W4 phải có vertical slice thật. W8 feature complete; W10 model/release candidate; W12 nghiệm thu scope chính; W13–16 dùng để cải thiện và buffer. Không bắt đầu tính năng loại tài liệu thứ ba chỉ vì dư lịch trên giấy.

## 2. Kế hoạch theo tuần

| Tuần | Data Engineer | AI-1 | AI-2 | Backend | Lead và exit gate |
|---|---|---|---|---|---|
| W1 | Manifest, 10–20 mẫu fake, 2 template mỗi loại | OCR contract, baseline smoke | Fine-tune feasibility plan, model license audit | Repo, contracts, DB, upload, CI skeleton | Khóa FR/schema/ownership; review API/OCR fixtures |
| W2 | Generator + split family, audit ReceiptVQA tùy chọn | Engine vi, geometry, CER sample | Load/infer/train-step trên hardware thật | Job/worker, input limits, first UI | G0: model/resource/profile quyết định bằng số đo |
| W3 | Mở template diversity, JSON label QA | OCR thật, evidence matching | Rule/model adapters cùng contract | Review revisions, viewer/editor | API↔AI integration test; không chờ full training |
| W4 | Dataset v0.1 và tiny regression set | OCR lỗi ảnh nghiêng/text nhỏ | Baseline eval + fine-tune pilot | Approve/export, CAS test | G1: một receipt xuyên suốt thật, invoice smoke |
| W5 | Dataset v1, đủ train/dev family | Geometry adversarial fixtures | Full run #1, errors theo type/field | Invoice editor + items grid | Khóa final-test manifest và evaluator protocol |
| W6 | Verify table labels và template imbalance | Optimize lỗi OCR có evidence | Run #2 theo lỗi #1; normalization | Outbox, duplicate-delivery, audit | G2: hai loại + bảng có review; basic failure tests |
| W7 | Evidence/label coverage report | Source highlight và score features | Calibrator validation, missing/ambiguity cases | Rerun/adopt, warning ack, ownership guards | Review confidence scope; check annotations↔payload |
| W8 | Frozen evaluator + dev report | OCR version freeze | Candidate model manifest | Cancel/recovery, export history | G3: feature complete; stop scope expansion |
| W9 | Independent mock/test forms QA | Stress suite, CPU/GPU timing | Targeted improvement cycle cuối | Load/failure tests, logging/metrics | Reassess nếu ba vòng không giảm lỗi; chọn baseline thực |
| W10 | Run frozen holdout, per-slice report | Final OCR/error analysis | Final model card, artifact hashes | Release candidate, backup/restore drill | G4: quality + correctness gates; không tune final test |
| W11 | Data lineage packaging | Reproducible inference commands | Training reproduction subset | Demo UX, docs/runbooks, rollback rehearsal | Requirements review, code review, simplify unused paths |
| W12 | Report/sample predictions | Support demo | Support demo | Smoke end-to-end clean env | G5: nghiệm thu, handoff, limitations rõ |
| W13–14 | Thêm independent samples nếu cần | Fix hard OCR failures có repro | Re-evaluate trên dev mới có version | Reliability/performance polish | Buffer; không dùng final test như dev |
| W15–16 | Reproducibility audit | Freeze | Freeze | Release packaging, presentation support | Final verification; chưa deploy/publish nếu chưa yêu cầu |

## 3. Backlog theo vertical slice

| Epic/task | Owner | Depends | Acceptance cụ thể |
|---|---|---|---|
| E0 Contracts + CI | Backend, Lead review | Scope | Schema examples pass; routes/types consumer thống nhất |
| E1 Generator + manifest | Data | E0 | Labels khớp rendered text, Unicode, seed; split không overlap family |
| E2 OCR adapter | AI-1 | E0,E1 sample | Text/boxes canonical; không crash file profile hợp lệ |
| E3 Rule baseline | AI-2 | E0,E2 fixture | Hai payload schemas; missing null; stable output |
| E4 Upload/job processing | Backend | E0,E3 | 201/202; API không blocked; job terminal và artifacts |
| E5 Review/approve/export | Backend | E4 | Revision append, stale save 409, approved export checksum |
| E6 Extraction fine-tune | AI-2 | E1,E2 | Weights/config/seed/hash; dev report so baseline |
| E7 Line items/evidence | AI-1+AI-2, khác files | E2,E6 | Không trộn dòng khi wrap; mapping highlight verified |
| E8 Evaluation | Data | E1,E3,E6 | Per-type metrics, coverage, bootstrap uncertainty khi đủ mẫu |
| E9 Reliability | Backend | E4,E5 | Outbox publish gap/duplicate/stale fence kill tests |
| E10 Release | Backend+AI, Lead gate | E8,E9 | Fresh env smoke, manifest pin, rollback rehearsal |

Dependencies là interfaces, không là lý do để chờ cả epic. Consumer dùng fixture theo contract; fixture chỉ để integration, không ghi thành kết quả model thật.

## 4. Gate và completion criteria

- **G0/W2**: OCR vi và một extraction candidate chạy trên hardware; 20 sample smoke, JSON validity/latency/VRAM có số đo. Nếu không đủ GPU cho VLM, chọn một extractor nhỏ hoặc OCR-text model bằng evidence, giữ scope/output và ghi ADR thay đổi. Không hứa fine-tune VLM trước khi có spike.
- **G1/W4**: Receipt E2E, source review, save, approve, export; hai user/tab conflict có test. Chưa cần đạt model quality cuối.
- **G2/W6**: Invoice + receipt + items; generated ground truth coverage; one job/run invariant. Acceptance các field nullable không đồng nghĩa model được phép trả toàn null.
- **G3/W8**: Rerun/adopt/recovery/auth; stable schemas; staging compose reproducible. UI bắt buộc đủ ba màn hình; không đòi frontend design system.
- **G4/W10**: Model report và holdout criteria tại tài liệu 06; lỗi blocking vẫn là release blocker. Nếu không đạt, báo failed criteria, không rename milestone thành success.
- **G5/W12**: Demo + runbook + checks + limitations + clean diff. Output source chạy được; docs/UML không thay implementation khi chuyển sang coding phase.

## 5. PR và merge workflow

1. Lead viết issue có problem, input/output, non-goals, acceptance, owner và contract version. Một task có một accountable owner.
2. Implementer tạo branch ngắn `feat/<issue>-<module>`; một PR một increment. Aim review được trong 20–40 phút, không phải giới hạn line count cứng.
3. Contract PR đi trước consumer PR. Backend implement Pydantic/OpenAPI, Lead review và AI consumers xác nhận fixture.
4. Tác giả chạy focused tests, thêm evidence vào PR: screenshots UI, sample input/output fake, test command và kết quả, ML config + dev comparison nếu có.
5. CI CPU: formatter/lint/type checks, contract/import checks, unit/integration có DB; frontend typecheck/build. GPU eval chạy riêng khi model/preprocessing/prompt đổi, không yêu cầu mọi UI PR chạy training.
6. Reviewer của module kiểm code; Lead kiểm requirements, boundaries, data leakage, rollback và compatibility. Required checks + approval mới merge.
7. Lead squash merge theo thứ tự dependency. Sau contract/migration merge, authors rebase/update downstream branches và rerun checks.
8. Main phải có smoke path; release tag/deploy/push chỉ khi được yêu cầu, không tự chạy external mutations từ kế hoạch này.

Pipeline checks được thiết kế; chưa có workflow GitHub Actions production trong hồ sơ này. Khi viết `.github/workflows`, audit permissions và pin action revisions theo workflow-testing skill.

## 6. Check conflict: Git và semantic

| Vùng dễ conflict | Policy |
|---|---|
| contracts/OpenAPI | Một người merge sequence; consumer reviewer; regenerate types, không sửa generated file bằng tay |
| pyproject/lockfile | Tác giả ghi lý do dependency; Backend regenerate lock sau merge; không ghép text lockfile |
| Alembic migrations | Backend cấp migration lineage; PR song song kiểm heads; không sửa migration đã applied |
| model config/prompts | AI-2 owns; phiên bản/hash; không thay preprocessing nếu manifest chưa đổi |
| dataset splits | Data owns; immutable final holdout; hash/template-family gate |
| evidence geometry | AI-1 owns; Backend verify UI mapping, inverse transform test |
| review state/export | Backend owns; Lead yêu cầu race tests, không chỉ nhìn diff |

Khi Git conflict: owner file resolve bằng cách hiểu cả hai thay đổi, không chọn ours/theirs toàn file. Lead hỗ trợ quyết định contract; tác giả chịu kiểm thử nội dung. Khi semantic conflict: mở issue ngắn ghi incompatible inputs/outputs và acceptance, cập nhật contract/ADR trước merge.

## 7. Cadence cho Lead

Đầu tuần 30 phút: scope/blockers/dependency order. Giữa tuần integration demo 20 phút bằng tiny fixtures. Hai cửa sổ review cố định/tuần, không để PR chờ đến sprint cuối. Cuối tuần 30 phút: metric, failed cases, risk register và next slice.

Lead theo dõi: oldest PR age, contract changes, active blockers, latest E2E result, dataset/model version và acceptance chưa đạt. Không đánh giá thành viên bằng commit count hoặc số file.

## 8. Risk register và cắt scope có thứ tự

| Risk | Trigger | Action |
|---|---|---|
| Backend quá tải UI | W3 chưa có viewer/save | Giữ 3 screen, reuse components; giảm dashboard/polish |
| GPU/training infeasible | G0 không chạy train step | Chọn smaller extractor; benchmark lại; giữ output và fine-tune objective |
| Synthetic overfit | Unseen-template dev drop lớn | Thêm template family/dev và independent mock; không thêm noise vô hạn |
| Public data không hợp terms/PII | Audit fail | Không dùng; generator vẫn là nguồn chính |
| Bảng trộn dòng | Row error trên dev | Giới hạn dạng bảng trước; sửa grouping; không xóa test khó |
| Confidence sai | High-score wrong có nhiều | Null score + review flags; sửa calibrator; không autoapprove |
| Không giảm lỗi sau 3 cycles | Dev gần như không đổi | Reassess error source, freeze tốt nhất, báo criterion còn thiếu |

Cắt trước: CSV, dashboard biểu đồ, auto classification, WebSocket, nhiều trang, loại thứ ba, external ERP, OCR fine-tune. Không cắt review/approval/export, data split, field/table evaluation hoặc model provenance vốn là core.
