# SPEC — src

## Purpose và owner

Python AI/Data source root Owner: Data/AI theo module.

## Đặt gì ở đây?

Package vietdoc dưới src; Java source ở backend, không business Python mới.

## Ranh giới

Training/eval/serving tách nhau; no business DB creds.

## Workflow và kiểm tra

Đọc [doc vai trò](../docs/team/ai-2-extraction.md), nhận một task có input/version/output/acceptance. Đọc SPEC module, no Python business persistence imports. Ghi actual commands/results và limitations, [Git Flow](../docs/git-flow.md); không tự commit/push/deploy.

## Liên quan

[Scope](../specs/scope.md), [structure](../docs/source-structure.md), [architecture](../docs/architecture.md).
- [vietdoc](vietdoc/SPEC.md)

File đích chưa implement không là code chạy được; tạo implementation/SPEC con theo increment được giao.
