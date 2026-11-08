# Data strict-review fixes — 01/11/2026

Scope: sửa R01–R09 trong bản review ngày 25/10/2026 trên working tree
`feature/data-d3-2`. Giữ các edits D1.2 có sẵn và bổ sung đường D2/evaluator;
không thực hiện merge order hay thao tác GitHub trong tài liệu review.
Bản review gốc là evidence lịch sử, không bị viết lại thành kết quả mới.

## Thay đổi

| Finding | Source/behavior sau sửa |
| --- | --- |
| R01 | Consumer D1/D2 so exact từng occurrence, ghép wrap theo pointer, dùng đúng prefix standard/alternate; total lặp D1/D2.1 kiểm riêng. |
| R02 | Type-specific business schema; schema/generator/seed/rows/status counts; D2.1 source/template và D2.2 assignment/template/variant/seed được kiểm. |
| R03 | Consumer dùng explicit ValueError/require, không assert; corruption probes chạy cả normal và `-O`, tách biệt strict validators. |
| R04 | UTF-8/LF cho reads/writers liên quan; D2 semantic tests chọn font local và pin config theo font thực. Canonical bytes vẫn opt-in, fingerprint mismatch không được gọi canonical pass. |
| R05 | Producers khai full-page/draw-call transcript. Adapter versioned cho D1.2 v1/v2, D2.1/D2.2 v1 lịch sử; evaluator xử lý manifest-relative paths D2. QA/unknown scope vẫn excluded; thiếu OCR vẫn nằm trong failure accounting. |
| R06 | Reject envelope D1.1, typo/out-of-range pointer, label sai shape/status bằng lỗi có sample ID trước scoring/slices. Flat partial labels vẫn được phép, missing = unlabeled. |
| R07 | Generate/verify D1 và D2.2 cùng manifest mới; không verify snapshot cũ bằng source mới. |
| R08 | Dataset version dùng cùng fallback đã validate; manifest format version ghi riêng trong reports/correctness exports/freeze preparation. |
| R09 | Polygon area theo local coordinates + fsum; positive/finite union và degeneracy guards; invalid evidence có diagnostics thay vì abort/chia 0. Không clamp IoU. |

Evaluator versions mới: `d3.1.v2`, `d3.2.v2`. Prediction envelope và shared
business schemas không đổi. Normalization/table/calibration policies vẫn Proposed.
`renderer-draw-call-v1` mô tả output hiện tại, không tự chốt C01 thay AI-1/Lead.
Không đổi split, near-duplicate thresholds, capacity limit hay freeze authority.

## Reproduction và artifacts

Dùng Python có `Pillow==10.2.0`, `jsonschema==4.10.3`; `.venv` hiện tại không có
Pillow, vì vậy checks lượt này dùng `python3` hệ thống có sẵn dependencies.
Không cài dependencies/font/model/dataset hay gọi paid API.

```sh
PYTHONPATH=src python3 -m unittest discover -s tests/unit -p 'test_data*.py' -v
PYTHONPATH=src python3 -m unittest discover -s tests/unit -p 'test_evaluation*.py' -v
PYTHONPATH=src python3 -m unittest discover -s tests/unit -p 'test_review_regressions.py' -v
PYTHONPATH=src python3 -m vietdoc.data.generator.d21 --seed 2101 --output datasets/processed/d21-strict-review-v2-20261101
PYTHONPATH=src python3 -O -m vietdoc.data.generator.d21 --verify datasets/manifests/d21-strict-review-v2.json --assets-root datasets/processed/d21-strict-review-v2-20261101
PYTHONPATH=src python3 -m vietdoc.data.generator.d22 --config datasets/manifests/d22-strict-review-config-v2.json --seed 2202 --output datasets/processed/d22-strict-review-v2-20261101
```

