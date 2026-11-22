# #77 — label adapter integration, 19/11/2026

## Scope và baseline

PR: [#77](https://github.com/harivodich/SE2026-T08/pull/77), issue #36,
branch `feature/SE-36_validated_label_adapter`.
Head trước sync: `f08de75e6d1abd55fa44097df4d394290e2bf2d5`.
Merge commit A1: `7685fd15427ae884d6119cf2585a677d5ae197e0`, parents là
head #77 cũ và develop dưới đây; không squash/rebase commits của branch.
Develop đã sync: `b9bd7f478bb5037e3a14a1ca90375d462497d90f`, gồm Data #14
và AI1 #4/#81/#82. #14 đã merge bằng squash `b703c647…`; không làm lại baseline.

Đây là evidence mới cho A1–A3; không viết lại snapshot ngày 08/11.
Không đổi policies Proposed, split, schema hoặc generator format.
Giữ các branch cũ local/remote; không force-push hoặc tự merge develop.

## Conflict resolution và compatibility

- Resolve từng hunk trong `SPEC.md`, `docs/cicd.md`, `scripts/ci/SPEC.md`,
  `src/vietdoc/README.md` và `generator/integration.py`.
- Giữ docs/CI/dependencies/provider source mới của develop; bỏ đoạn PDF runbook
  bị lặp do merge, không thay owning CI logic.
- Giữ `check_labeled_sample` trả chính `(gold, labels)` đã kiểm,
  `check_sample` trả gold và `load_artifacts` yield `(sample, gold)`.
- File adapter giữ no-reread, no-partial-yield và distinct statuses. Không thêm
  collator/loss hoặc suy labels từ null.
- Data/evaluator source và adapter tests sau resolve trùng bytes head #77 cũ;
  không thêm test trùng chỉ để tạo commit A2. Chạy lại regressions trên candidate.

Trước docs evidence mới, own diff so develop đúng sáu files adapter cũ.
Các file AI1/CI/dependencies được kiểm bằng diff với develop; không có own delta.

Source pins của candidate (không thay historical dataset/evidence pins):

```text
70f4f4c74f42a3b16bb9de24b06ab8e6a7f41f62f08cf8681298c12242da365a  src/vietdoc/data/adapters/labels.py
f22f76e43467fe7b90ed98185e2ba56bcd6c88f6cbb5295e1129dfcb7647c52e  src/vietdoc/data/generator/integration.py
c7789f4b54bf75065bfb296615fab027a5d8a3c4eef7ff4dac825db42f31b335  tests/unit/test_data_label_adapter.py
```

## Focused verification snapshot trước publication

Môi trường có sẵn: Python 3.12.3/Linux, Pillow 10.2.0/jsonschema 4.10.3.
Commands từ repo root, prefix `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src`.
Không cài dependencies, tải model/dataset, inference hoặc training.
Logs local ở ignored `artifacts/evaluation/data-label-adapter-integration-20261119/`.
Snapshot này ghi các checks đã hoàn tất trước publication. Kết quả full gates/CI
cuối của cùng candidate/source pins được cập nhật trong PR #77; không dùng các
greens lịch sử trước sync để thay thế.

| Command sau prefix | Kết quả |
|---|---|
| `python3 -B -m unittest discover -s tests/unit -p test_data_label_adapter.py -v` | 12 PASS |
| `python3 -B -O -m unittest discover -s tests/unit -p test_data_label_adapter.py -v` | 12 PASS; rerun, không cộng unique tests |
| `python3 -B -m unittest discover -s tests/unit -p 'test_evaluation*.py' -v` | 49 PASS |

Các commands full local được chạy tuần tự sau focused checks, kết quả cuối ghi
ở PR #77 và logs tương ứng, chưa được snapshot này chứng nhận PASS:

```sh
python3 -B -m scripts.ci.checks tests data --separate-pdf
python3 -B -m unittest discover -s tests/unit -p test_review_regressions.py -v
python3 -B -m scripts.ci.checks tests pdf
python3 -B -m scripts.ci.checks integration
```

## DE smoke và packet cho AI2

Smoke đã chạy trên candidate, output local `smoke.json` trong directory trên.
Đây là DE self-run, không AI2 sign-off hoặc training evidence.

Tiny D1.2 manifest SHA-256:
`b9fcb952f95f86e0c2c3bc1420acf2e43e1a47d1ed3c51ed5170dd3200ef989c`.

| Boundary/input | Pointer | Value | Status |
|---|---|---|---|
| File adapter, `d12-receipt-03` | `/total_amount` | `"178000"` | present |
| File adapter, `d12-invoice-04` | `/total_amount` | `"233000"` | present |
| In-memory content-only, `d11-invoice-02` | `/buyer_name` | null | absent |
| In-memory content-only, `d11-invoice-02` | `/items/1/quantity` | null | obscured |
| In-memory content-only, `d11-invoice-02` | `/items/2/unit_price` | null | unlabeled |
| In-memory content-only, `d11-invoice-02` | `/total_amount` | `"180500"` | present |

Version trong cả hai paths là `vietdoc.field-labels.v1`. D1.1 chỉ là accessor
oracle; không đưa fixture này qua renderer file adapter hoặc gọi nó là audited
renderer manifest. D1 renderer chỉ sinh present/absent.

AI2 có thể tái chạy contract examples và hai focused commands sau trong Data env:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m unittest discover -s tests/unit -p test_data_label_adapter.py -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m unittest discover -s tests/unit -p 'test_data_integration.py' -v
```

Để nhận helper, AI2 xác nhận consumer đọc đúng version/sample/pointer/value/status
và ghi command/input/output trên candidate. Không buộc hoàn thành fine-tune,
collator hoặc loss trước khi nhận adapter. Actual batch/mask/loss evidence và
policy supervision là task AI2 riêng (#52), chưa hoàn tất từ smoke này.

## Acceptance còn chờ

- Required hosted CI trên head sau sync; không dùng greens trước squash.
- AI1/AI2 review và AI2 consumer smoke; chưa gửi message/comment thay người dùng.
- Lead quyết định merge #77; giữ Draft trong khi còn consumer/acceptance pending.
- Post-merge smoke trên develop, full training handoff và actual model quality
  vẫn cần evidence riêng. Validation không chứng nhận pixel truth hoặc calibration.

Package/schema/AI/Java/actual-provider checks chưa chạy local trong increment này;
required hosted workflow cần kiểm riêng. Không thay requirements/gates để ép xanh.
