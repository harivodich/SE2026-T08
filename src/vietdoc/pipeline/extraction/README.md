# B0 rules baseline / offline predictions

`extract_baseline(page, document_type, *, prepared=None, evidence_matcher=None)`
nhận AI1 OcrPage/PreparedPage objects hoặc JSON representation của proposal tại
`3712c65`. AI2 giữ internal snapshots, không copy owning types, không thay neutral
schemas. Type do caller chọn: `receipt` hoặc `invoice`, Vietnamese, một trang.

## Logic và profile

- Scalar dùng label/context: cửa hàng, ngày/giờ, seller/buyer, subtotal/tax/discount/total.
  Không dùng số lớn nhất, sample ID/filename hoặc gold/pointers để chọn giá trị.
- Table dùng role từ headers và canonical cell geometry; nhóm cells rồi giữ reading
  order đã khai báo. Description wrap giữ cùng row; thiếu cell không dịch cột.
- Khi không có geometry, chỉ nhận ordered-cell grammar có headers đủ rõ, description
  trước values và common units đã hỗ trợ; thiếu/ambiguous cells trả typed failure.
- Profile tối đa 4096 blocks, 128 Ki text characters, canonical 20 MP, 30 items.
  Vượt profile trả `PROFILE_EXCEEDED`, không truncate. B0 chưa hỗ trợ header gộp
  nhiều cột vào một OCR block hoặc nhiều bảng trên cùng trang.
- Prepared geometry available phải explicit. Positive axis-aligned scale/translation
  giữ layout được; rotated/sheared/projective transforms trả
  `LAYOUT_TRANSFORM_UNSUPPORTED`, chờ AI1 processed-frame layout adapter. Không dùng
  missing inverse như identity. Unavailable geometry không được mang canonical quads.
- Tái dùng `vi-VND.v2`. Invalid/ambiguous raw -> null + diagnostics, không sửa từ
  gold hoặc tính lại tiền. Arithmetic chỉ tạo warning khi đủ operands.
- Không tìm được field = `unknown`; label có nhưng không đọc được = `unreadable`.
  Bare label chưa tìm được value là `unknown` + `FIELD_VALUE_NOT_LOCATED`;
  chỉ recognized unreadable marker mới dùng field state `unreadable`.
  Chỉ wording explicit `Không có`/`Không áp dụng`/`N/A` mới là `absent` trong B0
  policy proposal này. Không nhìn Data annotation để quyết định field_states.

Result có `payload`, `raw_candidates` (raw + context IDs), `field_metadata`,
`issues`, `field_states`. Không runtime IDs/envelope. Metadata giữ đủ required
keys; confidence/confidence_method luôn null. OCR score không là correctness.

`evidence_matcher(path, raw_value, context_block_ids)` là hook bind AI1
EvidenceRequest/match_evidence với OcrPage/PreparedPage. Scope là field/cell/span,
không whole page/table. Hook output phải giữ paths/raw, source block IDs/quads và
null confidence; malformed output là `EVIDENCE_INVALID`. Khi chưa gắn matcher,
source_regions rỗng + `SOURCE_MATCHER_UNAVAILABLE`. Repeated/conflicting candidates
không được chọn highlight tùy ý. Scalar label+value nằm chung block có thể bị
matcher từ chối substring evidence; không tự chia box để tăng coverage.

## OCR v2 consumer diagnostics

AI2 nhận legacy v1 và explicit v2 theo provider snapshot `7d96e93`. V2 giữ
unreadable detection IDs/quads/reasons/scores riêng với recognized blocks, validate
status/flags theo arrays, không downgrade partial hoặc suy missing thành absent.
Partial/unreadable truyền `OCR_UNREADABLE_REGIONS` và `SOURCE_OCR_INCOMPLETE` qua
field flags; bare label chưa locate value là unknown, không phải unreadable gold.

Exporter giữ shape `vietdoc.predictions.v1` và ghi thêm `ocr-diagnostics.json`
(`vietdoc.ocr-diagnostics.v1`), chứa validated snapshots cho từng sample và lỗi
input khi có. `predictions_sha256` liên kết companion với exact prediction bytes;
dataset/OCR-input manifest hashes giữ provenance. Đây là internal/offline format,
không phải shared wire schema hoặc approval/default-v2 acceptance của Backend.

