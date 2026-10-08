# SPEC — tests/integration/api

## Purpose và owner

Private Python compute integration tests Owner: AI-2.

## Đặt gì ở đây?

Multipart/private auth/shape/errors/limits/lifecycle/busy tests.

## Ranh giới

Không public FastAPI business API; Java API tests ở backend.

## Workflow và kiểm tra

Đọc [doc vai trò](../../../docs/team/ai-2-extraction.md), nhận một task có input/version/output/acceptance. M2.3 use fixtures wiring + real OCR smoke separately. Ghi actual commands/results và limitations, [Git Flow](../../../docs/git-flow.md); không tự commit/push/deploy.

## Liên quan

[Scope](../../../specs/scope.md), [structure](../../../docs/source-structure.md), [architecture](../../../docs/architecture.md).


File đích chưa implement không là code chạy được; tạo implementation/SPEC con theo increment được giao.
