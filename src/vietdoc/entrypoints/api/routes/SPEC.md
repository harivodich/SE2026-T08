# SPEC — src/vietdoc/entrypoints/api/routes

## Purpose và owner

Private compute/health routes Owner: AI-2.

## Đặt gì ở đây?

POST /internal/v1/compute; GET /health/live,/health/ready.

## Ranh giới

Không documents/review/export/public login routes; no arbitrary file/URL input.

## Workflow và kiểm tra

Đọc [doc vai trò](../../../../../docs/team/ai-2-extraction.md), nhận một task có input/version/output/acceptance. M2.3 schema/correlation/errors/body caps và no fake success. Ghi actual commands/results và limitations, [Git Flow](../../../../../docs/git-flow.md); không tự commit/push/deploy.

## Liên quan

[Scope](../../../../../specs/scope.md), [structure](../../../../../docs/source-structure.md), [architecture](../../../../../docs/architecture.md).


File đích chưa implement không là code chạy được; tạo implementation/SPEC con theo increment được giao.
