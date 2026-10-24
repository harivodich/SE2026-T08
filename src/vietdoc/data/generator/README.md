# D1.2 bounded integration renderer

`integration.py` tạo đúng 20 samples từ data object, gold và draw calls dùng chung object đó. D1.1 `fake-values.json` cung cấp vocabulary fictional. Không render các status obscured/unlabeled của D1.1; integration set này annotate đầy đủ present/absent, không chuyển unlabeled thành absent.

Dependencies đã chạy: Python 3.12, Pillow 10.2.0, jsonschema 4.10.3; optional extra `.[data]` khai báo trong pyproject. Không cần mạng, model hoặc API. Font mặc định `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`; có thể truyền `--font`. Manifest lưu hash font/config. PNG byte reproducibility cần cùng font/Pillow/render stack; không bảo đảm byte-identical giữa mọi OS/version.

Từ repository root, tái tạo vào **paths mới** (không overwrite):

```sh
PYTHONPATH=src python3 -m vietdoc.data.generator.integration --output datasets/processed/d12-recreated --manifest datasets/manifests/d12-recreated.json --seed 1202
PYTHONPATH=src python3 -m vietdoc.data.generator.integration --verify
PYTHONPATH=src python3 -m vietdoc.data.generator.integration --tiny --output tests/fixtures/d12-recreated --manifest tests/fixtures/d12-recreated/manifest.json
PYTHONPATH=src python3 -m unittest discover -s tests/unit -p 'test_data*.py' -v
```

Main assets: `datasets/processed/d12-integration-v1/` (ignored), 100 files: 20 PNG/gold/transcript/regions/labels. Safe manifest `datasets/manifests/d12-integration-v1.json`; QA theo ID ở `datasets/manifests/d12-QA.md`. Tiny subset: `tests/fixtures/d12/`, receipt-03 + invoice-04 (3 rows mỗi mẫu), deterministic seed 1202, hai type và hai layout. Không đưa main assets vào Git.

Mọi asset path relative repository root; SHA-256 từng file. Manifest có sample/base/family/template/type/schema/seed/version và status counts; labels sidecar có status/raw/reason từng JSON Pointer. Business payload chỉ schema keys. Base ID riêng từng chứng từ, family theo layout; không có split hoặc holdout claim.

Geometry sidecar là **renderer-local-v1**, chưa là shared contract: PNG 1500×2600, page 0, origin top-left, pixel text ink rectangles đo bằng Pillow `textbbox` cho chính font/draw call; identity transform. Mỗi fragment có pointer và text; wrap có nhiều regions cùng pointer, repeated total cũng có nhiều occurrences. Không cấp boxes cho absent, không sinh confidence. Chưa xuất normalized quad/shared PreparedPage khi O1.1/B1.2 chưa được chốt.

Consumer thực chạy được:

```python
from pathlib import Path
from vietdoc.data.generator.integration import load_artifacts
root = Path.cwd()
for metadata, gold in load_artifacts(root, root / 'datasets/manifests/d12-integration-v1.json'):
    print(metadata['sample_id'], len(gold['items']))
```

QA limitations và các review cần AI-1/AI-2/Backend ghi trong QA notes. Đây là integration set đã được mở xem, không untouched holdout.

## D2.1 — generator/validation v1

D2.1 tiếp tục dùng **cùng** `values.integration_samples`, templates và renderer D1.2;
không có renderer thứ hai. `values.document_cases` tạo các boundary profiles từ
nguồn này. `templates/__init__.py` giữ title/labels/canvas/table arrangement;
`rendering.py` wrap/draw và đo ink boxes; `pdf.py` đóng gói chính RGB raster thành
PDF 1.4 một trang, Flate lossless, không JPEG, không font substitution. PDF có
MediaBox 1500×2600 points (72 dpi bằng canonical PNG), chưa target khổ A4 hoặc
text-searchable PDF. Geometry tiếp tục là renderer-local-v1, identity, pixel,
page 0; chưa là shared viewer contract.

### Chạy lại

Từ repository root, cần Python và extra `.[data]` trong `pyproject.toml` đã có sẵn.
Không cần mạng/API/OCR/model/DB. Các output directory **phải chưa tồn tại**:

```sh
PYTHONPATH=src PYTHONHASHSEED=11 python3 -m vietdoc.data.generator.d21 --seed 2101 --config src/vietdoc/data/generator/d21.json --version d2.1.v1 --output datasets/processed/d21-review-a
PYTHONPATH=src PYTHONHASHSEED=89 python3 -m vietdoc.data.generator.d21 --seed 2101 --config src/vietdoc/data/generator/d21.json --version d2.1.v1 --output datasets/processed/d21-review-b
PYTHONPATH=src python3 -m vietdoc.data.generator.d21 --verify datasets/processed/d21-review-a/manifest.json
PYTHONPATH=src python3 -m unittest discover -s tests/unit -p 'test_data*.py' -v
```

