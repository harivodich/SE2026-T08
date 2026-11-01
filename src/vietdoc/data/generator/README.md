# D1.2 bounded integration renderer — review fixes R01–R06

`integration.py` tạo 20 samples từ cùng business data object với ảnh/gold. D1.1
`values.py` cung cấp dictionary fictional; không lấy OCR/model output làm gold.
D1.2 chỉ annotate present/absent, không dùng loader này cho D1.1 obscured/unlabeled.

## Runtime và font

Giữ offline Data render environment riêng với Python AI serving/train. Các exact
pins trong `.[data]` (Pillow 10.2.0, jsonschema 4.10.3) là môi trường render D1/D2,
không phải tuyên bố đã resolve chung với versions của AI-1/AI-2. D1.1 tests cũng cần
jsonschema: cài extra `data` trước cả tests D1.1. Không cần model/API/DB/dataset tải về.

Canonical bytes được kiểm trên Linux, Python 3.12.3, Pillow 10.2.0, jsonschema
4.10.3, FreeType 2.13.2/RAQM 0.10.1, zlib 1.3 và DejaVuSans.ttf SHA-256
`ae7b7855e115a5966d8b1b3f80f254ccc117ec86f9965e202ee2940453837280`.
Fingerprint đầy đủ (gồm renderer binaries) ở
`tests/fixtures/d12/canonical-environment.json`. DejaVu là font hệ thống, không
bundle/tải font trong repo. Dùng font local có license phù hợp của người chạy.

CLI nhận `--font`; test/CLI nhận `VIETDOC_DATA_FONT`. Nếu không chỉ định, thử
DejaVu hệ thống, font Pillow tìm được, rồi Arial trong Windows Fonts. Không có font
đọc được dấu tiếng Việt thì fail với hướng dẫn rõ, không bỏ dấu hoặc skip render.
Font khác có thể đổi wrap/transcript/regions/PNG; manifest v2 ghi font hash và
render environment thực tế, không gán output mới thành bytes canonical cũ.
JSON/text luôn UTF-8, LF, không phụ thuộc default locale hoặc CRLF trên Windows.

## Fresh checkout — Bash/Linux

Từ repository root; chọn paths output chưa tồn tại. Tạo environment riêng nếu chưa
có, cài từ dependencies đã chuẩn bị hoặc package index theo quy định của team:

```sh
python3 -m venv .venv-data
. .venv-data/bin/activate
python -m pip install -e '.[data]'
export PYTHONPATH=src
export VIETDOC_DATA_FONT=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
python -m vietdoc.data.generator.integration --output datasets/processed/d12-recreated --manifest datasets/manifests/d12-recreated.json --seed 1202 --font "$VIETDOC_DATA_FONT"
python -m vietdoc.data.generator.integration --verify --full-set --manifest datasets/manifests/d12-recreated.json
python -m unittest discover -s tests/unit -p 'test_data_values.py' -v
python -m unittest discover -s tests/unit -p 'test_data_integration.py' -v
```

## Fresh checkout — Windows PowerShell

Python 3.12, từ repository root; không cần bật UTF-8 mode để đọc artifacts:

```powershell
py -3.12 -m venv .venv-data
.\.venv-data\Scripts\python.exe -m pip install -e '.[data]'
$env:PYTHONPATH = 'src'
$env:VIETDOC_DATA_FONT = "$env:WINDIR\Fonts\arial.ttf"
.\.venv-data\Scripts\python.exe -m vietdoc.data.generator.integration --output datasets/processed/d12-recreated --manifest datasets/manifests/d12-recreated.json --seed 1202 --font $env:VIETDOC_DATA_FONT
.\.venv-data\Scripts\python.exe -m vietdoc.data.generator.integration --verify --full-set --manifest datasets/manifests/d12-recreated.json
.\.venv-data\Scripts\python.exe -m unittest discover -s tests/unit -p 'test_data_values.py' -v
.\.venv-data\Scripts\python.exe -m unittest discover -s tests/unit -p 'test_data_integration.py' -v
```

Cả hai lệnh generate/verify dùng **cùng manifest mới**, output phải 20 samples,
receipt=10/invoice=10. Build đã chạy loader full-set trước khi thành công. Không
chạy default generator lên reference manifest đã track, không overwrite reference.
`--verify` chung hỗ trợ tiny; `--full-set` mới xác nhận đầy đủ 20 IDs, 10/10 type,
5 mẫu/type/layout, cùng seed và row profiles. Manifest rỗng không pass full-set.

