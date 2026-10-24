# SPEC — docs/history

## Purpose và owner

Historical records Owner: Lead.

## Đặt gì ở đây?

Bootstrap/old week plan/tasks retired, dated context.

## Ranh giới và dữ liệu

Không status GitHub lịch sử như trạng thái hiện tại hoặc active backlog. Scope chung: receipt/invoice tiếng Việt, chữ in một trang; prediction/revision bất biến, human approve trước export. File đích chưa có logic là task cần implement, không tự thêm fake implementation.

## Workflow và kết quả cần kiểm

1. Nhận một task nhỏ có input/version/output/acceptance từ Lead; xem [doc vai trò](../team/lead.md) khi cần task chi tiết.
2. Sửa đúng vùng này, báo affected consumer nếu contract/config/version đổi; không tự nhận phần module khác.
3. Archive links/context date; preserve records.
4. Ghi commands/checks/output thật và limitations, peer review trước Lead duyệt; [Git Flow](../git-flow.md), không direct push main/develop.

## Folder liên quan

[Folder cha](../SPEC.md). [Scope](../../specs/scope.md).
- [tasks-retired-2026-10-07](tasks-retired-2026-10-07/SPEC.md)

SPEC.md là hướng dẫn local, không chứng minh app/model/CI đang chạy. .git/verification tooling/caches và immutable design snapshot không phải folders để team viết application code.
