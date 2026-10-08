# SPEC — tests

## Purpose và owner

Python/shared/cross-runtime test evidence Owner: Owning implementer; Backend E2E.

## Đặt gì ở đây?

Python tests, neutral fixtures, browserE2E; Java unit/DB/Flyway ở backend tests.

## Ranh giới

Legacy Python business folders không Java test roots; no real PII/model binaries.

## Workflow và kiểm tra

Đọc [doc vai trò](../docs/team/backend.md), nhận một task có input/version/output/acceptance. Focused actual tests, failures explicit; contracts/schema/UML pass không app pass. Ghi actual commands/results và limitations, [Git Flow](../docs/git-flow.md); không tự commit/push/deploy.

## Liên quan

[Scope](../specs/scope.md), [structure](../docs/source-structure.md), [architecture](../docs/architecture.md).
- [unit](unit/SPEC.md)
- [integration](integration/SPEC.md)
- [architecture](architecture/SPEC.md)
- [contract](contract/SPEC.md)
- [e2e](e2e/SPEC.md)
- [fixtures](fixtures/SPEC.md)

File đích chưa implement không là code chạy được; tạo implementation/SPEC con theo increment được giao.
