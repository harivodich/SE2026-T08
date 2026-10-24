# D2.2 — smoke và handoff, 2026-10-25

Trạng thái: implementation + bounded smoke để review; **không pilot/final freeze**.
Không mở model predictions/final errors, không dùng corrections làm gold, không
tải public data/model, không gọi API, không chạy large dataset/training. Không
commit/push/PR/deploy. Branch hiện hành được giữ nguyên; `.awb/` và `skills/`
là untracked có sẵn, không sửa chúng.

## Inputs và gates

Đã đọc task D2.2 trong `docs/team/data-engineer.md`, workflow/G0–G5, SPEC của
data/generator/templates/datasets/tests, D2.1 source/tests/QA, business schema,
ADR-0004 (vẫn Proposed), và phần generator/splits của design v1 chỉ làm reference.
Không thấy G0 resource/capacity decision đã được Lead duyệt trong repo. Không có
dev error report được phép dùng làm input; increment này dựa contract/boundary
cases, không đọc predictions. Hai skills adaptive-engineering/software-architect
không có trong catalog session, không tự cài skill.

## Deliverables và policies

- `generator/templates/families.py`: 10 families/type, 6 train / 2 dev / 2 final;
  5 thứ tự cột × stacked header/totals sau bảng hoặc header hai cột/totals trước
  bảng và vocabulary thay thế. Chi tiết từng family ở generator README/catalog.
  Giữ màu/font cố định. Đây là structural variants của cùng renderer, chưa phải
  independent mock và cần consumer/Lead review độ đa dạng.
- `data/splits.py`: union family/source/base groups trước values; duplicate source
  aliases transitive không qua split/subpartition. Conflict fail, không random
  resplit. Plan/value seed, assignment hash và full lineage trong manifest.
- `generator/augmentation.py`: seeded shear/blur/noise/crop có hard bounds.
  Full-field masking khi một fragment bị mất; variant gold null + obscured, không
  absent. Regions/transcript bỏ trường đã che; base sạch giữ source truth/hash.
  Canonical dimensions/quads/affine inverse theo chính variant; PDF cùng raster.
  Unreadable là failure slice full-text masking, không claim mô phỏng mọi ảnh thật.
- `generator/d22.py`, `d22.json`: default 20 bases, limit 40; config hỗ trợ
  150–300 bases/family để đạt 3.000–6.000 **sau capacity review**. Các manifests
  có dataset/generator/config/template versions, source/config/schema/font/
  vocabulary/environment/assignment hashes và sáu assets/sample SHA-256.
- Exact images across bases và exact content cross-split fail; redundant identical
  variant cùng base bị loại có report. Clean-base dHash và content value-set
  signatures báo candidates, không tự chứng nhận independence. Không đếm
  variants là bases độc lập. Safe metadata dùng signatures, không chứa gold corpus.
- `integration.load_artifacts` hỗ trợ manifest-relative paths và null statuses
  obscured/unlabeled; giữ D1.2 convention. Đây là consumer smoke, không viết
  AI-2 training loader hay xác nhận AI-2 đã nghiệm thu.

## Commands và kiểm chứng

Các commands đã thực chạy từ repository root (output generation phải là path mới):

```sh
PYTHONPATH=src PYTHONHASHSEED=89 python3 -m unittest discover -s tests/unit -p 'test_data*.py' -v
PYTHONPATH=src PYTHONHASHSEED=11 python3 -m vietdoc.data.generator.d22 --seed 2202 --output datasets/processed/d22-smoke-c
PYTHONPATH=src PYTHONHASHSEED=89 python3 -m unittest discover -s tests/unit -p 'test_data_d22.py' -v
PYTHONPATH=src python3 -O -m vietdoc.data.generator.d22 --verify datasets/manifests/d22-smoke-v01.json --assets-root datasets/processed/d22-smoke-c
sha256sum --check datasets/manifests/d22-smoke-v01.sha256
git diff --check
```

Regression toàn data suite: **23 tests pass, 399,123 giây**, gồm independent
Poppler PDF check không skip; sau đó chỉnh safe metadata (hashed content tokens,
license pending), bổ sung counts/transform-loss flags, fail sớm khi metadata drift
và thêm zero-row invoice regression. Source cuối: **10/10 focused D2.2 tests pass,
279,623 giây**. Hai fresh builds so bằng toàn bộ manifest/assets/report/checksum
bytes, consumer đọc cả 80 samples, deliberate metadata drift bị reject, bounds/
full-field masking và connected source aliases được kiểm. Chạy `python -O` verify
snapshot sau chuyển vị trí cũng `valid=true`, 20 bases, 80 samples, 81 ambiguous
pairs; không dựa trên assertions có thể bị tắt.

CLI build+verify source cuối: `valid=true`, 20 bases, 80 samples, 81 ambiguous pairs,
`final_frozen=false`. `compileall` cho các Python files mới, `git diff --check` và
checksum checks pass; processed assets được `git check-ignore` xác nhận ignored.

Artifacts cuối (paths trong manifest relative explicit assets-root, không trỏ root
máy cá nhân):

- Local assets: `datasets/processed/d22-smoke-c/`, 480 asset files + manifest/report/
  manifest checksum, khoảng 76 MiB theo `du -sh` (không là measured capacity approval).
