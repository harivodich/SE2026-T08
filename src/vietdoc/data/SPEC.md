# SPEC — src/vietdoc/data

## Purpose và owner

Data/gold/lineage/splits Owner: Data Engineer.

## Đặt gì ở đây?

Generator/adapters/manifest.py/validation.py/splits.py; assets lớn ở datasets/

`benchmark.py`: bounded local D2.1 render/strict validate/consumer load/evaluate
cost measurements; xem [BENCHMARK.md](BENCHMARK.md). Không nhận final holdout,
không tăng base-limit trên 40, không inference hoặc tự approve capacity.
Measurements chỉ trên Linux Data environment; import/guard tests portable,
unsupported runtime fail rõ và không tạo measurements giả.

`pilot.py`: model-neutral D2.2 membership preparation from a hash-bound review;
confirmed source/family/base/duplicate unions and unresolved risk components stay
separate. Whole-component quarantine, original train/dev only, per-type support
and exclusions; no resplit, final access or training/Lead acceptance claim.
Duplicate screening requires exactly one `quality == 'clean'` representative
for every base present in the supplied inventory, including metadata-only callers.
Valid subsets must retain that representative and their declared variants.

`review_batches.py`: prepares cross-split-first inspection queues from the pinned
review and a byte-identical local asset manifest, using the existing whole-source
records validation boundary. Mechanical comparisons never become dispositions;
image/content/lineage inspection and peer verdict remain explicit.

`pilot_records.py`: prepares a versioned companion selection and compatible
`training-records.v1` payload from a recomputed plan and fully validated source.
Rejects zero type/split support and plan drift; never edits/cuts the canonical
source manifest or exports historical final records. Preparation still requires
membership acceptance, asset archive/QA and actual consumer ACK before training.

`exposure.py`: records validated integration identities/hashes and known lineage;
metadata-only holdout preflight rejects known exposure even after ID renaming.
Unknown legacy lineage stays null. No final asset access, independence certification,
per-person access authentication or final-open authority.

`pilot_packet.py`: bounded non-final D22 inputs with unchanged canonical manifest
and `training-records.v1`, exact render verification, decoded-pixel hashes, pending
duplicate review and safe fresh-root archive receiver. Explicit family selection
in D22 config is optional; omitted means the original 20-family generation.
Packet contains quarantined inputs for OCR/QA work and never grants training
clearance or human/Lead approval. See [pilot packet commands](PILOT-PACKET.md).

## Ranh giới và dữ liệu

Không predictions làm gold hoặc random variant splits qua tập Scope chung: receipt/invoice tiếng Việt, chữ in một trang; prediction/revision bất biến, human approve trước export. File đích chưa có logic là task cần implement, không tự thêm fake implementation.

## Workflow và kết quả cần kiểm

1. Nhận một task nhỏ có input/version/output/acceptance từ Lead; xem [doc vai trò](../../../docs/team/data-engineer.md) khi cần task chi tiết.
2. Sửa đúng vùng này, báo affected consumer nếu contract/config/version đổi; không tự nhận phần module khác.
3. D1–D5: render-label QA/schema/Unicode/duplicates/family grouping/PII
4. Ghi commands/checks/output thật và limitations, peer review trước Lead duyệt; [Git Flow](../../../docs/git-flow.md), không direct push main/develop.

## Folder liên quan

[Folder cha](../SPEC.md). [Scope](../../../specs/scope.md).
- [adapters](adapters/SPEC.md)
- [generator](generator/SPEC.md)

SPEC.md là hướng dẫn local, không chứng minh app/model/CI đang chạy. .git/verification tooling/caches và immutable design snapshot không phải folders để team viết application code.
