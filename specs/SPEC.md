# SPEC — specs

## Purpose và owner

Requirements và reference contracts Owner: Lead design, Backend contracts.

## Đặt gì ở đây?

scope/approval-policy/contracts; local folder SPEC.md và compatibility navigation.

## Ranh giới và dữ liệu

Không implementation/training results hay tự thay requirements để tests pass. Scope chung: receipt/invoice tiếng Việt, chữ in một trang; prediction/revision bất biến, human approve trước export. File đích chưa có logic là task cần implement, không tự thêm fake implementation.

## Workflow và kết quả cần kiểm

1. Nhận một task nhỏ có input/version/output/acceptance từ Lead; xem [doc vai trò](../docs/team/lead.md) khi cần task chi tiết.
2. Sửa đúng vùng này, báo affected consumer nếu contract/config/version đổi; không tự nhận phần module khác.
3. Schema/approval invariants + affected consumer review.
4. Ghi commands/checks/output thật và limitations, peer review trước Lead duyệt; [Git Flow](../docs/git-flow.md), không direct push main/develop.

## Folder liên quan

[Folder cha](../SPEC.md). [Scope](scope.md).
- [contracts](contracts/SPEC.md)

SPEC.md là hướng dẫn local, không chứng minh app/model/CI đang chạy. .git/verification tooling/caches và immutable design snapshot không phải folders để team viết application code.
