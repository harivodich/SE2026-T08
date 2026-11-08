# Duplicate review — D1/D2, 2026-11-08

D1 tooling hoàn tất. D2 **chưa hoàn tất review ảnh/content**: đã kiểm metadata
của 81 pairs, giữ 81 `pending` (43 cross-split). Không leakage-cleared, không
pilot/freeze approval. `d22-QA.md`, manifest/report lịch sử và splits giữ nguyên.

## Binding và cách chạy

`d22-duplicate-review-v1.json` là audit bổ sung, bind theo tên và SHA-256 bytes của
`d22-smoke-v01.json` và `d22-report-v01.json`. Mỗi `candidate_id` là `pair-` cộng
SHA-256 của `manifest.encoded(sorted(base_ids))`, không phụ thuộc thứ tự review.
Validator kiểm report hash trong manifest, tính lại screening từ sample metadata,
và yêu cầu đúng một disposition cho mỗi candidate.

```sh
PYTHONPATH=src python3 -m vietdoc.data.duplicate_review \
  --manifest datasets/manifests/d22-smoke-v01.json \
  --report datasets/manifests/d22-report-v01.json \
  --review datasets/manifests/d22-duplicate-review-v1.json
PYTHONPATH=src python3 -m unittest discover -s tests/unit -p 'test_data_duplicate_review.py' -v
```

Format `duplicate-review-v1`: root `version`, `manifest`, `report`, `dispositions`.
Mỗi disposition có `candidate_id`, hai `base_ids`, `disposition`, `reason`,
`reviewer`, và `evidence` gồm ba boolean `image/content/lineage`.
Giá trị `pending` dùng cho chưa đủ kiểm chứng; `distinct`, `duplicate`, `ambiguous`
chỉ dùng sau khi đã thực sự kiểm cả ba loại evidence. Không suy ra duplicate từ
dHash-close. `ambiguous` vẫn unresolved; `review_complete` chỉ nói đủ coverage,
không thay peer/Lead approval. Reviewer là attribution, không phải authentication.
Khi cập nhật audit, ghi reason cụ thể và reviewer thực, không nhận attribution của
Codex là human sign-off. Giữ audit version trước trong Git history.

## Evidence thực hiện và phần còn chờ

- Đã tính lại screening khớp report lịch sử: 81 pairs, 43 cross-split.
- Đã đối chiếu từng pair: family/source/assignment group, content SHA-256 và
  source-gold SHA-256 đều khác nhau. Per-pair distance/Jaccard và kết quả lineage
  nằm trong reason. Hash khác không chứng minh independence; renderer dùng chung
  cũng không chứng minh duplicate. Không dùng predictions hoặc final errors.
- Không có `datasets/processed/d22-smoke-c` hoặc archive ảnh D2 tương ứng trong
  workspace/bản bàn giao local đã tìm. Chưa mở được PNG, transcript hoặc gold
  matching hash. Không regenerate bằng source mới rồi coi là ảnh snapshot cũ.
- DE tiếp tục khi có assets snapshot: verify SHA-256 PNG/content theo manifest,
  xem cả 20 clean bases và so từng candidate, ưu tiên 43 cross-split; ghi các
  khác biệt content/layout và lineage đủ cụ thể. Tiny safe report chỉ chứa metadata,
  không đưa raw assets/content corpus vào Git.
- AI1/AI2 kiểm nhóm còn mơ hồ; Lead duyệt grouping/split trước pilot/freeze.
  Nếu có leakage thật: task tiếp theo tạo dataset version mới để regenerate hoặc
  reassign, không sửa snapshot hay split trong task này.

## Verification và bàn giao

Đã chạy 8 focused unit tests: pass; CLI `python -O`: 81 pending, 43 cross-split,
`review_complete=false`, `unresolved=81`. Tests gồm thiếu/trùng/unknown IDs,
candidate mismatch, missing reason/reviewer, evidence/version invalid, byte drift,
report rebinding không che được screening drift, không mutation và approval semantics.
Không chạy renderer/full Data suite: Python hiện tại thiếu Pillow; task này dùng
stdlib, không cài dependency. Không claim visual review hoặc consumer acceptance.

Branch `codex/duplicate_review_audit` tách từ checkout
`feature/SE-36_validated_label_adapter` tại `f08de75` để giữ Data dependencies hiện có;
không có issue ID được giao cho nhóm D nên không tự gán số `SE-*`.
Chưa push/tạo PR; cần đối chiếu base `develop` mới nhất khi chuẩn bị PR riêng.