Mỗi output có `manifest.json`, `rejections.json` và sáu assets/sample: PNG, PDF,
gold JSON, UTF-8 transcript, regions JSON, labels JSON. Asset paths relative
**thư mục chứa manifest** (khác convention repo-root của manifest D1.2).
Không overwrite output cũ; đổi directory khi chạy lại. Lỗi vận hành như font sai,
I/O hoặc config sai làm command fail; không đánh tráo thành sample bị loại.
Mẫu schema/semantic/render invalid được ghi ID/reason, không ghi assets nửa chừng.
Build chỉ công bố manifest sau khi xử lý hết cases; CLI chạy validator trước khi
trả thành công. Không có manifest hoàn chỉnh thì không coi output là dataset hợp lệ.

Snapshot an toàn của manifest/report ở `datasets/manifests/d21-sample-v1.json`
và `d21-rejections-v1.json`; assets lớn vẫn ignored. Sau khi tái tạo đúng source,
config, seed và môi trường snapshot, có thể verify snapshot đã chuyển vị trí:

```sh
PYTHONPATH=src python3 -m vietdoc.data.generator.d21 --verify datasets/manifests/d21-sample-v1.json --assets-root datasets/processed/d21-review-a
```

`--assets-root` là directory do caller chọn rõ, không lấy root tuyệt đối từ manifest.
Absolute/traversal/backslash paths, missing files và symlink thoát asset root bị chặn.
Hashes là integrity checks, không là chữ ký xác thực manifest không đáng tin.

### Reproducibility policy

- Cùng seed/config canonical/version, vocabulary/schema/source hashes và môi trường
  được pin: IDs, thứ tự samples, gold/labels/transcript/regions, **PNG/PDF bytes**,
  rejection report và toàn bộ manifest phải byte-identical giữa fresh directories.
  Output path, wall clock, mtime và PYTHONHASHSEED không tham gia nội dung.
- Config hash tính trên JSON được canonicalize bởi `manifest.encoded` (UTF-8,
  indent=2, insertion order xác định, newline cuối). Whitespace của file input
  config không có ý nghĩa. Gold/sidecars dùng cùng serialization; không binary float.
- Không timestamp, PDF CreationDate/ModDate/Producer/path/document ID hoặc UUID
  ngẫu nhiên. PDF xref/object order cố định; zlib compression level=9. Không dùng
  Pillow PDF writer có metadata thời gian mặc định.
- Python 3.12.3/Linux, Pillow 10.2.0, jsonschema 4.10.3, FreeType 2.13.2,
  RAQM 0.10.1, zlib 1.3 là môi trường đã kiểm. Font DejaVuSans.ttf ở
  `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`, SHA-256
  `ae7b7855e115a5966d8b1b3f80f254ccc117ec86f9965e202ee2940453837280`.
  `--font` cho phép đổi vị trí font; bytes phải khớp hash trong config.
- Manifest lưu versions và hash Pillow binary modules; trên Linux lưu thêm hash
  các shared libraries FreeType/RAQM/HarfBuzz/FriBidi/zlib/libpng đã load. Pillow
  build này không trả HarfBuzz/FriBidi version, nên binary hashes pin chúng.
  Validator từ chối khi source/font/schema/vocabulary/environment khác snapshot.
  Không hứa PNG/PDF byte-identical xuyên OS hoặc các renderer builds khác nhau.
  Chưa cung cấp container/lock toàn OS; muốn reproduce snapshot cần giữ renderer
  binaries đúng hash. Không tải/cài font hay model tự động.
- IDs là local trong một manifest, không global qua seed/version. Lineage dùng
  sample/base/family/template/type/schema; chưa assign split hoặc augmentations.
- Mọi sửa label phải sửa values/config/template/renderer nguồn, tăng version và
  tái sinh manifest/assets vào directory mới. Không sửa gold theo prediction.
  Strict validator chỉ hỗ trợ current source/version; historical outputs cần source
  và environment tương ứng, không nới validator để hợp thức hóa nhãn sai.

### Validation và approval

`data/manifest.py` xử lý IDs/paths/hash/JSON primitives; `data/validation.py`
validate schema theo type được chọn, semantic calendar/time/Decimal, Unicode NFC,
controls/empty strings và font glyph coverage. `d21.validate` còn kiểm decode,
RGB 1500×2600, references, duplicate IDs/image hashes/paths, row count/status counts,
source/gold và regenerate cả sáu assets. Bounds/wrap kiểm **trước khi chấp nhận**;
không cắt rows/text, không tự giảm font để giấu overflow. Validator không dùng
`assert`, nên vẫn kiểm khi chạy Python `-O`.

