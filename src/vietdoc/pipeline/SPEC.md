# SPEC — src/vietdoc/pipeline

## Purpose và owner

CPU/GPU compute stages Owner: AI-1/AI-2; đề xuất Backend thin wiring.

## Đặt gì ở đây?

AI-1 preprocess.py/geometry.py/evidence.py/ocr; AI-2 extraction/normalization.py/confidence.py; Backend service.py chỉ nối stage khi Lead xác nhận

## Ranh giới và dữ liệu

Không DB/approval/SQL; không viết lại thuật toán AI trong worker/wiring Scope chung: receipt/invoice tiếng Việt, chữ in một trang; prediction/revision bất biến, human approve trước export. File đích chưa có logic là task cần implement, không tự thêm fake implementation.

## Workflow và kết quả cần kiểm

1. Nhận một task nhỏ có input/version/output/acceptance từ Lead; xem [doc vai trò](../../../docs/team/ai-1-ocr.md) khi cần task chi tiết.
2. Sửa đúng vùng này, báo affected consumer nếu contract/config/version đổi; không tự nhận phần module khác.
3. O1–O5/M1–M6/B3.2: canonical transforms/contracts/errors/versioned adapters
4. Ghi commands/checks/output thật và limitations, peer review trước Lead duyệt; [Git Flow](../../../docs/git-flow.md), không direct push main/develop.

## Folder liên quan

[Folder cha](../SPEC.md). [Scope](../../../specs/scope.md).
- [extraction](extraction/SPEC.md)
- [ocr](ocr/SPEC.md)

SPEC.md là hướng dẫn local, không chứng minh app/model/CI đang chạy. .git/verification tooling/caches và immutable design snapshot không phải folders để team viết application code.
