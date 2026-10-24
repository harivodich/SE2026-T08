# D2.1 QA — 2026-10-25

Scope: offline synthetic receipt/invoice một trang. Task authority đã đọc từ
`docs/team/data-engineer.md` sau khi đồng bộ main baseline; các SPEC data/generator/
templates/datasets/tests và business schema/approval policy được giữ nguyên.
Không đổi shared schema/ADR status; không claim application/OCR/model hoạt động.

## Thiết kế và files

- `src/vietdoc/data/generator/values.py`: chuyển nguyên value factory D1.2 từ
  integration vào owning values module, thêm boundary profiles/config; giữ D1.1 API.
- `generator/templates/__init__.py`: labels/title/canvas/table columns và version;
  `generator/rendering.py`: renderer chung D1.2/D2.1, null cells/totals không in,
  từ quá rộng/ink ngoài trang fail, không cắt rows. Phần tách renderer/templates đã
  có trong working tree trước task, được tiếp tục sử dụng.
- `generator/integration.py`: import factory/renderer chung, giữ API D1.2 và fixture hashes.
- `generator/d21.py`, `generator/d21.json`: CLI, config/seed/version, build/validate;
  `generator/pdf.py`: PDF một trang từ cùng RGB image, lossless, metadata ổn định.
- `data/manifest.py`, `data/validation.py`: paths/IDs/hash/JSON, semantic checks,
  Unicode/glyph và approval diagnostics offline. Không DB/service dependencies.
- `pyproject.toml`: đóng gói thêm d21.json; không thêm dependency runtime mới.
- `tests/unit/test_data_d21.py`: focused valid/invalid/boundary/corruption/PDF tests.
- `generator/README.md`: commands, reproducibility policy, font/dependency requirements.
- `datasets/manifests/d21-sample-v1.json`, `d21-rejections-v1.json`: safe snapshots;
  full assets ở ignored `datasets/processed/d21-review-a` và `d21-review-b`.

## Commands và kết quả đã chạy

Từ repo root:

```sh
PYTHONPATH=src PYTHONHASHSEED=11 python3 -m vietdoc.data.generator.d21 --seed 2101 --config src/vietdoc/data/generator/d21.json --version d2.1.v1 --output datasets/processed/d21-review-a
PYTHONPATH=src PYTHONHASHSEED=89 python3 -m vietdoc.data.generator.d21 --seed 2101 --config src/vietdoc/data/generator/d21.json --version d2.1.v1 --output datasets/processed/d21-review-b
PYTHONPATH=src python3 -O -m vietdoc.data.generator.d21 --verify datasets/manifests/d21-sample-v1.json --assets-root datasets/processed/d21-review-a
PYTHONPATH=src python3 -m unittest discover -s tests/unit -p 'test_data*.py' -v
```

Hai generation commands: accepted=14, rejected=6, valid=true. Verification với `-O`
cũng accepted=14, rejected=6, valid=true. Test suite: 14 tests pass, gồm regression
D1.1/D1.2 và D2.1; optional PDF test thực chạy, không skip.

Đối chiếu hai fresh directories bằng SHA-256 mọi file (gồm manifests/report):
**86/86 files byte-identical**, IDs và gold giống hệt. Khác PYTHONHASHSEED không
ảnh hưởng. Có thể đối chiếu lại bằng:

```sh
python3 - <<'PY'
from pathlib import Path
import hashlib

def hashes(directory):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path(directory).iterdir() if p.is_file()}

a = hashes('datasets/processed/d21-review-a')
b = hashes('datasets/processed/d21-review-b')
assert len(a) == 86 and a == b
print('86/86 identical')
PY
```

Final manifest SHA-256:
`3d6099f2d256464dea9a574e25db796faff68c0d3b4b94c02dcebc9e243be083`.
Tái chạy dùng **directory mới**; existing directory gây FileExistsError, không overwrite.

## Validation và rejection

20 candidates (10/type), 14 accepted (7/type), 6 rejected, 0 excluded.
Accepted có hai layouts/type ở rows 0/1/30 và một missing-total/type ở 3 rows.
Mọi scalar/cell đều có present/absent status và raw/reason tương ứng, không confidence.

