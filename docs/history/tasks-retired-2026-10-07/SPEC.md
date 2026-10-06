# SPEC — docs/history/tasks-retired-2026-10-07

## Purpose và owner

Retired tasks backup Owner: Lead.

## Đặt gì ở đây?

README/current.md archived từ tasks; có thể restore, không current workflow.

## Ranh giới và dữ liệu

Không giao task từ archived statuses; issue/PR hiện hành. Scope chung: receipt/invoice tiếng Việt, chữ in một trang; prediction/revision bất biến, human approve trước export. File đích chưa có logic là task cần implement, không tự thêm fake implementation.

## Workflow và kết quả cần kiểm

1. Nhận một task nhỏ có input/version/output/acceptance từ Lead; xem [doc vai trò](../../team/lead.md) khi cần task chi tiết.
2. Sửa đúng vùng này, báo affected consumer nếu contract/config/version đổi; không tự nhận phần module khác.
3. Links/date/backup preserved; no root tasks folder.
4. Ghi commands/checks/output thật và limitations, peer review trước Lead duyệt; [Git Flow](../../git-flow.md), không direct push main/develop.

## Folder liên quan

[Folder cha](../SPEC.md). [Scope](../../../specs/scope.md).
Folder này không có subfolder làm việc cần spec riêng.

SPEC.md là hướng dẫn local, không chứng minh app/model/CI đang chạy. .git/verification tooling/caches và immutable design snapshot không phải folders để team viết application code.
