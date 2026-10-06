# SPEC — artifacts

## Purpose và owner

Generated experiment artifacts Owner: AI-2/Data/AI-1.

## Đặt gì ở đây?

models/ weights; evaluation/ raw predictions/reports/overlays.

## Ranh giới và dữ liệu

Không source code hoặc secrets; safe cards/reports đặt docs khi cần. Scope chung: receipt/invoice tiếng Việt, chữ in một trang; prediction/revision bất biến, human approve trước export. File đích chưa có logic là task cần implement, không tự thêm fake implementation.

## Workflow và kết quả cần kiểm

1. Nhận một task nhỏ có input/version/output/acceptance từ Lead; xem [doc vai trò](../docs/team/ai-2-extraction.md) khi cần task chi tiết.
2. Sửa đúng vùng này, báo affected consumer nếu contract/config/version đổi; không tự nhận phần module khác.
3. Versions/hash/ignored probe before stage.
4. Ghi commands/checks/output thật và limitations, peer review trước Lead duyệt; [Git Flow](../docs/git-flow.md), không direct push main/develop.

## Folder liên quan

[Folder cha](../SPEC.md). [Scope](../specs/scope.md).
- [evaluation](evaluation/SPEC.md)
- [models](models/SPEC.md)

SPEC.md là hướng dẫn local, không chứng minh app/model/CI đang chạy. .git/verification tooling/caches và immutable design snapshot không phải folders để team viết application code.