Default config `[0,1,30,31]`: 20 candidates → 14 accepted + 6 rejected. Mỗi type có
hai layouts × rows 0/1/30; thêm một missing-total case có 3 rows. Bốn cases 31 rows
bị business schema maxItems=30 reject; hai cases 30 rows với description dài bị
clipping reject, dù business schema vẫn valid. Chưa có loại sample excluded khác:
report `excluded=[]`. Rejected assets không được ghi.

Accepted nghĩa schema/semantic/render valid cho dataset, **không approval-valid**.
Missing total là blocker nhưng vẫn có thể dùng làm dataset false-fill case;
`items=[]` có completeness warning. Arithmetic differences chỉ là warnings, không
recompute hoặc override số nguồn. Mọi sample đều `approval_valid=false` và
`review_required=true`; module offline này không cấp quyền, CAS/head check hoặc
thay Java approval service. Generator D2.1 hiện chỉ tạo present/absent có nguồn
rõ; không chuyển obscured/unlabeled D1.1 thành absent. Validation đối chiếu chính
xác sidecars từ source. Chưa thêm renderer che chữ hoặc partial annotation.

Tests gồm source invalid/date/time/money/Unicode/font, boundary rows, overflow,
non-overwrite, changed seed, hai fresh builds, manifest/path/hash/reference,
corrupt PNG cả khi hash được cập nhật, dimensions, labels/transcript/regions/gold/PDF
drift, duplicate images/IDs/paths, report tampering và source omissions.
Nếu Poppler `pdfinfo`, `pdfimages`, `pdftoppm` có sẵn, test độc lập kiểm cả 14 PDF:
parse một trang, render thành PNG và extract raster nhúng giống từng pixel nguồn.
Nếu thiếu thì test này skip rõ, không cài tool tự động. PNG render lại từ PDF có thể
resample/anti-alias theo viewer; không yêu cầu nó byte/pixel-identical với PNG gốc.
Xem evidence/limitations tại `datasets/manifests/d21-QA.md`.

## D2.2 — layout families, grouped assignment và bounded variants

`d22.py` dùng value vocabulary D1.1 và value factory D1.2, validation/PDF/environment
của D2.1. `templates/families.py` thêm structural renderer riêng; không thay output
renderer D1.2/D2.1. Business schema không đổi. CLI mặc định chỉ sinh **20 clean
bases**, không phải dataset pilot đủ support hoặc final đã freeze.

Mỗi type có cùng catalog cấu trúc nhưng fields/labels riêng của receipt/invoice.
Font, màu và canvas được giữ cố định. Family IDs chứa type để không nhập nhằng.

| Index | Thứ tự cột | Header / totals | Split |
|---|---|---|---|
| f00 | description, quantity, unit, unit_price, line_total | stacked / sau bảng | train |
| f01 | quantity, description, unit_price, unit, line_total | stacked / sau bảng | train |
| f02 | line_total, description, unit, quantity, unit_price | stacked / sau bảng | train |
| f03 | unit_price, quantity, description, line_total, unit | stacked / sau bảng | train |
| f04 | unit, line_total, quantity, unit_price, description | stacked / sau bảng | train |
| f05 | như f00 | hai cột / trước bảng, vocabulary thay thế | train |
| f06 | như f01 | hai cột / trước bảng, vocabulary thay thế | dev |
| f07 | như f02 | hai cột / trước bảng, vocabulary thay thế | dev |
| f08 | như f03 | hai cột / trước bảng, vocabulary thay thế | final |
| f09 | như f04 | hai cột / trước bảng, vocabulary thay thế | final |

Ví dụ vocabulary thay `Cửa hàng` → `Điểm bán`, `Ngày lập` → `Ngày phát hành`,
`Tổng thanh toán` → `Phải trả`. Các families này vẫn chung renderer/vocabulary
nguồn, **không phải independent mocks**. AI-1/AI-2 và Lead cần review mức đa dạng.

### Assignment và targets

`splits.assign_groups` nối transitive family/source/base aliases trước khi values
được tạo. `source_aliases` map family sang nguồn trùng đã biết; conflicting split
bị reject, không tự đổi holdout. `source_group` là issuance/layout source group,
không phải tên merchant được bốc từ vocabulary; shared generator/vocabulary được
ghi riêng trong provenance. Không dùng giả định này cho public data chưa audit.
Plan, assignment hash và value seed từng base được ghi vào manifest. Variant seed
derive từ base seed + variant name; Python hash randomization không tham gia.

`bases_per_family=150` hỗ trợ 3.000 clean bases; `300` hỗ trợ 6.000. Đây là khả năng
cấu hình, chưa là approval G0. CLI có `--base-limit=40` mặc định, chặn accidental
large run trước khi tạo output. Chỉ tăng limit và sửa config sau quyết định capacity
của Lead, giữ evidence nguồn quyết định trong handoff. Không tự chạy quy mô lớn.
Không có thao tác final freeze/approve trong CLI. `dataset_version` có thể đặt cho
v0.1/v1 candidate; mọi manifest hiện vẫn `final_frozen=false`.

