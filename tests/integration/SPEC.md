# SPEC — tests/integration

## Purpose và owner

Python compute và cross-runtime boundaries Owner: AI-2 compute; Backend integration consumer.

## Đặt gì ở đây?

api private AI tests; legacy queue/persistence/storage giữ reference.

## Ranh giới

DB/CAS/Flyway tests đặt Java; HTTP lost response/busy/cancel actual integration quan trọng.

## Workflow và kiểm tra

Đọc [doc vai trò](../../docs/team/ai-2-extraction.md), nhận một task có input/version/output/acceptance. M2.3/B3/B6: no mock locks claims as real PostgreSQL proof. Ghi actual commands/results và limitations, [Git Flow](../../docs/git-flow.md); không tự commit/push/deploy.

## Liên quan

[Scope](../../specs/scope.md), [structure](../../docs/source-structure.md), [architecture](../../docs/architecture.md).
- [queue](queue/SPEC.md)
- [storage](storage/SPEC.md)
- [persistence](persistence/SPEC.md)
- [api](api/SPEC.md)

File đích chưa implement không là code chạy được; tạo implementation/SPEC con theo increment được giao.
