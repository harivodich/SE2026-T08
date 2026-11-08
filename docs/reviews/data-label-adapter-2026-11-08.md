# Nhóm C — DE labels adapter, 08/11/2026

C1 source/tests: `3c135f6`. Baseline: `b966771` trên
`feature/data-d3-2`. Nhánh riêng: `feature/data-validated-label-adapter`;
chưa nhận số issue để đặt tên `feature/SE-<ISSUE>_validated_label_adapter`.
Sau `git fetch origin`, baseline chưa nằm trong `origin/develop` (`e5326f3`).
Hai commits C1/C2 đang local, phụ thuộc baseline; PR độc lập vào develop còn chờ
baseline tích hợp. Chưa push/tạo PR/merge. Không gom file untracked có sẵn.

## Đã thực hiện

- Giữ `load_artifacts` yield `(sample, gold)` và `check_sample` trả gold.
- Thêm validated labels path dùng cùng validator, không đọc lại labels sau kiểm.
- Adapter `vietdoc.field-labels.v1` trả business string/null, exact pointer và
  explicit present/absent/obscured/unlabeled; không tạo training mask/loss.
- Fixture tests: cùng-null statuses, decimal strings, invalid pointers/status,
  updated-hash semantic corruption, bad hash/path/missing asset, no partial yield,
  legacy API parity, full-set gate; D2.2 fresh bounded render có content loss.
- [Contract và consumer examples](../label-adapter.md) ghi rõ responsibilities,
  compatibility, validation scope và acceptance còn chờ.

## Verification đã chạy

Python 3.12.3; dependencies/font dùng môi trường có sẵn. Commands chạy từ root với
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src`; không cài dependency, tải dataset/model,
gọi paid API, inference hoặc training.

| Command sau prefix environment | Kết quả |
|---|---|
| `python3 -m unittest discover -s tests/unit -p 'test_data_label_adapter.py' -v` | 12/12 PASS, 13.494s |
| `python3 -O -m unittest discover -s tests/unit -p 'test_data_label_adapter.py' -v` | 12/12 PASS, 13.583s |
| `python3 -m unittest discover -s tests/unit -p 'test_data_integration.py' -v` | 8 discovered: 7 PASS, 1 canonical-byte opt-in skip; 28.100s |
| `python3 -m unittest discover -s tests/unit -p 'test_evaluation*.py' -v` | 49/49 PASS, 12.305s |
| `git diff --check`, `git diff --cached --check` | PASS cho C1 trước commit |

Ví dụ file consumer trong contract đã chạy trên tiny D1.2 fixture: receipt-03
`/total_amount` = `"178000"`, invoice-04 = `"233000"`, cả hai `present`, version
đúng `vietdoc.field-labels.v1`. Đây là smoke của adapter, không là training batch.

Tổng 69 tests riêng: 68 PASS, 1 skip. Lượt `-O` là chạy lại 12 tests, không cộng
thành tests riêng. Lượt exploratory D2.2 test đầu FAIL vì base được chọn không có
absent field; test cuối chọn base có null từ gold thật trước render, giữ expected
ba statuses. Không đổi generator/validator hoặc hạ assertion để che lỗi.

Không chạy full Data/PDF/review/Java/actual-provider E2E hay hosted CI trong
increment này. Existing evaluator tests kiểm compatibility của wrapper
`check_sample`. Không dùng evidence toàn bộ suites từ baseline làm kết quả patch.

## PENDING — chưa nghiệm thu

- **AI2:** tích hợp dataset/batch/collator/loss và consumer regression chứng minh
  supervision/masking đúng policy được review; giữ khác nhau giữa ba null statuses
  qua actual batches. Chưa có consumer run/artifacts, không claim training handoff.
- **AI1/AI2 và Lead:** peer review semantics/API, review policy và acceptance.
- **Integration:** gắn issue thật, baseline merge, branch/PR độc lập, hosted CI và
  post-merge consumer smoke. Không thay đổi lịch sử baseline hoặc tự merge.

Trạng thái DE: **adapter ready for consumer review**. Annotation integrity không
chứng minh pixels, historical replay, annotation truth hoặc model quality.
