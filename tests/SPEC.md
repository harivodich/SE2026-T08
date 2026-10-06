# SPEC — tests

## Purpose và owner

Python test root Owner: Owner behavior, Lead/consumer review.

## Đặt gì ở đây?

unit/integration/contract/architecture/e2e/fixtures; hiện 0 application tests.

## Ranh giới và dữ liệu

Không fake tests để claim app chạy; không PII/full datasets/weights. Scope chung: receipt/invoice tiếng Việt, chữ in một trang; prediction/revision bất biến, human approve trước export. File đích chưa có logic là task cần implement, không tự thêm fake implementation.

## Workflow và kết quả cần kiểm

1. Nhận một task nhỏ có input/version/output/acceptance từ Lead; xem [doc vai trò](../docs/team/backend.md) khi cần task chi tiết.
2. Sửa đúng vùng này, báo affected consumer nếu contract/config/version đổi; không tự nhận phần module khác.
3. Focused tests cho behavior thật, failed paths/versions/denominators rõ.
4. Ghi commands/checks/output thật và limitations, peer review trước Lead duyệt; [Git Flow](../docs/git-flow.md), không direct push main/develop.

## Folder liên quan

[Folder cha](../SPEC.md). [Scope](../specs/scope.md).
- [architecture](architecture/SPEC.md)
- [contract](contract/SPEC.md)
- [e2e](e2e/SPEC.md)
- [fixtures](fixtures/SPEC.md)
- [integration](integration/SPEC.md)
- [unit](unit/SPEC.md)

SPEC.md là hướng dẫn local, không chứng minh app/model/CI đang chạy. .git/verification tooling/caches và immutable design snapshot không phải folders để team viết application code.
