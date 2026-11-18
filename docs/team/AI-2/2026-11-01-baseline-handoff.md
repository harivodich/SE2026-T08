# M-N1/M-N2/M-N3 handoff — 01/11/2026

Baseline branch `feature/AI2-M2_ai_service_docker`, HEAD trước increment `3a2b701`.
Source mới đang ở working tree, chưa commit/push. Đây là self-run evidence,
không thay AI1/Data/Backend peer review hoặc Lead acceptance.

## Requirement → source/test → result

| Requirement | Source / tests | Kết quả |
|---|---|---|
| R11 malformed release không chặn release tốt | `ml/release_manifest.py`, `test_release_manifest.py` numeric/deep probes | RED 2 decoder failures → GREEN; good release discover được |
| R12 Windows containment | `_contained_file`, drive/colon/reparse/resolved checks | RED controlled drive-relative escape → GREEN trên Windows; không đọc ngoài temp test root; native junction/cross-drive fixtures chưa chạy |
| B0 scalar/table logic | `extraction/baseline.py`, `table.py`, `ocr_input.py`, `test_baseline.py` | Label-based totals, two schemas, wrap/repeated items, missing cells, reordered columns/reading order, 0/1/30 rows; 31/multiple tables/unsupported transform fail explicit |
| Raw/normalized/unknown/evidence | BaselineResult + matcher hook | Required metadata keys, null confidence, no invented boxes; explicit absent khác unreadable/unknown; no gold lookup |
| Prediction producer | `extraction/predictions.py`, CLI `baseline.py`, `test_baseline_export.py` | `vietdoc.predictions.v1`, exact manifest/version/source hashes, failures retained, input identity/hash/path checks, no overwrite |
| M-N3 constraints | [hardware/candidate report](2026-11-01-model-constraints.md) | Host/GPU/container readiness đo thật; 2 observed candidate revisions/licenses/hash references; G0 model execution BLOCKED chờ approval/artifacts |

Baseline/export focused tests cuối: **51 passed**. R11/R12 + API focused: **89
passed, 1 Windows symlink skipped**. Full AI inventory/Docker kết quả cuối ở plan
ledger; không cộng subtests vào số tests hoặc coi tests là số chứng từ/accuracy.

## CLI và artifacts đã thực chạy

```powershell
.\.venv\Scripts\python.exe -m vietdoc.entrypoints.cli.baseline --root . --manifest tests/fixtures/d12/manifest.json --renderer-fixtures --output artifacts/evaluation/mn2-b0-reviewed
```

Kết quả `ok=2, failed=0`. Frozen predictions:
`artifacts/evaluation/mn2-b0-reviewed/predictions.json` (ignored).
Hai IDs `d12-receipt-03` và `d12-invoice-04`. Input text/boxes là renderer fixtures,
`actual_ocr=false`, scores null; pointers/gold/labels không vào extraction logic.
No-gold-read test chặn Path.open cho gold/label files, không chỉ kiểm mock unused.

Nhận actual OCR artifacts dùng `--ocr-inputs`; format/CLI ở
[extraction README](../../../src/vietdoc/pipeline/extraction/README.md). Producer
không tự certify native engine execution từ một file JSON được cung cấp.

## Consumer smoke, chưa phải peer acceptance

AI1 sources tại `3712c65` được đọc qua connector, copy vào ignored reference
overlay; Git blob hashes khớp:

- `contracts/ocr.py`: `b8b210288519a472319802c7d24c60e7e30c3dbb`.
- `pipeline/geometry.py`: `8027f5a0c0875bda611aaaa98eda22f240e2c0fd`.
- `pipeline/evidence.py`: `2d5806011746b697c0e0a5b1e82b4931aa73ab43`.

Actual AI1 OcrPage/PreparedPage `.from_dict`/`.validate_against` và
EvidenceRequest/match_evidence chạy cùng baseline trên simulated D1 blocks.
Mỗi sample có 3 rows; hook chọn được 15 item metadata fields có regions, confidence
vẫn null. Scalar label+value chung block bị conservative matcher giữ unresolved
thay vì baseline tự cắt box. Evidence tại `.verification/mn2/ai1-consumer-reviewed.json`.
Đây không phải actual OCR/provider smoke.

