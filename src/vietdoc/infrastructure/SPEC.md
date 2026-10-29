# SPEC — src/vietdoc/infrastructure

## Purpose và owner

Compute adapters Owner: AI-2; AI-1 engine integration.

## Đặt gì ở đây?

Attempt storage/logging/release loading; persistence/queue subfolders legacy.

## Ranh giới

Không business ORM/broker/DB credentials, no originals/exports writable.

## Workflow và kiểm tra

Đọc [doc vai trò](../../../docs/team/ai-2-extraction.md), nhận một task có input/version/output/acceptance. M2.3 path/hash/attempt isolation và lifecycle; consumer Backend kiểm artifacts. Ghi actual commands/results và limitations, [Git Flow](../../../docs/git-flow.md); không tự commit/push/deploy.

## Liên quan

[Scope](../../../specs/scope.md), [structure](../../../docs/source-structure.md), [architecture](../../../docs/architecture.md).
- [queue](queue/SPEC.md)
- [persistence](persistence/SPEC.md)
- [storage](storage/SPEC.md)

File đích chưa implement không là code chạy được; tạo implementation/SPEC con theo increment được giao.
