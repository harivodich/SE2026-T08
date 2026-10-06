# SPEC — src/vietdoc/review

## Purpose và owner

Immutable revisions và human approval Owner: Backend.

## Đặt gì ở đây?

Edit/adopt/validate/approve/public ports/audit; expected head/version CAS

## Ranh giới và dữ liệu

Không mutate prediction/old revisions, last-write-wins hoặc client-only approval Scope chung: receipt/invoice tiếng Việt, chữ in một trang; prediction/revision bất biến, human approve trước export. File đích chưa có logic là task cần implement, không tự thêm fake implementation.

## Workflow và kết quả cần kiểm

1. Nhận một task nhỏ có input/version/output/acceptance từ Lead; xem [doc vai trò](../../../docs/team/backend.md) khi cần task chi tiết.
2. Sửa đúng vùng này, báo affected consumer nếu contract/config/version đổi; không tự nhận phần module khác.
3. B4.1/B4.2/B4.3: two saves/races/missing total/warnings/ownership
4. Ghi commands/checks/output thật và limitations, peer review trước Lead duyệt; [Git Flow](../../../docs/git-flow.md), không direct push main/develop.

## Folder liên quan

[Folder cha](../SPEC.md). [Scope](../../../specs/scope.md).
Folder này không có subfolder làm việc cần spec riêng.

SPEC.md là hướng dẫn local, không chứng minh app/model/CI đang chạy. .git/verification tooling/caches và immutable design snapshot không phải folders để team viết application code.
