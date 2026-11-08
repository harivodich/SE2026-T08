# PR #14 — closure A1–A4, 08/11/2026

## Phạm vi và provenance

PR [#14](https://github.com/harivodich/SE2026-T08/pull/14) vẫn OPEN,
branch `feature/data-d3-2`. HEAD local và remote được đối chiếu trước sửa:
`42354651829eab1a765ffb0ce7e07c6a647a1fba`.
A1–A3 được chốt trong local source commit
`122fd8ab55b67cd7123c6a3a855785d038b06ccc`, cùng logic và regression tests.
Quality, occurrence và catalog lookup cùng sửa consumer và dùng chung render
fixtures nên giữ trong một commit; A4 là docs commit kế tiếp, không sửa source/tests.
Chưa push; không dùng CI xanh của HEAD nền làm evidence cho các local commits.
Tests chạy trên working tree trước source commit; SHA-256 bên dưới được đối chiếu
lại với committed bytes, không gọi chúng là hosted checks của commit tương lai.

Closure này bổ sung cho các reports ngày 01/11 và 07/11, không viết lại evidence
lịch sử và không đánh dấu toàn bộ backlog Data/consumer acceptance là Done.

## Findings và thay đổi

| Subtask | Evidence và behavior |
|---|---|
| A1 | Trước sửa, consumer nhận sample `v0-1-d22-smoke-review-v2-receipt-f00-b0000-unreadable` với duy nhất metadata `quality` đổi thành `clean`. Consumer D2.2 nay tính expected quality từ augmentation đã validate và actual label statuses; thiếu/sai quality bị reject. Clean không có obscured; D2.2 renderer variants không có unlabeled; unreadable không có present labels hoặc regions. |
| A2 | Repro từ fresh renders: thêm occurrence **cùng giá trị**, cập nhật transcript và hashes, consumer cũ vẫn nhận. Nay mỗi present field/cell của D2.2 có đúng một logical occurrence. Cả 20 catalog families đều được kiểm, không giả định total lặp hai lần. D1/D2.1 vẫn yêu cầu hai total occurrences; mất/thừa occurrence có regression riêng. |
| A3 | Consumer đọc `vocabulary` từ catalog, bỏ parse suffix family ID; renderer cũng đọc cùng catalog property. Test đổi vocabulary của f00 sang alternate trong catalog, giữ nguyên ID/index, và kiểm cả render lẫn consumer. Catalog mặc định không đổi; không sửa historical bytes/pins. |
| A4 | Ghi riêng source/test evidence của patch này với các consumer/CI/approval gaps bên dưới. Không kế thừa số PASS cũ cho source mới. |

`occurrences` ghép fragments của một table cell trước khi đếm. Null fields vẫn
không được có evidence. Guards dùng `require`/ValueError, không dùng assert;
mutation probes chạy cả interpreter normal và `-O`, kiểm sample ID và reason.
Đây là sidecar/schema/metadata integrity, không chứng minh pixel/text alignment,
strict historical replay hoặc annotation truth.

## Verification của patch

Python 3.12.3/Linux, Pillow 10.2.0, jsonschema 4.10.3 có sẵn. Không cài dependencies,
font, model/dataset hoặc gọi inference/training/paid API.

Commands từ repository root, dùng `PYTHONPATH=src python3 -m`:

| Module/command | Kết quả |
|---|---|
| `unittest discover -s tests/unit -p 'test_data_d2_semantics.py' -v` | 5 tests PASS, 315.947s; final gate bên dưới còn bao gồm probe unreadable mang clean evidence bổ sung sau lượt riêng này |
| `scripts.ci.checks tests data --separate-pdf` | PASS: 44 discovered, 43 selected, 42 executed, 1 canonical opt-in skip; 0 failures/errors, 1159.087s. Bao gồm 5 D2 semantics tests cuối, full D2.2 build/byte equality/strict replay và D1 handoff/integration. PDF delegated sang gate riêng. |
| `scripts.ci.checks tests pdf` | 1/1 PASS, 0 skip, 31.873s; independent Poppler parse/render/lossless checks |
| `unittest discover -s tests/unit -p 'test_review_regressions.py' -v` | Final 7/7 PASS, 182.339s; 17 cases × D2.1/D2.2 × normal/`-O` trong consumer mutation test |
| `unittest discover -s tests/unit -p 'test_evaluation*.py' -v` | 49 tests PASS, 13.291s |
| `git diff --check` | PASS trước handoff |

Exploratory regression chạy trước/trong lúc sửa ghi nhận FAIL như dự kiến ở
catalog vocabulary và duplicate occurrences; không tính lượt có source thay đổi
trong khi chạy là final verification. Final gate phải chạy trên bytes ổn định.
Logs local `/tmp/vietdoc-A-*.log` không là artifact bền vững hoặc consumer handoff.

Tổng final gates: **100 tests selected/run, 99 executed PASS, 1 canonical opt-in
skip**, không failures/errors (Data 43 + PDF 1 + review 7 + evaluator 49).
Không cộng lượt D2 riêng hoặc các subprocess probes thành tests độc lập.

Source/test SHA-256 tại source commit `122fd8a` (giữ nguyên trong docs HEAD):

```text
4c4a2bd6e1b9b10c290e57498c59dc2b02f81addde6eb681f03dd8450a4881d4  src/vietdoc/data/generator/integration.py
bf7d971a34546bdd3867d2b49d099001992ba8d806fa1bfda589866559f73b31  src/vietdoc/data/generator/templates/families.py
bacb599c717886b1cf6d27f3cb5f25c88edf04d8a45475a644f6973cdcccbb07  tests/unit/test_data_d2_semantics.py
515e58819a3ce7dce7f9b93a1dce577119384d0a8439ac437e0cb2706f5af4d5  tests/unit/test_review_regressions.py
```

## Acceptance gaps còn mở

- Hosted CI của patch **chưa chạy** vì các local commits chưa push. CI xanh trên PR
  được đọc ở HEAD nền, không chứng minh patch hiện tại. Data runner tự discover
  `test_data*.py`, nên module D2 mới được chọn; required-file inventory hiện chưa
  bắt buộc module mới. Evaluator/review suites chưa nằm trong mandatory Data gate;
  việc gia cố CI thuộc Backend/Lead, không sửa ownership đó trong closure này.
- Chưa chạy native Windows trên patch, canonical reference byte opt-in replay,
  actual AI-1 native20/PDF pipeline, AI-2 consumer hoặc actual-provider E2E.
  Local PDF parser/render/lossless test không thay thế consumer acceptance.
- Chưa có actual B0/M0/M1 predictions/measurements, calibration fit, G0/capacity,
  pilot/diversity acceptance, 81 near-duplicate dispositions hoặc final freeze.
  C01–C06/normalization/matching/calibration policies vẫn giữ authority/status cũ;
  không tự chuyển Proposed sang Accepted hoặc mở final holdout.
- Cần AI-1/AI-2 peer review và Lead approval trên nội dung cuối, cùng post-merge
  consumer smoke theo workflow. Không comment/gửi message/merge/deploy trong lượt này.

Diff chỉ chạm Data consumer/family renderer, regression tests và report này.
Không đổi shared schemas, business payload, Flyway/migration lineage, split hoặc
dataset scope. Không sửa snapshots/checksums/source pins lịch sử để hợp thức hóa
code mới. Các untracked files có sẵn trước lượt làm được giữ nguyên.
