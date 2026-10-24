# SPEC — src/vietdoc/evaluation

## Purpose và owner

Independent evaluator Owner: Data; hai AI/Lead review.

## Đặt gì ở đây?

Fields/rows/OCR/geometry/evidence/reports; đọc frozen artifacts không production API

D3.1 implementation: `scalar_ocr.py`, `policy.py`, CLI `python -m vietdoc.evaluation`.
Input envelope/definitions/version/review points ở [README](README.md).
Policy `d31-canonical-nfc-v1-proposed` chưa được AI-1/AI-2 duyệt; không thay production normalization.
Known-score tests: `tests/unit/test_evaluation.py`; rows/evidence vẫn thuộc D3.2.

## Ranh giới và dữ liệu

Không tune final test, bỏ failures hoặc dùng unlabeled như absent Scope chung: receipt/invoice tiếng Việt, chữ in một trang; prediction/revision bất biến, human approve trước export. File đích chưa có logic là task cần implement, không tự thêm fake implementation.

## Workflow và kết quả cần kiểm

1. Nhận một task nhỏ có input/version/output/acceptance từ Lead; xem [doc vai trò](../../../docs/team/data-engineer.md) khi cần task chi tiết.
2. Sửa đúng vùng này, báo affected consumer nếu contract/config/version đổi; không tự nhận phần module khác.
3. D3.1/D3.2/D5.1: tiny known-score cases, support/slices/duplicates/missing/F1/EM
4. Ghi commands/checks/output thật và limitations, peer review trước Lead duyệt; [Git Flow](../../../docs/git-flow.md), không direct push main/develop.

## Folder liên quan

[Folder cha](../SPEC.md). [Scope](../../../specs/scope.md).
Folder này không có subfolder làm việc cần spec riêng.

SPEC.md là hướng dẫn local, không chứng minh app/model/CI đang chạy. .git/verification tooling/caches và immutable design snapshot không phải folders để team viết application code.
