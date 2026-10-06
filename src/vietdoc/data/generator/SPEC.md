# SPEC — src/vietdoc/data/generator

## Purpose và owner

Sinh fake documents và gold Owner: Data.

## Đặt gì ở đây?

values/render/templates: render image/PDF/transcript/regions từ cùng gold object và seed/version.

## Ranh giới và dữ liệu

Không OCR predictions làm gold/real PII; không nhãn bị clip nhưng coi visible. Scope chung: receipt/invoice tiếng Việt, chữ in một trang; prediction/revision bất biến, human approve trước export. File đích chưa có logic là task cần implement, không tự thêm fake implementation.

## Workflow và kết quả cần kiểm

1. Nhận một task nhỏ có input/version/output/acceptance từ Lead; xem [doc vai trò](../../../../docs/team/data-engineer.md) khi cần task chi tiết.
2. Sửa đúng vùng này, báo affected consumer nếu contract/config/version đổi; không tự nhận phần module khác.
3. D1/D2: field/row/image QA, Unicode, reproducibility và schema.
4. Ghi commands/checks/output thật và limitations, peer review trước Lead duyệt; [Git Flow](../../../../docs/git-flow.md), không direct push main/develop.

## Folder liên quan

[Folder cha](../SPEC.md). [Scope](../../../../specs/scope.md).
- [templates](templates/SPEC.md)

SPEC.md là hướng dẫn local, không chứng minh app/model/CI đang chạy. .git/verification tooling/caches và immutable design snapshot không phải folders để team viết application code.