Dev partitions chỉ bật khi **mỗi type có đủ clean bases trong cả hai partitions**
theo `dev_min_clean_per_type` (mặc định 100, là operational threshold đề xuất).
Giữ toàn bộ connected group/family trong một partition; thiếu support thì toàn bộ
dev giữ `dev_partition=null`. Report số thật, kể cả unpartitioned bases. Đủ count
**không chứng minh calibration đủ**: cần correctness labels, field/class coverage,
metric protocol và Lead/AI-2 review riêng. Không tune trên final.

### Augmentation và labels

- Skew là affine horizontal shear có dấu, `abs(shear)<=0.025` (~1,43° lệch đường
  dọc), không phải rotation. Gaussian blur radius `[0,1]`, noise amplitude integer
  `[0,18]` trên kênh 8-bit. Noise grid seeded nội bộ, bilinear resize, cộng có clip;
  không dùng RNG toàn cục. Crop mỗi mép `[0,200]` pixels.
- `mild`: shear 0.015 / blur 0.4 / noise 8; `crop`: shear -0.025, left 100 và top
  180; `unreadable`: full-text masking + blur/noise. Unreadable là failure slice
  synthetic về mất thông tin, không mô phỏng đủ mọi ảnh unreadable thực tế.
- Bounds kiểm cả bốn góc sau shear/crop. Nếu một fragment/occurrence bị mất,
  renderer che **mọi** occurrence của field, null value trong gold variant,
  status `obscured`, raw null, bỏ regions/transcript field đó. Không đổi thành
  `absent`; absent nguồn vẫn absent. Gold sạch nằm trong clean base, có
  `source_gold_sha256` để nối lineage. Static text bị crop cũng bỏ fragment.
- PNG/PDF của variant dùng cùng raster. Regions là pixel trên **chính** canonical
  PNG đã biến đổi, thêm quads và affine forward/inverse; width/height đổi theo
  crop. Geometry là renderer-local, chưa phải shared viewer contract. Loss được
  đánh dấu; inverse tọa độ không khôi phục nội dung đã mất.
- Transcript chỉ chứa các fragments còn giữ. Không có OCR output/prediction nào
  làm gold. Severity bounds không thay human readability QA; `bounded` là policy
  slice, không phải xác nhận từng ảnh đều dễ đọc.

### Integrity, screening và consumer

SHA-256 từng asset, source/config/schema/vocabulary/font/environment và manifest
được lưu; reproducibility chỉ trong cùng renderer stack như D2.1. `--verify`
regenerate tất cả assets và so bytes, metadata, plan, report; không chỉ tin hashes
do manifest khai. Không overwrite directory. Build lỗi không có manifest hoàn chỉnh
thì không dùng directory đó làm dataset. IDs local trong dataset version.

Exact PNG trùng trong cùng base bị loại và report; trùng giữa bases fail. Exact
content (bỏ invoice_number để tránh ID giả che leakage) cross-split cũng fail.
Near-duplicate screening dùng clean bases: dHash 64-bit distance <=8 hoặc content
value-set Jaccard >=0.85. Các candidate pairs được công khai kèm split và metric,
không tự gọi là đã xử lý. Sparse pages dễ tạo false positives; heuristic này
không chứng minh không còn semantic duplicates. Không dùng variants làm observations
độc lập. Report có counts base/image, type/family/source/split/quality/rows/status,
base summaries và cross-count slices. Ambiguous findings phải review trước pilot/freeze.

CLI và consumer smoke (output phải là đường dẫn mới):

```sh
PYTHONPATH=src PYTHONHASHSEED=11 python3 -m vietdoc.data.generator.d22 --seed 2202 --output datasets/processed/d22-smoke-c
PYTHONPATH=src python3 -O -m vietdoc.data.generator.d22 --verify datasets/manifests/d22-smoke-v01.json --assets-root datasets/processed/d22-smoke-c
PYTHONPATH=src PYTHONHASHSEED=89 python3 -m unittest discover -s tests/unit -p 'test_data*.py' -v
```

Manifest paths relative directory chứa manifest. Safe snapshot chuyển sang
`datasets/manifests/` có thể verify với `--assets-root datasets/processed/d22-smoke-c`.
`integration.load_artifacts(Path.cwd(), output / 'manifest.json')` vẫn đọc format
image/gold/labels/regions/transcript hiện có; thêm convention asset root rõ ràng và
status obscured/unlabeled null. Đây là **consumer smoke loader**, không phải AI-2
training loader. AI-2 vẫn cần kiểm wiring thực, filters và batching của mình.
