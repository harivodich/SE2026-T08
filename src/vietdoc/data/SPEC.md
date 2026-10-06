# SPEC — src/vietdoc/data

## Purpose và owner

Data/gold/lineage/splits Owner: Data Engineer.

## Đặt gì ở đây?

Generator/adapters/manifest.py/validation.py/splits.py; assets lớn ở datasets/

## Ranh giới và dữ liệu

Không predictions làm gold hoặc random variant splits qua tập Scope chung: receipt/invoice tiếng Việt, chữ in một trang; prediction/revision bất biến, human approve trước export. File đích chưa có logic là task cần implement, không tự thêm fake implementation.

## Workflow và kết quả cần kiểm

1. Nhận một task nhỏ có input/version/output/acceptance từ Lead; xem [doc vai trò](../../../docs/team/data-engineer.md) khi cần task chi tiết.
2. Sửa đúng vùng này, báo affected consumer nếu contract/config/version đổi; không tự nhận phần module khác.
3. D1–D5: render-label QA/schema/Unicode/duplicates/family grouping/PII
4. Ghi commands/checks/output thật và limitations, peer review trước Lead duyệt; [Git Flow](../../../docs/git-flow.md), không direct push main/develop.

## Folder liên quan

[Folder cha](../SPEC.md). [Scope](../../../specs/scope.md).
- [adapters](adapters/SPEC.md)
- [generator](generator/SPEC.md)

SPEC.md là hướng dẫn local, không chứng minh app/model/CI đang chạy. .git/verification tooling/caches và immutable design snapshot không phải folders để team viết application code.
