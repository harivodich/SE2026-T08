# SPEC — src/vietdoc/entrypoints

## Purpose và owner

Khởi động API/worker/dispatcher/CLI Owner: Backend composition; owning CLI logic theo vai trò.

## Đặt gì ở đây?

api, worker, dispatcher, cli; inject shared services/adapters

## Ranh giới và dữ liệu

Không duplicate core logic hoặc tạo commands giả chưa chạy Scope chung: receipt/invoice tiếng Việt, chữ in một trang; prediction/revision bất biến, human approve trước export. File đích chưa có logic là task cần implement, không tự thêm fake implementation.

## Workflow và kết quả cần kiểm

1. Nhận một task nhỏ có input/version/output/acceptance từ Lead; xem [doc vai trò](../../../docs/team/backend.md) khi cần task chi tiết.
2. Sửa đúng vùng này, báo affected consumer nếu contract/config/version đổi; không tự nhận phần module khác.
3. B1.3/B3/B7: actual process start/health/cleanup/no API model load
4. Ghi commands/checks/output thật và limitations, peer review trước Lead duyệt; [Git Flow](../../../docs/git-flow.md), không direct push main/develop.

## Folder liên quan

[Folder cha](../SPEC.md). [Scope](../../../specs/scope.md).
- [api](api/SPEC.md)
- [cli](cli/SPEC.md)
- [dispatcher](dispatcher/SPEC.md)
- [worker](worker/SPEC.md)

SPEC.md là hướng dẫn local, không chứng minh app/model/CI đang chạy. .git/verification tooling/caches và immutable design snapshot không phải folders để team viết application code.
