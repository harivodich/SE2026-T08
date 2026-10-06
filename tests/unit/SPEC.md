# SPEC — tests/unit

## Purpose và owner

Deterministic unit tests Owner: Owning module engineer.

## Đặt gì ở đây?

documents/jobs/review/pipeline logic; stub I/O đúng boundaries.

## Ranh giới và dữ liệu

Không cần DB/GPU thật cho pure helper tests hoặc duplicate app algorithms. Scope chung: receipt/invoice tiếng Việt, chữ in một trang; prediction/revision bất biến, human approve trước export. File đích chưa có logic là task cần implement, không tự thêm fake implementation.

## Workflow và kết quả cần kiểm

1. Nhận một task nhỏ có input/version/output/acceptance từ Lead; xem [doc vai trò](../../docs/team/backend.md) khi cần task chi tiết.
2. Sửa đúng vùng này, báo affected consumer nếu contract/config/version đổi; không tự nhận phần module khác.
3. Normal/edge/invalid/state/geometry cases.
4. Ghi commands/checks/output thật và limitations, peer review trước Lead duyệt; [Git Flow](../../docs/git-flow.md), không direct push main/develop.

## Folder liên quan

[Folder cha](../SPEC.md). [Scope](../../specs/scope.md).
- [documents](documents/SPEC.md)
- [jobs](jobs/SPEC.md)
- [pipeline](pipeline/SPEC.md)
- [review](review/SPEC.md)

SPEC.md là hướng dẫn local, không chứng minh app/model/CI đang chạy. .git/verification tooling/caches và immutable design snapshot không phải folders để team viết application code.
