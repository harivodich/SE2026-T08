# SPEC — src/vietdoc/infrastructure

## Purpose và owner

I/O adapters/composition support Owner: Backend.

## Đặt gì ở đây?

persistence/storage/queue, registry/observability khi code cần

## Ranh giới và dữ liệu

Không domain approval logic hoặc ORM thứ hai Scope chung: receipt/invoice tiếng Việt, chữ in một trang; prediction/revision bất biến, human approve trước export. File đích chưa có logic là task cần implement, không tự thêm fake implementation.

## Workflow và kết quả cần kiểm

1. Nhận một task nhỏ có input/version/output/acceptance từ Lead; xem [doc vai trò](../../../docs/team/backend.md) khi cần task chi tiết.
2. Sửa đúng vùng này, báo affected consumer nếu contract/config/version đổi; không tự nhận phần module khác.
3. B2/B3/B6: real boundaries, transactions, lifecycle, safe paths/config
4. Ghi commands/checks/output thật và limitations, peer review trước Lead duyệt; [Git Flow](../../../docs/git-flow.md), không direct push main/develop.

## Folder liên quan

[Folder cha](../SPEC.md). [Scope](../../../specs/scope.md).
- [persistence](persistence/SPEC.md)
- [queue](queue/SPEC.md)
- [storage](storage/SPEC.md)

SPEC.md là hướng dẫn local, không chứng minh app/model/CI đang chạy. .git/verification tooling/caches và immutable design snapshot không phải folders để team viết application code.