Generation commands chỉ chạy khi directory mới chưa tồn tại. D2 format vẫn là
`d2.1.v1`/`d2.2.v1` với metadata transcript bổ sung và source pins mới. Suffix v2
ở tên snapshot/directory là revision của output review fixes; không phải đổi format.
D2.2 dataset version riêng `v0.1-d22-smoke-review-v2`. Historical outputs/snapshots
không bị sửa hash hay ghi đè. Strict replay historical cần source/environment cũ;
consumer/evaluator vẫn có adapter format lịch sử.

## Giới hạn

Môi trường lượt này Linux/Python 3.12.3/Pillow 10.2.0/jsonschema 4.10.3;
renderer binary fingerprint khác canonical reference. Same-environment replay và
semantic checks không chứng minh tái tạo canonical reference bytes. Locale cp1252
được mô phỏng bằng default encoding ở read boundary; chưa chạy native Windows.

C01–C06 và Increment B–D còn cần consumer/Lead decisions, actual AI-1/AI-2 outputs,
G0/pilot/diversity review, calibration support và final freeze riêng. Không có
B0/M0/M1 measurements, training/calibration hoặc actual-provider E2E trong lượt
sửa này; fixture/empty predictions chỉ kiểm accounting, không là model scores.

## Kết quả đã kiểm

- Evaluator suite: 32/32 pass.
- Strict-review regression suite: 7/7 pass, gồm 60 consumer subprocess cases
  (15 cases × D2.1/D2.2 × normal/`-O`), corrupt asset probes cho hai strict
  validators ở cả hai interpreter modes, labels format/pointers/partial status,
  cp1252-default read simulation/LF output, version provenance và tiny geometry.
  Bộ D2 nhỏ trong regression là subset có chủ đích; full source replay nằm ở
  Data suite và fresh D2 CLI, không suy strict dataset completeness từ subset.
- Fresh D2.1 build + validate: 14 accepted / 6 rejected / valid=true. Snapshot
  verify bằng `python -O` cũng đạt. Poppler PDF parse/render/embedded-pixel check
  trong Data suite thực chạy, không skip.
- Fresh D2.2 consumer load: 80 samples. Public evaluator nhận OCR support 80/80;
  empty fixture giữ 80 missing_or_failed_ocr, trong đó 20 empty-reference samples.
  Đây chỉ là failure/scope accounting, không phải OCR/model accuracy.
- `sha256sum --check datasets/manifests/data-strict-review-v2.sha256`: 5/5 khớp.
  `git diff --check`: pass.

Safe snapshots D2 mới và checksums ở `datasets/manifests/*strict-review*v2*`.
Full assets ignored ở hai directory output mới ghi trên; filenames trong D2
manifest relative output directory. Để consumer/evaluator load, dùng chính
`datasets/processed/d22-strict-review-v2-20261101/manifest.json`; safe snapshot đã
chuyển vị trí chỉ replay bằng strict validator có `--assets-root` rõ ràng.
Không sửa source pins hay hash của snapshots ngày 25/10.

Fresh D2.2 CLI build + strict replay đã hoàn tất: valid=true, 20 bases,
80 samples, 81 near-duplicate candidate pairs, final_frozen=false. Candidates
vẫn cần human review; số 81 không phải chứng nhận leakage-cleared/pilot-ready.

Full Data suite đã hoàn tất: 30 tests run, 29 pass, 1 canonical-byte opt-in skip,
không failures/errors. D2.1/D2.2 fresh-directory byte equality và strict replay
đều pass trong môi trường hiện tại. Tổng ba suites: 69 tests run, 68 pass,
1 skip. Lượt Data suite gồm full D2.2 20-base/80-sample builds; không suy số này
từ bounded subset của regression suite. Thời gian full Data suite 835.672 giây,
bao gồm nhiều lần render/replay và concurrent checks; không là inference SLA.

Đã rà diff, compatibility/path conventions và safe snapshot hashes; không đổi
shared schemas, Flyway/migration lineage, model/data scope hay unrelated files.
Working tree vẫn chứa các edits/untracked có sẵn trước lượt sửa; không stage,
commit, push, tạo/merge PR hoặc deploy.
