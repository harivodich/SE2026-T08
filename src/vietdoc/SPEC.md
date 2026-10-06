# SPEC — src/vietdoc

## Purpose và owner

Production Python modules cùng contracts/services. Owner: Theo module; Backend integration.

## Đặt gì ở đây?

contracts, identity, documents, jobs, review, exports, pipeline, data, ml, evaluation, infrastructure, entrypoints; hiện 25 __init__.py docstrings.

## Ranh giới và dữ liệu

Model không ghi DB; API không load weights; cross-module calls qua public services. Scope chung: receipt/invoice tiếng Việt, chữ in một trang; prediction/revision bất biến, human approve trước export. File đích chưa có logic là task cần implement, không tự thêm fake implementation.

## Workflow và kết quả cần kiểm

1. Nhận một task nhỏ có input/version/output/acceptance từ Lead; xem [doc vai trò](../../docs/team/backend.md) khi cần task chi tiết.
2. Sửa đúng vùng này, báo affected consumer nếu contract/config/version đổi; không tự nhận phần module khác.
3. Contracts trước adapters/consumers, actual receipt E2E trước nghiệm thu runtime.
4. Ghi commands/checks/output thật và limitations, peer review trước Lead duyệt; [Git Flow](../../docs/git-flow.md), không direct push main/develop.

## Folder liên quan

[Folder cha](../SPEC.md). [Scope](../../specs/scope.md).
- [contracts](contracts/SPEC.md)
- [data](data/SPEC.md)
- [documents](documents/SPEC.md)
- [entrypoints](entrypoints/SPEC.md)
- [evaluation](evaluation/SPEC.md)
- [exports](exports/SPEC.md)
- [identity](identity/SPEC.md)
- [infrastructure](infrastructure/SPEC.md)
- [jobs](jobs/SPEC.md)
- [ml](ml/SPEC.md)
- [pipeline](pipeline/SPEC.md)
- [review](review/SPEC.md)

SPEC.md là hướng dẫn local, không chứng minh app/model/CI đang chạy. .git/verification tooling/caches và immutable design snapshot không phải folders để team viết application code.
