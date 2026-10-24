# SPEC — src/vietdoc/pipeline/ocr

## Purpose và owner

OCR adapter Owner: AI-1; AI-2 consumer.

## Đặt gì ở đây?

Port và pretrained Vietnamese engine adapter trả blocks/text/order/quads/scores/page dimensions/version.

## Ranh giới và dữ liệu

Không train extractor hoặc business DB; engine failures không fake text. Scope chung: receipt/invoice tiếng Việt, chữ in một trang; prediction/revision bất biến, human approve trước export. File đích chưa có logic là task cần implement, không tự thêm fake implementation.

## Workflow và kết quả cần kiểm

1. Nhận một task nhỏ có input/version/output/acceptance từ Lead; xem [doc vai trò](../../../../docs/team/ai-1-ocr.md) khi cần task chi tiết.
2. Sửa đúng vùng này, báo affected consumer nếu contract/config/version đổi; không tự nhận phần module khác.
3. O1.3/O2: actual engine smoke, OCR CER/geometry/order/error/timing.
4. Ghi commands/checks/output thật và limitations, peer review trước Lead duyệt; [Git Flow](../../../../docs/git-flow.md), không direct push main/develop.

## Folder liên quan

[Folder cha](../SPEC.md). [Scope](../../../../specs/scope.md).
Folder này không có subfolder làm việc cần spec riêng.

SPEC.md là hướng dẫn local, không chứng minh app/model/CI đang chạy. .git/verification tooling/caches và immutable design snapshot không phải folders để team viết application code.