- [Manifest snapshot](d22-smoke-v01.json), SHA-256
  `eaabf08f5511de0db7bfdf9b7f087716cd0acf197bb00bca9fcb34341f8314db`.
- [Report snapshot](d22-report-v01.json), SHA-256
  `5173053cfb5197fe4e6642ed1a903a96b5f41f7ffcf0531c4029ffabc8af0d1e`.
- [Checksum file](d22-smoke-v01.sha256); config SHA-256
  `864c4c3c6316568f84a10003666fa8c444239191fe0833c689450d2babb3b57c`,
  assignment SHA-256 `cafe5cf3236fb22b0216ada43c7995ed17a5d657f94c65c4e882b9004aa9d340`.

Snapshot chứa dataset version `v0.1-d22-smoke`, generator/config `d2.2.v1`,
templates `families-v1`, seed 2202 và hashes từng source/asset. Python 3.12.3,
Pillow 10.2.0, jsonschema 4.10.3, FreeType 2.13.2, RAQM 0.10.1, zlib 1.3;
native library hashes trong manifest. Fresh build phải cùng renderer environment.
Để recreate snapshot dùng command trên với output path mới; output path không
tham gia hash. Không gọi snapshot là dataset v1/final đã freeze.

## Counts smoke và target gaps

Counts thực từ smoke: 20 clean bases = 10 receipt + 10 invoice, mỗi family 1 base.
80 ảnh = 20 clean + 20 bounded + 20 content-loss + 20 unreadable. Rows gốc
0/1/3/12/30: mỗi mức 4 bases (16 ảnh kể cả variants).

| Split | Receipt bases | Invoice bases | Tổng bases | Ảnh cả variants |
|---|---:|---:|---:|---:|
| train | 6 | 6 | 12 | 48 |
| dev | 2 | 2 | 4 | 16 |
| final candidate | 2 | 2 | 4 | 16 |

Clean labels: present 1.042, absent 8. Cả variants: present 2.845, absent 32,
obscured 1.323, unlabeled 0. Field status counts khác số documents. Per-family,
source, base và cross slices ở report JSON. Unlabeled chưa được generator này
sinh, không tự giả lập nó thành absent.

Target gaps: thiếu 2.980–5.980 clean bases so planning targets. Mỗi family hiện chỉ
có một row profile; full config hỗ trợ xoay các profiles qua bases nhưng chưa đo
coverage/cost ở quy mô lớn. Final candidate chỉ 4 bases, chưa đạt holdout target
200–400. Không có independent mock families. Chỉ 2 dev bases/type, partitions
chưa bật. Minimum count 100/type/partition là đề xuất operational, không chứng minh
calibration; chưa có correctness labels hoặc đo field/class coverage.

Leakage smoke: group overlap 0; exact PNG/content groups 0. Có **81 ambiguous
clean-base pairs, 43 cross-split**, giữ toàn bộ IDs/distances/similarities và
`reviewed=false`. Đây là findings chưa giải quyết, không gọi leakage-cleared.
Sparse pages và cùng renderer dễ gây false positives; cần review trước pilot/freeze.
Không dùng final prediction errors để phân xử hoặc tune. Nếu cần xem/chỉnh final
candidate assets để audit labels, Lead phải xác nhận lại protocol/freeze sau đó.

## QA và limitations

Đã xem contact sheets của cả 20 clean family samples và so receipt-f04 clean/crop/
unreadable: bố cục/table arrangement khác, crop che scalar/unit bị mất và unreadable
không giữ text. Đây là spot-check bố cục; không phải independent human audit đọc
từng glyph của 80 ảnh. Renderer validation/regeneration và consumer coverage checks
không thay readability review. Bound policy slice không chứng nhận readable.

Một lần chạy thử ban đầu reject invoice rows=0 vì discount lớn hơn subtotal làm
total âm. Đã sửa nguồn values để cap discount theo subtotal + tax; không sửa gold
theo predictions. Directory build lỗi không có manifest hoàn chỉnh không là dataset.
Output trước thay đổi source dùng để debug không thay snapshot cuối.

Reproducibility chỉ trong pinned font/Pillow/native libraries như D2.1; chưa có
container lock xuyên OS. Full-scale throughput/storage/memory chưa đo; near-duplicate
screening có pairwise cost. Vocabulary hiện rất nhỏ (fictional business/products),
không chứng minh generalization sang hóa đơn thực tế. Distribution terms chưa được
Lead chốt, không tự viện dẫn repository LICENSE khi repo chưa có LICENSE.

## Lead / consumers cần review

1. G0 hardware/storage/time budget và số bases chạy v0.1/v1; chưa tăng base-limit.
2. 20 family structures, source aliases và 81 ambiguous pairs; quyết định tách,
   gom nhóm, loại hoặc chấp nhận có evidence trước pilot/freeze.
3. Augmentation caps, conservative field masking, canonical local geometry và
   unreadable slice với AI-1; format/filtering/batching thực với AI-2.
4. Dev partition threshold + correctness/coverage protocol; dataset distribution
   terms và independent mock ownership. Không claim calibration đủ từ count.
5. Freeze W5/final manifest/hash là quyết định riêng của Lead sau QA và capacity;
   mọi output hiện `final_frozen=false`. Chưa consumer smoke sau merge/review.
