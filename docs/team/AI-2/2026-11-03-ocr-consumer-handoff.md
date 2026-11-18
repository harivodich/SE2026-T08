# AI2 — PR3 fixes và OCR v2/native consumer handoff, 03/11/2026

Đây là evidence local của increment được người dùng yêu cầu; không thay Issue/PR,
Lead approval hoặc trạng thái nghiệm thu. Chưa push, chưa comment GitHub, chưa merge PR.

## Source và phạm vi

- Consumer bắt đầu tại `1bc7fe84b5290d9f29b6bda8d8209832b490ad12`.
- Base tích hợp: develop `729be6fe493dc00e1d7cb87e7db94b94c79a0816`.
- Provider/fixtures: PR4 `7d96e93bf8315beb6fa33807231316e957671249`, theo
  [Issue #23](https://github.com/harivodich/SE2026-T08/issues/23).
- Candidate local: `bug/SE-23_ai2_review_consumer`, worktree riêng
  `E:/OCR_SE/.verification/ai2-review-candidate`. Ngày 04/11, source đã đưa về
  checkout IDE `E:/OCR_SE` trên branch gốc `feature/AI2-M2_ai_service_docker` bằng
  fast-forward. Giữ đủ 10 docs dirty có sẵn; không đưa chúng vào các commit này.
- B0 `vi-label-header-b0.v2`; normalizer `vi-VND.v2`; neutral schemas giữ nguyên.
- Hoãn hardware/model/training, runtime composition/HTTP và Java-provider/browser E2E.

## Commit riêng theo từng mục

| Mục | Commit | Thay đổi |
|---|---|---|
| 1.1 / A1 | `dc2a502` | Merge develop vào candidate; resolve đúng một conflict `.dockerignore`, giữ Web/AI inputs |
| 1.2 / A2 | `cc011fa` | Schema env tuyệt đối, real installed-wheel smoke, mandatory baseline inventory |
| 1.3 / A3 | `afefc79` | Scalar pairing theo row/context; footer value-before-label không tạo item giả |
| 1.4 / A4 | `410667e` | Reject control/NUL path trước filesystem, isolate bad release, all-invalid not-ready |
| 2.1 | `d6f7548` | Consumer v1/v2 validation, unreadable detection provenance, golden pin/hashes |
| 2.2 | `106ab65` | Partial diagnostics qua fields/issues, bare-label unknown, companion OCR diagnostics |
| 2.3 | `26842d6` | Isolated actual-provider evidence bridge và B0 callback acceptance |
| 2.4 | Xem commit chứa file này | Native B0 replay/report, correlation tests, fixture pin và runbook |

Từng mục đã có RED→GREEN trước commit. Mục 1.1 là integration/config; kiểm existing
tests sau resolve, không tạo test chỉ để dò text `.dockerignore`.

## Verification thực chạy

Python3.13.5/Windows, serve/test env có sẵn; thêm đúng setuptools75.8.0/wheel0.45.1
đã khai báo trong test extra để build wheel offline. Không cài model/OCR engine.

| Command/check | Kết quả | Giới hạn |
|---|---|---|
| `python -m scripts.ci.ai --allow-windows-symlink-skip --junitxml=test-results/ai-final.xml` | 472 passed, 1 skipped, 58 subtests; 473 collected; policy failures rỗng | Chỉ skip symlink do Windows thiếu quyền; Linux CI không được skip |
| `docker build -f infra/ai-service.Dockerfile --target test -t vietdoc-ai-service:ai2-review-09d5d0a-test .` | 473 passed, 58 subtests; 0 skips, policy failures rỗng; pip check PASS | Linux/Python3.12, source `09d5d0a`; fixture gate, không model inference |
| `python -m pytest tests/unit/pipeline/test_ocr_consumer.py tests/unit/pipeline/test_baseline.py tests/unit/pipeline/test_baseline_export.py -q` | 81 passed | Native JSON replay, không chạy OCR mới |
| `python -m scripts.ci.lint` | PASS, no findings (3 suppressions theo tooling) | Local Windows, không thay hosted checks |
| `node --test` tại `backend/src/test/js` | 29 passed | Web asset tests, không browser E2E |
| `mvnw.cmd -B test` tại `backend` | 23 tests, 0 failure/error/skip, BUILD SUCCESS | H2/fixture integration, không PostgreSQL/provider thật |
| Installed-wheel probe trong AI gate | PASS: build local không network, noneditable install ngoài checkout; thiếu config fail, có config validate 3 fixtures | Dùng dependencies của serve/test env hiện có, không fresh dependency-resolution |
| Actual evidence bridge | 12/12 PASS; native examples 5/5 PASS | Dependency-free types/geometry/evidence từ provider SHA pin |
| `python -m pip check` | No broken requirements found | Local env |
| AI runtime Docker build + HTTP smoke | PASS: live200, ready503, unauthenticated compute401; user app/rootfs read-only | Empty models/pipeline nên not-ready là expected; không actual-provider E2E |
| `docker build -f backend/Dockerfile -t vietdoc-web:ai2-review-09d5d0a .` + Web smoke | PASS: Thymeleaf root200 + CSRF meta; app.js/api.js/domain.js/styles.css200; auth/me401 | Demo mode/worker disabled, user app, không browser/PG/provider E2E |
| Hosted candidate AI/Data/Web checks, negative hosted fail-closed probe | PENDING | Chưa được yêu cầu push; R17/merge gate còn mở |

Logs/JUnit/report nằm trong `.verification/` và `test-results/` ignored. Report
trước commit ghi `consumer_worktree_dirty=true` và exact source-content hashes;
không giả rằng test đã chạy trên commit sạch chưa tồn tại. Chạy lại command dưới
trên final HEAD tạo report mới có exact candidate SHA.

## Chạy lại consumer acceptance

Từ candidate root, dùng Python của serve/test env đã cài package hoặc đặt source
path của **candidate**, không trỏ nhầm về checkout PR3 cũ. Provider root phải là
worktree riêng tại SHA pin và imported source files chưa đổi:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
$env:VIETDOC_CONTRACTS_DIR = (Resolve-Path specs/contracts).Path
python -m vietdoc.entrypoints.cli.ocr_consumer --provider-root <AI1-worktree-at-7d96e93> --provider-sha 7d96e93bf8315beb6fa33807231316e957671249 --output <new-directory>
```

Trong lượt local dùng executable `E:/OCR_SE/.venv/Scripts/python.exe`, provider
`E:/OCR_SE/.verification/ai1-7d96e93`. CLI dùng subprocess Python `-I` để tách hai
package cùng tên; kiểm commit và hashes của sáu provider source files trước mỗi call.
Fixtures byte-exact từ provider pin, có blob/SHA-256 trong
`tests/fixtures/ocr-ai2-source.json`; CLI đối chiếu lại Git blob trước replay.
Không import Paddle/model, không merge/copy nguyên branch AI1 vào consumer.

`consumer-report.json` chứa consumer/provider SHA + source hashes + dependencies,
golden/native outputs, raw candidates, evidence, uncertainty, coverage và limitations.
Các native input PNG hash khớp hai tiny D1 fixtures hiện có. Encoded canonical PNG
không được bàn giao trong bundle, nên canonical asset-byte verification là NOT_RUN;
matching dimensions/hashes khai báo không thay byte verification hoặc Java promotion.

Resume ngày 04/11/2026: xác nhận source hashes khớp report trước gián đoạn; chạy lại
AI gate đạt 472 passed, 1 permitted skip, 58 subtests; `pip check`, UTF-8/local links,
diff và secret-pattern scan đạt. Rà soát diff do chính implementer thực hiện vì
project không cho tự spawn agents; chưa thay peer review/Lead approval.

### Hoàn tất Docker và checkout PR3 — 04/11/2026

Docker Desktop đã có sẵn được khởi động để kiểm chứng; không cài thêm dịch vụ.
AI test/runtime và Web images đều build từ root context đã resolve ở `09d5d0a`.
Maven go-offline lần đầu mất292.6s; kết thúc thành công, không đổi pins hoặc dùng
host cache thay fresh container build. Docker smoke containers chỉ mở loopback,
đã dừng sau khi kiểm; không chạy train/GPU/model hoặc dùng business DB thật.

Evidence local ignored: `.verification/ai2-docker-test-09d5d0a.log`,
`ai2-docker-linux-09d5d0a.xml`, `ai2-docker-runtime-09d5d0a.log`,
`ai2-docker-web-09d5d0a.log`, `ai2-runtime-smoke-result.json`,
`ai2-web-smoke-result.json`. JUnit có473 top-level tests và58 subtests, không skip.

Trước khi chuyển source về IDE, lưu byte backups của10 docs cùng Git state trong
`.verification/ai2-transfer-20261104/`. Chỉ `docs/adr/README.md` giao nhau: merge
ba chiều trên bản sao đã sạch, kết quả checkout khớp preview và giữ dòng model
người dùng sửa cùng ADR0010/0011 từ develop. Chín file còn lại giữ nguyên hashes;
generated plan gốc có backup. Không stash/reset hoặc commit local edits của người dùng.

Consumer chạy trực tiếp từ `E:/OCR_SE` sau fast-forward:12/12 evidence checks,
2/2 native records và5/5 native evidence checks PASS; source hashes khớp candidate
đã kiểm. Report `.verification/ai2-rootcheckout-report-20261104/consumer-report.json`.
Commit theo sau chỉ cập nhật handoff Docker/local integration; executable source
và build inputs giữ đúng code snapshot `09d5d0a`.

## Kết quả native và giới hạn chất lượng

| Input observed OCR | Version/status | B0 total | Rows/fields | Evidence |
|---|---|---|---|---|
| `d12-receipt-03` | v2 / complete, 0 unreadable | `178000` | 3 rows, 20/20 fields có value | 15/20 fields có selected regions |
| `d12-invoice-04` | v2 / complete, 0 unreadable | `233000` | 0 rows, 7/8 scalar fields có value | 0/8 fields có selected regions |

Đây là coverage của đúng hai sample, không là accuracy/benchmark D1 hoặc quality
acceptance. Cả hai total khớp tiny fictional gold khi đối chiếu độc lập **sau**
inference; gold/labels/transcript không được đọc trong inference path.

- Receipt giữ nguyên `nộp` từ OCR thay vì sửa thành `hộp`; đây là field sai dù
  selected OCR evidence có thể đúng. OCR score không thành correctness probability.
- Invoice header `SsL` không thuộc B0 header vocabulary; bảng không được locate,
  trả `items=[]` và `TABLE_NOT_LOCATED`, không tự thêm alias theo sample. Các line
  items bị abstain; không gọi đây là table extraction thành công. Buyer thiếu là
  prediction `unknown`, không suy paper-annotation `absent` từ OCR thiếu.
- Scalar labels/values nằm chung block giữ values/raw nhưng evidence matcher
  abstain substring; không dựng tight boxes. Đây giải thích source coverage giảm.
- Receipt wrapped description được ghép bằng table-cell scope, giữ page order.
  Native evidence examples có field path do caller cung cấp, không dùng path đó
  để gán row của B0; B0 callback tự cấp context IDs từ extraction thực.
- Hai native page đều complete. Partial/unreadable acceptance đến từ golden riêng:
  mixed gồm empty/whitespace, all-unreadable, no-detections và invalid/migration cases.
- Denominator provider lịch sử: 20 requested, 2 native attempted/ok, 18 not_run.
  Lượt này chỉ replay 2 observed JSON, không nhận đã chạy OCR lại hoặc đủ20 ảnh.

## Phản hồi cho AI1/Backend — chưa gửi GitHub

AI2 đã nhận internal legacy-v1/opt-in-v2 và giữ IDs/quads/reasons/flags; missing
khác absent. Unscoped partial/repeated values abstain; explicit scope có thể match
nhưng vẫn giữ incomplete flags. Invalid version/status/score/quad không thành
unreadable success. Confidence/confidence_method luôn null.

R04 AI1 tiếp tục pending default/migration policy + Backend acceptance và required-field
blocker semantics; không đổi provider default hoặc shared schemas/DTO. R04 AI2 về
deadline là finding khác, không mở lại limiter/cancel/output/trusted-ingress fixes.

A1 candidate local và Docker tests/smokes đã kiểm; hosted gate vẫn chưa được chứng minh,
R17 chưa đóng. Cần Backend/Lead review shared CI patch, actual hosted checks đúng
candidate, canonical promotion/approval gates và smoke develop sau merge. Không tự
merge PR, bật HTTP provider hoặc chuyển Issue Done chỉ bằng report này.
