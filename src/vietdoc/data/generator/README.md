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
