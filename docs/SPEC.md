# SPEC — docs

## Purpose và owner

Human docs Owner: Lead/owning contributor.

## Đặt gì ở đây?

architecture/source-structure/git-flow/team/adr/uml/history/reviews; spec con ngay folder.

## Ranh giới và dữ liệu

Không secrets/raw data/weights hoặc context docs thay runnable code. Scope chung: receipt/invoice tiếng Việt, chữ in một trang; prediction/revision bất biến, human approve trước export. File đích chưa có logic là task cần implement, không tự thêm fake implementation.

## Workflow và kết quả cần kiểm

1. Nhận một task nhỏ có input/version/output/acceptance từ Lead; xem [doc vai trò](team/lead.md) khi cần task chi tiết.
2. Sửa đúng vùng này, báo affected consumer nếu contract/config/version đổi; không tự nhận phần module khác.
3. Internal links/status/authority/version consistency.
4. Ghi commands/checks/output thật và limitations, peer review trước Lead duyệt; [Git Flow](git-flow.md), không direct push main/develop.

## Folder liên quan

[Folder cha](../SPEC.md). [Scope](../specs/scope.md).
- [adr](adr/SPEC.md)
- [design](design/SPEC.md)
- [history](history/SPEC.md)
- [reviews](reviews/SPEC.md)
- [team](team/SPEC.md)
- [uml](uml/SPEC.md)

SPEC.md là hướng dẫn local, không chứng minh app/model/CI đang chạy. .git/verification tooling/caches và immutable design snapshot không phải folders để team viết application code.
