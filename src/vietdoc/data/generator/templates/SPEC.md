# SPEC — src/vietdoc/data/generator/templates

## Purpose và owner

Layout source assets Owner: Data.

## Đặt gì ở đây?

receipt/ và invoice/ templates khác spatial/label/table structure.

## Ranh giới và dữ liệu

Đổi màu/font không tự là family mới; không raw datasets/weights. Scope chung: receipt/invoice tiếng Việt, chữ in một trang; prediction/revision bất biến, human approve trước export. File đích chưa có logic là task cần implement, không tự thêm fake implementation.

## Workflow và kết quả cần kiểm

1. Nhận một task nhỏ có input/version/output/acceptance từ Lead; xem [doc vai trò](../../../../../docs/team/data-engineer.md) khi cần task chi tiết.
2. Sửa đúng vùng này, báo affected consumer nếu contract/config/version đổi; không tự nhận phần module khác.
3. D2.2: family/source/base IDs và split lineage, layout/overflow tests.
4. Ghi commands/checks/output thật và limitations, peer review trước Lead duyệt; [Git Flow](../../../../../docs/git-flow.md), không direct push main/develop.

## Folder liên quan

[Folder cha](../SPEC.md). [Scope](../../../../../specs/scope.md).
- [invoice](invoice/SPEC.md)
- [receipt](receipt/SPEC.md)

SPEC.md là hướng dẫn local, không chứng minh app/model/CI đang chạy. .git/verification tooling/caches và immutable design snapshot không phải folders để team viết application code.