## CLI đã implement

OCR consumer replay (source checkout có serve/test env, không cần OCR/model):

```powershell
$env:VIETDOC_CONTRACTS_DIR = (Resolve-Path specs/contracts).Path
python -m vietdoc.entrypoints.cli.ocr_consumer --provider-root <AI1-worktree-at-7d96e93> --output <new-output-directory>
```

Provider phải đúng pinned commit và các imported source files chưa đổi. Python
subprocess tách package AI1/AI2; không merge/copy provider code vào consumer.
CLI kiểm source fixture hashes với pinned Git blobs, chạy golden partial diagnostics,
actual evidence bridge và B0 trên hai native observed JSON. `consumer-report.json`
ghi source/dependency/fixture versions, metadata, coverage/abstain, input hash checks
và limitations; không đọc gold/labels/transcript để infer. Native replay không là
native OCR run mới. `--fixtures` chỉ định thư mục fixtures khi không dùng default.
Output directory phải mới; quality gaps của B0 được báo riêng, không sửa bằng gold.

Từ repo root, AI environment có `.[serve,test]` hoặc contracts dependencies:

```powershell
python -m vietdoc.entrypoints.cli.baseline --root . --manifest tests/fixtures/d12/manifest.json --renderer-fixtures --output artifacts/evaluation/b0-local-run-01
```

Output directory phải mới. `predictions.json` theo Data
`vietdoc.predictions.v1`: exact manifest SHA256, dataset/model/normalizer/OCR/
preprocess/schema/evaluator versions, source/schema hashes, successes và typed
failures. `sample_id` chỉ nằm trong offline harness, không thêm vào compute schema.
Producer ghi `target_evaluator_versions` cho compatibility; actual evaluator
version/source hash chỉ có trong evaluator report sau khi thực chạy, không giả pin đã chấm.
CLI chỉ in counts/path/mode, không raw document payload. Batch có failed records
vẫn ghi artifact đầy đủ và exit 1; invalid manifest hoặc output tồn tại exit 2.

`--renderer-fixtures` là opt-in simulated OCR. Adapter chỉ lấy text/bbox từ D1
renderer regions, bỏ pointers; verify region/PNG hashes và dimensions trước dùng.
Không đọc gold/labels. `actual_ocr=false`, score null, synthetic identity transform
được ghi rõ. Đây không phải native OCR, unseen evaluation hoặc B0 quality evidence.

Mode nhận artifacts OCR thay vì renderer:

```powershell
python -m vietdoc.entrypoints.cli.baseline --root . --manifest <dataset-manifest.json> --ocr-inputs <ocr-inputs.json> --output <new-output-directory>
```

`ocr-inputs.json` là offline producer input proposal, không shared schema mới:

```json
{
  "artifact_version": "vietdoc.baseline-inputs.v1",
  "ocr_version": "exact-engine-model-version",
  "preprocess_version": "exact-preprocess-version",
  "samples": [{
    "sample_id": "same-id-as-dataset",
    "ocr": {"path": "relative/ocr.json", "sha256": "<exact bytes SHA256>"},
    "prepared": {"path": "relative/prepared.json", "sha256": "<exact bytes SHA256>"}
  }]
}
```

Page JSON theo AI1 proposal. Missing sample giữ failed record; duplicate/unknown
IDs bị reject. Paths phải dưới `--root`, no traversal/drive/colon/link/reparse;
hash/version/dimensions/mapping mismatch không được im lặng bỏ qua. Mode này ghi
`actual_ocr=null`: consumer không tự chứng nhận native engine đã tạo artifact.
Data evaluator độc lập đọc gold sau extraction; producer không thay evaluator.

## Checks / limits

```powershell
python -m pytest -q tests/unit/pipeline/test_baseline.py tests/unit/pipeline/test_baseline_export.py
```

AI runner hiện tự collect tests dưới pipeline. Backend cần bổ sung hai file mới
vào mandatory inventory khi nhận patch CI; AI2 không đồng thời sửa CI writer files.
Native OCR receipt/invoice, actual Java provider, accepted source matching,
calibrated confidence và model/training vẫn là gates chưa được đóng bởi fixture tests.