Data D3.2 source pin `a0d71b2112437e0b25b6b20cbc8fdcc8b6da4c37`, lấy read-only
`git archive` cho `src/vietdoc/evaluation` và `src/vietdoc/data/manifest.py` trong
`.verification/mn2/data-reference`. Chạy nguyên evaluator `--candidate B0=...`,
không copy/merge source Data vào product branch và không viết evaluator thay Data.
Bundle: `artifacts/evaluation/mn2-data-reviewed/` (ignored).

Preliminary observations trên hai fixtures đã nhìn, policy còn Proposed:

| Observation | Result |
|---|---|
| Sample accounting | 2 ok, 0 failed/unknown IDs |
| Scalars | 12/12 present slots đúng; 1 absent support; wrong/missing/false-fill = 0 |
| Tables | 6 predicted/matched rows; 30/30 cells, 6/6 exact rows; missing/extra = 0 |
| Default CLI evidence | 0/42 fields covered, 0/46 regions: chưa bind matcher trong CLI, không fake highlight |
| B0/M0/M1 comparison | `fair=false`, missing M0/M1; không full comparison/calibration/freeze |

Không gọi các số này là native OCR quality, unseen B0 accuracy hoặc final benchmark.
D1 integration set đã dùng để phát triển. AI1 matcher smoke là một đường riêng,
không gán 15 fields có region vào coverage của default CLI artifact.

## M-N1 CI / PR description handoff

R05/R09/R14 và CI code đã có ở `3a2b701`. Query connector PR workflow runs tại
head đó chưa trả run; chưa xác định nguyên nhân. Không có hosted failure probe
hoặc peer acceptance mới. R17 vẫn mở; không sửa CI writer files trong increment này.

Backend/Lead nhận suite inventory hiện tại cộng hai modules mới:
`tests/unit/pipeline/test_baseline.py`, `test_baseline_export.py`; bổ sung mandatory
inventory theo policy CI. Existing runner tự collect pipeline folder; không model/
weights/download trong default tests. Cần exact-candidate hosted run trước acceptance.

Draft PR body bổ sung cho lần push được yêu cầu riêng sau này:

> Target develop; framework cùng normalizer vi-VND.v2. Bổ sung R11 decoder isolation,
> R12 path containment, B0 label/header extraction hai schemas và hash-pinned offline
> predictions producer. B0 đã smoke trên simulated OCR fixtures và consumer AI1/Data
> sources pinned; không claim actual OCR/model, full pipeline/G0 hoặc hosted CI của
> working tree chưa push. R05/R09/R14 giữ fixes từ 3a2b701. R17, shared transport/
> resource/typed-stage/UUID gates vẫn cần owner acceptance.

## Các gate còn mở

- M-N2 actual receipt + invoice từ native AI1 OCR: NOT_RUN; cần O-N2 artifact/
  PreparedPage/version/input hashes và approved consumer policy. Fixtures không thay nó.
- M-N3 G0 inference/train-step/checkpoint/reload: BLOCKED theo constraints report.
- M-N4 actual composition/artifact writer/Java promotion và R01/R06/R13/R15: pending
  shared fixtures, lifecycle/admission/typed failure/UUID policy và actual-provider evidence.
- B0 hiện hỗ trợ separated headers, một table và axis-preserving layout profile;
  unsupported cases fail/diagnose rõ, không tự nhận general document extraction.
- Native Windows junction/cross-drive test matrix chưa chạy; reparse guards có code,
  drive-relative controlled probe đã pass. Không claim model release acceptance.
- Data renderer/full repo suite không chạy trong AI env thiếu PIL. Data consumer
  evaluator smoke là stdlib riêng; không thay renderer/package matrix hoặc Java tests.
- Không peer approval, GitHub writes, commit/push hoặc deployment trong lượt này.