Portable tests kiểm schema/gold/labels và geometry/transcript nhất quán cho font
được chọn; tái tạo hai lần cùng môi trường phải cùng hashes. Chỉ gold/labels so
hashes cross-platform với tiny reference. Các test corruption chạy cả normal/-O.
Test canonical riêng phải chủ động bật trong environment khớp fingerprint:

```sh
VIETDOC_CANONICAL_BYTES=1 PYTHONPATH=src python3 -m unittest discover -s tests/unit -p 'test_data_integration.py' -v
```

Khi bật mà fingerprint/font khác thì **fail**, không skip để báo canonical pass.
Mặc định chỉ skip test canonical; portable render/negative tests vẫn chạy đủ.
Không có chế độ tự overwrite/materialize reference: hãy tạo output mới và so hashes
với reference trong canonical test. Không bảo đảm PNG cùng bytes giữa mọi OS.

## Artifacts và consumer

Bản gốc v1 còn ở `datasets/processed/d12-integration-v1/` (ignored), manifest
`datasets/manifests/d12-integration-v1.json`. Loader vẫn đọc v1 nhưng không gán
metadata environment ngược lại cho bản lịch sử. Outputs mới dùng `d1.2.v2` và
lưu environment; geometry v1 và PNG không đổi với cùng stack. Bộ v2 đã kiểm local
ở `datasets/processed/d12-review-fixed-v2/`, manifest an toàn
`datasets/manifests/d12-integration-v2.json`. Tiny reference
`tests/fixtures/d12/`: receipt-03 + invoice-04, seed 1202, 3 rows/mẫu.

Asset paths D1 relative repository root; SHA-256 từng file, labels map theo JSON
Pointer và metadata ngoài business. Sample/base/family/template/type/schema/version,
row_count và status counts được kiểm rules; type buộc nhánh business schema tương
ứng. D1 lineage theo ID và bốn template đã khai báo, không là proof về nguồn độc lập.
D2.1/D2.2 có adapter smoke riêng, kiểm type/schema/counts và lineage theo source
plan/template/variant; replay pixels/source/splits đầy đủ vẫn dùng strict validator.
Outputs mới khai `transcript_scope=full_page`,
`transcript_order=renderer-draw-call-v1`; format lịch sử có adapter ở evaluator.
Thứ tự này mô tả draw calls hiện có (wrap trong cell trước cell tiếp theo), chưa
là reading-order protocol được AI-1/Lead duyệt; không dùng fixture CER/WER để báo
accuracy OCR thật.

```python
from pathlib import Path
from vietdoc.data.generator.integration import load_artifacts
root = Path.cwd()
for metadata, gold in load_artifacts(root, root / 'datasets/manifests/d12-recreated.json', full_set=True):
    print(metadata['sample_id'], metadata['document_type'], len(gold['items']))
```

## Evidence và limitations

Geometry là renderer-local-v1, page 0, top-left pixel ink boxes, chưa là shared
contract approved. Scalar region bao label + value. Loader dùng adapter versioned:
strip đúng label prefix theo template; ghép fragment wrap liên tiếp theo pointer;
so **toàn bộ** value của **mọi occurrence** với raw. Repeated total được kiểm riêng
hai occurrences, không nhận `0 đ` trong `37.500 đ` hoặc `80.000 đ` trong `180.000 đ`.
Unknown pointer, missing occurrence, schema/type/count/status sai đều bị từ chối.
Không cấp bbox/confidence cho absent; không đổi obscured/unlabeled thành absent.

Hashes chỉ integrity, không xác thực nguồn. Kiểm sidecar text/bounds không chứng
minh pixels khớp chữ hoặc bbox đúng vị trí; box dịch sai nhưng còn trong trang vẫn
cần visual audit/renderer check. Chưa có OCR/model/API/viewer hoặc consumer approval.
Các review AI-1 geometry, AI-2 normalization/status/reading order và Backend adapter
vẫn là gates chưa hoàn tất; không tự đổi ADR Proposed thành Accepted.

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
PYTHONPATH=src python3 -O -m vietdoc.data.generator.d22 --verify datasets/processed/d22-smoke-c/manifest.json
PYTHONPATH=src PYTHONHASHSEED=89 python3 -m unittest discover -s tests/unit -p 'test_data*.py' -v
```

Manifest paths relative directory chứa manifest. Safe snapshot chuyển sang
`datasets/manifests/` có thể verify với `--assets-root datasets/processed/d22-smoke-c`.
`integration.load_artifacts(Path.cwd(), output / 'manifest.json')` vẫn đọc format
image/gold/labels/regions/transcript hiện có; thêm convention asset root rõ ràng và
status obscured/unlabeled null. Đây là **consumer smoke loader**, không phải AI-2
training loader. AI-2 vẫn cần kiểm wiring thực, filters và batching của mình.
