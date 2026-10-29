# D1.2 bounded integration renderer — review fixes R01–R06

`integration.py` tạo 20 samples từ cùng business data object với ảnh/gold. D1.1
`values.py` cung cấp dictionary fictional; không lấy OCR/model output làm gold.
D1.2 chỉ annotate present/absent, không dùng loader này cho D1.1 obscured/unlabeled.

## Runtime và font

Giữ offline Data render environment riêng với Python AI serving/train. Các exact
pins trong `.[data]` (Pillow 10.2.0, jsonschema 4.10.3) là môi trường render D1/D2,
không phải tuyên bố đã resolve chung với versions của AI-1/AI-2. D1.1 tests cũng cần
jsonschema: cài extra `data` trước cả tests D1.1. Không cần model/API/DB/dataset tải về.
Core package không kéo validator khác vào `.[data]`; compute dùng các extras
`contracts`/`serve`/`train` trong môi trường riêng. Không cài gộp chúng với `data`.

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
Loader D1.2 không là adapter cho D1.1 partial labels hoặc generator/evaluator D2/D3.

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