| Rejected sample ID | Rows | Reason |
|---|---:|---|
| d21-receipt-l0-r31 | 31 | business schema maxItems=30 |
| d21-receipt-l1-r31 | 31 | business schema maxItems=30 |
| d21-invoice-l0-r31 | 31 | business schema maxItems=30 |
| d21-invoice-l1-r31 | 31 | business schema maxItems=30 |
| d21-receipt-overflow | 30 | schema-valid nhưng render ink bbox y=2602..2627 vượt height=2600 |
| d21-invoice-overflow | 30 | schema-valid nhưng render ink bbox y=2602..2627 vượt height=2600 |

Không ghi asset cho rejected sample; không cắt 31 rows thành 30. Missing-total
samples schema-valid/render-valid nhưng có total_amount_missing blocker. Rows=0
cần completeness review. Tất cả accepted đều approval_valid=false; offline
validation không thay runtime approval/authorization/current-head/CAS/review guards.
Arithmetic differences giữ nguyên nguồn và cảnh báo, không sửa gold theo công thức.

Tests phát hiện date/time không tồn tại, float/negative/leading-zero money,
empty/NFD/control/missing glyph, invalid type/font/config/seed/version, missing cell,
long word và clipping. Manifest tests gồm invalid/duplicate IDs, hashes, corrupt
images với cả hash cập nhật, wrong dimensions, absolute/traversal/missing/escaping
symlink paths, duplicate paths/images, missing assets, row count, labels/transcript/
regions/gold/PDF drift, report reason drift, omitted sample và environment mismatch.
Tests dùng temporary directories, khôi phục nội dung sau deliberate corruption.

## Visual/PDF QA

- Đã xem hai contact sheets bao phủ cả 14 accepted PNG (0/1/30/missing-total, cả
  receipt/invoice và hai layouts); xem crop native-resolution của invoice-l1-r30
  và receipt-l0-r30. Dấu tiếng Việt đọc được, descriptions wrap, cột/các hàng không
  chồng và không thấy clipping ở samples accepted. Trang ngắn có khoảng trắng chủ ý.
- `pdfinfo`, `pdftoppm -r 72 -singlefile -png`, `pdfimages -png` thực chạy với cả
  14 PDF: parse đúng một trang, render được, extracted RGB giống từng pixel PNG.
  Test tự động kiểm này giữ trong suite. Đã xem crop PDF render của invoice-l0-r0.
- Poppler-rendered PNG có resampling/anti-alias khác PNG nguồn (đã kiểm thấy khi thử
  pixel equality). Không dùng check này để claim PDF render giống từng pixel;
  lossless claim dựa trên extracted image, không dựa ảnh viewer đã resample.

## Requirements và limitations

Python 3.12.3/Linux, Pillow 10.2.0, jsonschema 4.10.3, FreeType 2.13.2,
RAQM 0.10.1, zlib 1.3; versions/binary hashes cụ thể ở snapshot manifest.
DejaVuSans.ttf SHA-256:
`ae7b7855e115a5966d8b1b3f80f254ccc117ec86f9965e202ee2940453837280`.
HarfBuzz/FriBidi version API trả null trên build này; hashes shared library pin
binary thực đã load. Giữ đúng binaries/font khi tái tạo snapshot; chưa có OS
container lock, chưa kiểm cross-OS. Poppler chỉ cần cho independent PDF QA/tests,
không cần cho generator. Không cài thêm dependency/font hoặc tải dữ liệu.

PDF là raster, không text-searchable/A4. Geometry vẫn renderer-local, chưa consumer
viewer contract. Bộ này chỉ present/absent; chưa render che chữ/partial annotation,
không tái diễn giải obscured/unlabeled của D1.1. Chưa có independent peer review của
AI-1/AI-2/Lead hoặc đối chiếu thủ công độc lập từng ký tự. Không OCR/inference,
family split/augmentation D2.2, training, business DB hoặc public data.

`git diff --check`, `git diff --cached --check` không báo lỗi; không unmerged index
entries. Asset ignore probes xác nhận final images/PDF/manifests trong processed
không vào tracked changes. Business schema và migrations không sửa bởi D2.1.
Baseline merge từ yêu cầu trước đã được commit riêng ở `b5a6ee9`.
Thay đổi D2.1 được bàn giao trên nhánh riêng; `.awb/`, `skills/` giữ ngoài commit.
Commit/push/PR được người dùng yêu cầu sau nghiệm thu; không deploy.
